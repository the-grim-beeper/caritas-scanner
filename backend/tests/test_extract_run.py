"""extract_pending: items become signals (or are discarded), with topics,
entities, events and relation candidates written."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select

from mhs.db.models import Entity, Event, FeedItem, RelationCandidate, Signal, SignalEntity, SignalTopic, Source
from mhs.entities import load_seed
from mhs.extract.run import extract_pending
from scripts.load_sources import upsert_entities

DATA = Path(__file__).resolve().parents[2] / "data"


def _source(layer="landkreis", method="rss"):
    return Source(slug="s", name="s", layer=layer, authority="high", scope="landkreis", method=method,
                  url="https://s.test/f", collect=True)


async def _setup(db_session, title, summary, layer="landkreis"):
    await upsert_entities(db_session, load_seed(DATA / "entities.yaml"))
    src = _source(layer)
    db_session.add(src)
    await db_session.flush()
    item = FeedItem(source_id=src.id, external_id="1", title=title, summary=summary,
                    url="https://s.test/1", canonical_url="https://s.test/1", content_hash="h")
    db_session.add(item)
    await db_session.commit()
    return src, item


async def test_signal_item_writes_signal_topics_entities_and_events(db_session):
    src, item = await _setup(db_session,
        "Sozialbeirat tagt am 12.11.2026 im Landratsamt Miesbach — Anmeldeschluss 30.10.2026",
        "Thema ist die Koordination der Pflege im Landkreis Miesbach.")
    stats = await extract_pending(db_session)
    assert stats.processed == 1 and stats.signals == 1
    sig = (await db_session.execute(select(Signal))).scalar_one()
    assert sig.source_id == src.id and sig.authority == 1.0 and sig.consequence > 0
    topics = {t.topic_code for t in (await db_session.execute(select(SignalTopic))).scalars()}
    assert {"koordination", "pflege"} <= topics
    linked = set((await db_session.execute(
        select(Entity.slug).join(SignalEntity, SignalEntity.entity_id == Entity.id))).scalars())
    assert {"sozialbeirat", "landratsamt-miesbach", "landkreis-miesbach"} <= linked
    ev = (await db_session.execute(select(Event))).scalar_one()
    assert str(ev.deadline) == "2026-10-30" and str(ev.start_date) == "2026-11-12"
    assert ev.origin == "signal" and ev.kind == "event" and ev.signal_id == sig.id
    await db_session.refresh(item)
    assert item.processed and not item.discarded


async def test_deadline_only_event_is_stored_as_kind_deadline(db_session):
    # Wrong: every extracted event is kind "event", so the calendar shows a call as a meeting.
    await _setup(db_session, "Förderaufruf PflegesoNah: Antragsfrist endet am 31.10.2026",
                 "Gemeinden im Landkreis Miesbach können Zuschüsse beantragen.")
    await extract_pending(db_session)
    ev = (await db_session.execute(select(Event))).scalar_one()
    assert ev.kind == "deadline" and ev.start_date is None and str(ev.deadline) == "2026-10-31"


async def test_non_signal_item_is_discarded_not_left_unprocessed(db_session):
    # Wrong: leaving non-signals processed=False so they are re-extracted every cycle.
    src, item = await _setup(db_session, "TSV Hausham: Derby am Sonntag", "Fußball in der Kreisliga.", layer="medien")
    stats = await extract_pending(db_session)
    assert stats.processed == 1 and stats.signals == 0 and stats.discarded == 1
    await db_session.refresh(item)
    assert item.processed and item.discarded
    assert (await db_session.execute(select(Signal))).first() is None


def _live_payload(**over):
    payload = {
        "is_signal": True,
        "headline_en": "Youth welfare committee extends outreach contract",
        "headline_de": "Jugendhilfeausschuss verlängert Vertrag für Streetwork",
        "summary_en": "The committee extended the contract.", "summary_de": "Der Ausschuss verlängerte den Vertrag.",
        "signal_type": "decision", "topics": ["jugend-familie", "vereinbarungen"],
        "places": ["Landkreis Miesbach"], "organisations": ["Jugendamt", "Diakonie Rosenheim"],
        "forums": ["Jugendhilfeausschuss"], "programmes": [], "offices": ["Jugendamtsleitung"],
        "regional_relevance": 1.0, "consequence": 0.65, "forward_lag": 0.6, "events": [],
        "relations": [{"a": "Jugendamt", "b": "Diakonie Rosenheim", "relation": "commissioning",
                       "quote": "im Auftrag des Jugendamts"}],
    }
    payload.update(over)
    return payload


async def _run_live(db_session, monkeypatch, payload):
    from mhs import config
    from mhs.extract import run as extract_run
    from mhs.extract.schema import from_payload

    monkeypatch.setattr(config.settings, "anthropic_api_key", "sk-test")

    async def fake_live(item, source):
        return from_payload(payload)

    monkeypatch.setattr(extract_run, "_extract_live", fake_live)
    await _setup(db_session, "Jugendhilfeausschuss tagt", "Streetwork im Auftrag des Jugendamts.")
    return await extract_pending(db_session)


async def test_live_payload_writes_consequence_forum_link_office_and_relation_candidate(db_session, monkeypatch):
    # Wrong: relations dropped on the floor, forums/offices never resolved, or the old
    # economic_materiality field read instead of consequence.
    stats = await _run_live(db_session, monkeypatch, _live_payload())
    assert stats.signals == 1
    sig = (await db_session.execute(select(Signal))).scalar_one()
    assert sig.consequence == 0.65
    cands = (await db_session.execute(select(RelationCandidate))).scalars().all()
    assert [(c.a_text, c.b_text, c.relation, c.quote, c.signal_id, c.processed) for c in cands] == [
        ("Jugendamt", "Diakonie Rosenheim", "commissioning", "im Auftrag des Jugendamts", sig.id, False)]
    linked = {(e.slug, e.kind) for e in (await db_session.execute(
        select(Entity).join(SignalEntity, SignalEntity.entity_id == Entity.id))).scalars()}
    assert ("jugendhilfeausschuss", "forum") in linked
    assert ("jugendamtsleitung-miesbach", "office") in linked
    assert ("diakonie-rosenheim", "organisation") in linked


async def test_live_payload_with_unknown_relation_writes_no_candidate(db_session, monkeypatch):
    bad = _live_payload(relations=[{"a": "Jugendamt", "b": "Diakonie Rosenheim", "relation": "likes",
                                    "quote": "im Auftrag des Jugendamts"}])
    stats = await _run_live(db_session, monkeypatch, bad)
    assert stats.signals == 1
    assert (await db_session.execute(select(RelationCandidate))).first() is None


async def test_extraction_cap_does_not_starve_undated_page_items(db_session):
    # Wrong: ORDER BY published_at DESC NULLS LAST — list-page items have no date, so
    # under the per-cycle cap they are never extracted while any dated RSS item exists.
    await upsert_entities(db_session, load_seed(DATA / "entities.yaml"))
    src = _source(method="page")
    db_session.add(src)
    await db_session.flush()
    old = datetime.now(timezone.utc) - timedelta(days=20)
    db_session.add(FeedItem(source_id=src.id, external_id="rss-old", title="Kreistag beschließt Haushalt 2027",
                            url="https://s.test/a", canonical_url="https://s.test/a", content_hash="a", published_at=old,
                            created_at=old))
    db_session.add(FeedItem(source_id=src.id, external_id="page-new", title="Pflegestützpunkt verkürzt Öffnungszeiten",
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
    src = _source()
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
    src = _source()
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
    await upsert_entities(db_session, load_seed(DATA / "entities.yaml"))
    src = _source()
    db_session.add(src)
    await db_session.flush()
    db_session.add(FeedItem(source_id=src.id, external_id="1", title="Kreistag beschließt höhere Kreisumlage",
                            url="https://s.test/1", canonical_url="https://s.test/1", content_hash="1"))
    db_session.add(FeedItem(source_id=src.id, external_id="2", title="Pflegestützpunkt verkürzt Öffnungszeiten",
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


# --- item date (first live run: municipal list pages carry their archive) -----------------

def test_from_payload_reads_item_date():
    from datetime import date
    from mhs.extract.schema import from_payload
    assert from_payload(_live_payload(item_date="2023-12-10")).item_date == date(2023, 12, 10)
    assert from_payload(_live_payload(item_date=None)).item_date is None
    assert from_payload(_live_payload(item_date="Dezember")).item_date is None


async def test_undated_item_whose_own_date_is_old_is_archive_not_signal(db_session, monkeypatch):
    stats = await _run_live(db_session, monkeypatch, _live_payload(item_date="2023-12-10"))
    assert stats.signals == 0 and stats.discarded == 1
    assert (await db_session.execute(select(Signal))).first() is None
    item = (await db_session.execute(select(FeedItem))).scalar_one()
    assert item.processed and item.discarded


async def test_undated_item_with_a_recent_own_date_becomes_a_signal_dated_by_it(db_session, monkeypatch):
    from datetime import date, timedelta
    recent = date.today() - timedelta(days=5)
    stats = await _run_live(db_session, monkeypatch, _live_payload(item_date=recent.isoformat()))
    assert stats.signals == 1
    sig = (await db_session.execute(select(Signal))).scalar_one()
    assert sig.published_at.date() == recent
