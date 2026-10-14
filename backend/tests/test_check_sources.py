"""scripts/check_sources.py: liveness checks for query/diff/pdf, and the rss/page
autodiscovery it shares with the template. Each test names the wrong implementation
it defends against. Uses httpx.MockTransport rather than respx so several distinct
URLs on one entry (own url, homepage, discovered feed) can be routed by hand."""
from __future__ import annotations

import asyncio

import httpx
import pytest

from mhs.sources.catalogue import CatalogueEntry
from scripts import check_sources as cs

_BASE = dict(slug="t", name="t", layer="gemeinden", authority="high", scope="gemeinde")


def _entry(**kw):
    return CatalogueEntry(**_BASE, **kw)


async def _check(handler, entry):
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        return await cs._check(http, entry, asyncio.Semaphore(1))


def _rss(title="A"):
    return f"""<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>{title}</title><link>https://x.test/a</link><guid>a</guid></item>
</channel></rss>""".encode()


async def test_query_entry_is_live_when_the_built_search_url_returns_items():
    async def handler(request):
        assert str(request.url).startswith("https://news.google.com/rss/search?q=")
        return httpx.Response(200, headers={"content-type": "application/rss+xml"}, content=_rss())

    entry = _entry(method="query", query='"Kreuth"')
    result = await _check(handler, entry)
    assert result["ok"] and result["method"] == "query"
    assert result["resolved_url"].startswith("https://news.google.com/rss/search?q=")


async def test_query_entry_is_not_live_when_the_search_feed_has_no_items():
    async def handler(request):
        return httpx.Response(200, headers={"content-type": "application/rss+xml"},
                              content=b'<?xml version="1.0"?><rss version="2.0"><channel></channel></rss>')

    entry = _entry(method="query", query='"Niemandsland"')
    result = await _check(handler, entry)
    assert not result["ok"]


async def test_diff_entry_is_live_only_past_the_200_char_floor():
    short_html = "<html><body><main><p>Zu kurz.</p></main></body></html>"
    long_html = "<html><body><main><p>" + ("Haushalt. " * 40) + "</p></main></body></html>"

    async def handler_short(request):
        return httpx.Response(200, text=short_html)

    async def handler_long(request):
        return httpx.Response(200, text=long_html)

    entry = _entry(method="diff", url="https://gemeinde.test/rat/")
    short_result = await _check(handler_short, entry)
    long_result = await _check(handler_long, entry)
    assert not short_result["ok"]
    assert long_result["ok"] and long_result["method"] == "diff"


async def test_diff_entry_honours_item_selector_as_the_container():
    # Wrong: ignore item_selector in the liveness check (even though main_text now
    # accepts it), so a catalogue entry that needs a selector to find its own content
    # is checked against the generic main/article/body fallback instead and reports
    # a char count from some other part of the page.
    html = (
        '<html><body><div class="related-links">' + ("Verwandte Links. " * 60) + "</div>"
        '<div class="col-sm-10"><p>Kurz.</p></div></body></html>'
    )

    async def handler(request):
        return httpx.Response(200, text=html)

    whole_page = _entry(method="diff", url="https://gemeinde.test/rat/")
    with_selector = _entry(method="diff", url="https://gemeinde.test/rat/", item_selector="div.col-sm-10")
    whole_result = await _check(handler, whole_page)
    selector_result = await _check(handler, with_selector)
    assert whole_result["ok"]  # falls back to body, which includes the unrelated box
    assert not selector_result["ok"]  # the actual content column is thin


async def test_pdf_entry_is_live_when_at_least_one_pdf_link_is_found():
    html = '<html><body><a href="/amtsblatt.pdf">Amtsblatt</a></body></html>'

    async def handler(request):
        return httpx.Response(200, text=html)

    entry = _entry(method="pdf", url="https://gemeinde.test/blaetter/")
    result = await _check(handler, entry)
    assert result["ok"] and result["method"] == "pdf" and result["item_count"] == 1


async def test_pdf_entry_is_not_live_with_no_pdf_links():
    async def handler(request):
        return httpx.Response(200, text="<html><body><a href='/impressum.html'>Impressum</a></body></html>")

    entry = _entry(method="pdf", url="https://gemeinde.test/blaetter/")
    result = await _check(handler, entry)
    assert not result["ok"]


async def test_diff_and_pdf_entries_never_run_homepage_feed_autodiscovery():
    # Wrong: fall through to the rss/page autodiscovery loop on failure, so a
    # WordPress site's homepage feed (advertised on every page) gets attached to a
    # diff or pdf entry meant to watch one specific page.
    async def handler(request):
        url = str(request.url)
        if url == "https://gemeinde.test/rat/":
            return httpx.Response(200, text="<html><body><p>Zu kurz.</p></body></html>")
        # A homepage that DOES carry a discoverable feed — must never be reached.
        return httpx.Response(
            200,
            text='<html><head><link rel="alternate" type="application/rss+xml" href="/feed.xml"></head></html>',
        )

    entry = _entry(method="diff", url="https://gemeinde.test/rat/", homepage="https://gemeinde.test/")
    result = await _check(handler, entry)
    assert not result["ok"]
    assert all(t[0] != "autodiscover" for t in result["tried"])


async def test_rss_and_page_autodiscovery_tries_the_entrys_own_url_before_the_homepage():
    # Wrong: try homepage first, so a homepage that happens to carry a (wrong, more
    # general) feed shadows the feed actually advertised on the entry's own page.
    async def handler(request):
        url = str(request.url)
        if url == "https://gemeinde.test/presse/":
            return httpx.Response(
                200,
                text='<html><head><link rel="alternate" type="application/rss+xml" href="/own-feed.xml"></head></html>',
            )
        if url == "https://gemeinde.test/own-feed.xml":
            return httpx.Response(200, headers={"content-type": "application/rss+xml"}, content=_rss("own"))
        if url == "https://gemeinde.test/":
            return httpx.Response(
                200,
                text='<html><head><link rel="alternate" type="application/rss+xml" href="/homepage-feed.xml"></head></html>',
            )
        if url == "https://gemeinde.test/homepage-feed.xml":
            return httpx.Response(200, headers={"content-type": "application/rss+xml"}, content=_rss("home"))
        return httpx.Response(404)

    entry = _entry(method="page", url="https://gemeinde.test/presse/", homepage="https://gemeinde.test/")
    result = await _check(handler, entry)
    assert result["ok"] and result["resolved_url"] == "https://gemeinde.test/own-feed.xml"


async def test_page_entry_still_honours_item_selector_when_no_feed_is_found():
    # Regression guard: the new query/diff/pdf branches must not disturb the
    # existing page path, which the StMFH-style sources rely on for non-standard
    # markup the generic extractor misses.
    html = (
        '<html><body><div class="col-sm-10"><a href="/a.html">Schlüsselzuweisung A</a></div>'
        '<div class="col-sm-10"><a href="/b.html">Schlüsselzuweisung B</a></div>'
        '<div class="col-sm-10"><a href="/c.html">Schlüsselzuweisung C</a></div></body></html>'
    )

    async def handler(request):
        return httpx.Response(200, text=html)

    entry = _entry(method="page", url="https://stmfh.test/foerderung/", item_selector="div.col-sm-10 a")
    result = await _check(handler, entry)
    assert result["ok"] and result["method"] == "page" and result["item_count"] == 3
