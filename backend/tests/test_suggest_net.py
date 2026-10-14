"""The fetch guard for model-proposed URLs (port of Sandglass tending's _is_public_host/_fetch).

A web-searching model chooses these URLs, so they are untrusted: only http/https, only public
hosts — checked before the first request AND before every redirect hop — and a size cap that
holds even when the server sends no Content-Length."""
import httpx
import pytest
import respx

from mhs.suggest import net
from mhs.suggest.net import fetch, is_public_host

PUBLIC_IP = "93.184.216.34"


def _no_dns(host):
    raise AssertionError(f"DNS lookup attempted for {host!r}")


@pytest.fixture
def public_dns(monkeypatch):
    monkeypatch.setattr(net, "_resolve", lambda host: [PUBLIC_IP])


def test_private_and_local_hosts_are_not_public(monkeypatch):
    # Literal addresses and local names are decided without touching DNS.
    monkeypatch.setattr(net, "_resolve", _no_dns)
    for h in ["localhost", "127.0.0.1", "10.0.0.5", "192.168.1.1", "169.254.169.254", "intranet",
              "::1", "foo.localhost", "svc.internal", "printer.local", "100.64.0.1", "0.0.0.0",
              "::ffff:127.0.0.1", "", "LOCALHOST."]:
        assert not is_public_host(h), h


def test_a_name_that_resolves_to_a_private_address_is_not_public(monkeypatch):
    # Wrong: a literal-only check (Sandglass's) passes any hostname.
    monkeypatch.setattr(net, "_resolve", lambda host: ["10.1.2.3"])
    assert not is_public_host("rebind.example")
    # One private address among public ones is enough to refuse.
    monkeypatch.setattr(net, "_resolve", lambda host: [PUBLIC_IP, "127.0.0.1"])
    assert not is_public_host("mixed.example")


def test_a_public_name_is_public_and_an_unresolvable_one_is_not(monkeypatch):
    monkeypatch.setattr(net, "_resolve", lambda host: [PUBLIC_IP])
    assert is_public_host("www.weyarn.de")

    def nxdomain(host):
        raise OSError("nodename nor servname provided")

    monkeypatch.setattr(net, "_resolve", nxdomain)
    assert not is_public_host("gibtsnicht.example")


@respx.mock
async def test_non_http_schemes_are_refused_without_a_request(public_dns):
    async with httpx.AsyncClient() as http:
        assert await fetch(http, "file:///etc/passwd") is None
        assert await fetch(http, "ftp://a.test/x") is None
        assert await fetch(http, "javascript:alert(1)") is None


@respx.mock
async def test_private_target_is_refused_without_a_request():
    route = respx.get("http://169.254.169.254/latest/meta-data")
    async with httpx.AsyncClient() as http:
        assert await fetch(http, "http://169.254.169.254/latest/meta-data") is None
    assert not route.called


@respx.mock
async def test_redirect_to_a_private_address_is_never_requested(public_dns):
    # Wrong: follow_redirects=True and check the final host afterwards — the private
    # target has then already been requested (Sandglass's original order).
    respx.get("https://public.test/feed").respond(302, headers={"Location": "http://127.0.0.1/admin"})
    inner = respx.get("http://127.0.0.1/admin").respond(200, content=b"secret")
    async with httpx.AsyncClient() as http:
        assert await fetch(http, "https://public.test/feed") is None
    assert not inner.called


@respx.mock
async def test_redirect_to_a_public_host_is_followed(public_dns):
    respx.get("https://a.test/alt").respond(301, headers={"Location": "/neu"})
    respx.get("https://a.test/neu").respond(200, content=b"ok")
    async with httpx.AsyncClient() as http:
        r = await fetch(http, "https://a.test/alt")
    assert r is not None and r.status_code == 200 and r.content == b"ok"
    assert str(r.url) == "https://a.test/neu"


@respx.mock
async def test_redirect_loop_gives_up(public_dns):
    respx.get("https://loop.test/a").respond(302, headers={"Location": "https://loop.test/a"})
    async with httpx.AsyncClient() as http:
        assert await fetch(http, "https://loop.test/a") is None


@respx.mock
async def test_size_cap_holds_with_and_without_content_length(public_dns):
    respx.get("https://big.test/x").respond(200, content=b"x" * 2001)
    respx.get("https://fits.test/x").respond(200, content=b"x" * 2000)
    # No Content-Length header: the cap must be enforced while reading, not only from the header.
    respx.get("https://chunked.test/x").mock(
        return_value=httpx.Response(200, stream=httpx.ByteStream(b"y" * 5000)))
    async with httpx.AsyncClient() as http:
        assert await fetch(http, "https://big.test/x", max_bytes=2000) is None
        assert await fetch(http, "https://chunked.test/x", max_bytes=2000) is None
        fits = await fetch(http, "https://fits.test/x", max_bytes=2000)
    assert fits is not None and fits.content == b"x" * 2000


@respx.mock
async def test_error_status_is_returned_for_the_caller_to_report(public_dns):
    respx.get("https://gone.test/x").respond(404)
    async with httpx.AsyncClient() as http:
        r = await fetch(http, "https://gone.test/x")
    assert r is not None and r.status_code == 404
