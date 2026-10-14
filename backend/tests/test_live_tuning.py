"""Tuning from the first live run (2026-10-15): the extraction cap must spend its slots on
core and local sources first, and list pages must not turn image credits or navigation
links into items."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from mhs.collect.page import extract_items
from mhs.db.models import FeedItem, Source
from mhs.extract.run import extract_pending


async def test_cap_spends_slots_on_core_local_sources_before_thematic_national(db_session):
    core = Source(slug="waakirchen-news", name="Waakirchen", layer="gemeinden", authority="high", scope="gemeinde",
                  method="page", url="https://w.test/", priority="core", collect=True)
    far = Source(slug="thuenen", name="Thünen", layer="medien", authority="medium", scope="bund",
                 method="page", url="https://t.test/", priority="thematic", collect=True)
    db_session.add_all([core, far])
    await db_session.flush()
    now = datetime.now(timezone.utc)
    # The national items are undated (list page) and therefore look "newest" by arrival.
    for i in range(3):
        db_session.add(FeedItem(source_id=far.id, external_id=f"f{i}", title=f"Hummel-Challenge {i} startet bundesweit",
                                url=f"https://t.test/{i}", canonical_url=f"https://t.test/{i}", content_hash=f"hf{i}"))
    for i in range(2):
        db_session.add(FeedItem(source_id=core.id, external_id=f"c{i}", title=f"Gemeinderat beschließt Haushalt {i}",
                                url=f"https://w.test/{i}", canonical_url=f"https://w.test/{i}", content_hash=f"hc{i}",
                                published_at=now - timedelta(days=3)))
    await db_session.commit()

    await extract_pending(db_session, limit=2)

    done = (await db_session.execute(select(FeedItem).where(FeedItem.processed.is_(True)))).scalars().all()
    assert {i.source_id for i in done} == {core.id}


def test_list_page_drops_image_credits_and_navigation_links():
    html = b"""<html><body><main><ul>
      <li><a href="/a">Gemeinderat beschliesst neuen Haushalt fuer 2027</a></li>
      <li><a href="/b">\xc2\xa9 Caritas Fulda/Ann-Katrin Jehn</a></li>
      <li><a href="/c">Mehr Inhalte anzeigen</a></li>
      <li><a href="/d">DZA-Newsletter abonnieren</a></li>
      <li><a href="/e">zu unserer digitalen Bibliothek</a></li>
      <li><a href="/f">Pflegestuetzpunkt erweitert Sprechzeiten im Oberland</a></li>
    </ul></main></body></html>"""
    titles = [i.title for i in extract_items(html, "https://x.test/list")]
    assert titles == ["Gemeinderat beschliesst neuen Haushalt fuer 2027", "Pflegestuetzpunkt erweitert Sprechzeiten im Oberland"]
