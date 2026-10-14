"""Fetch every rss/page entry in data/sources.yaml and write data/sources-live.json.

Verification is a build step, not a flag. For each entry:
  1. if it has an explicit rss url, fetch + parse it (≥1 item → live as rss)
  2. otherwise, or on failure, try feed autodiscovery on the homepage/url
     (<link rel=alternate type=application/rss+xml|atom+xml>, plus the usual
     /feed/ and /rss suffixes) — a found feed with ≥1 item → live as rss
  3. if the entry is a page monitor and no feed was found, fetch the list page
     and run the extractor (≥3 items → live as page)
Everything else is recorded in data/sources-check-report.json with the reason.
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import httpx
from selectolax.parser import HTMLParser

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mhs.collect.page import extract_items  # noqa: E402
from mhs.collect.rss import parse_feed  # noqa: E402
from mhs.config import settings  # noqa: E402
from mhs.sources.catalogue import COLLECTED_METHODS, load_catalogue  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
MIN_PAGE_ITEMS = 3
HEADERS = {
    "User-Agent": settings.user_agent,
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/html;q=0.9, */*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.7",
}
FEED_SUFFIXES = ("/feed/", "/feed", "/rss", "/rss.xml", "/feed.xml", "/?feed=rss2")


async def _get(http: httpx.AsyncClient, url: str) -> httpx.Response | None:
    try:
        r = await http.get(url, follow_redirects=True)
        return r
    except Exception:  # noqa: BLE001
        return None


def _looks_like_feed(r: httpx.Response) -> bool:
    ctype = r.headers.get("content-type", "")
    head = r.content[:400].lstrip().lower()
    return ("xml" in ctype) or head.startswith(b"<?xml") or b"<rss" in head or b"<feed" in head


async def _try_feed(http: httpx.AsyncClient, url: str) -> tuple[int, str] | None:
    r = await _get(http, url)
    if r is None or r.status_code != 200 or not _looks_like_feed(r):
        return None
    items = parse_feed(r.content, str(r.url))
    return (len(items), str(r.url)) if items else None


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
        if any(k in href.lower() for k in ("rss", "feed", ".xml")) and not href.startswith("mailto:"):
            found.append(urljoin(base, href))
    out: list[str] = []
    for u in found:
        if u not in out:
            out.append(u)
    return out[:12]


async def _autodiscover(http: httpx.AsyncClient, page_url: str) -> tuple[int, str] | None:
    r = await _get(http, page_url)
    if r is None or r.status_code != 200:
        return None
    if _looks_like_feed(r):
        items = parse_feed(r.content, str(r.url))
        if items:
            return len(items), str(r.url)
    candidates = _discover_links(r.text, str(r.url))
    candidates += [urljoin(str(r.url), s) for s in FEED_SUFFIXES]
    for c in candidates:
        hit = await _try_feed(http, c)
        if hit:
            return hit
    return None


async def _check(http: httpx.AsyncClient, entry, sem: asyncio.Semaphore) -> dict:
    async with sem:
        report = {"slug": entry.slug, "catalogue_method": entry.method, "tried": []}
        if entry.method == "rss" and entry.url:
            hit = await _try_feed(http, entry.url)
            report["tried"].append(("rss", entry.url, bool(hit)))
            if hit:
                return {**report, "ok": True, "method": "rss", "resolved_url": hit[1], "item_count": hit[0]}
        for base in [u for u in (entry.homepage, entry.url) if u]:
            hit = await _autodiscover(http, base)
            report["tried"].append(("autodiscover", base, bool(hit)))
            if hit:
                return {**report, "ok": True, "method": "rss", "resolved_url": hit[1], "item_count": hit[0]}
        if entry.method == "page" and entry.url:
            r = await _get(http, entry.url)
            if r is not None and r.status_code == 200:
                items = extract_items(r.text, str(r.url), entry.item_selector)
                report["tried"].append(("page", entry.url, len(items)))
                if len(items) >= MIN_PAGE_ITEMS:
                    return {**report, "ok": True, "method": "page", "resolved_url": str(r.url), "item_count": len(items)}
                return {**report, "ok": False, "reason": f"page extracted only {len(items)} items"}
            code = r.status_code if r is not None else "no response"
            report["tried"].append(("page", entry.url, code))
            return {**report, "ok": False, "reason": f"page fetch failed: {code}"}
        return {**report, "ok": False, "reason": "no feed found"}


def dedupe_resolved(results: list[dict]) -> list[dict]:
    """Autodiscovery can land two catalogue entries on one feed (Heidelberg's
    Baustellen entry resolving to the general press feed). Keep the first in
    catalogue order; the rest are not verified, and say which feed they hit."""
    seen: dict[str, str] = {}
    out: list[dict] = []
    for r in results:
        if r.get("ok"):
            url = r["resolved_url"]
            if url in seen:
                out.append({**{k: v for k, v in r.items() if k not in ("method", "resolved_url", "item_count")},
                            "ok": False, "reason": f"resolved to the same feed as {seen[url]}"})
                continue
            seen[url] = r["slug"]
        out.append(r)
    return out


async def main() -> int:
    entries = [e for e in load_catalogue(DATA / "sources.yaml") if e.method in COLLECTED_METHODS]
    sem = asyncio.Semaphore(8)
    async with httpx.AsyncClient(timeout=settings.feed_timeout_seconds, headers=HEADERS) as http:
        results = await asyncio.gather(*(_check(http, e, sem) for e in entries))
    results = dedupe_resolved(list(results))
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    live = [
        {"slug": r["slug"], "method": r["method"], "resolved_url": r["resolved_url"], "item_count": r["item_count"]}
        for r in results if r["ok"]
    ]
    (DATA / "sources-live.json").write_text(json.dumps({"checked_at": now, "results": live}, indent=2, ensure_ascii=False) + "\n")
    (DATA / "sources-check-report.json").write_text(json.dumps({"checked_at": now, "results": results}, indent=2, ensure_ascii=False) + "\n")
    ok = len(live)
    print(f"{ok}/{len(entries)} rss/page sources verified live ({ok / len(entries):.0%})")
    for r in results:
        mark = "OK " if r["ok"] else "-- "
        detail = f"{r['method']} {r['item_count']} items" if r["ok"] else r["reason"]
        print(f"  {mark}{r['slug']:<36} {detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
