"""extract_pending: items become signals (or are discarded), with topics,
entities and events written."""
from pathlib import Path

from sqlalchemy import select

from mhs.db.models import Event, FeedItem, Signal, SignalEntity, SignalTopic, Source
from mhs.entities import load_seed
from mhs.extract.run import extract_pending

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


async def test_extraction_cap_does_not_starve_undated_page_items(db_session):
    # Wrong: ORDER BY published_at DESC NULLS LAST — list-page items have no date, so
    # under the per-cycle cap they are never extracted while any dated RSS item exists.
    from datetime import datetime, timedelta, timezone
    from scripts.load_sources import upsert_entities
    await upsert_entities(db_session, load_seed(DATA / "entities.yaml"))
    src = Source(slug="s", name="s", layer="policy", authority="high", scope="region", method="page",
                 url="https://s.test/f", collect=True)
    db_session.add(src)
    await db_session.flush()
    old = datetime.now(timezone.utc) - timedelta(days=20)
    db_session.add(FeedItem(source_id=src.id, external_id="rss-old", title="BASF investiert 100 Millionen in Ludwigshafen",
                            url="https://s.test/a", canonical_url="https://s.test/a", content_hash="a", published_at=old,
                            created_at=old))
    db_session.add(FeedItem(source_id=src.id, external_id="page-new", title="Kreistag beschließt Förderprogramm Glasfaser",
                            url="https://s.test/b", canonical_url="https://s.test/b", content_hash="b", published_at=None))
    await db_session.commit()
    stats = await extract_pending(db_session, limit=1)
    assert stats.processed == 1
    done = (await db_session.execute(select(FeedItem).where(FeedItem.processed.is_(True)))).scalar_one()
    assert done.external_id == "page-new"


async def test_auth_error_aborts_the_batch_instead_of_calling_per_item(db_session, monkeypatch):
    # Wrong: catching the 401 per item and carrying on, so a dead key costs a request
    # per feed item and the cycle "completes" with zero signals.
    from mhs import config
    from mhs.extract import run as extract_run
    from mhs.llm.client import LLMAuthError

    monkeypatch.setattr(config.settings, "anthropic_api_key", "sk-dead")
    monkeypatch.setattr(config.settings, "extraction_concurrency", 2)
    src = Source(slug="s", name="s", layer="policy", authority="high", scope="region", method="rss",
                 url="https://s.test/f", collect=True)
    db_session.add(src)
    await db_session.flush()
    for i in range(20):
        db_session.add(FeedItem(source_id=src.id, external_id=str(i), title=f"Meldung {i}", url=f"https://s.test/{i}",
                                canonical_url=f"https://s.test/{i}", content_hash=str(i)))
    await db_session.commit()

    calls = 0

    async def dead(item, source):
        nonlocal calls
        calls += 1
        raise LLMAuthError("API key is invalid")

    monkeypatch.setattr(extract_run, "_extract_live", dead)
    stats = await extract_pending(db_session)
    assert stats.processed == 0 and stats.failed == 20
    assert calls <= 2
    assert stats.aborted == "LLMAuthError: API key is invalid"
    unprocessed = (await db_session.execute(select(FeedItem).where(FeedItem.processed.is_(False)))).scalars().all()
    assert len(unprocessed) == 20  # nothing marked processed; the next cycle retries


async def test_bad_request_aborts_the_batch_too(db_session, monkeypatch):
    # A 400 (e.g. an unsupported schema keyword) is a bug in our request, identical on
    # every item — one failure per item would burn the whole batch for nothing.
    from mhs import config
    from mhs.extract import run as extract_run
    from mhs.llm.client import LLMRequestError

    monkeypatch.setattr(config.settings, "anthropic_api_key", "sk-x")
    monkeypatch.setattr(config.settings, "extraction_concurrency", 1)
    src = Source(slug="s", name="s", layer="policy", authority="high", scope="region", method="rss",
                 url="https://s.test/f", collect=True)
    db_session.add(src)
    await db_session.flush()
    for i in range(5):
        db_session.add(FeedItem(source_id=src.id, external_id=str(i), title=f"Meldung {i}", url=f"https://s.test/{i}",
                                canonical_url=f"https://s.test/{i}", content_hash=str(i)))
    await db_session.commit()
    calls = 0

    async def bad(item, source):
        nonlocal calls
        calls += 1
        raise LLMRequestError("output_config.format.schema: minimum not supported")

    monkeypatch.setattr(extract_run, "_extract_live", bad)
    stats = await extract_pending(db_session)
    assert calls == 1 and stats.failed == 5 and stats.aborted.startswith("LLMRequestError")


async def test_one_items_persist_failure_does_not_lose_the_batch(db_session, monkeypatch):
    # Wrong: an exception while writing one signal rolls back every extraction in the
    # cycle — 400 paid model calls gone.
    from mhs.extract import run as extract_run
    from scripts.load_sources import upsert_entities
    await upsert_entities(db_session, load_seed(DATA / "entities.yaml"))
    src = Source(slug="s", name="s", layer="corporate", authority="high", scope="region", method="rss",
                 url="https://s.test/f", collect=True)
    db_session.add(src)
    await db_session.flush()
    db_session.add(FeedItem(source_id=src.id, external_id="1", title="BASF investiert 100 Millionen in Ludwigshafen",
                            url="https://s.test/1", canonical_url="https://s.test/1", content_hash="1"))
    db_session.add(FeedItem(source_id=src.id, external_id="2", title="SAP investiert 50 Millionen in Walldorf",
                            url="https://s.test/2", canonical_url="https://s.test/2", content_hash="2"))
    await db_session.commit()

    real = extract_run._persist
    calls = {"n": 0}

    async def flaky(session, item, source, result):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("simulated unique violation")
        return await real(session, item, source, result)

    monkeypatch.setattr(extract_run, "_persist", flaky)
    stats = await extract_pending(db_session)
    assert stats.signals == 1 and stats.failed == 1
    saved = (await db_session.execute(select(Signal))).scalars().all()
    assert len(saved) == 1
    unprocessed = (await db_session.execute(select(FeedItem).where(FeedItem.processed.is_(False)))).scalars().all()
    assert len(unprocessed) == 1  # the failed item is retried next cycle
