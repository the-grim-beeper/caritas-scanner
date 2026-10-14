"""collect_all — fetch every collected source, dedup on canonical URL across
sources, record source health. One item, one row, whichever feed it came from."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhs.collect.canonical import RawItem
from mhs.collect.diff import fetch_diff
from mhs.collect.page import fetch_page
from mhs.collect.pdf import fetch_pdf
from mhs.collect.query import fetch_query, title_key as _title_key
from mhs.collect.rss import fetch_rss
from mhs.config import settings
from mhs.db.models import FeedItem, Source, utcnow

log = logging.getLogger(__name__)

# A handful of hosts (digitalfabrix SessionNet, and every query source sharing
# news.google.com) carry several sources at once; some 503 under parallel load.
# Two in flight per host is gentle regardless of how many sources share it.
_PER_HOST_LIMIT = 2


def _target_host(source: Source) -> str | None:
    """The host _fetch_one will actually hit — source.url for every method except
    query, whose request goes to the search template's host, not the source row."""
    if source.method == "query":
        url = settings.query_url_template
    elif source.url:
        url = source.url
    else:
        return None
    host = urlsplit(url).hostname
    return host.lower() if host else None


@dataclass
class CollectStats:
    fetched: int = 0
    new_items: int = 0
    failed_sources: int = 0
    sources_ok: int = 0
    skipped_old: int = 0


@dataclass
class _Fetched:
    source: Source
    items: list[RawItem]
    page_hash: str | None = None
    error: str | None = None
    unchanged: bool = False
    # method=diff: the fetch's own text/hash, stored on the source whether or not an
    # item was emitted — a baseline or an unchanged page still updates the snapshot.
    snapshot_text: str | None = None
    snapshot_hash: str | None = None


async def _fetch_one(
    http: httpx.AsyncClient,
    source: Source,
    sem: asyncio.Semaphore,
    host_sem: asyncio.Semaphore,
    seen_urls: frozenset[str] = frozenset(),
) -> _Fetched:
    async with sem, host_sem:
        try:
            if source.method == "rss":
                return _Fetched(source, await fetch_rss(http, source.url))
            if source.method == "page":
                items, phash = await fetch_page(http, source.url, source.item_selector)
                if phash == source.last_page_hash:
                    return _Fetched(source, [], page_hash=phash, unchanged=True)
                return _Fetched(source, items[: settings.max_page_items], page_hash=phash)
            if source.method == "query":
                return _Fetched(source, await fetch_query(http, source))
            if source.method == "diff":
                items, new_text, new_hash = await fetch_diff(http, source)
                return _Fetched(source, items, snapshot_text=new_text, snapshot_hash=new_hash)
            if source.method == "pdf":
                return _Fetched(source, await fetch_pdf(http, source, set(seen_urls)))
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

    pdf_sources = [s for s in sources if s.method == "pdf"]
    seen_by_source: dict = {}
    if pdf_sources:
        rows = (
            await session.execute(
                select(FeedItem.source_id, FeedItem.canonical_url).where(
                    FeedItem.source_id.in_([s.id for s in pdf_sources])
                )
            )
        ).all()
        for source_id, canon in rows:
            seen_by_source.setdefault(source_id, set()).add(canon)

    sem = asyncio.Semaphore(settings.feed_concurrency)
    host_sems: dict[str, asyncio.Semaphore] = {}

    def _host_sem(source: Source) -> asyncio.Semaphore:
        host = _target_host(source)
        if host is None:
            return asyncio.Semaphore(settings.feed_concurrency)  # nothing to share a limit with
        if host not in host_sems:
            host_sems[host] = asyncio.Semaphore(_PER_HOST_LIMIT)
        return host_sems[host]

    results = await asyncio.gather(
        *(
            _fetch_one(http, s, sem, _host_sem(s), frozenset(seen_by_source.get(s.id, ())))
            for s in sources
        )
    )

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
        if res.snapshot_hash is not None:
            src.snapshot_text = res.snapshot_text
            src.snapshot_hash = res.snapshot_hash
        if res.unchanged:
            continue
        stats.fetched += len(res.items)
        cutoff = now - timedelta(days=settings.max_item_age_days)
        fresh = [i for i in res.items if i.published_at is None or i.published_at >= cutoff]
        stats.skipped_old += len(res.items) - len(fresh)
        stats.new_items += await _store(session, src, fresh)

    await session.commit()
    return stats


async def _store(session: AsyncSession, source: Source, items: list[RawItem]) -> int:
    if not items:
        return 0
    is_query = source.method == "query"
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

    keys = [(_title_key(item.title) or None) if item.title else None for item in items]
    # A search feed's redirect URL changes on every crawl, so a query source's items
    # are matched to an existing headline instead of a canonical URL — any source,
    # within the freshness window, so the search item is credited, not duplicated.
    by_title_key: dict[str, FeedItem] = {}
    if is_query:
        wanted = {k for k in keys if k}
        if wanted:
            cutoff = utcnow() - timedelta(days=60)
            rows = (
                await session.execute(
                    select(FeedItem).where(
                        FeedItem.title_key.in_(wanted), FeedItem.created_at >= cutoff
                    )
                )
            ).scalars().all()
            for row in rows:
                by_title_key.setdefault(row.title_key, row)

    new = 0
    for item, tk in zip(items, keys):
        if is_query:
            match = by_title_key.get(tk) if tk else None
            if match is not None:
                if source.id not in (match.also_seen_in or []):
                    match.also_seen_in = [*(match.also_seen_in or []), source.id]
                continue
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
            title_key=tk,
            outlet=item.outlet,
            published_at=item.published_at,
        )
        session.add(row)
        existing[item.canonical_url] = row
        if tk and is_query:
            by_title_key[tk] = row
        new += 1
    await session.flush()
    return new
