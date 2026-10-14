"""The loader removes catalogue rows that left the catalogue — but never a source that
has collected something (a dead feed with history is coverage evidence)."""
from sqlalchemy import select

from mhs.db.models import FeedItem, Source
from scripts.load_sources import prune_sources


async def test_stale_source_without_items_is_removed_and_one_with_items_is_kept(db_session):
    stale = Source(slug="mannheim-presse", name="Stadt Mannheim", layer="gemeinden", authority="high",
                   scope="gemeinde", method="rss", url="https://mannheim.test/rss")
    with_history = Source(slug="old-but-used", name="Old", layer="medien", authority="medium",
                          scope="landkreis", method="rss", url="https://old.test/rss")
    current = Source(slug="lk-presse", name="Landkreis Presse", layer="landkreis", authority="high",
                     scope="landkreis", method="rss", url="https://lk.test/rss")
    db_session.add_all([stale, with_history, current])
    await db_session.flush()
    db_session.add(FeedItem(source_id=with_history.id, external_id="1", title="t", url="https://old.test/1",
                            canonical_url="https://old.test/1", content_hash="h"))
    await db_session.commit()

    removed = await prune_sources(db_session, keep_slugs={"lk-presse"})

    slugs = {s.slug for s in (await db_session.execute(select(Source))).scalars()}
    assert removed == 1
    assert slugs == {"lk-presse", "old-but-used"}
