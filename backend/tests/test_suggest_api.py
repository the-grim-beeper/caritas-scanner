"""/api/suggestions: list, decline, adopt now, run. Mounted on a bare app so the test does not
depend on main.py's wiring (Task 8 includes the router)."""
from datetime import timedelta

import httpx
import pytest
import respx
from fastapi import FastAPI
from httpx import ASGITransport
from sqlalchemy import select

from mhs.api import auth, suggestions
from mhs.config import settings
from mhs.db.engine import get_session
from mhs.db.models import Source, SourceSuggestion, utcnow
from mhs.suggest import net, run
from mhs.suggest.discover import Candidate

PAGE = "".join(
    f'<li class="news-item"><a href="https://weyarn.test/aktuelles/m-{i}">Gemeinderat Weyarn berät Meldung Nummer {i}</a></li>'
    for i in range(3)
).join(["<html><body><ul>", "</ul></body></html>"]).encode()


@pytest.fixture(autouse=True)
def public_dns(monkeypatch):
    monkeypatch.setattr(net, "_resolve", lambda host: ["93.184.216.34"])


@pytest.fixture
async def client(db_session, session_factory):
    app = FastAPI()
    app.include_router(auth.router, prefix="/api")
    app.include_router(suggestions.router, prefix="/api")

    async def _session():
        yield db_session

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[suggestions.get_session_factory] = lambda: session_factory
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/api/login", json={"password": settings.app_password})
        assert r.status_code == 200
        yield c


def _sugg(url="https://weyarn.test/aktuelles", *, status="pending", adopt_in_days=3, name="Gemeinde Weyarn"):
    now = utcnow()
    return SourceSuggestion(url=url, name=name, layer="gemeinden", scope="gemeinde", places=["Weyarn"],
                            rationale_de="de", rationale_en="en", model="mock", status=status,
                            suggested_at=now - timedelta(days=7 - adopt_in_days),
                            adopt_after=now + timedelta(days=adopt_in_days))


async def test_suggestions_need_a_session(db_session):
    app = FastAPI()
    app.include_router(suggestions.router, prefix="/api")
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        assert (await c.get("/api/suggestions")).status_code == 401
        assert (await c.post("/api/suggestions/run")).status_code == 401


async def test_api_decline_then_adopt_conflicts(client, db_session):
    s = _sugg()
    db_session.add(s)
    await db_session.commit()
    r = await client.post(f"/api/suggestions/{s.id}/decline")
    assert r.status_code == 200 and r.json()["status"] == "declined" and r.json()["resolved_at"]
    assert (await client.post(f"/api/suggestions/{s.id}/adopt")).status_code == 409
    assert (await client.post(f"/api/suggestions/{s.id}/decline")).status_code == 409


async def test_unknown_or_malformed_id_is_404(client):
    assert (await client.post("/api/suggestions/not-a-uuid/decline")).status_code == 404
    assert (await client.post("/api/suggestions/00000000-0000-0000-0000-000000000000/adopt")).status_code == 404


@respx.mock
async def test_adopt_now_creates_the_source_and_reports_its_slug(client, db_session):
    s = _sugg()
    db_session.add(s)
    await db_session.commit()
    respx.get("https://weyarn.test/aktuelles").respond(200, content=PAGE, headers={"content-type": "text/html"})
    respx.route().respond(404)
    r = await client.post(f"/api/suggestions/{s.id}/adopt")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "adopted" and body["source_slug"] == "vorschlag-gemeinde-weyarn"
    assert body["method"] == "page" and body["items_at_check"] == 3
    src = (await db_session.execute(select(Source))).scalar_one()
    assert src.origin == "suggestion" and src.collect is True


@respx.mock
async def test_adopt_now_that_fails_verification_is_422_with_reason(client, db_session):
    s = _sugg()
    db_session.add(s)
    await db_session.commit()
    respx.get("https://weyarn.test/aktuelles").respond(503)
    sid = s.id
    r = await client.post(f"/api/suggestions/{sid}/adopt")
    assert r.status_code == 422 and "503" in r.json()["detail"]
    db_session.expire_all()
    assert (await db_session.get(SourceSuggestion, sid)).status == "failed"
    assert (await db_session.execute(select(Source))).first() is None


async def test_list_puts_pending_first_and_filters_by_status(client, db_session):
    db_session.add_all([
        _sugg("https://spaet.test/x", adopt_in_days=5, name="Später"),
        _sugg("https://bald.test/x", adopt_in_days=1, name="Bald"),
        _sugg("https://weg.test/x", status="declined", adopt_in_days=-10, name="Weg"),
    ])
    await db_session.commit()
    items = (await client.get("/api/suggestions")).json()
    assert [i["name"] for i in items] == ["Bald", "Später", "Weg"]
    first = items[0]
    assert set(first) >= {"id", "name", "url", "layer", "scope", "places", "rationale_de", "rationale_en", "method",
                          "feed_url", "items_at_check", "status", "reason", "suggested_at", "adopt_after",
                          "resolved_at", "source_slug"}
    assert [i["name"] for i in (await client.get("/api/suggestions", params={"status": "declined"})).json()] == ["Weg"]
    assert [i["name"] for i in (await client.get("/api/suggestions", params={"status": "pending"})).json()] == ["Bald", "Später"]
    assert (await client.get("/api/suggestions", params={"status": "bogus"})).status_code == 422


async def test_run_returns_counts_and_refuses_a_concurrent_run(client, monkeypatch):
    async def fake(session):
        return [Candidate(name="Lokal", url="http://10.0.0.1/x", layer="gemeinden", scope="gemeinde", places=[],
                          rationale_de="d", rationale_en="e")]

    monkeypatch.setattr(run, "propose", fake)
    r = await client.post("/api/suggestions/run")
    assert r.status_code == 200
    assert r.json() == {"proposed": 1, "pending_new": 0, "rejected": 1, "known": 0}
    async with run.running():
        assert (await client.post("/api/suggestions/run")).status_code == 409
