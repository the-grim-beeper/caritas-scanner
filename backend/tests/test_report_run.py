"""The weekly Lagebericht end to end: what goes in (this week's founders, judgements,
the next 30 days of the calendar), what comes out (a validated report with the Friday
note), which model wrote it, and the API that serves it."""
import asyncio
import json
import sys
import types
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
import yaml
from httpx import ASGITransport
from sqlalchemy import select

from mhs.calendar import load_calendar
from mhs.config import settings
from mhs.db.engine import get_session
from mhs.db.models import Cycle, Digest, Edge, Entity, Event, FeedItem, Judgement, Question, Signal, Source
from mhs.report import run as report_run
from mhs.report.run import write_report
from mhs.report.validate import friday_paragraphs

DATA = Path(__file__).resolve().parents[2] / "data"
TODAY = date(2026, 10, 15)  # a Thursday
NOW = datetime(2026, 10, 15, 16, 0, tzinfo=timezone.utc)
UTC = timezone.utc


def _questions() -> list[Question]:
    cols = {c.name for c in Question.__table__.columns}
    items = yaml.safe_load((DATA / "questions.yaml").read_text(encoding="utf-8"))
    return [Question(sort=i + 1, **{k: v for k, v in it.items() if k in cols}) for i, it in enumerate(items)]


def _signal(src: Source, headline: str, *, created: datetime, founder: bool = True, score: float = 0.5,
            item: FeedItem | None = None) -> Signal:
    return Signal(source_id=src.id, feed_item_id=item.id if item else None, headline_de=headline,
                  headline_en=f"EN {headline}", summary_de=f"Zusammenfassung: {headline}", summary_en="Summary",
                  signal_type="decision", score=score, is_founder=founder, published_at=created, created_at=created)


async def _world(db_session, now: datetime) -> dict:
    src = Source(slug="lk-presse", name="Landratsamt Miesbach – Presse", layer="landkreis", authority="high",
                 scope="landkreis", method="rss", url="https://lk.test/rss", collect=True,
                 last_ok_at=now - timedelta(hours=2))
    bad = Source(slug="gemeinde-x", name="Gemeinde X", layer="gemeinden", authority="high", scope="gemeinde",
                 method="page", url="https://x.test", collect=True, consecutive_failures=2)
    db_session.add_all([src, bad, *_questions(), Cycle(started_at=now - timedelta(hours=3))])
    await db_session.flush()
    item = FeedItem(source_id=src.id, external_id="1", url="https://lk.test/kreisumlage",
                    canonical_url="https://lk.test/kreisumlage", content_hash="h1")
    db_session.add(item)
    await db_session.flush()
    founder = _signal(src, "Kreistag beschließt Kreisumlage von 52 Prozent für 2027", created=now - timedelta(days=1),
                      item=item, score=0.8)
    second = _signal(src, "Sozialraumlotsen: Stelle bis 2027 befristet verlängert", created=now - timedelta(days=2),
                     score=0.6)
    member = _signal(src, "Kreisumlage (Bericht 2)", created=now - timedelta(hours=20), founder=False, score=0.0)
    old = _signal(src, "Alte Meldung vom September", created=now - timedelta(days=10), score=0.9)
    db_session.add_all([founder, second, member, old])
    await db_session.flush()
    j_now = Judgement(signal_id=second.id, question_id="q03", direction="against", strength="moderate", weight=2,
                      quote="Stelle bis 2027 befristet verlängert", rationale_de="r", rationale_en="r", model="mock",
                      created_at=now - timedelta(days=1))
    j_old = Judgement(signal_id=old.id, question_id="q03", direction="for", strength="strong", weight=3,
                      quote="Alte Meldung", rationale_de="r", rationale_en="r", model="mock",
                      created_at=now - timedelta(days=9))
    a = Entity(slug="landkreis-miesbach", kind="place", name="Landkreis Miesbach")
    b = Entity(slug="sozialraumlotsen", kind="programme", name="Interkommunale Sozialraumlotsen")
    db_session.add_all([j_now, j_old, a, b])
    await db_session.flush()
    e_new = Edge(a_entity_id=a.id, b_entity_id=b.id, relation="funding", origin="signal", signal_id=second.id,
                 quote="befristet verlängert", created_at=now - timedelta(days=2))
    e_old = Edge(a_entity_id=b.id, b_entity_id=a.id, relation="coordination", origin="report", brief_ref="56",
                 created_at=now - timedelta(days=40))
    db_session.add_all([e_new, e_old])
    await db_session.commit()
    return {"src": src, "founder": founder, "second": second, "member": member, "old": old,
            "j_now": j_now, "j_old": j_old}


@pytest.fixture
def movements(monkeypatch):
    """mhs.questions.balance belongs to another task; the report reaches it through one
    injectable function, replaced here."""
    seen: list = []

    async def fake(session, today):
        seen.append(today)
        return {"q03": "against", "q12": "quiet"}

    monkeypatch.setattr(report_run, "_question_movements", fake)
    return seen


def _valid(w: dict, *, judgement_ids=None) -> dict:
    f = str(w["founder"].id)
    return {
        "lead_de": "Der Kreistag hat die Kreisumlage beschlossen.", "lead_en": "The Kreistag set the levy.",
        "questions": [{"question_id": "q03", "movement": "for", "note_de": "n", "note_en": "n",
                       "judgement_ids": judgement_ids if judgement_ids is not None else [str(w["j_now"].id)]}],
        "sections": [{"layer": "landkreis", "items": [{"signal_id": f, "note_de": "n", "note_en": "n"}]}],
        "chains": [],
        "watch": [],
        "friday_de": "Der Kreistag hat die Kreisumlage für 2027 beschlossen.\n\nFür die Lotsen kann das enger werden.",
        "friday_en": "The Kreistag set the 2027 levy.\n\nFor the Lotsen this may tighten things.",
        "friday_signal_ids": [f],
    }


# ---------------------------------------------------------------------------
# mock path
# ---------------------------------------------------------------------------
async def test_mock_report_written_with_friday(db_session, movements):
    w = await _world(db_session, NOW)
    await load_calendar(db_session, DATA / "calendar.yaml")
    d = await write_report(db_session, today=TODAY)

    assert d is not None and d.model == "mock"
    assert d.week == date(2026, 10, 12)  # ISO Monday of the Thursday
    assert movements == [TODAY]
    paras_de = friday_paragraphs(d.friday_de)
    assert len(paras_de) >= 2 and len(friday_paragraphs(d.friday_en)) >= 2
    assert "Diese Woche" in paras_de[0] and paras_de[1].startswith("Für die Frage der Sozialraumlotsen")
    # The question with most judgements this week is q03; the note names it.
    assert "Wird aus dem Projekt Sozialraumlotsen vor Förderende eine reguläre Struktur?" in paras_de[1]
    founders = {str(w["founder"].id), str(w["second"].id)}
    assert d.payload["friday_signal_ids"] and set(d.payload["friday_signal_ids"]) <= founders
    assert d.friday_de == d.payload["friday_de"] and d.lead_de == d.payload["lead_de"]
    q = {x["question_id"]: x for x in d.payload["questions"]}
    # Movement is the computed one, the judgement is this week's, not the 9-day-old one.
    assert q["q03"]["movement"] == "against" and q["q03"]["judgement_ids"] == [str(w["j_now"].id)]
    stored = (await db_session.execute(select(Digest))).scalars().all()
    assert [s.id for s in stored] == [d.id]


async def test_no_founders_this_week_writes_nothing(db_session, movements):
    src = Source(slug="s", name="S", layer="landkreis", authority="high", scope="landkreis", method="rss")
    db_session.add(src)
    await db_session.flush()
    db_session.add_all([
        _signal(src, "Vor zehn Tagen", created=NOW - timedelta(days=10)),
        _signal(src, "Nur eine Bestätigung", created=NOW - timedelta(days=1), founder=False),
        _signal(src, "Morgen erst", created=NOW + timedelta(days=2)),  # after the report's day
    ])
    await db_session.commit()
    assert await write_report(db_session, today=TODAY) is None
    assert (await db_session.execute(select(Digest))).scalars().all() == []


# ---------------------------------------------------------------------------
# live path (complete_json replaced: tests never spend money)
# ---------------------------------------------------------------------------
@pytest.fixture
def live(monkeypatch):
    from mhs.llm import client

    monkeypatch.setattr(settings, "anthropic_api_key", "sk-test-not-a-key")
    calls: list[dict] = []
    replies: list = []

    async def fake_complete_json(**kw):
        calls.append(kw)
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply(kw) if callable(reply) else reply

    monkeypatch.setattr(client, "complete_json", fake_complete_json)
    return calls, replies


async def test_live_inputs_are_this_weeks_founders_judgements_and_next_30_days(db_session, movements, live):
    calls, replies = live
    w = await _world(db_session, NOW)
    await load_calendar(db_session, DATA / "calendar.yaml")
    replies.append(_valid(w))
    d = await write_report(db_session, today=TODAY)
    assert d is not None

    inputs = json.loads(calls[0]["user"])
    sig_ids = [s["id"] for s in inputs["signals"]]
    # Ranked by score; founders only; created within 7 days of the report day.
    assert sig_ids == [str(w["founder"].id), str(w["second"].id)]
    first = inputs["signals"][0]
    assert first["layer"] == "landkreis" and first["source"] == "Landratsamt Miesbach – Presse"
    assert first["headline_de"].startswith("Kreistag") and first["summary_de"] and first["type"] == "decision"

    by_slug = {e.slug: str(e.id) for e in (await db_session.execute(select(Event))).scalars()}
    ev_ids = {e["id"] for e in inputs["events"]}
    # Windows open during the next 30 days are in, although they started earlier or end later.
    assert {by_slug["sela-laufend"], by_slug["haushalte-2027-landkreis-gemeinden"],
            by_slug["pflegesonah-frist-2026"], by_slug["waakirchen-gr-2026-11-10"]} <= ev_ids
    assert by_slug["waakirchen-gr-2026-10-13"] not in ev_ids  # two days past
    assert by_slug["waakirchen-gr-2026-12-08"] not in ev_ids and by_slug["sgb2-stufe2-2027-08-01"] not in ev_ids
    window = next(e for e in inputs["events"] if e["id"] == by_slug["haushalte-2027-landkreis-gemeinden"])
    assert window["kind"] == "window" and window["end_date"] == "2027-03-31" and window["origin"] == "report"

    q = {x["id"]: x for x in inputs["questions"]}
    assert len(q) == 15 and q["q03"]["movement"] == "against" and q["q01"]["movement"] == "quiet"
    assert [j["id"] for j in q["q03"]["judgements"]] == [str(w["j_now"].id)]
    j = q["q03"]["judgements"][0]
    assert j["direction"] == "against" and j["quote"] and j["signal_id"] == str(w["second"].id) and j["headline_de"]

    assert [e["relation"] for e in inputs["edges"]] == ["funding"]
    assert inputs["edges"][0]["a"] == "Landkreis Miesbach" and inputs["edges"][0]["signal_id"] == str(w["second"].id)
    assert inputs["source_health"] == {"collected": 2, "ok_last_cycle": 1, "failing": 1}
    assert inputs["week"]["monday"] == "2026-10-12"

    assert calls[0]["model"] == settings.digest_model
    assert "Florian" in calls[0]["system"] and "friday_de" in calls[0]["system"]


async def test_live_retry_carries_the_problems_and_records_the_model(db_session, movements, live):
    calls, replies = live
    w = await _world(db_session, NOW)
    replies.extend([_valid(w, judgement_ids=["j-old"]), _valid(w)])
    d = await write_report(db_session, today=TODAY)

    assert d is not None and d.model == settings.digest_model
    assert len(calls) == 2 and "j-old" in calls[1]["user"] and "j-old" not in calls[0]["user"]
    # The model's movement label is replaced by the computed one.
    assert d.payload["questions"][0]["movement"] == "against"


async def test_fallback_model_is_the_one_recorded(db_session, movements, live):
    from mhs.llm.client import LLMEmptyCompletion

    calls, replies = live
    w = await _world(db_session, NOW)
    replies.extend([LLMEmptyCompletion("empty"), _valid(w)])
    d = await write_report(db_session, today=TODAY)
    assert d is not None and d.model == settings.digest_fallback_model
    assert [c["model"] for c in calls] == [settings.digest_model, settings.digest_fallback_model]


async def test_two_rejections_store_nothing(db_session, movements, live):
    calls, replies = live
    w = await _world(db_session, NOW)
    bad = {**_valid(w), "friday_de": "Nur ein Absatz."}
    replies.extend([bad, bad])
    assert await write_report(db_session, today=TODAY) is None
    assert len(calls) == 2 and "friday_de" in calls[1]["user"]
    assert (await db_session.execute(select(Digest))).scalars().all() == []


async def test_an_invented_number_in_the_friday_note_is_rejected(db_session, movements, live):
    calls, replies = live
    w = await _world(db_session, NOW)
    invented = {**_valid(w), "friday_de": "Die Kreisumlage steigt auf 47 Prozent.\n\nDas trifft die Lotsen."}
    replies.extend([invented, _valid(w)])
    d = await write_report(db_session, today=TODAY)
    assert d is not None and "47" in calls[1]["user"]
    assert "52" in d.friday_de or "2027" in d.friday_de


# ---------------------------------------------------------------------------
# _question_movements against a stand-in for mhs.questions.balance
# ---------------------------------------------------------------------------
async def test_question_movements_feed_balance_with_signal_dates(db_session, monkeypatch):
    w = await _world(db_session, NOW)
    # The same signal read again by a newer judge model counts once (the newest reading).
    db_session.add(Judgement(signal_id=w["second"].id, question_id="q03", direction="for", strength="strong",
                             weight=3, quote="Stelle", rationale_de="r", rationale_en="r", model="judge-v2",
                             created_at=NOW - timedelta(hours=1)))
    await db_session.commit()

    seen: dict = {}
    fake = types.ModuleType("mhs.questions.balance")

    def balance_series(judgements, *, weeks, today):
        seen.setdefault("calls", []).append((sorted(judgements), weeks, today))
        return [("point", tuple(sorted(judgements)))]

    def movement(series):
        js = series[0][1]
        return "quiet" if not js else ("for" if any(d == "for" for _, d, _ in js) else "against")

    fake.balance_series, fake.movement = balance_series, movement
    monkeypatch.setitem(sys.modules, "mhs.questions.balance", fake)
    if "mhs.questions" not in sys.modules:
        try:
            import mhs.questions  # noqa: F401
        except ImportError:
            monkeypatch.setitem(sys.modules, "mhs.questions", types.ModuleType("mhs.questions"))

    out = await report_run._question_movements(db_session, TODAY)
    assert len(out) == 15 and out["q01"] == "quiet"
    assert out["q03"] == "for"
    q03 = next(c for c in seen["calls"] if c[0])
    assert q03[0] == sorted([(w["old"].published_at.date(), "for", 3), (w["second"].published_at.date(), "for", 3)])
    assert q03[1] == 12 and q03[2] == TODAY


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
@pytest.fixture
async def client(db_session):
    from fastapi import FastAPI

    from mhs.api import auth, reports

    app = FastAPI()
    app.include_router(auth.router, prefix="/api")
    app.include_router(reports.router, prefix="/api")

    async def _override():
        yield db_session

    app.dependency_overrides[get_session] = _override
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def _login(client):
    assert (await client.post("/api/login", json={"password": settings.app_password})).status_code == 200


async def test_reports_api_serves_the_report_with_resolved_citations(client, db_session, movements):
    assert (await client.get("/api/reports")).status_code == 401
    await _login(client)
    now = datetime.now(UTC)
    w = await _world(db_session, now)
    await load_calendar(db_session, DATA / "calendar.yaml")
    db_session.add(Digest(lead_de="Alter Tagesdigest", lead_en="old", payload={}, model="mock", week=None))
    # An extracted deadline, so the watch list is not empty whatever day the suite runs on.
    db_session.add(Event(signal_id=w["founder"].id, name="Antragsfrist Quartiersförderung", kind="deadline",
                         deadline=now.date() + timedelta(days=5)))
    await db_session.commit()

    r = await client.post("/api/report/run")
    assert r.status_code == 200 and r.json()["ok"] is True
    rid = r.json()["id"]

    lst = (await client.get("/api/reports")).json()["items"]
    assert [x["id"] for x in lst] == [rid]  # the template's daily digests are not Lageberichte
    assert set(lst[0]) >= {"id", "week", "created_at", "model", "lead_de", "lead_en"}

    full = (await client.get("/api/reports/latest")).json()
    assert full["id"] == rid and full["model"] == "mock" and full["week"]
    assert full["friday_de"] and full["friday_en"] and full["friday_signal_ids"]
    fid = full["friday_signal_ids"][0]
    cited = full["signals"][fid]
    assert set(cited) >= {"headline_de", "headline_en", "layer", "source_name", "url", "published_at"}
    assert full["signals"][str(w["founder"].id)]["url"] == "https://lk.test/kreisumlage"
    jid = str(w["j_now"].id)
    j = full["judgements"][jid]
    assert j["question_id"] == "q03" and j["direction"] == "against" and j["weight"] == 2
    assert j["signal"]["id"] == str(w["second"].id) and j["signal"]["source_name"]
    watched = [x["event_id"] for x in full["watch"]]
    assert watched and all(e in full["events"] for e in watched)
    assert full["events"][watched[0]]["kind"] in {"event", "deadline", "window"}

    same = (await client.get(f"/api/reports/{rid}")).json()
    assert same["friday_de"] == full["friday_de"]
    assert (await client.get("/api/reports/00000000-0000-0000-0000-000000000000")).status_code == 404
    assert (await client.get("/api/reports/not-a-uuid")).status_code == 404


async def test_report_run_without_signals_says_why(client, db_session, movements):
    await _login(client)
    r = await client.post("/api/report/run")
    assert r.status_code == 200 and r.json() == {"ok": False, "id": None, "reason": "no_signals"}
    assert (await client.get("/api/reports/latest")).status_code == 404


async def test_report_run_refuses_to_run_twice_at_once(client, movements):
    from mhs.api import reports

    await _login(client)
    async with reports._run_lock:
        # Wrong: queueing behind the lock — the second click would wait minutes for Opus
        # and then write a second report. The timeout turns that hang into a failure.
        r = await asyncio.wait_for(client.post("/api/report/run"), timeout=5)
    assert r.status_code == 409
