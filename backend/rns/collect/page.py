"""List-page monitor: the brief's second collection tier ("watch the list page rather
than individual articles") for sources without a feed."""
from __future__ import annotations

import hashlib
import re
from urllib.parse import urljoin, urlsplit

import httpx
from selectolax.parser import HTMLParser, Node

from rns.collect.canonical import RawItem, canonical_url, content_hash

_WS = re.compile(r"\s+")
_MIN_TITLE = 20
_EXCLUDED_ANCESTORS = {"nav", "footer"}
_CONTAINER_TAGS = {"article", "li", "h1", "h2", "h3", "h4"}
_CONTAINER_CLASS_HINTS = ("news", "teaser", "list", "press", "meldung", "aktuell", "item", "entry")


def _clean(text: str | None) -> str:
    return _WS.sub(" ", text or "").strip()


def _has_excluded_ancestor(node: Node) -> bool:
    cur = node.parent
    while cur is not None:
        tag = cur.tag
        if tag in _EXCLUDED_ANCESTORS:
            return True
        if tag == "header" and (cur.attributes.get("role") == "banner"):
            return True
        cur = cur.parent
    return False


_HEADINGS = {"h1", "h2", "h3", "h4"}


def _in_item_container(node: Node) -> Node | None:
    """Nearest ancestor that looks like a list item; None if there is none.

    A heading qualifies the anchor as an item, but the *summary* lives in the
    enclosing article/li/list div, so keep walking past headings when a wider
    item container exists."""
    cur = node.parent
    heading: Node | None = None
    while cur is not None:
        cls = (cur.attributes.get("class") or "").lower()
        if cur.tag in _HEADINGS:
            heading = heading or cur
        elif cur.tag in _CONTAINER_TAGS or (
            cur.tag == "div" and any(h in cls for h in _CONTAINER_CLASS_HINTS)
        ):
            return cur
        cur = cur.parent
    return heading


def _summary_for(container: Node | None, title: str) -> str:
    if container is None:
        return ""
    text = _clean(container.text(separator=" "))
    if text.startswith(title):
        text = text[len(title) :].strip()
    return text[:1000]


def extract_items(html: str, base_url: str, item_selector: str | None = None) -> list[RawItem]:
    tree = HTMLParser(html)
    base_host = (urlsplit(base_url).hostname or "").lower()
    seen: set[str] = set()
    items: list[RawItem] = []

    if item_selector:
        anchors = [n if n.tag == "a" else n.css_first("a") for n in tree.css(item_selector)]
        anchors = [a for a in anchors if a is not None]
    else:
        anchors = tree.css("a[href]")

    for a in anchors:
        href = a.attributes.get("href")
        if not href or href.startswith(("#", "mailto:", "javascript:", "tel:")):
            continue
        title = _clean(a.text(separator=" "))
        url = urljoin(base_url, href)
        host = (urlsplit(url).hostname or "").lower()
        if not item_selector:
            if len(title) < _MIN_TITLE or host != base_host or _has_excluded_ancestor(a):
                continue
            container = _in_item_container(a)
            if container is None:
                continue
        else:
            container = a.parent
        canon = canonical_url(url)
        if canon in seen or canon == canonical_url(base_url):
            continue
        seen.add(canon)
        summary = _summary_for(container, title)
        items.append(
            RawItem(
                external_id=canon,
                title=title,
                url=url,
                canonical_url=canon,
                summary=summary,
                published_at=None,
                content_hash=content_hash(title, summary),
            )
        )
    return items


def page_hash(html: str) -> str:
    return hashlib.sha256(_WS.sub(" ", html).strip().encode()).hexdigest()


async def fetch_page(http: httpx.AsyncClient, url: str, item_selector: str | None = None) -> tuple[list[RawItem], str]:
    response = await http.get(url, follow_redirects=True)
    response.raise_for_status()
    html = response.text
    return extract_items(html, str(response.url), item_selector), page_hash(html)
