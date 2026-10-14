"""Query sources — rural outlets with no feed of their own, found through a
Google News RSS search instead. The search result's link is a Google redirect
that changes on every crawl, so these items cannot be deduped by canonical URL;
`_store` in collect/run.py matches them to an existing item by headline instead."""
from __future__ import annotations

import re
import string
from urllib.parse import quote_plus

import httpx

from mhs.collect.canonical import RawItem
from mhs.collect.rss import fetch_rss
from mhs.config import settings

_WS = re.compile(r"\s+")
_STRIP = string.punctuation + string.whitespace


def build_query_url(q: str) -> str:
    return settings.query_url_template.format(q=quote_plus(q))


def split_outlet(title: str) -> tuple[str, str | None]:
    """"Kreistag erhöht Kreisumlage - Merkur" -> ("Kreistag erhöht Kreisumlage", "Merkur").
    Google News titles end in " - Outlet"; a title without that separator has no outlet."""
    title = title.strip()
    if " - " not in title:
        return title, None
    head, _, tail = title.rpartition(" - ")
    head, tail = head.strip(), tail.strip()
    if not head or not tail:
        return title, None
    return head, tail


def title_key(title: str) -> str:
    """Casefold, strip any trailing outlet, collapse whitespace, strip punctuation at
    the ends — so the same headline from a direct feed and a search feed match."""
    head, _ = split_outlet(title)
    key = _WS.sub(" ", head).strip().casefold()
    return key.strip(_STRIP)


async def fetch_query(http: httpx.AsyncClient, source) -> list[RawItem]:
    url = build_query_url(source.query or "")
    raw_items = await fetch_rss(http, url)
    out: list[RawItem] = []
    for item in raw_items:
        title, outlet = split_outlet(item.title)
        out.append(
            RawItem(
                external_id=item.external_id,
                title=title,
                url=item.url,
                canonical_url=item.canonical_url,
                summary=item.summary,
                published_at=item.published_at,
                content_hash=item.content_hash,
                outlet=outlet,
            )
        )
    return out
