"""API: auth gate, filters, score decomposition, deadlines vs dates, coverage honesty."""
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest
from httpx import ASGITransport

from rns.config import settings
from rns.db.engine import get_session
from rns.db.models import (
    Cycle, Digest, Entity, Event, Signal, SignalEntity, SignalTopic, Source, Story, TrendCell, utcnow,
)


@pytest.fixture
async def seeded(db_session):
    fund = Source(slug="foerderdatenbank", name="Förderdatenbank", layer="funding", authority="high",
                  scope="national", method="rss", url="https://f.test/rss", collect=True)
    pol = Source(slug="mannheim-presse", name="Stadt Mannheim", layer="policy", authority="high",
                 scope="city", method="rss", url="https://m.test/rss", collect=True)
    nl = Source(slug="biorn-newsletter", name="BioRN newsletter", layer="innovation", authority="high",
                scope="region", method="newsletter", collect=False,
                not_collected_reason="newsletter sources are catalogued, not collected (v1)")
    db_session.add_all([fund, pol, nl])
    await db_session.flush()
    ent = Entity(slug="patrick-henry-village", kind="project", name="Patrick-Henry-Village", aliases=["PHV"], seeded=True)
    db_session.add(ent)
    await db_session.flush()
    now = utcnow()
    s1 = Signal(source_id=fund.id, headline_en="New EU call", headline_de="Neuer EU-Aufruf", signal_type="funding_call",
                authority=1.0, regional_relevance=0.6, novelty=1.0, economic_materiality=0.7, forward_lag=1.0,
                score=0.42, published_at=now, is_founder=True)
    s2 = Signal(source_id=pol.id, headline_en="PHV plan approved", headline_de="PHV-Plan beschlossen", signal_type="decision",
                authority=1.0, regional_relevance=1.0, novelty=0.8, economic_materiality=0.8, forward_lag=0.6,
                score=0.384, published_at=now - timedelta(hours=2), is_founder=True)
    s3 = Signal(source_id=fund.id, headline_en="PHV plan approved (wire)", headline_de="PHV (Agentur)", signal_type="decision",
                authority=1.0, regional_relevance=1.0, novelty=0.0, economic_materiality=0.8, forward_lag=0.6,
                score=0.0, published_at=now - timedelta(hours=1), is_founder=False)
    db_session.add_all([s1, s2, s3])
    await db_session.flush()
    st1 = Story(founding_signal_id=s1.id, score=0.42, first_seen=now, last_seen=now)
    st2 = Story(founding_signal_id=s2.id, corroboration_count=1, distinct_sources=2, confidence=0.75, score=0.384,
                first_seen=now - timedelta(hours=2), last_seen=now - timedelta(hours=1))
    db_session.add_all([st1, st2])
    await db_session.flush()
    s1.story_id, s2.story_id, s3.story_id = st1.id, st2.id, st2.id
    db_session.add_all([
        SignalTopic(signal_id=s1.id, topic_code="EU-funding"),
        SignalTopic(signal_id=s2.id, topic_code="brownfield"),
        SignalEntity(signal_id=s2.id, entity_id=ent.id),
        Event(signal_id=s1.id, name="EIC Accelerator call", deadline=date.today() + timedelta(days=10)),
        Event(signal_id=s2.id, name="Council session", start_date=date.today() + timedelta(days=3)),
        TrendCell(week=date.today() - timedelta(days=date.today().weekday()), topic="EU-funding", layer="funding", count=3),
        TrendCell(week=date.today() - timedelta(days=date.today().weekday() + 35), topic="EU-funding", layer="funding", count=1),
    ])
    cyc = Cycle(mode="mock", finished_at=now, signals=2, digest_ok=True)
    db_session.add(cyc)
    await db_session.flush()
    db_session.add(Digest(cycle_id=cyc.id, lead_en="Lead EN", lead_de="Lead DE", model="mock", payload={
        "lead_en": "Lead EN", "lead_de": "Lead DE",
        "sections": [{"layer": "funding", "items": [{"signal_id": str(s1.id), "note_en": "n", "note_de": "n"}]}],
        "chains": [], "watch": []}))
    await db_session.commit()
    return {"s1": s1, "s2": s2, "s3": s3, "ent": ent}


@pytest.fixture
async def client(db_session):
    from rns.main import app

    async def _override():
        yield db_session

    app.dependency_overrides[get_session] = _override
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c
    app.dependency_overrides.clear()


async def _login(client):
    r = await client.post("/api/login", json={"password": settings.app_password})
    assert r.status_code == 200


async def test_health_is_open_but_signals_need_a_session(client):
    assert (await client.get("/api/health")).status_code == 200
    assert (await client.get("/api/signals")).status_code == 401
    r = await client.post("/api/login", json={"password": "wrong"})
    assert r.status_code == 401


async def test_signals_filter_by_layer_and_return_founders_only(client, seeded):
    # Wrong: returning corroborations as rows, or ignoring the layer filter.
    await _login(client)
    r = await client.get("/api/signals", params={"layer": "funding"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1 and body["items"][0]["headline_en"] == "New EU call"
    assert body["items"][0]["layer"] == "funding"
    r2 = await client.get("/api/signals")
    assert {i["headline_en"] for i in r2.json()["items"]} == {"New EU call", "PHV plan approved"}


async def test_signal_detail_has_five_factors_story_members_and_topics(client, seeded):
    await _login(client)
    r = await client.get(f"/api/signals/{seeded['s2'].id}")
    assert r.status_code == 200
    d = r.json()
    assert set(d["factors"]) == {"authority", "regional_relevance", "novelty", "economic_materiality", "forward_lag"}
    assert d["story"]["distinct_sources"] == 2 and d["story"]["confidence"] == 0.75
    assert len(d["story"]["members"]) == 2
    assert d["topics"] == ["brownfield"]
    assert d["entities"][0]["slug"] == "patrick-henry-village"


async def test_events_keep_deadline_and_start_separate(client, seeded):
    await _login(client)
    r = await client.get("/api/events")
    evs = {e["name"]: e for e in r.json()["items"]}
    assert evs["EIC Accelerator call"]["deadline"] and evs["EIC Accelerator call"]["start_date"] is None
    assert evs["Council session"]["start_date"] and evs["Council session"]["deadline"] is None


async def test_sources_lists_not_collected_with_reason(client, seeded):
    await _login(client)
    r = await client.get("/api/sources")
    rows = {s["slug"]: s for s in r.json()["items"]}
    assert rows["biorn-newsletter"]["collect"] is False
    assert "newsletter" in rows["biorn-newsletter"]["not_collected_reason"]
    assert rows["foerderdatenbank"]["signals_7d"] == 1


async def test_trends_and_overview_and_meta(client, seeded):
    await _login(client)
    t = (await client.get("/api/trends", params={"weeks": 12})).json()
    assert t["movers"][0]["topic"] == "EU-funding" and t["movers"][0]["delta"] == 2
    o = (await client.get("/api/overview")).json()
    assert o["latest_digest"]["lead_en"] == "Lead EN"
    assert o["top_stories"][0]["headline_en"] == "New EU call"
    assert {l["layer"] for l in o["layers"]} >= {"funding", "policy"}
    m = (await client.get("/api/meta")).json()
    assert m["mode"] == "mock" and m["languages"] == ["en", "de"]


async def test_entity_timeline(client, seeded):
    await _login(client)
    r = await client.get("/api/entities/patrick-henry-village")
    assert r.status_code == 200
    assert r.json()["kind"] == "project" and r.json()["timeline"][0]["headline_en"] == "PHV plan approved"
    lst = (await client.get("/api/entities", params={"kind": "project"})).json()["items"]
    assert lst[0]["slug"] == "patrick-henry-village" and lst[0]["count_90d"] == 1


async def test_digests_latest(client, seeded):
    await _login(client)
    r = await client.get("/api/digests/latest")
    assert r.status_code == 200
    body = r.json()
    assert body["sections"][0]["items"][0]["signal"]["headline_en"] == "New EU call"
