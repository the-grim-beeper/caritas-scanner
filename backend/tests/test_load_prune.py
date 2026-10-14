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


async def test_prune_keeps_adopted_suggestion_sources(db_session):
    # An adopted suggestion is in no catalogue and may not have collected yet; reloading the
    # catalogue must not undo the adoption. Wrong: pruning on "not in catalogue, no items" alone.
    adopted = Source(slug="vorschlag-gemeinde-weyarn", name="Gemeinde Weyarn", layer="gemeinden", authority="medium",
                     scope="gemeinde", method="page", url="https://weyarn.test/aktuelles", origin="suggestion",
                     collect=True)
    stale = Source(slug="alt", name="Alt", layer="gemeinden", authority="high", scope="gemeinde", method="rss",
                   url="https://alt.test/rss")
    db_session.add_all([adopted, stale])
    await db_session.commit()

    removed = await prune_sources(db_session, keep_slugs=set())

    slugs = {s.slug for s in (await db_session.execute(select(Source))).scalars()}
    assert removed == 1
    assert slugs == {"vorschlag-gemeinde-weyarn"}


async def test_catalogue_sources_default_to_origin_catalogue(db_session):
    src = Source(slug="lk", name="LK", layer="landkreis", authority="high", scope="landkreis", method="rss")
    db_session.add(src)
    await db_session.commit()
    assert src.origin == "catalogue"
