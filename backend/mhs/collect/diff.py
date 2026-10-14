"""Diff sources — a static page with no feed and no list, watched for changes to its
own text (council minutes pages, budget pages). Every fetch is compared against the
snapshot last stored on the Source row; an item is emitted only when the text actually
moved, so a changed "Stand:" date alone — or a visitor counter — never fires.

The Advantic CMS used by the Landkreis and several municipalities (Bad Wiessee, Gmund,
Kreuth, Rottach-Egern, Tegernsee) puts a 4-item "Aktuelles" teaser box on every page;
a whole-page diff would fire on every press release elsewhere on the site. `main_text`
therefore narrows to the page's own content container before hashing or diffing."""
from __future__ import annotations

import difflib
import hashlib
import re

import httpx
from selectolax.parser import HTMLParser, Node

from mhs.collect.canonical import RawItem, content_hash
from mhs.config import settings

_DROP_TAGS = ("script", "style", "nav", "header", "footer", "form", "aside")
# Tried in order; the first that matches is the content container. A catalogue
# item_selector (passed in explicitly) always wins over all of these.
_CONTAINER_SELECTORS = ("main", "article", "#content", ".content", "#inhalt", ".inhalt", "[role=main]")
# A descendant whose class/id names one of these is chrome, not content — the
# Advantic sidebar, a "news-list" box, an "aktuell" teaser — even when it sits
# inside the chosen container. The container itself is never dropped this way.
_NOISE_HINTS = ("teaser", "sidebar", "news-list", "aktuell")
_DATE = re.compile(r"\b\d{1,2}\.\d{1,2}\.\d{2,4}\b")
_TIME = re.compile(r"\b\d{1,2}:\d{2}(?:\s?Uhr)?\b")
# After dates/times are folded to "·", a line that is only digits/punctuation/that
# marker carries no information — a visitor counter, a bare separator.
_ONLY_NOISE = re.compile(r"^[\d\s.,:;\-–—/()·]*$")


def _is_noise(node: Node) -> bool:
    cls = (node.attributes.get("class") or "").lower()
    ident = (node.attributes.get("id") or "").lower()
    return any(hint in cls or hint in ident for hint in _NOISE_HINTS)


def _select_container(tree: HTMLParser, item_selector: str | None) -> Node | None:
    if item_selector:
        node = tree.css_first(item_selector)
        if node is not None:
            return node
    for selector in _CONTAINER_SELECTORS:
        node = tree.css_first(selector)
        if node is not None:
            return node
    return tree.body


def main_text(html: bytes, item_selector: str | None = None) -> str:
    tree = HTMLParser(html)
    for tag in _DROP_TAGS:
        for node in tree.css(tag):
            node.decompose()
    root = _select_container(tree, item_selector)
    if root is None:
        return ""
    for node in root.css("[class], [id]"):
        if node is not root and _is_noise(node):
            node.decompose()
    lines: list[str] = []
    for raw_line in root.text(separator="\n").split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        line = _DATE.sub("·", line)
        line = _TIME.sub("·", line)
        if _ONLY_NOISE.match(line):
            continue
        lines.append(line)
    return "\n".join(lines)


def snapshot_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def change_summary(old: str, new: str, limit: int) -> str | None:
    diff = difflib.ndiff(old.splitlines(), new.splitlines())
    changed = [line for line in diff if line.startswith("+ ") or line.startswith("- ")]
    if not changed:
        return None
    return "\n".join(changed)[:limit]


async def fetch_diff(http: httpx.AsyncClient, source) -> tuple[list[RawItem], str, str]:
    response = await http.get(source.url, follow_redirects=True)
    response.raise_for_status()
    new_text = main_text(response.content, source.item_selector)
    new_hash = snapshot_hash(new_text)
    old_hash = source.snapshot_hash

    if not old_hash or old_hash == new_hash:
        # First sight establishes the baseline; an unchanged hash has nothing to report.
        return [], new_text, new_hash

    summary = change_summary(source.snapshot_text or "", new_text, settings.max_diff_chars) or ""
    title = f"Änderung: {source.name}"
    item = RawItem(
        external_id=f"diff:{new_hash}",
        title=title,
        url=source.url,
        canonical_url=f"{source.url}#diff-{new_hash[:12]}",
        summary=summary,
        published_at=None,
        content_hash=content_hash(title, summary),
    )
    return [item], new_text, new_hash
