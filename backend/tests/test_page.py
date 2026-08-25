"""List-page monitor: picks article links, not chrome."""
from pathlib import Path

from rns.collect.page import extract_items, page_hash

FIXTURE = (Path(__file__).parent / "fixtures" / "page_list.html").read_text()
BASE = "https://www.rhein-neckar-kreis.de/startseite/aktuelles/pressemeldungen.html"


def test_extracts_article_links_and_skips_nav_footer_and_short_titles():
    # Wrong: every <a> with a long title — that would pick the nav and footer links.
    items = extract_items(FIXTURE, BASE)
    titles = [i.title for i in items]
    assert "Kreistag beschließt Haushalt 2027 mit Rekordinvestitionen in Schulen" in titles
    assert "Sanierung der B3 bei Weinheim beginnt im September" in titles
    assert "Landkreis startet Förderprogramm für Glasfaserausbau in 14 Gemeinden" in titles
    assert not any("Impressum" in t or "Investorenservice" in t or "Facebook" in t for t in titles)
    assert not any(t == "Kurz" for t in titles)
    assert len(items) == 3


def test_relative_links_resolved_and_canonicalised():
    items = {i.title: i for i in extract_items(FIXTURE, BASE)}
    b3 = items["Sanierung der B3 bei Weinheim beginnt im September"]
    assert b3.url.startswith("https://www.rhein-neckar-kreis.de/")
    assert "utm_source" not in b3.canonical_url
    assert b3.summary and "3,2 km" in b3.summary


def test_item_selector_overrides_heuristic():
    # A site-specific selector should be the whole truth when given.
    items = extract_items(FIXTURE, BASE, item_selector="footer a")
    assert [i.title for i in items] == ["Impressum und Datenschutzerklärung des Landkreises"]


def test_page_hash_ignores_volatile_whitespace():
    assert page_hash("<p>a</p>\n\n  <p>b</p>") == page_hash("<p>a</p> <p>b</p>")
