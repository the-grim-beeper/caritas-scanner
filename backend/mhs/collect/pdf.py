"""PDF sources — Amtsblätter and similar notices linked from a list page rather than
syndicated. The list page itself is fetched fresh every cycle; only PDFs not already
stored for this source (`seen_urls`) are downloaded and read.

Several municipal sites (Irschenberg, Holzkirchen, Rottach-Egern) serve the PDF from
a download handler with no `.pdf` in the URL (`/ceasy/resource/<id>?download=1`,
`output/download.php?fid=…`). `pdf_links` also accepts same-domain links whose href or
text looks like a download, and `fetch_pdf` confirms the content actually is a PDF
(content-type or `%PDF-` magic bytes) before parsing — so a page full of download
links that are not PDFs is skipped, not mis-parsed."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from io import BytesIO
from urllib.parse import urljoin, urlsplit

import httpx
from pypdf import PdfReader
from selectolax.parser import HTMLParser

from mhs.collect.canonical import RawItem, canonical_url, content_hash
from mhs.config import settings

_PDF_HREF = re.compile(r"\.pdf(?:$|\?)", re.IGNORECASE)
_DOWNLOAD_HINT = re.compile(r"download|datei|dokument", re.IGNORECASE)
_WS = re.compile(r"\s+")
_PDF_DATE = re.compile(r"D:(\d{4})(\d{2})(\d{2})(\d{2})?(\d{2})?(\d{2})?")


def _clean(text: str | None) -> str:
    return _WS.sub(" ", text or "").strip()


def _registrable_domain(host: str) -> str:
    labels = host.split(".")
    return ".".join(labels[-2:]) if len(labels) >= 2 else host


def pdf_links(html: bytes, base_url: str) -> list[tuple[str, str]]:
    """(absolute url, link text) on the same registrable domain as base_url, in
    document order, each absolute URL kept once. Kept when the href ends .pdf
    (case-insensitive, a query string allowed) OR — for the download handlers some
    sites use instead of a plain .pdf link — the href or link text contains
    "download"/"datei"/"dokument"; `fetch_pdf` is what actually confirms the latter
    group is a PDF before reading it."""
    tree = HTMLParser(html)
    base_domain = _registrable_domain((urlsplit(base_url).hostname or "").lower())
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for a in tree.css("a[href]"):
        href = a.attributes.get("href") or ""
        if not href or href.startswith(("#", "mailto:", "javascript:", "tel:")):
            continue
        text = _clean(a.text(separator=" "))
        if not (_PDF_HREF.search(href) or _DOWNLOAD_HINT.search(href) or _DOWNLOAD_HINT.search(text)):
            continue
        url = urljoin(base_url, href)
        host = (urlsplit(url).hostname or "").lower()
        if _registrable_domain(host) != base_domain:
            continue
        if url in seen:
            continue
        seen.add(url)
        out.append((url, text))
    return out


def _looks_like_pdf(response: httpx.Response) -> bool:
    ctype = response.headers.get("content-type", "")
    return "pdf" in ctype.lower() or response.content[:5] == b"%PDF-"


def pdf_text(data: bytes, max_pages: int, max_chars: int) -> tuple[str, datetime | None]:
    reader = PdfReader(BytesIO(data))
    parts = [(page.extract_text() or "") for page in reader.pages[:max_pages]]
    text = "\n".join(parts).strip()[:max_chars]

    created: datetime | None = None
    meta = reader.metadata
    raw = meta.get("/CreationDate") if meta else None
    if raw:
        m = _PDF_DATE.match(raw)
        if m:
            year, month, day, hour, minute, second = (int(g) if g else 0 for g in m.groups())
            try:
                created = datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)
            except ValueError:
                created = None
    return text, created


async def fetch_pdf(http: httpx.AsyncClient, source, seen_urls: set[str]) -> list[RawItem]:
    response = await http.get(source.url, follow_redirects=True)
    response.raise_for_status()
    links = pdf_links(response.content, str(response.url))

    items: list[RawItem] = []
    attempts = 0
    for url, link_text in links:
        canon = canonical_url(url)
        if canon in seen_urls:
            continue
        # The attempt cap — not just the found-item cap — bounds every fetch,
        # including a probe that turns out not to be a PDF at all: a list page
        # with 200 "download" links can cost at most max_pdfs_per_source requests.
        if attempts >= settings.max_pdfs_per_source:
            break
        attempts += 1
        try:
            pdf_resp = await http.get(url, follow_redirects=True)
            pdf_resp.raise_for_status()
        except httpx.HTTPError:
            continue
        if len(pdf_resp.content) > settings.max_pdf_bytes:
            continue
        if not _looks_like_pdf(pdf_resp):
            continue
        try:
            body, created = pdf_text(pdf_resp.content, settings.max_pdf_pages, settings.max_pdf_chars)
        except Exception:  # noqa: BLE001 — a corrupt PDF is a skip, not a crash
            continue
        title = link_text or url.rsplit("/", 1)[-1]
        items.append(
            RawItem(
                external_id=canon,
                title=title,
                url=url,
                canonical_url=canon,
                summary=body,
                published_at=created,
                content_hash=content_hash(title, body),
            )
        )
    return items
