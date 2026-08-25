"""One cycle: collect → extract → analyse (embed, stories, score) → trends → digest.
Each stage is separately callable; the cycle row records what each one did."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rns.analyse import trends
from rns.analyse.run import analyse_pending
from rns.collect.run import collect_all
from rns.config import settings
from rns.db.models import Cycle, Digest
from rns.digest.run import write_digest
from rns.extract.run import extract_pending

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

            await trends.rebuild(session)
            await write_digest(session, cycle)
        except Exception as exc:  # noqa: BLE001
            log.exception("cycle failed")
            cycle.error = f"{type(exc).__name__}: {exc}"[:2000]
        cycle.finished_at = datetime.now(timezone.utc)
        await session.commit()
        return cycle


async def run_digest_only(session_factory: async_sessionmaker[AsyncSession]) -> Digest | None:
    async with session_factory() as session:
        return await write_digest(session, None)
