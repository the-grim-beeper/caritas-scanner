"""One daily cycle: adopt due source suggestions → collect → extract → analyse (embed,
stories, score) → judge against the fifteen questions → resolve relations into the
network → trends. The weekly Lagebericht and the weekly source discovery are separate
jobs (see main.py); the cycle row records what each stage did."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mhs.analyse import trends
from mhs.analyse.run import analyse_pending
from mhs.collect.run import collect_all
from mhs.config import settings
from mhs.db.models import Cycle, Digest
from mhs.network.resolve import resolve_candidates
from mhs.questions.judge import judge_pending
from mhs.report.run import write_report
from mhs.suggest.adopt import adopt_due
from mhs.extract.run import extract_pending

log = logging.getLogger(__name__)


def _http() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=settings.feed_timeout_seconds,
        headers={"User-Agent": settings.user_agent, "Accept-Language": "de-DE,de;q=0.9,en;q=0.7"},
    )


async def run_cycle(session_factory: async_sessionmaker[AsyncSession], *, http: httpx.AsyncClient | None = None) -> Cycle:
    async with session_factory() as session:
        cycle = Cycle(mode="live" if settings.llm_enabled else "mock")
        session.add(cycle)
        await session.commit()
        try:
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
    """The weekly Lagebericht (Thursday evening, ready for the Friday note)."""
    async with session_factory() as session:
        return await write_report(session)
