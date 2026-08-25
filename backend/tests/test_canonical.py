"""Canonical URLs: the dedup key. Each test names the wrong implementation it defends against."""
from rns.collect.canonical import canonical_url, content_hash


def test_strips_tracking_params_but_keeps_real_query():
    # Wrong: strip *every* query string, which would merge ?id=42 and ?id=43.
    assert (
        canonical_url("HTTPS://WWW.Example.de/Pfad/Seite?id=42&utm_source=x&fbclid=abc#top")
        == "https://www.example.de/Pfad/Seite?id=42"
    )


def test_host_lowercased_but_path_case_preserved():
    # Wrong: lowercase the whole URL; many CMS paths are case-sensitive.
    assert canonical_url("https://Heidelberg.DE/HD/Aktuelles.html") == "https://heidelberg.de/HD/Aktuelles.html"


def test_trailing_slash_and_default_port_normalised():
    assert canonical_url("https://www.mrn-news.de:443/2026/08/24/x-650793/") == canonical_url(
        "https://www.mrn-news.de/2026/08/24/x-650793"
    )


def test_content_hash_is_stable_under_whitespace_and_case_of_summary():
    a = content_hash("Titel", "Der  Text\n hier")
    b = content_hash("Titel", "der text hier")
    assert a == b
    assert content_hash("Anderer Titel", "der text hier") != a
