"""RSS/Atom collection — the brief's first collection tier."""
from __future__ import annotations

from datetime import datetime, timezone
from time import mktime

import feedparser
import httpx

from mhs.collect.canonical import RawItem, canonical_url, content_hash


def _published(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        st = entry.get(key)
        if st:
            # feedparser normalises struct_time to UTC.
            return datetime.fromtimestamp(mktime(st), tz=timezone.utc).replace(tzinfo=timezone.utc)
    return None


def _summary(entry) -> str:
    if entry.get("summary"):
        return entry.summary
    content = entry.get("content") or []
    return content[0].get("value", "") if content else ""


def parse_feed(payload: bytes, feed_url: str) -> list[RawItem]:
    parsed = feedparser.parse(payload)
    items: list[RawItem] = []
    for entry in parsed.entries:
        link = entry.get("link") or ""
        if not link:
            continue
        canon = canonical_url(link)
        guid = entry.get("id") or ""
        # A permalink guid is just the link again; only a non-URL guid is a better id.
        external_id = guid if guid and not guid.startswith(("http://", "https://")) else canon
        title = (entry.get("title") or "").strip()
        summary = _strip_html(_summary(entry))
        items.append(
            RawItem(
                external_id=external_id,
                title=title,
                url=link,
                canonical_url=canon,
                summary=summary,
                published_at=_published(entry),
                content_hash=content_hash(title, summary),
            )
        )
    return items


def _strip_html(text: str) -> str:
    from selectolax.parser import HTMLParser

    if "<" not in text:
        return text.strip()
    return HTMLParser(text).text(separator=" ").strip()


async def fetch_rss(http: httpx.AsyncClient, url: str) -> list[RawItem]:
    response = await http.get(url, follow_redirects=True)
    response.raise_for_status()
    return parse_feed(response.content, str(response.url))
