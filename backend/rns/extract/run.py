"""extract_pending — turn unprocessed feed items into signals (or discard them),
writing topics, resolved entities and events. Live (Claude) or mock, same shape."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from rns import vocab
from rns.config import settings
from rns.db.models import Event, FeedItem, Signal, SignalEntity, SignalTopic, Source, utcnow
from rns.entities import resolve
from rns.extract import prompt
from rns.extract.schema import EXTRACTION_SCHEMA, ExtractionResult, from_payload
from rns.llm.client import LLMAuthError, LLMRequestError
from rns.llm.mock import mock_extract

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
    from rns.llm.client import complete_json

    payload = await complete_json(
        model=settings.extraction_model,
        system=prompt.SYSTEM,
        user=prompt.user_message(item, source),
        schema=EXTRACTION_SCHEMA,
        max_tokens=2048,
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
        economic_materiality=result.economic_materiality,
        forward_lag=result.forward_lag,
        published_at=item.published_at or item.created_at or utcnow(),
    )
    session.add(signal)
    await session.flush()
    for code in dict.fromkeys(result.topics):
        session.add(SignalTopic(signal_id=signal.id, topic_code=code))
    seen: set = set()
    for kind, names in (("place", result.places), ("organisation", result.organisations), ("project", result.projects)):
        for ent in await resolve(session, list(names), kind=kind):
            if ent.id in seen:
                continue
            seen.add(ent.id)
            session.add(SignalEntity(signal_id=signal.id, entity_id=ent.id, role="mentioned"))
    for ev in result.events:
        session.add(Event(
            signal_id=signal.id, name=ev.name, organizer=ev.organizer, location=ev.location,
            start_date=ev.start_date, end_date=ev.end_date, deadline=ev.deadline, topic=ev.topic,
            registration_url=ev.registration_url, funding_program=ev.funding_program,
            target_audience=ev.target_audience,
        ))
    return signal


async def extract_pending(session: AsyncSession, *, limit: int | None = None) -> ExtractStats:
    stats = ExtractStats(mode="live" if settings.llm_enabled else "mock")
    limit = limit or settings.max_extractions_per_cycle
    items = (
        await session.execute(
            select(FeedItem)
            .options(selectinload(FeedItem.source))
            .where(FeedItem.processed.is_(False))
            # Undated list-page items count as new on arrival; otherwise the cap starves them.
            .order_by(func.coalesce(FeedItem.published_at, FeedItem.created_at).desc())
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
        item.processed = True
        stats.processed += 1
        if not result.is_signal:
            item.discarded = True
            stats.discarded += 1
            continue
        await _persist(session, item, item.source, result)
        stats.signals += 1
    await session.commit()
    return stats
