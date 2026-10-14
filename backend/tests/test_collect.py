"""collect_all: dedup across sources, page-hash short-circuit, source health."""
from pathlib import Path

import httpx
import pytest
import respx
from sqlalchemy import select

from mhs.collect.run import collect_all
from mhs.db.models import FeedItem, Source

FIX = Path(__file__).parent / "fixtures"


def _source(slug, method, url, **kw):
    return Source(slug=slug, name=slug, layer="editorial", authority="high", scope="region",
                  method=method, url=url, collect=True, **kw)


@pytest.fixture
def http():
    return httpx.AsyncClient(timeout=5)


@respx.mock
async def test_same_canonical_url_from_two_sources_is_one_item_with_also_seen_in(db_session, http):
    # Wrong: unique on (source, external_id) only, so MM Wirtschaft and MM Unternehmen
    # der Region produce two feed items for one article.
    a = _source("mm-wirtschaft", "rss", "https://mm.test/a.xml")
    b = _source("mm-unternehmen", "rss", "https://mm.test/b.xml")
    db_session.add_all([a, b])
    await db_session.commit()
    respx.get("https://mm.test/a.xml").mock(return_value=httpx.Response(200, content=(FIX / "feed_a.xml").read_bytes()))
    respx.get("https://mm.test/b.xml").mock(return_value=httpx.Response(200, content=(FIX / "feed_b.xml").read_bytes()))

    stats = await collect_all(db_session, http)

    items = (await db_session.execute(select(FeedItem))).scalars().all()
    assert stats.fetched == 3 and stats.new_items == 2
    assert len(items) == 2
    basf = next(i for i in items if "BASF" in (i.title or ""))
    assert basf.source_id == a.id
    assert basf.also_seen_in == [b.id]


@respx.mock
async def test_second_run_adds_nothing_and_page_monitor_skips_unchanged_page(db_session, http):
    # Wrong: re-inserting every item each cycle (or re-extracting an unchanged page).
    s = _source("rnk-presse", "page", "https://www.rhein-neckar-kreis.de/startseite/aktuelles/pressemeldungen.html")
    db_session.add(s)
    await db_session.commit()
    route = respx.get("https://www.rhein-neckar-kreis.de/startseite/aktuelles/pressemeldungen.html").mock(
        return_value=httpx.Response(200, text=(FIX / "page_list.html").read_text())
    )
    first = await collect_all(db_session, http)
    second = await collect_all(db_session, http)
    assert first.new_items == 3
    assert second.new_items == 0 and second.fetched == 0  # unchanged hash → nothing parsed
    assert route.call_count == 2
    await db_session.refresh(s)
    assert s.last_page_hash and s.last_ok_at is not None


@respx.mock
async def test_failed_source_counts_up_and_quarantines_after_max(db_session, http, monkeypatch):
    from mhs import config
    monkeypatch.setattr(config.settings, "max_consecutive_failures", 2)
    s = _source("dead", "rss", "https://dead.test/feed.xml")
    db_session.add(s)
    await db_session.commit()
    respx.get("https://dead.test/feed.xml").mock(return_value=httpx.Response(404))

    await collect_all(db_session, http)
    await db_session.refresh(s)
    assert s.consecutive_failures == 1 and s.status == "active" and "404" in (s.last_error or "")
    await collect_all(db_session, http)
    await db_session.refresh(s)
    assert s.consecutive_failures == 2 and s.status == "quarantined"
    # Quarantined sources are not fetched again.
    calls = respx.calls.call_count
    await collect_all(db_session, http)
    assert respx.calls.call_count == calls


@respx.mock
async def test_not_collected_sources_are_never_fetched(db_session, http):
    s = _source("newsletter-only", "newsletter", "https://nl.test/")
    s.collect = False
    db_session.add(s)
    await db_session.commit()
    stats = await collect_all(db_session, http)
    assert stats.fetched == 0 and respx.calls.call_count == 0


@respx.mock
async def test_items_older_than_the_freshness_window_are_not_stored(db_session, http, monkeypatch):
    # Wrong: ingesting a publisher's whole archive (MVV's feed carries ~1,700 items going
    # back years) as if it were this cycle's news.
    from mhs import config
    monkeypatch.setattr(config.settings, "max_item_age_days", 60)
    s = _source("mvv", "rss", "https://mvv.test/feed.xml")
    db_session.add(s)
    await db_session.commit()
    old = (FIX / "feed_a.xml").read_text().replace("Mon, 24 Aug 2026 06:30:00 +0200", "Tue, 23 Dec 2025 06:30:00 +0100")
    respx.get("https://mvv.test/feed.xml").mock(return_value=httpx.Response(200, content=old.encode()))
    stats = await collect_all(db_session, http)
    titles = [i.title for i in (await db_session.execute(select(FeedItem))).scalars()]
    assert stats.new_items == 1 and "BASF" not in " ".join(titles)
    assert stats.skipped_old == 1
