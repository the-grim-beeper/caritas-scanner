"""API: auth gate, filters, score decomposition, deadlines vs dates, coverage honesty."""
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest
from httpx import ASGITransport

from mhs import vocab
from mhs.config import settings
from mhs.db.engine import get_session
from mhs.db.models import (
    Cycle, Digest, Entity, Event, Signal, SignalEntity, SignalTopic, Source, Story, TrendCell, utcnow,
)


@pytest.fixture
async def seeded(db_session):
    fund = Source(slug="lk-miesbach-presse", name="Landratsamt Miesbach", layer="landkreis", authority="high",
                  scope="landkreis", method="rss", url="https://f.test/rss", collect=True)
    pol = Source(slug="waakirchen-gemeinderat", name="Gemeinde Waakirchen", layer="gemeinden", authority="high",
                 scope="gemeinde", method="rss", url="https://m.test/rss", collect=True)
    nl = Source(slug="caritas-newsletter", name="Caritas newsletter", layer="wohlfahrt", authority="high",
                scope="bezirk", method="newsletter", collect=False,
                not_collected_reason="newsletter sources are catalogued, not collected (v1)")
    db_session.add_all([fund, pol, nl])
    await db_session.flush()
    ent = Entity(slug="sozialraumlotsen", kind="programme", name="Interkommunale Sozialraumlotsen",
                 aliases=["Sozialraumlotsen"], seeded=True, actor_kind="programme")
    db_session.add(ent)
    await db_session.flush()
    now = utcnow()
    s1 = Signal(source_id=fund.id, headline_en="New SeLA call", headline_de="Neuer SeLA-Aufruf", signal_type="funding_call",
                authority=1.0, regional_relevance=0.6, novelty=1.0, consequence=0.7, forward_lag=1.0,
                score=0.42, published_at=now, is_founder=True)
    s2 = Signal(source_id=pol.id, headline_en="Lotsen funding approved", headline_de="Lotsen-Förderung beschlossen", signal_type="decision",
                authority=1.0, regional_relevance=1.0, novelty=0.8, consequence=0.8, forward_lag=0.6,
                score=0.384, published_at=now - timedelta(hours=2), is_founder=True)
    s3 = Signal(source_id=fund.id, headline_en="Lotsen funding approved (county)", headline_de="Lotsen (Landkreis)", signal_type="decision",
                authority=1.0, regional_relevance=1.0, novelty=0.0, consequence=0.8, forward_lag=0.6,
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
        SignalTopic(signal_id=s1.id, topic_code="foerderung"),
        SignalTopic(signal_id=s2.id, topic_code="verstetigung"),
        SignalEntity(signal_id=s2.id, entity_id=ent.id),
        Event(signal_id=s1.id, name="SeLA call", kind="deadline", deadline=date.today() + timedelta(days=10)),
        Event(signal_id=s2.id, name="Council session", start_date=date.today() + timedelta(days=3)),
        # A seeded calendar window carries no signal; the events API must not choke on it.
        Event(signal_id=None, origin="report", kind="window", slug="haushalte-2027", name="Haushalte 2027",
              start_date=date.today() + timedelta(days=5), end_date=date.today() + timedelta(days=120)),
        TrendCell(week=date.today() - timedelta(days=date.today().weekday()), topic="foerderung", layer="landkreis", count=3),
        TrendCell(week=date.today() - timedelta(days=date.today().weekday() + 35), topic="foerderung", layer="landkreis", count=1),
    ])
    cyc = Cycle(mode="mock", finished_at=now, signals=2, digest_ok=True)
    db_session.add(cyc)
    await db_session.flush()
    db_session.add(Digest(cycle_id=cyc.id, lead_en="Lead EN", lead_de="Lead DE", model="mock", payload={
        "lead_en": "Lead EN", "lead_de": "Lead DE",
        "sections": [{"layer": "landkreis", "items": [{"signal_id": str(s1.id), "note_en": "n", "note_de": "n"}]}],
        "chains": [], "watch": []}))
    await db_session.commit()
    return {"s1": s1, "s2": s2, "s3": s3, "ent": ent}


@pytest.fixture
async def client(db_session):
    from mhs.main import app

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
    r = await client.get("/api/signals", params={"layer": "landkreis"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1 and body["items"][0]["headline_en"] == "New SeLA call"
    assert body["items"][0]["layer"] == "landkreis"
    r2 = await client.get("/api/signals")
    assert {i["headline_en"] for i in r2.json()["items"]} == {"New SeLA call", "Lotsen funding approved"}


async def test_signal_detail_has_five_factors_story_members_and_topics(client, seeded):
    await _login(client)
    r = await client.get(f"/api/signals/{seeded['s2'].id}")
    assert r.status_code == 200
    d = r.json()
    assert d["factors"] == {"authority": 1.0, "regional_relevance": 1.0, "novelty": 0.8, "consequence": 0.8,
                            "forward_lag": 0.6}
    assert d["story"]["distinct_sources"] == 2 and d["story"]["confidence"] == 0.75
    assert len(d["story"]["members"]) == 2
    assert d["topics"] == ["verstetigung"]
    assert d["entities"][0]["slug"] == "sozialraumlotsen"


async def test_events_keep_deadline_and_start_separate(client, seeded):
    await _login(client)
    r = await client.get("/api/events")
    evs = {e["name"]: e for e in r.json()["items"]}
    assert evs["SeLA call"]["deadline"] and evs["SeLA call"]["start_date"] is None
    assert evs["Haushalte 2027"]["signal_id"] is None
    assert evs["Council session"]["start_date"] and evs["Council session"]["deadline"] is None


async def test_sources_lists_not_collected_with_reason(client, seeded):
    await _login(client)
    r = await client.get("/api/sources")
    rows = {s["slug"]: s for s in r.json()["items"]}
    assert rows["caritas-newsletter"]["collect"] is False
    assert "newsletter" in rows["caritas-newsletter"]["not_collected_reason"]
    assert rows["lk-miesbach-presse"]["signals_7d"] == 1


async def test_trends_and_overview_and_meta(client, seeded):
    await _login(client)
    t = (await client.get("/api/trends", params={"weeks": 12})).json()
    assert t["movers"][0]["topic"] == "foerderung" and t["movers"][0]["delta"] == 2
    o = (await client.get("/api/overview")).json()
    assert o["latest_digest"]["lead_en"] == "Lead EN"
    assert o["top_stories"][0]["headline_en"] == "New SeLA call"
    assert [l["layer"] for l in o["layers"]] == list(vocab.LAYERS)
    m = (await client.get("/api/meta")).json()
    assert m["mode"] == "mock" and m["languages"] == ["en", "de"]


async def test_entity_timeline(client, seeded):
    await _login(client)
    r = await client.get("/api/entities/sozialraumlotsen")
    assert r.status_code == 200
    assert r.json()["kind"] == "programme" and r.json()["timeline"][0]["headline_en"] == "Lotsen funding approved"
    lst = (await client.get("/api/entities", params={"kind": "programme"})).json()["items"]
    assert lst[0]["slug"] == "sozialraumlotsen" and lst[0]["count_90d"] == 1


async def test_digests_latest(client, seeded):
    await _login(client)
    r = await client.get("/api/digests/latest")
    assert r.status_code == 200
    body = r.json()
    assert body["sections"][0]["items"][0]["signal"]["headline_en"] == "New SeLA call"
