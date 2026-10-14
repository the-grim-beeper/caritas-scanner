"""Adoption: a pending suggestion nobody declined becomes a collected Source once its
adopt_after has passed — but only after a fresh live verification (a page that verified a week
ago may be gone). Declined is final; adopt_now and decline are the reader's two buttons.

Each suggestion is locked (SELECT … FOR UPDATE) and committed on its own, so the daily
adopt_due and a reader's "Jetzt aufnehmen"/"Ablehnen" can never both resolve the same row."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhs.db.models import Source, SourceSuggestion, utcnow
from mhs.entities import slugify
from mhs.suggest.net import maybe_client
from mhs.suggest.validate import suggest_key, verify_candidate

log = logging.getLogger(__name__)

SLUG_PREFIX = "vorschlag-"
SLUG_MAX = 120


class SuggestionNotFound(LookupError):
    pass


class SuggestionNotPending(RuntimeError):
    def __init__(self, status: str):
        super().__init__(f"suggestion is {status}, not pending")
        self.status = status


async def _unique_slug(session: AsyncSession, name: str) -> str:
    base = f"{SLUG_PREFIX}{slugify(name)}"[:SLUG_MAX].rstrip("-")
    stem = base[:SLUG_MAX - 20]  # every suffixed variant still starts with this
    taken = set((await session.execute(select(Source.slug).where(Source.slug.like(f"{stem}%")))).scalars())
    if base not in taken:
        return base
    n = 2
    while True:
        suffix = f"-{n}"
        candidate = base[:SLUG_MAX - len(suffix)].rstrip("-") + suffix
        if candidate not in taken:
            return candidate
        n += 1


async def _existing_source(session: AsyncSession, urls: list[str]) -> Source | None:
    keys = {suggest_key(u) for u in urls if u}
    for src in (await session.execute(select(Source).where(Source.url.is_not(None) | Source.homepage.is_not(None)))).scalars():
        if any(u and suggest_key(u) in keys for u in (src.url, src.homepage)):
            return src
    return None


async def _resolve(session: AsyncSession, http: httpx.AsyncClient, sugg: SourceSuggestion, now: datetime) -> bool:
    """Re-verify and adopt, or mark failed. True when adopted. The caller commits."""
    verdict = await verify_candidate(http, sugg.url)
    sugg.resolved_at = now
    if not verdict.ok:
        sugg.status, sugg.reason = "failed", verdict.reason
        return False
    # The catalogue may have gained this source while the suggestion waited.
    dup = await _existing_source(session, [sugg.url, verdict.url])
    if dup is not None:
        sugg.status, sugg.reason = "failed", f"bereits als Quelle erfasst: {dup.slug}"
        return False
    src = Source(
        slug=await _unique_slug(session, sugg.name),
        name=sugg.name,
        layer=sugg.layer,
        authority=sugg.authority,
        scope=sugg.scope,
        places=list(sugg.places or []),
        language="de",
        method=verdict.method,
        url=verdict.url,
        homepage=sugg.url,
        priority="thematic",
        brief_ref="vorschlag",
        notes=sugg.rationale_de,
        collect=True,
        status="active",
        items_at_check=verdict.items,
        origin="suggestion",
    )
    session.add(src)
    await session.flush()
    sugg.status, sugg.reason, sugg.source_id = "adopted", None, src.id
    sugg.method, sugg.feed_url, sugg.items_at_check = verdict.method, verdict.feed_url, verdict.items
    return True


async def _locked(session: AsyncSession, suggestion_id: uuid.UUID, *, skip_locked: bool = False) -> SourceSuggestion | None:
    stmt = (select(SourceSuggestion).where(SourceSuggestion.id == suggestion_id)
            .with_for_update(skip_locked=skip_locked).execution_options(populate_existing=True))
    return (await session.execute(stmt)).scalar_one_or_none()


async def adopt_due(session: AsyncSession, http: httpx.AsyncClient | None = None, *,
                    now: datetime | None = None) -> dict:
    """Adopt every pending suggestion whose adopt_after has passed. {"adopted": n, "failed": m}."""
    now = now or utcnow()
    counts = {"adopted": 0, "failed": 0}
    due = (await session.execute(
        select(SourceSuggestion.id)
        .where(SourceSuggestion.status == "pending", SourceSuggestion.adopt_after <= now)
        .order_by(SourceSuggestion.adopt_after))).scalars().all()
    await session.commit()
    async with maybe_client(http) as client:
        for sid in due:
            try:
                sugg = await _locked(session, sid, skip_locked=True)
                if sugg is None or sugg.status != "pending":  # taken by a concurrent adopt/decline
                    await session.commit()  # nothing changed; ends the transaction
                    continue
                adopted = await _resolve(session, client, sugg, now)
                await session.commit()
            except Exception:  # one bad row must not stop the others; it stays pending for tomorrow
                await session.rollback()
                log.exception("suggest: adoption of %s crashed", sid)
                continue
            counts["adopted" if adopted else "failed"] += 1
            log.info("suggest: %s %s (%s)", "adopted" if adopted else "failed", sugg.url, sugg.reason or sugg.method)
    return counts


async def _pending(session: AsyncSession, suggestion_id: uuid.UUID) -> SourceSuggestion:
    """The suggestion, locked, if it is pending. Otherwise the transaction is ended (commit, not
    rollback: nothing changed, and a rollback would expire the caller's loaded objects) and
    SuggestionNotFound / SuggestionNotPending is raised."""
    sugg = await _locked(session, suggestion_id)
    if sugg is None:
        await session.commit()
        raise SuggestionNotFound(str(suggestion_id))
    if sugg.status != "pending":
        await session.commit()
        raise SuggestionNotPending(sugg.status)
    return sugg


async def adopt_now(session: AsyncSession, http: httpx.AsyncClient | None, suggestion_id: uuid.UUID) -> SourceSuggestion:
    """The same path as adopt_due, without waiting for adopt_after. The returned suggestion is
    "adopted" or "failed" (reason set). Raises SuggestionNotFound / SuggestionNotPending."""
    sugg = await _pending(session, suggestion_id)
    async with maybe_client(http) as client:
        await _resolve(session, client, sugg, utcnow())
    await session.commit()
    return sugg


async def decline(session: AsyncSession, suggestion_id: uuid.UUID) -> SourceSuggestion:
    """Pending → declined, for good: the URL stays known and is never proposed again."""
    sugg = await _pending(session, suggestion_id)
    sugg.status, sugg.resolved_at = "declined", utcnow()
    await session.commit()
    return sugg
