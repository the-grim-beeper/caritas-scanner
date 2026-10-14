"""collect_all: dedup across sources, page-hash short-circuit, source health."""
import asyncio
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pytest
import respx
from sqlalchemy import select

from mhs.collect.run import _target_host, collect_all
from mhs.db.models import FeedItem, Source

FIX = Path(__file__).parent / "fixtures"


def _source(slug, method, url, **kw):
    return Source(slug=slug, name=slug, layer="medien", authority="high", scope="landkreis",
                  method=method, url=url, collect=True, **kw)


@pytest.fixture
def http():
    return httpx.AsyncClient(timeout=5)


@respx.mock
async def test_same_canonical_url_from_two_sources_is_one_item_with_also_seen_in(db_session, http, monkeypatch):
    # Wrong: unique on (source, external_id) only, so Merkur Region Miesbach and Merkur
    # Holzkirchen produce two feed items for one article.
    from mhs import config
    monkeypatch.setattr(config.settings, "max_item_age_days", 36500)  # not a freshness test
    a = _source("merkur-miesbach", "rss", "https://mm.test/a.xml")
    b = _source("merkur-holzkirchen", "rss", "https://mm.test/b.xml")
    db_session.add_all([a, b])
    await db_session.commit()
    respx.get("https://mm.test/a.xml").mock(return_value=httpx.Response(200, content=(FIX / "feed_a.xml").read_bytes()))
    respx.get("https://mm.test/b.xml").mock(return_value=httpx.Response(200, content=(FIX / "feed_b.xml").read_bytes()))

    stats = await collect_all(db_session, http)

    items = (await db_session.execute(select(FeedItem))).scalars().all()
    assert stats.fetched == 3 and stats.new_items == 2
    assert len(items) == 2
    umlage = next(i for i in items if "Kreisumlage" in (i.title or ""))
    assert umlage.source_id == a.id
    assert umlage.also_seen_in == [b.id]


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
    from email.utils import format_datetime
    from datetime import datetime, timedelta, timezone
    recent = format_datetime(datetime.now(timezone.utc) - timedelta(days=1))
    old = ((FIX / "feed_a.xml").read_text()
           .replace("Mon, 12 Oct 2026 06:30:00 +0200", "Tue, 23 Dec 2025 06:30:00 +0100")
           .replace("Mon, 12 Oct 2026 08:00:00 +0200", recent))
    respx.get("https://mvv.test/feed.xml").mock(return_value=httpx.Response(200, content=old.encode()))
    stats = await collect_all(db_session, http)
    titles = [i.title for i in (await db_session.execute(select(FeedItem))).scalars()]
    assert stats.new_items == 1 and "Kreisumlage" not in " ".join(titles)
    assert stats.skipped_old == 1


def test_target_host_is_the_query_templates_host_not_the_source_url():
    # Wrong: key the per-host limit on source.url (None for a query source), so every
    # query source gets its own unlimited semaphore and news.google.com sees them all
    # fire in parallel — the opposite of what the limit is for.
    rss = _source("lk-presse", "rss", "https://lk.test/rss")
    q = Source(slug="q-waak", name="Q Waak", layer="medien", authority="medium", scope="gemeinde",
              method="query", query='"Waakirchen"', collect=True)
    assert _target_host(rss) == "lk.test"
    from mhs.config import settings
    assert _target_host(q) == urlsplit(settings.query_url_template).hostname


@respx.mock
async def test_concurrency_to_the_same_host_is_capped_even_across_many_sources(db_session, monkeypatch):
    # Wrong: only the global feed_concurrency semaphore, so six sources on one fragile
    # host (digitalfabrix SessionNet; every query source on news.google.com) all fire
    # at once and the host 503s under the load.
    from mhs import config
    monkeypatch.setattr(config.settings, "feed_concurrency", 10)
    active = 0
    max_active = 0
    lock = asyncio.Lock()

    async def _handler(request):
        nonlocal active, max_active
        async with lock:
            active += 1
            max_active = max(max_active, active)
        await asyncio.sleep(0.03)
        async with lock:
            active -= 1
        return httpx.Response(200, content=(FIX / "feed_a.xml").read_bytes())

    transport = httpx.MockTransport(_handler)
    shared_http = httpx.AsyncClient(timeout=5, transport=transport)
    sources = [_source(f"shared-{i}", "rss", f"https://shared-host.test/feed{i}.xml") for i in range(6)]
    db_session.add_all(sources)
    await db_session.commit()

    await collect_all(db_session, shared_http)
    assert max_active <= 2
