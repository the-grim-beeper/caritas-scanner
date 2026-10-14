"""Canonical URLs and content hashes — the two dedup keys of the brief's pipeline."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING_PREFIXES = ("utm_",)
_TRACKING_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "referrer", "source", "xtor"}
_DEFAULT_PORTS = {"http": "80", "https": "443"}
_WS = re.compile(r"\s+")


@dataclass(frozen=True)
class RawItem:
    """One collected item before any interpretation."""

    external_id: str
    title: str
    url: str
    canonical_url: str
    summary: str
    published_at: datetime | None
    content_hash: str
    # method=query: "Headline - Outlet" search results carry the outlet separately.
    outlet: str | None = None


def canonical_url(url: str) -> str:
    """Lowercase scheme and host, drop default ports, strip tracking params and
    fragments, normalise the trailing slash. Path case is preserved."""
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower() or "https"
    host = parts.hostname.lower() if parts.hostname else ""
    port = parts.port
    if port and str(port) != _DEFAULT_PORTS.get(scheme):
        host = f"{host}:{port}"
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith(_TRACKING_PREFIXES) and k.lower() not in _TRACKING_KEYS
    ]
    path = parts.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return urlunsplit((scheme, host, path, urlencode(query), ""))


def _norm_text(text: str | None) -> str:
    return _WS.sub(" ", (text or "")).strip().lower()


def content_hash(title: str | None, summary: str | None) -> str:
    return hashlib.sha256(f"{_norm_text(title)}\n{_norm_text(summary)}".encode()).hexdigest()
