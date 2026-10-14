"""Resolve-before-propose (Sandglass's validate_candidate, with this project's verification rules
from scripts/check_sources.py): a candidate is a source only if it verifies live

  1. as a feed with at least one item (the URL itself), else
  2. via feed autodiscovery on its HTML (<link rel=alternate type=rss/atom>, feed-looking
     links, then the usual suffixes) — a found feed with at least one item, else
  3. as a list page the extractor reads at least MIN_PAGE_ITEMS items from.

Every fetch goes through the public-host / redirect / size guard in mhs.suggest.net."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
from selectolax.parser import HTMLParser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhs.collect.canonical import canonical_url
from mhs.collect.page import extract_items
from mhs.collect.rss import parse_feed
from mhs.db.models import Source, SourceSuggestion
from mhs.suggest.net import fetch, fetch_checked

MIN_PAGE_ITEMS = 3
MAX_DISCOVERED_LINKS = 12
# As scripts/check_sources.py; duplicated because the app package must not import scripts/.
FEED_SUFFIXES = ("/feed/", "/feed", "/rss", "/rss.xml", "/feed.xml", "/?feed=rss2")


@dataclass
class Verdict:
    ok: bool
    method: str | None  # "rss" | "page" when ok
    feed_url: str | None  # the verified feed (rss only)
    items: int
    reason: str | None  # why not, in German (shown in the UI); None when ok
    # What to collect from: the feed URL (rss) or the list page after redirects (page).
    url: str | None = None


def canonical(url: str) -> str:
    return canonical_url(url)


def suggest_key(url: str) -> str:
    """Identity of a URL for "have we seen this source?": the canonical URL without scheme,
    without a leading "www." and without a trailing slash, so a declined https://a.test/x
    also blocks http://www.a.test/x/. Path case is kept (it is meaningful on many servers)."""
    parts = urlsplit(canonical_url(url))
    host = parts.netloc[4:] if parts.netloc.startswith("www.") else parts.netloc
    path = parts.path.rstrip("/")
    return urlunsplit(("", host, path, parts.query, "")).lstrip("/")


async def known_urls(session: AsyncSession) -> set[str]:
    """Canonical URL and homepage of every Source, and URL and feed URL of every
    SourceSuggestion whatever its status — declined and rejected ones included."""
    found: set[str] = set()
    for url, homepage in (await session.execute(select(Source.url, Source.homepage))).all():
        found.update(canonical_url(u) for u in (url, homepage) if u)
    for url, feed_url in (await session.execute(select(SourceSuggestion.url, SourceSuggestion.feed_url))).all():
        found.update(canonical_url(u) for u in (url, feed_url) if u)
    return found


def _looks_like_feed(r: httpx.Response) -> bool:
    ctype = r.headers.get("content-type", "").lower()
    head = r.content[:400].lstrip().lower()
    return ("xml" in ctype) or head.startswith(b"<?xml") or b"<rss" in head or b"<feed" in head


async def _feed_items(r: httpx.Response) -> int:
    if r.status_code != 200 or not _looks_like_feed(r):
        return 0
    items = await asyncio.to_thread(parse_feed, r.content, str(r.url))
    return len(items)


def _discover_links(html: str, base: str) -> list[str]:
    tree = HTMLParser(html)
    found: list[str] = []
    for link in tree.css("link[rel~=alternate]"):
        t = (link.attributes.get("type") or "").lower()
        href = link.attributes.get("href")
        if href and ("rss" in t or "atom" in t or "xml" in t):
            found.append(urljoin(base, href))
    for a in tree.css("a[href]"):
        href = a.attributes.get("href") or ""
        if any(k in href.lower() for k in ("rss", "feed", ".xml")) and not href.startswith(("mailto:", "javascript:")):
            found.append(urljoin(base, href))
    return list(dict.fromkeys(found))[:MAX_DISCOVERED_LINKS]


async def verify_candidate(http: httpx.AsyncClient, url: str) -> Verdict:
    r, why = await fetch_checked(http, url)
    if r is None:
        return Verdict(False, None, None, 0, why)
    if r.status_code != 200:
        return Verdict(False, None, None, 0, f"nicht erreichbar: HTTP {r.status_code}")
    final = str(r.url)

    # 1. the URL is itself a feed
    n = await _feed_items(r)
    if n:
        return Verdict(True, "rss", final, n, None, url=final)

    # 2. feed autodiscovery on the HTML
    html = r.text
    tried = {canonical_url(final)}
    for candidate in _discover_links(html, final) + [urljoin(final, s) for s in FEED_SUFFIXES]:
        if canonical_url(candidate) in tried:
            continue
        tried.add(canonical_url(candidate))
        fr = await fetch(http, candidate)
        if fr is None:
            continue
        n = await _feed_items(fr)
        if n:
            return Verdict(True, "rss", str(fr.url), n, None, url=str(fr.url))

    # 3. a list page the extractor can read
    items = await asyncio.to_thread(extract_items, html, final)
    if len(items) >= MIN_PAGE_ITEMS:
        return Verdict(True, "page", None, len(items), None, url=final)
    return Verdict(False, None, None, len(items),
                   f"kein Feed gefunden und nur {len(items)} Listeneinträge (mindestens {MIN_PAGE_ITEMS} nötig)")
