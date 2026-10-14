"""The weekly suggestion cycle: propose → drop what is known → verify each live → store it as
pending (adopted after settings.suggest_adopt_after_days unless declined) or as rejected with
the reason. Known means: any URL of any Source, and of any earlier suggestion whatever its
status, compared by suggest_key (scheme, www. and trailing slash do not make a URL new).

One run at a time per process (the scheduler and the API share the lock)."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mhs.config import settings
from mhs.db.models import SourceSuggestion, utcnow
from mhs.suggest.discover import Candidate, propose
from mhs.suggest.net import maybe_client
from mhs.suggest.validate import Verdict, canonical, known_urls, suggest_key, verify_candidate

log = logging.getLogger(__name__)

VERIFY_CONCURRENCY = 4
_lock = asyncio.Lock()


class SuggestRunInProgress(RuntimeError):
    pass


def is_running() -> bool:
    return _lock.locked()


@asynccontextmanager
async def running() -> AsyncIterator[None]:
    """Hold the run lock; raises SuggestRunInProgress instead of queueing behind a run."""
    if _lock.locked():
        raise SuggestRunInProgress("a suggestion run is already in progress")
    async with _lock:
        yield


async def _verify(http: httpx.AsyncClient, url: str, sem: asyncio.Semaphore) -> Verdict:
    async with sem:
        try:
            return await verify_candidate(http, url)
        except Exception as exc:  # one malformed candidate must not end the run
            log.warning("suggest: verification of %s crashed", url, exc_info=True)
            return Verdict(False, None, None, 0, f"Prüfung abgebrochen ({type(exc).__name__})")


async def suggest_cycle(session_factory: async_sessionmaker[AsyncSession],
                        http: httpx.AsyncClient | None = None) -> dict:
    """{"proposed", "pending_new", "rejected", "known"}. Raises SuggestRunInProgress when a run
    is already going, and the mhs.llm.client errors when the proposer fails (nothing stored)."""
    async with running():
        counts = {"proposed": 0, "pending_new": 0, "rejected": 0, "known": 0}
        async with session_factory() as session:
            candidates = await propose(session)
            known = await known_urls(session)
        counts["proposed"] = len(candidates)
        known_keys = {suggest_key(u) for u in known}

        fresh: list[tuple[Candidate, str]] = []
        for cand in candidates:
            url = canonical(cand.url)
            key = suggest_key(url)
            if key in known_keys:
                counts["known"] += 1
                continue
            known_keys.add(key)  # a duplicate later in the same batch is known too
            fresh.append((cand, url))
        if not fresh:
            log.info("suggest: %s", counts)
            return counts

        sem = asyncio.Semaphore(VERIFY_CONCURRENCY)
        async with maybe_client(http) as client:
            verdicts = await asyncio.gather(*(_verify(client, url, sem) for _, url in fresh))

        now = utcnow()
        model = settings.suggest_model if settings.llm_enabled else "mock"
        async with session_factory() as session:
            for (cand, url), v in zip(fresh, verdicts):
                status, reason = ("pending", None) if v.ok else ("rejected", v.reason)
                if v.ok and v.url and suggest_key(v.url) != suggest_key(url):
                    # A homepage whose feed the scanner already collects (or another candidate
                    # of this batch already leads to) adds nothing.
                    if suggest_key(v.url) in known_keys:
                        status, reason = "rejected", f"führt auf eine bereits bekannte Quelle: {v.url}"
                    else:
                        known_keys.add(suggest_key(v.url))
                session.add(SourceSuggestion(
                    url=url, name=cand.name, layer=cand.layer, scope=cand.scope, places=list(cand.places),
                    rationale_de=cand.rationale_de, rationale_en=cand.rationale_en,
                    method=v.method if status == "pending" else None,
                    feed_url=v.feed_url if status == "pending" else None,
                    items_at_check=v.items,
                    status=status, reason=reason, model=model, suggested_at=now,
                    adopt_after=now + timedelta(days=settings.suggest_adopt_after_days),
                    resolved_at=None if status == "pending" else now,
                ))
                counts["pending_new" if status == "pending" else "rejected"] += 1
            await session.commit()
        log.info("suggest: %s", counts)
        return counts
