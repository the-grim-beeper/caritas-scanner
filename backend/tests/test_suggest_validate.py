"""Resolve-before-propose: a candidate counts only if it verifies live as a feed with items or
as a list page the extractor can read (the same rules as scripts/check_sources.py)."""
from datetime import timedelta

import httpx
import pytest
import respx

from mhs.db.models import Source, SourceSuggestion, utcnow
from mhs.suggest import net
from mhs.suggest.validate import canonical, known_urls, suggest_key, verify_candidate

RSS = b"""<?xml version="1.0" encoding="utf-8"?><rss version="2.0"><channel><title>Gemeinde</title>
<link>https://feed.test</link>
<item><title>Gemeinderat beschliesst Haushalt</title><link>https://feed.test/1</link></item>
<item><title>Neue Sozialraumlotsin</title><link>https://feed.test/2</link></item>
</channel></rss>"""

ALTERNATE = b"""<html><head><title>Gemeinde Valley</title>
<link rel="alternate" type="application/rss+xml" href="/feed">
</head><body><p>Willkommen</p></body></html>"""


def listing(n: int, host: str = "liste.test") -> bytes:
    items = "".join(
        f'<li class="news-item"><a href="https://{host}/aktuelles/meldung-{i}">Meldung Nummer {i} aus dem Gemeinderat Weyarn</a>'
        f"<p>Kurztext {i}</p></li>"
        for i in range(n)
    )
    return f"<html><body><nav><a href='/'>Start</a></nav><ul>{items}</ul></body></html>".encode()


@pytest.fixture(autouse=True)
def public_dns(monkeypatch):
    monkeypatch.setattr(net, "_resolve", lambda host: ["93.184.216.34"])


@pytest.fixture
async def http():
    async with httpx.AsyncClient() as c:
        yield c


@respx.mock
async def test_feed_candidate_verifies_as_rss(http):
    respx.get("https://feed.test/rss").respond(200, content=RSS, headers={"content-type": "application/rss+xml"})
    v = await verify_candidate(http, "https://feed.test/rss")
    assert (v.ok, v.method, v.feed_url, v.items, v.reason) == (True, "rss", "https://feed.test/rss", 2, None)


@respx.mock
async def test_html_with_alternate_link_resolves_feed(http):
    respx.get("https://valley.test/aktuelles").respond(200, content=ALTERNATE, headers={"content-type": "text/html"})
    respx.get("https://valley.test/feed").respond(200, content=RSS, headers={"content-type": "application/rss+xml"})
    v = await verify_candidate(http, "https://valley.test/aktuelles")
    assert v.ok and v.method == "rss"
    assert v.feed_url == "https://valley.test/feed"  # absolute, resolved against the page
    assert v.items == 2


@respx.mock
async def test_listing_page_verifies_as_page(http):
    respx.get("https://liste.test/aktuelles").respond(200, content=listing(3), headers={"content-type": "text/html"})
    respx.route().respond(404)  # every feed-suffix probe misses
    v = await verify_candidate(http, "https://liste.test/aktuelles")
    assert v.ok and v.method == "page" and v.items == 3
    assert v.feed_url is None and v.url == "https://liste.test/aktuelles"


@respx.mock
async def test_thin_page_is_rejected_with_its_item_count(http):
    # Wrong: accepting any HTML page that answers 200.
    respx.get("https://duenn.test/x").respond(200, content=listing(1, "duenn.test"), headers={"content-type": "text/html"})
    respx.route().respond(404)
    v = await verify_candidate(http, "https://duenn.test/x")
    assert not v.ok and v.method is None
    assert "1" in v.reason


@respx.mock
async def test_dead_candidate_has_a_reason_naming_the_status(http):
    respx.get("https://tot.test/x").respond(404)
    v = await verify_candidate(http, "https://tot.test/x")
    assert not v.ok and "404" in v.reason


@respx.mock
async def test_private_candidate_is_refused_without_a_request(http, monkeypatch):
    route = respx.get("http://10.0.0.5/feed")
    v = await verify_candidate(http, "http://10.0.0.5/feed")
    assert not v.ok and v.reason
    assert not route.called


@respx.mock
async def test_feed_link_pointing_at_a_private_host_is_not_followed(http):
    page = b'<html><head><link rel="alternate" type="application/rss+xml" href="http://127.0.0.1/feed"></head></html>'
    respx.get("https://lockvogel.test/").respond(200, content=page, headers={"content-type": "text/html"})
    private = respx.get("http://127.0.0.1/feed").respond(200, content=RSS)
    respx.route().respond(404)
    v = await verify_candidate(http, "https://lockvogel.test/")
    assert not v.ok
    assert not private.called


def test_suggest_key_ignores_www_trailing_slash_and_scheme_but_not_path():
    assert suggest_key("https://a.test/x") == suggest_key("https://www.a.test/x/") == suggest_key("http://A.test/x")
    assert suggest_key("https://a.test/x") != suggest_key("https://a.test/y")
    assert suggest_key("https://a.test/X") != suggest_key("https://a.test/x")  # path case is meaningful
    assert suggest_key("https://a.test/") == suggest_key("https://www.a.test")
    assert canonical("https://www.a.test/x/?utm_source=nl") == "https://www.a.test/x"


async def test_known_urls_cover_sources_and_every_suggestion(db_session):
    now = utcnow()
    db_session.add_all([
        Source(slug="lk", name="LK", layer="landkreis", authority="high", scope="landkreis", method="rss",
               url="https://lk.test/rss/", homepage="https://www.lk.test/"),
        Source(slug="q", name="Query", layer="medien", authority="medium", scope="landkreis", method="query",
               query="Miesbach Pflege"),
        SourceSuggestion(url="https://declined.test/x", name="D", layer="gemeinden", scope="gemeinde",
                         rationale_de="r", rationale_en="r", model="mock", status="declined",
                         suggested_at=now, adopt_after=now + timedelta(days=7)),
        SourceSuggestion(url="https://rejected.test/y", name="R", layer="gemeinden", scope="gemeinde",
                         rationale_de="r", rationale_en="r", model="mock", status="rejected",
                         feed_url="https://rejected.test/y/feed", suggested_at=now,
                         adopt_after=now + timedelta(days=7)),
    ])
    await db_session.commit()
    known = await known_urls(db_session)
    assert {"https://lk.test/rss", "https://www.lk.test/", "https://declined.test/x",
            "https://rejected.test/y"} <= known
    assert None not in known
