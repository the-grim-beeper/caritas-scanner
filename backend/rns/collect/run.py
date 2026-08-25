"""collect_all — fetch every collected source, dedup on canonical URL across
sources, record source health. One item, one row, whichever feed it came from."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rns.collect.canonical import RawItem
from rns.collect.page import fetch_page
from rns.collect.rss import fetch_rss
from rns.config import settings
from rns.db.models import FeedItem, Source, utcnow

log = logging.getLogger(__name__)


@dataclass
class CollectStats:
    fetched: int = 0
    new_items: int = 0
    failed_sources: int = 0
    sources_ok: int = 0


@dataclass
class _Fetched:
    source: Source
    items: list[RawItem]
    page_hash: str | None = None
    error: str | None = None
    unchanged: bool = False


async def _fetch_one(http: httpx.AsyncClient, source: Source, sem: asyncio.Semaphore) -> _Fetched:
    async with sem:
        try:
            if source.method == "rss":
                return _Fetched(source, await fetch_rss(http, source.url))
            if source.method == "page":
                items, phash = await fetch_page(http, source.url, source.item_selector)
                if phash == source.last_page_hash:
                    return _Fetched(source, [], page_hash=phash, unchanged=True)
                return _Fetched(source, items[: settings.max_page_items], page_hash=phash)
            return _Fetched(source, [], error=f"method {source.method} is not collected")
        except httpx.HTTPStatusError as exc:
            return _Fetched(source, [], error=f"HTTP {exc.response.status_code}")
        except Exception as exc:  # noqa: BLE001 — every failure is source health, never a crash
            return _Fetched(source, [], error=f"{type(exc).__name__}: {exc}"[:500])


async def collect_all(session: AsyncSession, http: httpx.AsyncClient) -> CollectStats:
    stats = CollectStats()
    sources = (
        await session.execute(
            select(Source).where(Source.collect.is_(True), Source.status == "active")
        )
    ).scalars().all()
    sem = asyncio.Semaphore(settings.feed_concurrency)
    results = await asyncio.gather(*(_fetch_one(http, s, sem) for s in sources))

    now = utcnow()
    for res in results:
        src = res.source
        src.last_fetched_at = now
        if res.error:
            stats.failed_sources += 1
            src.consecutive_failures += 1
            src.last_error = res.error
            if src.consecutive_failures >= settings.max_consecutive_failures:
                src.status = "quarantined"
            continue
        src.consecutive_failures = 0
        src.last_error = None
        src.last_ok_at = now
        stats.sources_ok += 1
        if res.page_hash:
            src.last_page_hash = res.page_hash
        if res.unchanged:
            continue
        stats.fetched += len(res.items)
        stats.new_items += await _store(session, src, res.items)

    await session.commit()
    return stats


async def _store(session: AsyncSession, source: Source, items: list[RawItem]) -> int:
    if not items:
        return 0
    canons = [i.canonical_url for i in items]
    existing_rows = (
        await session.execute(select(FeedItem).where(FeedItem.canonical_url.in_(canons)))
    ).scalars().all()
    existing = {row.canonical_url: row for row in existing_rows}
    seen_ids = {
        (row.source_id, row.external_id)
        for row in (
            await session.execute(
                select(FeedItem).where(
                    FeedItem.source_id == source.id,
                    FeedItem.external_id.in_([i.external_id for i in items]),
                )
            )
        ).scalars()
    }
    new = 0
    for item in items:
        row = existing.get(item.canonical_url)
        if row is not None:
            if row.source_id != source.id and source.id not in (row.also_seen_in or []):
                row.also_seen_in = [*(row.also_seen_in or []), source.id]
            continue
        if (source.id, item.external_id) in seen_ids:
            continue
        row = FeedItem(
            source_id=source.id,
            external_id=item.external_id[:1024],
            title=item.title[:1024] if item.title else None,
            summary=item.summary or None,
            url=item.url[:2048],
            canonical_url=item.canonical_url[:2048],
            content_hash=item.content_hash,
            published_at=item.published_at,
        )
        session.add(row)
        existing[item.canonical_url] = row
        new += 1
    await session.flush()
    return new
