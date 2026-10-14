"""One daily cycle: adopt due source suggestions → collect → extract → analyse (embed,
stories, score) → judge against the fifteen questions → resolve relations into the
network → trends. The weekly Lagebericht and the weekly source discovery are separate
jobs (see main.py); the cycle row records what each stage did."""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mhs.analyse import trends
from mhs.analyse.run import analyse_pending
from mhs.collect.run import collect_all
from mhs.config import settings
from mhs.db.models import Cycle, Digest, Signal, Story
from mhs.network.resolve import resolve_candidates
from mhs.questions.judge import judge_pending
from mhs.report.run import write_report
from mhs.suggest.adopt import adopt_due
from mhs.extract.run import extract_pending

log = logging.getLogger(__name__)

# Postgres advisory-lock keys: one daily cycle and one Lagebericht at a time across every
# process that can start them (the API, the scheduler, scripts/run_cycle.py).
CYCLE_LOCK = 0x4D485301
REPORT_LOCK = 0x4D485302


@asynccontextmanager
async def exclusive(session_factory: async_sessionmaker[AsyncSession], key: int) -> AsyncIterator[bool]:
    """Yields whether this process holds the advisory lock `key` for the whole block. The lock
    lives on a connection of its own, checked out for the duration: a pooled session would
    hand its connection back at the first commit and the unlock could land elsewhere."""
    async with session_factory.kw["bind"].connect() as conn:
        conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
        got = bool(await conn.scalar(text("SELECT pg_try_advisory_lock(:k)"), {"k": key}))
        try:
            yield got
        finally:
            if got:
                try:
                    await conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": key})
                except Exception:  # noqa: BLE001 — never return a lock-holding connection to the pool
                    log.exception("advisory unlock %s failed; dropping the connection", key)
                    await conn.invalidate()


async def lock_held(session: AsyncSession, key: int) -> bool:
    """Whether any process holds advisory lock `key` right now (read from pg_locks; takes nothing).
    A single bigint key shows as classid = high half, objid = low half, objsubid = 1."""
    return bool(await session.scalar(text(
        "SELECT EXISTS (SELECT 1 FROM pg_locks WHERE locktype = 'advisory' AND granted"
        " AND database = (SELECT oid FROM pg_database WHERE datname = current_database())"
        " AND classid = 0 AND objid = CAST(CAST(:k AS bigint) AS oid) AND objsubid = 1)"), {"k": key}))


def _http() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=settings.feed_timeout_seconds,
        headers={"User-Agent": settings.user_agent, "Accept-Language": "de-DE,de;q=0.9,en;q=0.7"},
    )


async def repair_future_dates(session: AsyncSession) -> int:
    """No signal is published in the future. Rows written before extraction clamped their
    date (an item dated by the development it announces) are moved back to when they were
    collected, and their stories follow. Idempotent; returns the number of signals moved."""
    moved = (await session.execute(
        update(Signal).where(Signal.published_at > func.now()).values(published_at=Signal.created_at)
        .execution_options(synchronize_session=False)
    )).rowcount or 0
    first = select(func.min(Signal.published_at)).where(Signal.story_id == Story.id).scalar_subquery()
    last = select(func.max(Signal.published_at)).where(Signal.story_id == Story.id).scalar_subquery()
    await session.execute(
        update(Story)
        .where((Story.first_seen > func.now()) | (Story.last_seen > func.now()))
        .values(first_seen=func.least(Story.first_seen, func.coalesce(first, func.now())),
                last_seen=func.least(Story.last_seen, func.coalesce(last, func.now())))
        .execution_options(synchronize_session=False)
    )
    await session.commit()
    return moved


async def run_cycle(session_factory: async_sessionmaker[AsyncSession], *, http: httpx.AsyncClient | None = None) -> Cycle:
    """One cycle, unless another process is running one: then nothing is collected, paid for
    or recorded, and the returned (unsaved) cycle says why."""
    async with exclusive(session_factory, CYCLE_LOCK) as mine:
        if not mine:
            log.warning("cycle skipped: another cycle is running")
            now = datetime.now(timezone.utc)
            return Cycle(mode="live" if settings.llm_enabled else "mock", started_at=now, finished_at=now,
                         error="another cycle is running")
        return await _run_cycle(session_factory, http)


async def _run_cycle(session_factory: async_sessionmaker[AsyncSession], http: httpx.AsyncClient | None) -> Cycle:
    async with session_factory() as session:
        cycle = Cycle(mode="live" if settings.llm_enabled else "mock")
        session.add(cycle)
        await session.commit()
        try:
            repaired = await repair_future_dates(session)
            if repaired:
                log.info("repaired %d future-dated signals", repaired)
            own_http = http is None
            client = http or _http()
            try:
                # Adopted first, so a suggestion that came due collects the same day.
                adopted = await adopt_due(session, client)
                log.info("adopt: %s", adopted)
                c = await collect_all(session, client)
            finally:
                if own_http:
                    await client.aclose()
            cycle.items_fetched, cycle.items_new, cycle.failed_sources = c.fetched, c.new_items, c.failed_sources
            log.info("collect: %s", c)

            e = await extract_pending(session)
            cycle.extracted, cycle.signals = e.processed, e.signals
            if e.aborted:
                cycle.error = f"extraction aborted: {e.aborted}"
            log.info("extract: %s", e)

            a = await analyse_pending(session)
            cycle.stories_new, cycle.corroborations = a.stories_new, a.corroborations
            log.info("analyse: %s", a)

            j = await judge_pending(session)
            cycle.judged, cycle.judgements = j.judged, j.judgements
            if j.aborted and not cycle.error:
                cycle.error = f"judge aborted: {j.aborted}"
            log.info("judge: %s", j)

            n = await resolve_candidates(session)
            cycle.edges_new = n.edges_new
            log.info("network: %s", n)

            await trends.rebuild(session)
        except Exception as exc:  # noqa: BLE001
            log.exception("cycle failed")
            cycle.error = f"{type(exc).__name__}: {exc}"[:2000]
        cycle.finished_at = datetime.now(timezone.utc)
        await session.commit()
        return cycle


async def run_report(session_factory: async_sessionmaker[AsyncSession]) -> Digest | None:
    """The weekly Lagebericht (Thursday evening, ready for the Friday note); None, writing
    nothing, while another process is writing one."""
    async with exclusive(session_factory, REPORT_LOCK) as mine:
        if not mine:
            log.warning("report skipped: another report is being written")
            return None
        async with session_factory() as session:
            return await write_report(session)
