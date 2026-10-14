"""PDF sources: Amtsblätter linked from a list page. Each test names the wrong
implementation it defends against.

`_build_pdf` hand-assembles a minimal one-page PDF (a Helvetica font object and a
`BT ... Tj ET` content stream, with a real xref table) so the suite needs no extra
dependency beyond pypdf, which is already used to read it."""
from __future__ import annotations

import io
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
import respx

from mhs.collect.pdf import fetch_pdf, pdf_links, pdf_text
from mhs.config import settings
from mhs.db.models import Source

FIX = Path(__file__).parent / "fixtures"
LIST_HTML = (FIX / "pdf_list.html").read_bytes()
BASE_URL = "https://www.landkreis-miesbach.de/amtsblaetter.html"


def _build_pdf(text: str, creation_date: str | None = "D:20261012140500+02'00'") -> bytes:
    def esc(s: str) -> bytes:
        return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)").encode("latin-1")

    content = b"BT /F1 12 Tf 72 720 Td (" + esc(text) + b") Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> "
        b"/MediaBox [0 0 612 792] /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
    ]
    info = b"<<"
    if creation_date:
        info += b" /CreationDate (" + creation_date.encode("latin-1") + b")"
    info += b" >>"
    objects.append(info)

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode())
        out.write(obj)
        out.write(b"\nendobj\n")

    xref_offset = out.tell()
    n = len(objects) + 1
    out.write(f"xref\n0 {n}\n".encode())
    out.write(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {n} /Root 1 0 R /Info 6 0 R >>\nstartxref\n{xref_offset}\n%%EOF".encode())
    return out.getvalue()


def test_build_pdf_helper_round_trips_through_pypdf():
    data = _build_pdf("Haushalt 2027 Kreisumlage")
    text, created = pdf_text(data, max_pages=12, max_chars=20_000)
    assert "Haushalt 2027 Kreisumlage" in text
    assert created == datetime(2026, 10, 12, 14, 5, 0, tzinfo=timezone.utc)


def test_pdf_text_without_creation_date_returns_none():
    data = _build_pdf("Amtsblatt ohne Datum", creation_date=None)
    _, created = pdf_text(data, max_pages=12, max_chars=20_000)
    assert created is None


def test_pdf_text_truncates_to_max_chars():
    data = _build_pdf("Haushalt 2027 Kreisumlage")
    text, _ = pdf_text(data, max_pages=12, max_chars=5)
    assert text == "Haush"


def test_pdf_links_keeps_same_domain_pdfs_case_insensitively_and_drops_the_rest():
    # Wrong: match only a lowercase ".pdf" suffix with no query string allowed, or
    # keep links off the source's own domain.
    links = pdf_links(LIST_HTML, BASE_URL)
    urls = [u for u, _ in links]
    assert "https://www.landkreis-miesbach.de/dokumente/Amtsblatt_42.pdf" in urls
    assert "https://www.landkreis-miesbach.de/x.PDF?v=2" in urls
    assert not any("other.example" in u for u in urls)
    assert not any(u.endswith("/seite.html") for u in urls)


def test_pdf_links_deduplicates_the_same_absolute_url():
    links = pdf_links(LIST_HTML, BASE_URL)
    urls = [u for u, _ in links]
    assert urls.count("https://www.landkreis-miesbach.de/dokumente/Amtsblatt_42.pdf") == 1


def test_pdf_links_preserves_document_order():
    links = pdf_links(LIST_HTML, BASE_URL)
    urls = [u for u, _ in links]
    assert urls.index("https://www.landkreis-miesbach.de/dokumente/Amtsblatt_42.pdf") < urls.index(
        "https://www.landkreis-miesbach.de/x.PDF?v=2"
    )


_DOWNLOAD_LIST_HTML = b"""
<!doctype html>
<html lang="de"><head><title>Gemeindeblatt</title></head>
<body>
<main>
  <ul>
    <li><a href="/ceasy/resource/12?download=1">Gemeindeblatt Oktober 2026</a></li>
    <li><a href="/output/download.php?fid=99">Gemeindeblatt September 2026</a></li>
    <li><a href="/aktuelles/datei/42">Alte Fassung</a></li>
    <li><a href="/dokument/55">Dokument ohne Hinweis im Pfad</a></li>
    <li><a href="/impressum.html">Impressum</a></li>
  </ul>
</main>
</body></html>
"""
DOWNLOAD_BASE = "https://www.holzkirchen.de/gemeindeblatt"


def test_pdf_links_also_accepts_download_handlers_without_a_pdf_extension():
    # Wrong: require a literal ".pdf" in the href, so Irschenberg/Holzkirchen/
    # Rottach-Egern style download handlers (no .pdf extension at all) are never
    # even attempted and their Amtsblätter are silently never collected.
    links = pdf_links(_DOWNLOAD_LIST_HTML, DOWNLOAD_BASE)
    urls = [u for u, _ in links]
    assert any("ceasy/resource/12?download=1" in u for u in urls)
    assert any("download.php?fid=99" in u for u in urls)
    assert any("/aktuelles/datei/42" in u for u in urls)
    assert not any(u.endswith("/impressum.html") for u in urls)


@respx.mock
async def test_fetch_pdf_confirms_content_type_before_parsing_a_download_link():
    # Wrong: parse whatever a "download" link returns as if it were a PDF, so an
    # HTML error page or a redirect-to-login crashes pdf_text or is stored as content.
    respx.get(DOWNLOAD_BASE).mock(return_value=httpx.Response(200, content=_DOWNLOAD_LIST_HTML))
    pdf_data = _build_pdf("Gemeindeblatt Oktober 2026 Inhalt")
    respx.get("https://www.holzkirchen.de/ceasy/resource/12?download=1").mock(
        return_value=httpx.Response(200, content=pdf_data, headers={"content-type": "application/pdf"})
    )
    respx.get("https://www.holzkirchen.de/output/download.php?fid=99").mock(
        return_value=httpx.Response(200, text="<html>nicht gefunden</html>")
    )
    respx.get("https://www.holzkirchen.de/aktuelles/datei/42").mock(return_value=httpx.Response(404))
    respx.get("https://www.holzkirchen.de/dokument/55").mock(
        return_value=httpx.Response(200, text="<html>auch keine Amtsblatt-Seite</html>")
    )

    src = _source(url=DOWNLOAD_BASE)
    async with httpx.AsyncClient(timeout=5) as http:
        items = await fetch_pdf(http, src, set())

    assert len(items) == 1
    assert "Gemeindeblatt Oktober 2026 Inhalt" in items[0].summary


@respx.mock
async def test_fetch_pdf_bounds_non_pdf_probes_by_the_same_per_source_cap(monkeypatch):
    # Wrong: cap only confirmed PDFs, so a list page with 200 non-PDF "download"
    # links costs 200 requests every cycle instead of at most max_pdfs_per_source.
    monkeypatch.setattr(settings, "max_pdfs_per_source", 2)
    respx.get(DOWNLOAD_BASE).mock(return_value=httpx.Response(200, content=_DOWNLOAD_LIST_HTML))
    not_a_pdf = httpx.Response(200, text="<html>nicht gefunden</html>")
    route_a = respx.get("https://www.holzkirchen.de/ceasy/resource/12?download=1").mock(return_value=not_a_pdf)
    route_b = respx.get("https://www.holzkirchen.de/output/download.php?fid=99").mock(return_value=not_a_pdf)
    route_c = respx.get("https://www.holzkirchen.de/aktuelles/datei/42").mock(return_value=not_a_pdf)
    route_d = respx.get("https://www.holzkirchen.de/dokument/55").mock(return_value=not_a_pdf)

    src = _source(url=DOWNLOAD_BASE)
    async with httpx.AsyncClient(timeout=5) as http:
        items = await fetch_pdf(http, src, set())

    assert items == []
    attempted = route_a.call_count + route_b.call_count + route_c.call_count + route_d.call_count
    assert attempted == 2


def _source(**kw):
    kw.setdefault("url", BASE_URL)
    return Source(slug="lk-amtsblatt", name="Landkreis Miesbach – Amtsblatt", layer="landkreis",
                 authority="high", scope="landkreis", method="pdf", collect=True, **kw)


@respx.mock
async def test_fetch_pdf_skips_seen_urls_and_respects_the_per_source_cap(monkeypatch):
    # Wrong: refetch every linked PDF every cycle, so the same Amtsblatt is re-read
    # (and re-extracted downstream) forever instead of once.
    monkeypatch.setattr(settings, "max_pdfs_per_source", 1)
    respx.get(BASE_URL).mock(return_value=httpx.Response(200, content=LIST_HTML))
    pdf_a = _build_pdf("Amtsblatt 42 Inhalt")
    pdf_b = _build_pdf("Amtsblatt 43 Inhalt")
    respx.get("https://www.landkreis-miesbach.de/dokumente/Amtsblatt_42.pdf").mock(
        return_value=httpx.Response(200, content=pdf_a)
    )
    respx.get("https://www.landkreis-miesbach.de/x.PDF?v=2").mock(return_value=httpx.Response(200, content=pdf_b))

    src = _source()
    seen = {"https://www.landkreis-miesbach.de/dokumente/Amtsblatt_42.pdf"}  # already-stored canonical url
    async with httpx.AsyncClient(timeout=5) as http:
        items = await fetch_pdf(http, src, seen)

    assert len(items) == 1
    assert "Amtsblatt 43" in items[0].summary


@respx.mock
async def test_fetch_pdf_skips_a_pdf_larger_than_the_byte_cap(monkeypatch):
    small = _build_pdf("klein")
    big = _build_pdf("Amtsblatt " * 50)
    assert len(small) < 900 < len(big)
    monkeypatch.setattr(settings, "max_pdf_bytes", 900)
    respx.get(BASE_URL).mock(return_value=httpx.Response(200, content=LIST_HTML))
    respx.get("https://www.landkreis-miesbach.de/dokumente/Amtsblatt_42.pdf").mock(
        return_value=httpx.Response(200, content=big)
    )
    respx.get("https://www.landkreis-miesbach.de/x.PDF?v=2").mock(return_value=httpx.Response(200, content=small))

    src = _source()
    async with httpx.AsyncClient(timeout=5) as http:
        items = await fetch_pdf(http, src, set())

    assert len(items) == 1
    assert "klein" in items[0].summary


@respx.mock
async def test_fetch_pdf_sets_title_from_link_text_and_published_at_from_metadata():
    respx.get(BASE_URL).mock(return_value=httpx.Response(200, content=LIST_HTML))
    data = _build_pdf("Haushalt 2027 Kreisumlage")
    respx.get("https://www.landkreis-miesbach.de/dokumente/Amtsblatt_42.pdf").mock(
        return_value=httpx.Response(200, content=data)
    )
    respx.get("https://www.landkreis-miesbach.de/x.PDF?v=2").mock(
        return_value=httpx.Response(200, content=_build_pdf("weiterer Inhalt"))
    )

    src = _source()
    async with httpx.AsyncClient(timeout=5) as http:
        items = await fetch_pdf(http, src, set())

    first = next(i for i in items if "42" in i.canonical_url)
    assert first.title == "Amtsblatt Nr. 42"
    assert first.published_at == datetime(2026, 10, 12, 14, 5, 0, tzinfo=timezone.utc)
