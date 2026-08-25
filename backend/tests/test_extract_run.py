"""extract_pending: items become signals (or are discarded), with topics,
entities and events written."""
from pathlib import Path

from sqlalchemy import select

from rns.db.models import Event, FeedItem, Signal, SignalEntity, SignalTopic, Source
from rns.entities import load_seed
from rns.extract.run import extract_pending

DATA = Path(__file__).resolve().parents[2] / "data"


async def _setup(db_session, title, summary, layer="editorial"):
    from scripts.load_sources import upsert_entities
    await upsert_entities(db_session, load_seed(DATA / "entities.yaml"))
    src = Source(slug="s", name="s", layer=layer, authority="high", scope="region", method="rss",
                 url="https://s.test/f", collect=True)
    db_session.add(src)
    await db_session.flush()
    item = FeedItem(source_id=src.id, external_id="1", title=title, summary=summary,
                    url="https://s.test/1", canonical_url="https://s.test/1", content_hash="h")
    db_session.add(item)
    await db_session.commit()
    return src, item


async def test_signal_item_writes_signal_topics_entities_and_events(db_session):
    src, item = await _setup(db_session,
        "NEXT Mannheim: Investor Roadshow am 12.10.2026 im CUBEX — Bewerbungsschluss 30.09.2026",
        "Startups aus Mannheim können sich bis zum 30.09.2026 bewerben.", layer="innovation")
    stats = await extract_pending(db_session)
    assert stats.processed == 1 and stats.signals == 1
    sig = (await db_session.execute(select(Signal))).scalar_one()
    assert sig.source_id == src.id and sig.authority == 1.0
    topics = {t.topic_code for t in (await db_session.execute(select(SignalTopic))).scalars()}
    assert "startup" in topics
    links = (await db_session.execute(select(SignalEntity))).scalars().all()
    assert links, "entities resolved"
    ev = (await db_session.execute(select(Event))).scalar_one()
    assert str(ev.deadline) == "2026-09-30" and str(ev.start_date) == "2026-10-12"
    await db_session.refresh(item)
    assert item.processed and not item.discarded


async def test_non_signal_item_is_discarded_not_left_unprocessed(db_session):
    # Wrong: leaving non-signals processed=False so they are re-extracted every cycle.
    src, item = await _setup(db_session, "Mycityhunt: Krimi-Spiel in der Heidelberger Altstadt", "")
    stats = await extract_pending(db_session)
    assert stats.processed == 1 and stats.signals == 0 and stats.discarded == 1
    await db_session.refresh(item)
    assert item.processed and item.discarded
    assert (await db_session.execute(select(Signal))).first() is None
