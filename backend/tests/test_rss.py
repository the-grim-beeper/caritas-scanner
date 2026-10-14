from pathlib import Path

from mhs.collect.rss import parse_feed

FEED_A = (Path(__file__).parent / "fixtures" / "feed_a.xml").read_bytes()


def test_parse_feed_uses_guid_as_external_id_and_canonicalises_link():
    # Wrong: use the link (with utm params) as the id, so the same story re-ingests
    # every time the publisher rotates the tracking parameter.
    items = parse_feed(FEED_A, "https://www.mannheimer-morgen.de/feed/56.xml")
    assert len(items) == 2
    first = items[0]
    assert first.external_id == "arid-123456"
    assert first.canonical_url == "https://www.mannheimer-morgen.de/wirtschaft/basf-investition-ludwigshafen_arid-123456.html"
    assert first.published_at is not None and first.published_at.tzinfo is not None
    assert first.published_at.utcoffset().total_seconds() == 0  # stored as UTC instant


def test_parse_feed_falls_back_to_canonical_link_when_no_guid():
    items = parse_feed(FEED_A, "https://www.mannheimer-morgen.de/feed/56.xml")
    assert items[1].external_id == items[1].canonical_url
