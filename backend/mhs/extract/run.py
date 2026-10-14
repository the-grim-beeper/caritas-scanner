"""extract_pending — turn unprocessed feed items into signals (or discard them),
writing topics, resolved entities, events and relation candidates. Live (Claude) or
mock, same shape."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import logging
from dataclasses import dataclass

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from mhs import vocab
from mhs.config import settings
from mhs.db.models import Event, FeedItem, RelationCandidate, Signal, SignalEntity, SignalTopic, Source, utcnow
from mhs.entities import resolve
from mhs.extract import prompt
from mhs.extract.schema import EXTRACTION_SCHEMA, ExtractionResult, from_payload
from mhs.llm.client import LLMAuthError, LLMRequestError
from mhs.llm.mock import mock_extract

log = logging.getLogger(__name__)


@dataclass
class ExtractStats:
    processed: int = 0
    signals: int = 0
    discarded: int = 0
    failed: int = 0
    mode: str = "mock"
    # Set when the batch was stopped early (a rejected key); items stay unprocessed.
    aborted: str | None = None


async def _extract_live(item: FeedItem, source: Source) -> ExtractionResult:
    from mhs.llm.client import complete_json

    payload = await complete_json(
        model=settings.extraction_model,
        system=prompt.SYSTEM,
        user=prompt.user_message(item, source),
        schema=EXTRACTION_SCHEMA,
        max_tokens=4096,  # bilingual summaries + events can pass 2k
    )
    return from_payload(payload)


class _Abort:
    """Shared across one batch: the first authentication error stops every later call."""

    reason: str | None = None


async def _extract_one(
    item: FeedItem, source: Source, sem: asyncio.Semaphore, abort: _Abort
) -> tuple[FeedItem, ExtractionResult | None]:
    async with sem:
        if abort.reason:
            return item, None
        try:
            if settings.llm_enabled:
                return item, await _extract_live(item, source)
            return item, mock_extract(item.title or "", item.summary or "", source.layer)
        except (LLMAuthError, LLMRequestError) as exc:
            abort.reason = f"{type(exc).__name__}: {exc}"
            log.error("extraction aborted: %s", exc)
            return item, None
        except Exception as exc:  # noqa: BLE001 — one bad item must not sink the cycle
            log.warning("extraction failed for %s: %s", item.url, exc)
            return item, None


async def _persist(session: AsyncSession, item: FeedItem, source: Source, result: ExtractionResult) -> Signal:
    signal = Signal(
        feed_item_id=item.id,
        source_id=source.id,
        headline_en=result.headline_en or (item.title or "")[:600],
        headline_de=result.headline_de or (item.title or "")[:600],
        summary_en=result.summary_en or None,
        summary_de=result.summary_de or None,
        signal_type=result.signal_type,
        places_text=list(result.places),
        authority=vocab.AUTHORITY_WEIGHTS.get(source.authority, 0.4),
        regional_relevance=result.regional_relevance,
        consequence=result.consequence,
        forward_lag=result.forward_lag,
        published_at=item.published_at or _as_instant(result.item_date) or item.created_at or utcnow(),
    )
    session.add(signal)
    await session.flush()
    for code in dict.fromkeys(result.topics):
        session.add(SignalTopic(signal_id=signal.id, topic_code=code))
    seen: set = set()
    for kind, names in (
        ("place", result.places),
        ("organisation", result.organisations),
        ("forum", result.forums),
        ("programme", result.programmes),
        ("office", result.offices),
    ):
        for ent in await resolve(session, list(names), kind=kind):
            if ent.id in seen:
                continue
            seen.add(ent.id)
            session.add(SignalEntity(signal_id=signal.id, entity_id=ent.id, role="mentioned"))
    for ev in result.events:
        only_deadline = ev.deadline is not None and ev.start_date is None and ev.end_date is None
        session.add(Event(
            signal_id=signal.id, origin="signal", kind="deadline" if only_deadline else "event",
            name=ev.name, organizer=ev.organizer, location=ev.location,
            start_date=ev.start_date, end_date=ev.end_date, deadline=ev.deadline, topic=ev.topic,
            registration_url=ev.registration_url, funding_program=ev.funding_program,
            target_audience=ev.target_audience,
        ))
    # Endpoints stay free text here; the network stage resolves them (or drops the candidate).
    for rel in result.relations:
        session.add(RelationCandidate(signal_id=signal.id, a_text=rel.a, b_text=rel.b,
                                      relation=rel.relation, quote=rel.quote))
    return signal


def _as_instant(d) -> datetime | None:
    return datetime(d.year, d.month, d.day, 12, tzinfo=timezone.utc) if d else None


def _is_archive(item: FeedItem, result: ExtractionResult) -> bool:
    """An undated list-page item whose own stated date lies outside the freshness window is
    archive, not news (first live run: "ab dem 10. Dezember 2023" on a municipal news page)."""
    if item.published_at is not None or result.item_date is None:
        return False
    return result.item_date < (utcnow() - timedelta(days=settings.max_item_age_days)).date()


async def extract_pending(session: AsyncSession, *, limit: int | None = None) -> ExtractStats:
    stats = ExtractStats(mode="live" if settings.llm_enabled else "mock")
    limit = limit or settings.max_extractions_per_cycle
    items = (
        await session.execute(
            select(FeedItem)
            .join(Source, Source.id == FeedItem.source_id)
            .options(selectinload(FeedItem.source))
            .where(FeedItem.processed.is_(False))
            # Undated list-page items count as new on arrival; otherwise the cap starves them.
            # The cap spends its slots where the client lives first: the report's core sources,
            # then local scope (municipality, county), then everything else; newest first within.
            .order_by(
                case((Source.priority == "core", 0), else_=1),
                case((Source.scope.in_(("gemeinde", "landkreis")), 0), else_=1),
                func.coalesce(FeedItem.published_at, FeedItem.created_at).desc(),
            )
            .limit(limit)
        )
    ).scalars().all()
    if not items:
        return stats

    sem = asyncio.Semaphore(settings.extraction_concurrency if settings.llm_enabled else 64)
    abort = _Abort()
    results = await asyncio.gather(*(_extract_one(i, i.source, sem, abort) for i in items))
    stats.aborted = abort.reason

    for item, result in results:
        if result is None:
            stats.failed += 1
            continue
        if not result.is_signal or _is_archive(item, result):
            item.processed = True
            item.discarded = True
            stats.processed += 1
            stats.discarded += 1
            continue
        # A savepoint per item: one bad write must not roll back a batch of paid calls.
        try:
            async with session.begin_nested():
                await _persist(session, item, item.source, result)
                item.processed = True
        except Exception as exc:  # noqa: BLE001
            log.warning("persist failed for %s: %s", item.url, exc)
            stats.failed += 1
            continue
        stats.processed += 1
        stats.signals += 1
    await session.commit()
    return stats
