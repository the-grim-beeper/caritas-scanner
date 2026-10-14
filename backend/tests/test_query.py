"""Query sources: a Google News search stands in for a feed. Each test names the
wrong implementation it defends against."""
from pathlib import Path

import httpx
import pytest
import respx
from sqlalchemy import select

from mhs.collect.canonical import RawItem
from mhs.collect.query import build_query_url, fetch_query, split_outlet, title_key
from mhs.collect.run import _store
from mhs.config import settings
from mhs.db.models import FeedItem, Source

FIX = Path(__file__).parent / "fixtures"


def test_build_query_url_encodes_the_query_into_the_template():
    # Wrong: paste the raw query into the URL, so spaces and quotes break the request.
    url = build_query_url('"Landkreis Miesbach" (Pflege OR Sozial)')
    assert url == settings.query_url_template.format(q="%22Landkreis+Miesbach%22+%28Pflege+OR+Sozial%29")
    assert url.startswith("https://news.google.com/rss/search?q=")


def test_split_outlet():
    assert split_outlet("Kreistag erhöht Kreisumlage - Merkur") == ("Kreistag erhöht Kreisumlage", "Merkur")
    assert split_outlet("Ohne Quelle") == ("Ohne Quelle", None)


def test_split_outlet_keeps_the_last_separator_when_the_headline_itself_has_a_dash():
    # Wrong: split on the first " - ", which would cut the headline instead of the outlet.
    assert split_outlet("Miesbach - Holzkirchen: Bus-Linie fällt aus - Merkur") == (
        "Miesbach - Holzkirchen: Bus-Linie fällt aus",
        "Merkur",
    )


def test_title_key_ignores_case_outlet_and_spacing():
    assert title_key("Kreistag  erhöht Kreisumlage - Merkur") == title_key("kreistag erhöht kreisumlage")


def test_title_key_strips_punctuation_at_the_ends():
    # Wrong: keep the trailing punctuation, so "...!" and the bare headline never match.
    assert title_key("Kreistag erhöht Kreisumlage!") == title_key("Kreistag erhöht Kreisumlage")


@respx.mock
async def test_fetch_query_builds_the_search_url_and_splits_the_outlet():
    # Wrong: store the Google News title as-is, so every item's "headline" ends in
    # " - Outlet" and content_hash never matches the direct feed's plain headline.
    src = Source(slug="q-lk", name="Q LK", layer="medien", authority="medium", scope="landkreis",
                 method="query", query='"Landkreis Miesbach"', collect=True)
    url = build_query_url(src.query)
    respx.get(url).mock(return_value=httpx.Response(200, content=(FIX / "gnews.xml").read_bytes()))

    async with httpx.AsyncClient(timeout=5) as http:
        items = await fetch_query(http, src)

    assert len(items) == 2
    first = next(i for i in items if "Kreisumlage" in i.title)
    assert first.title == "Kreistag erhöht Kreisumlage"
    assert first.outlet == "Merkur"
    second = next(i for i in items if "Pflegeheim" in i.title)
    assert second.title == "Pflegeheim Holzkirchen plant Erweiterung"
    assert second.outlet == "Süddeutsche Zeitung"


@respx.mock
async def test_fetch_query_keeps_items_with_no_pubdate():
    # Wrong: require a pubDate and drop items that lack one, so a council-system feed
    # with no dates (SessionNet/Bürgerinfo) loses every item at the query stage,
    # before collect_all's own "undated is kept" freshness rule even gets a say.
    undated_feed = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<item>
  <title>Sitzung des Gemeinderates Kreuth - Merkur</title>
  <link>https://news.google.com/rss/articles/CBMiZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ?oc=5</link>
  <guid isPermaLink="false">CBMiZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ</guid>
  <description>Sitzung des Gemeinderates Kreuth - Merkur</description>
  <source url="https://www.merkur.de">Merkur</source>
</item>
</channel></rss>
"""
    src = Source(slug="q-kreuth", name="Q Kreuth", layer="medien", authority="medium", scope="gemeinde",
                method="query", query='"Kreuth"', collect=True)
    url = build_query_url(src.query)
    respx.get(url).mock(return_value=httpx.Response(200, content=undated_feed))

    async with httpx.AsyncClient(timeout=5) as http:
        items = await fetch_query(http, src)

    assert len(items) == 1
    assert items[0].published_at is None
    assert items[0].title == "Sitzung des Gemeinderates Kreuth"


def _raw(external_id, title, url, outlet=None):
    return RawItem(
        external_id=external_id, title=title, url=url, canonical_url=url,
        summary="", published_at=None, content_hash=f"hash-{external_id}", outlet=outlet,
    )


async def test_query_item_matching_direct_item_is_credited_not_duplicated(db_session):
    # Wrong: dedup a query source on canonical URL, so the Google redirect link (which
    # changes every crawl) never matches the article it is reporting on the second time.
    direct = Source(slug="lk-presse", name="LK Presse", layer="landkreis", authority="high", scope="landkreis",
                    method="rss", url="https://lk.test/rss", collect=True)
    q = Source(slug="q-lk", name="Q LK", layer="medien", authority="medium", scope="landkreis",
              method="query", query='"Landkreis Miesbach"', collect=True)
    db_session.add_all([direct, q])
    await db_session.flush()

    headline = "Kreistag beschließt höhere Kreisumlage für das Jahr 2027"  # 8 words, specific enough to credit
    await _store(db_session, direct, [_raw("1", headline, "https://lk.test/a")])
    n = await _store(
        db_session, q,
        [_raw("g1", headline, "https://news.google.com/rss/articles/X", outlet="Merkur")],
    )

    rows = (await db_session.execute(select(FeedItem))).scalars().all()
    assert n == 0
    assert len(rows) == 1
    assert q.id in rows[0].also_seen_in


async def test_two_different_query_headlines_both_store(db_session):
    q = Source(slug="q-lk", name="Q LK", layer="medien", authority="medium", scope="landkreis",
              method="query", query='"Landkreis Miesbach"', collect=True)
    db_session.add(q)
    await db_session.flush()

    n = await _store(
        db_session, q,
        [
            _raw("g1", "Kreistag erhöht Kreisumlage", "https://news.google.com/rss/articles/X"),
            _raw("g2", "Pflegeheim Holzkirchen plant Erweiterung", "https://news.google.com/rss/articles/Y"),
        ],
    )
    rows = (await db_session.execute(select(FeedItem))).scalars().all()
    assert n == 2
    assert len(rows) == 2


async def test_short_generic_query_titles_are_never_merged_by_title_key(db_session):
    # Wrong: credit any title_key match regardless of how short or generic the
    # headline is, so two unrelated "Gemeinderatssitzung" stories from two different
    # municipalities (different URLs, both within the 60-day window) collapse into
    # one FeedItem — the second municipality's council meeting silently vanishes.
    q1 = Source(slug="q-kreuth", name="Q Kreuth", layer="medien", authority="medium", scope="gemeinde",
               method="query", query='"Kreuth"', collect=True)
    q2 = Source(slug="q-gmund", name="Q Gmund", layer="medien", authority="medium", scope="gemeinde",
               method="query", query='"Gmund"', collect=True)
    db_session.add_all([q1, q2])
    await db_session.flush()

    n1 = await _store(db_session, q1, [_raw("g1", "Gemeinderatssitzung", "https://news.google.com/rss/articles/A")])
    n2 = await _store(db_session, q2, [_raw("g2", "Gemeinderatssitzung", "https://news.google.com/rss/articles/B")])

    rows = (await db_session.execute(select(FeedItem))).scalars().all()
    assert n1 == 1 and n2 == 1
    assert len(rows) == 2
    assert all(row.also_seen_in == [] for row in rows)


async def test_query_match_is_scoped_to_the_sixty_day_window(db_session, monkeypatch):
    # Wrong: match on title_key alone with no age cutoff, so an unrelated story that
    # resurfaces a headline a year later gets silently merged into the old item.
    from datetime import timedelta
    from mhs.db.models import utcnow

    direct = Source(slug="lk-presse", name="LK Presse", layer="landkreis", authority="high", scope="landkreis",
                    method="rss", url="https://lk.test/rss", collect=True)
    q = Source(slug="q-lk", name="Q LK", layer="medien", authority="medium", scope="landkreis",
              method="query", query='"Landkreis Miesbach"', collect=True)
    db_session.add_all([direct, q])
    await db_session.flush()

    headline = "Kreistag beschließt höhere Kreisumlage für das Jahr 2027"  # 8 words, specific enough to credit
    await _store(db_session, direct, [_raw("1", headline, "https://lk.test/a")])
    old_row = (await db_session.execute(select(FeedItem))).scalars().one()
    old_row.created_at = utcnow() - timedelta(days=61)
    await db_session.flush()

    n = await _store(
        db_session, q,
        [_raw("g1", headline, "https://news.google.com/rss/articles/X", outlet="Merkur")],
    )
    rows = (await db_session.execute(select(FeedItem))).scalars().all()
    assert n == 1
    assert len(rows) == 2
