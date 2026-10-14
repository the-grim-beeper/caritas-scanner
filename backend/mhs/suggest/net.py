"""Guarded fetching of model-proposed URLs (port of Sandglass tending's _is_public_host/_fetch).

The scout's URLs come from a web-searching model and are prompt-injectable through any page it
reads, so they are untrusted input to an HTTP client running next to the database:
- http/https only;
- public hosts only: literal private/loopback/link-local/reserved addresses, "localhost",
  .local/.internal names and single-label intranet names are refused without DNS; other names
  are resolved and refused if ANY address is not global;
- the check runs before the first request and before every redirect hop (redirects are
  followed by hand, so a private target is never requested — Sandglass checked only the
  final URL, after the fact);
- the body is read in a stream and abandoned past max_bytes, Content-Length or not.

Not covered (as in Sandglass): DNS rebinding between this check and httpx's own lookup.
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import urljoin, urlsplit

import httpx

from mhs.config import settings

log = logging.getLogger(__name__)

MAX_BYTES = 3_000_000
TIMEOUT_SECONDS = 12.0
MAX_REDIRECTS = 5
HEADERS = {
    "User-Agent": settings.user_agent,
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/html;q=0.9, */*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.7",
}
_LOCAL_SUFFIXES = (".localhost", ".local", ".internal", ".lan", ".home.arpa", ".intranet")
# Headers describing the wire encoding of a body we have already decoded and re-wrapped.
_WIRE_HEADERS = {"content-encoding", "content-length", "transfer-encoding"}


def _resolve(host: str) -> list[str]:
    """Every address the name resolves to. Module-level so tests can replace it."""
    return [info[4][0] for info in socket.getaddrinfo(host, None)]


def _ip_is_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    # is_global excludes private, loopback, link-local, reserved, unspecified and shared
    # (100.64/10) space; multicast is global by that definition but never a web server.
    return ip.is_global and not ip.is_multicast


def is_public_host(host: str) -> bool:
    if not host:
        return False
    host = host.strip().lower().rstrip(".").strip("[]")
    if not host or host == "localhost" or host.endswith(_LOCAL_SUFFIXES):
        return False
    try:
        return _ip_is_public(ipaddress.ip_address(host.split("%", 1)[0]))
    except ValueError:
        pass  # a name, not a literal address
    if "." not in host:
        return False  # single-label names ("intranet") only resolve inside a network
    try:
        addresses = _resolve(host)
    except (OSError, UnicodeError):
        return False
    if not addresses:
        return False
    try:
        return all(_ip_is_public(ipaddress.ip_address(a.split("%", 1)[0])) for a in addresses)
    except ValueError:
        return False


async def fetch_checked(
    http: httpx.AsyncClient, url: str, max_bytes: int = MAX_BYTES
) -> tuple[httpx.Response | None, str | None]:
    """(response, None) for any final non-redirect status — the caller judges the status — or
    (None, reason) when the URL is refused or unreachable. Reasons are German (shown in the UI)."""
    current = url
    for _hop in range(MAX_REDIRECTS + 1):
        try:
            parts = urlsplit(current)
        except ValueError:
            return None, "ungültige URL"
        if parts.scheme not in ("http", "https"):
            return None, f"nur http/https erlaubt ({parts.scheme or 'ohne Schema'})"
        host = parts.hostname or ""
        if not await asyncio.to_thread(is_public_host, host):
            return None, f"kein öffentlicher Host: {host or current}"
        try:
            async with http.stream("GET", current, headers=HEADERS, timeout=TIMEOUT_SECONDS,
                                   follow_redirects=False) as r:
                if r.is_redirect:
                    current = urljoin(current, r.headers["location"])
                    continue
                declared = r.headers.get("content-length")
                if declared and declared.isdigit() and int(declared) > max_bytes:
                    return None, f"Antwort größer als {max_bytes // 1_000_000} MB"
                body = bytearray()
                async for chunk in r.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > max_bytes:
                        return None, f"Antwort größer als {max_bytes // 1_000_000} MB"
                headers = [(k, v) for k, v in r.headers.multi_items() if k.lower() not in _WIRE_HEADERS]
                return httpx.Response(r.status_code, headers=headers, content=bytes(body), request=r.request), None
        except httpx.InvalidURL:
            return None, "ungültige URL"
        except httpx.HTTPError as exc:
            log.debug("suggest fetch failed for %s: %s", current, exc)
            return None, f"nicht erreichbar ({type(exc).__name__})"
    return None, f"mehr als {MAX_REDIRECTS} Weiterleitungen"


async def fetch(http: httpx.AsyncClient, url: str, max_bytes: int = MAX_BYTES) -> httpx.Response | None:
    response, _reason = await fetch_checked(http, url, max_bytes)
    return response


@asynccontextmanager
async def maybe_client(http: httpx.AsyncClient | None) -> AsyncIterator[httpx.AsyncClient]:
    """The caller's client, or a fresh one closed afterwards."""
    if http is not None:
        yield http
        return
    async with httpx.AsyncClient(headers=HEADERS, timeout=TIMEOUT_SECONDS) as client:
        yield client
