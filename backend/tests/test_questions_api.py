"""/api/questions: the fifteen as a ledger with balance, movement, a 12-week series and the
latest evidence; /api/questions/{id} with the report's evidence descriptions and every quote."""
import uuid
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport

from mhs.api import auth
from mhs.api import questions as questions_api
from mhs.config import settings
from mhs.db.engine import get_session
from mhs.db.models import FeedItem, Judgement, Signal, Source
from mhs.questions.load import load_questions, upsert_questions

DATA = Path(__file__).resolve().parents[2] / "data"


def _app() -> FastAPI:
    # main.py is wired by the orchestrator; mount the router the way it will.
    app = FastAPI()
    app.include_router(auth.router, prefix="/api")
    app.include_router(questions_api.router, prefix="/api")
    return app


@pytest.fixture
async def client(db_session):
    app = _app()

    async def _override():
        yield db_session

    app.dependency_overrides[get_session] = _override
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def _login(c):
    assert (await c.post("/api/login", json={"password": settings.app_password})).status_code == 200


def _at(d: date) -> datetime:
    return datetime.combine(d, time(10, 0), tzinfo=timezone.utc)


@pytest.fixture
async def seeded(db_session):
    await upsert_questions(db_session, load_questions(DATA / "questions.yaml"))
    src = Source(slug="lk-presse", name="Landratsamt Miesbach", layer="landkreis", authority="high",
                 scope="landkreis", method="rss", url="https://l.test/rss", collect=True)
    db_session.add(src)
    await db_session.flush()
    today = datetime.now(timezone.utc).date()
    sigs = []
    for i in range(5):
        key = uuid.uuid4().hex
        item = FeedItem(source_id=src.id, external_id=key, title=f"Kreisumlage {i}", url=f"https://l.test/{i}",
                        canonical_url=f"https://l.test/{key}", content_hash=key)
        db_session.add(item)
        await db_session.flush()
        s = Signal(feed_item_id=item.id, source_id=src.id, headline_de=f"Kreisumlage steigt ({i})",
                   headline_en=f"Levy rises ({i})", signal_type="budget", is_founder=True, regional_relevance=1.0,
                   published_at=_at(today - timedelta(days=7 * i)), judged_by="mock")
        db_session.add(s)
        sigs.append(s)
    await db_session.flush()
    # q02: five "for" judgements spread over five weeks; q03: one "against" six months ago.
    for i, s in enumerate(sigs):
        db_session.add(Judgement(signal_id=s.id, question_id="q02", direction="for", strength="moderate", weight=2,
                                 quote=f"Kreisumlage steigt ({i})", rationale_de="Umlage verdrängt.",
                                 rationale_en="Levy crowds out.", model="mock"))
    old = Signal(source_id=src.id, headline_de="Lotsen-Projekt befristet verlängert", headline_en="Extended",
                 signal_type="decision", is_founder=True, regional_relevance=1.0,
                 published_at=_at(today - timedelta(days=180)), judged_by="mock")
    db_session.add(old)
    await db_session.flush()
    db_session.add(Judgement(signal_id=old.id, question_id="q03", direction="against", strength="weak", weight=1,
                             quote="Lotsen-Projekt befristet verlängert", rationale_de="Bleibt Projekt.",
                             rationale_en="Stays a project.", model="mock"))
    await db_session.commit()
    return {"signals": sigs, "old": old}


async def test_questions_need_a_session(client, seeded):
    assert (await client.get("/api/questions")).status_code == 401
    assert (await client.get("/api/questions/q02")).status_code == 401


async def test_ledger_lists_the_fifteen_with_balance_movement_series_and_latest(client, seeded):
    await _login(client)
    r = await client.get("/api/questions")
    assert r.status_code == 200
    body = r.json()
    assert [q["id"] for q in body] == [f"q{i:02d}" for i in range(1, 16)]
    q02 = body[1]
    for key in ("sort", "title_de", "title_en", "driver_de", "driver_en", "for_label_de", "for_label_en",
                "against_label_de", "against_label_en"):
        assert q02[key] not in (None, "")
    assert q02["for_label_de"] == "Umlagen verdrängen"
    assert q02["balance"] > 0 and q02["movement"] == "for"
    assert len(q02["series"]) == 12
    assert set(q02["series"][0]) == {"week", "net", "balance", "n"}
    weeks = [date.fromisoformat(p["week"]) for p in q02["series"]]
    assert weeks == sorted(weeks) and all(w.weekday() == 0 for w in weeks)
    assert sum(p["n"] for p in q02["series"]) == 5
    assert q02["counts"] == {"for": 5, "against": 0}
    # latest: at most three, newest signal first, with the signal it rests on.
    latest = q02["latest"]
    assert [j["quote"] for j in latest] == ["Kreisumlage steigt (0)", "Kreisumlage steigt (1)", "Kreisumlage steigt (2)"]
    j = latest[0]
    assert set(j) >= {"id", "question_id", "direction", "strength", "weight", "quote", "rationale_de",
                      "rationale_en", "model", "created_at", "signal"}
    assert j["signal"]["layer"] == "landkreis" and j["signal"]["source_name"] == "Landratsamt Miesbach"
    assert j["signal"]["url"] == "https://l.test/0" and j["signal"]["headline_de"] == "Kreisumlage steigt (0)"
    assert j["signal"]["published_at"]
    # q03's only evidence is six months old: decayed, quiet, outside the 12-week counts.
    q03 = body[2]
    assert q03["movement"] == "quiet" and q03["counts"] == {"for": 0, "against": 0}
    assert -0.1 < q03["balance"] <= 0
    assert body[0]["movement"] == "quiet" and body[0]["balance"] == 0 and body[0]["latest"] == []


async def test_detail_carries_the_evidence_descriptions_and_every_judgement(client, seeded):
    await _login(client)
    r = await client.get("/api/questions/q02")
    assert r.status_code == 200
    d = r.json()
    assert d["id"] == "q02" and d["movement"] == "for" and len(d["series"]) == 12
    for key in ("for_de", "for_en", "against_de", "against_en", "sources_de"):
        assert d[key]
    assert [j["quote"] for j in d["evidence"]] == [f"Kreisumlage steigt ({i})" for i in range(5)]
    r3 = await client.get("/api/questions/q03")
    assert [j["direction"] for j in r3.json()["evidence"]] == ["against"]  # old evidence still listed
    assert r3.json()["evidence"][0]["signal"]["url"] is None  # a signal without a feed item


async def test_unknown_question_is_404(client, seeded):
    await _login(client)
    assert (await client.get("/api/questions/q99")).status_code == 404


async def test_ledger_without_loaded_questions_is_empty(client, db_session):
    await _login(client)
    r = await client.get("/api/questions")
    assert r.status_code == 200 and r.json() == []
