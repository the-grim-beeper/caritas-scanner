"""Diff sources: a static page watched for changes to its own text. Each test names
the wrong implementation it defends against."""
from pathlib import Path

import httpx
import pytest
import respx

from mhs.collect.diff import change_summary, fetch_diff, main_text, snapshot_hash
from mhs.db.models import Source

FIX = Path(__file__).parent / "fixtures"
V1 = (FIX / "diff_v1.html").read_bytes()
V2 = (FIX / "diff_v2.html").read_bytes()
URL = "https://www.waakirchen.de/haushalt-2027.html"


def _source(**kw):
    return Source(slug="waakirchen-haushalt", name="Gemeinde Waakirchen – Haushalt 2027", layer="gemeinden",
                 authority="high", scope="gemeinde", method="diff", url=URL, collect=True, **kw)


def test_main_text_drops_script_nav_header_footer_and_pure_noise_lines():
    # Wrong: take body.text() wholesale, so nav links, the footer and the visitor
    # counter end up inside what is supposed to be the page's own content.
    text = main_text(V1)
    assert "Kontakt" not in text and "Impressum" not in text and "countVisitor" not in text
    assert "4213" not in text
    assert "Haushalt 2027" in text
    assert "Investitionen in die Kinderbetreuung sind vorgesehen." in text


_ADVANTIC_PAGE = """
<html><body>
<header role="banner"><nav>Hauptnavigation</nav></header>
<div id="content">
  <div class="aktuelles-sidebar">
    <h3>Aktuelles</h3>
    <a href="/a">Pressemeldung A</a>
    <a href="/b">Pressemeldung B</a>
  </div>
  <h1>Kreistag</h1>
  <p>Der Kreistag besteht aus 60 Mitgliedern.</p>
</div>
<footer>Impressum</footer>
</body></html>
"""


def test_main_text_isolates_the_content_container_from_the_advantic_sidebar():
    # Wrong: diff the whole page, so the Advantic CMS's 4-item "Aktuelles" teaser box
    # (present on every page of the site) changes the hash on every unrelated press
    # release and the diff source fires constantly on noise, never on its own content.
    page_1 = _ADVANTIC_PAGE
    page_2 = _ADVANTIC_PAGE.replace(
        '<a href="/b">Pressemeldung B</a>',
        '<a href="/b">Pressemeldung B</a>\n    <a href="/c">Pressemeldung C (neu!)</a>',
    )
    t1 = main_text(page_1.encode())
    t2 = main_text(page_2.encode())
    assert "Pressemeldung" not in t1
    assert snapshot_hash(t1) == snapshot_hash(t2)


def test_main_text_honours_a_catalogue_item_selector_as_the_container():
    html = (
        '<html><body><div class="wrap"><div class="col-sm-10"><a href="/x">Schlüsselzuweisung</a></div>'
        '<div class="aktuelles-sidebar">Teaser</div></div></body></html>'
    )
    text = main_text(html.encode(), item_selector="div.col-sm-10")
    assert text == "Schlüsselzuweisung"


def test_main_text_normalises_dates_and_times_to_the_same_token():
    # Wrong: hash the raw "Stand: 12.10.2026, 14:05 Uhr" line, so the snapshot changes
    # every day even when nothing on the page actually moved.
    text = main_text(V1)
    assert "Stand: ·, ·" in text
    assert "12.10.2026" not in text and "14:05" not in text


def test_snapshot_hash_is_stable_for_the_same_text():
    assert snapshot_hash(main_text(V1)) == snapshot_hash(main_text(V1))
    assert snapshot_hash(main_text(V1)) != snapshot_hash(main_text(V2))


def test_change_summary_has_added_and_removed_lines_only():
    s = change_summary("A\nB\nC", "A\nB2\nC", 6000)
    assert "+ B2" in s and "- B" in s
    assert "A" not in s.replace("B", "")


def test_change_summary_returns_none_when_nothing_added_or_removed():
    assert change_summary("A\nB\nC", "A\nB\nC", 6000) is None


@respx.mock
async def test_first_sight_is_baseline_only():
    # Wrong: emit an item on the very first fetch, so every diff source floods one
    # "change" the moment it is added, before there is anything to compare against.
    respx.get(URL).mock(return_value=httpx.Response(200, content=V1))
    src = _source()
    async with httpx.AsyncClient(timeout=5) as http:
        items, text, h = await fetch_diff(http, src)
    assert items == []
    assert text and h


@respx.mock
async def test_unchanged_page_emits_nothing():
    respx.get(URL).mock(return_value=httpx.Response(200, content=V1))
    src = _source()
    async with httpx.AsyncClient(timeout=5) as http:
        _, text, h = await fetch_diff(http, src)
    src.snapshot_text, src.snapshot_hash = text, h

    respx.get(URL).mock(return_value=httpx.Response(200, content=V1))
    async with httpx.AsyncClient(timeout=5) as http:
        items, *_ = await fetch_diff(http, src)
    assert items == []


@respx.mock
async def test_only_a_date_changed_emits_nothing():
    respx.get(URL).mock(return_value=httpx.Response(200, content=V1))
    src = _source()
    async with httpx.AsyncClient(timeout=5) as http:
        _, text, h = await fetch_diff(http, src)
    src.snapshot_text, src.snapshot_hash = text, h

    v1_new_date = V1.replace(b"12.10.2026", b"13.10.2026")
    respx.get(URL).mock(return_value=httpx.Response(200, content=v1_new_date))
    async with httpx.AsyncClient(timeout=5) as http:
        items, *_ = await fetch_diff(http, src)
    assert items == []


@respx.mock
async def test_changed_content_emits_one_item_with_a_bounded_change_summary():
    respx.get(URL).mock(return_value=httpx.Response(200, content=V1))
    src = _source()
    async with httpx.AsyncClient(timeout=5) as http:
        _, text, h = await fetch_diff(http, src)
    src.snapshot_text, src.snapshot_hash = text, h

    respx.get(URL).mock(return_value=httpx.Response(200, content=V2))
    async with httpx.AsyncClient(timeout=5) as http:
        items, new_text, new_hash = await fetch_diff(http, src)

    assert len(items) == 1
    item = items[0]
    assert item.external_id == f"diff:{new_hash}"
    assert item.url == URL
    assert item.canonical_url == f"{URL}#diff-{new_hash[:12]}"
    assert "Investitionen in die Kinderbetreuung werden auf 2,4 Millionen Euro erhöht." in item.summary
    assert new_hash != h and new_text != text
    # Undated by construction — collect_all's freshness filter must keep it anyway.
    assert item.published_at is None


@respx.mock
async def test_successive_changes_get_distinct_canonical_urls():
    # Wrong: use a canonical_url that does not depend on the hash, so a second
    # change to the same page collides with the first change's row.
    respx.get(URL).mock(return_value=httpx.Response(200, content=V1))
    src = _source()
    async with httpx.AsyncClient(timeout=5) as http:
        _, text, h = await fetch_diff(http, src)
    src.snapshot_text, src.snapshot_hash = text, h

    respx.get(URL).mock(return_value=httpx.Response(200, content=V2))
    async with httpx.AsyncClient(timeout=5) as http:
        items_a, text_a, hash_a = await fetch_diff(http, src)
    src.snapshot_text, src.snapshot_hash = text_a, hash_a

    v3 = V2.replace(b"2,4 Millionen", b"3,1 Millionen")
    respx.get(URL).mock(return_value=httpx.Response(200, content=v3))
    async with httpx.AsyncClient(timeout=5) as http:
        items_b, *_ = await fetch_diff(http, src)

    assert items_a[0].canonical_url != items_b[0].canonical_url
