"""The report's calendar: seeded dates and watch windows load without a signal, by slug,
and the events API shows a window on every day it is open, not only on its first day."""
from datetime import date, timedelta
from pathlib import Path

import httpx
import pytest
import yaml
from httpx import ASGITransport
from sqlalchemy import select

from mhs.calendar import load_calendar
from mhs.config import settings
from mhs.db.engine import get_session
from mhs.db.models import Event, Signal, Source

DATA = Path(__file__).resolve().parents[2] / "data"


async def test_seeded_window_loads_without_signal(db_session):
    n = await load_calendar(db_session, DATA / "calendar.yaml")
    ev = (await db_session.execute(select(Event).where(Event.slug == "haushalte-2027-landkreis-gemeinden"))).scalar_one()
    assert n == 10 and ev.kind == "window" and ev.signal_id is None and ev.origin == "report"
    assert ev.start_date == date(2026, 11, 1) and ev.end_date == date(2027, 3, 31) and ev.deadline is None
    assert ev.name == "Haushaltsberatungen 2027 in Landkreis und Gemeinden"
    assert ev.name_en == "Landkreis and municipal 2027 budget cycle"
    assert ev.place == "landkreis-miesbach" and ev.brief_ref == "calendar"
    # Wrong: inserting again on a second load.
    assert await load_calendar(db_session, DATA / "calendar.yaml") == 10
    assert len((await db_session.execute(select(Event))).scalars().all()) == 10


async def test_deadline_is_a_deadline_not_a_start(db_session):
    # Wrong: folding the deadline into start_date, so the calendar shows a Frist as a meeting.
    await load_calendar(db_session, DATA / "calendar.yaml")
    ev = (await db_session.execute(select(Event).where(Event.slug == "pflegesonah-frist-2026"))).scalar_one()
    assert ev.kind == "deadline" and ev.deadline == date(2026, 10, 31) and ev.start_date is None
    assert ev.programme == "pflegesonah" and ev.note_de.startswith("Letzter Termin")


async def test_reload_updates_by_slug_and_leaves_extracted_events_alone(db_session, tmp_path):
    src = Source(slug="s", name="S", layer="landkreis", authority="high", scope="landkreis", method="rss")
    db_session.add(src)
    await db_session.flush()
    sig = Signal(source_id=src.id, headline_en="h", headline_de="h", signal_type="event")
    db_session.add(sig)
    await db_session.flush()
    db_session.add(Event(signal_id=sig.id, name="Fachtag Pflege", kind="event", start_date=date(2026, 11, 5)))
    await db_session.commit()

    await load_calendar(db_session, DATA / "calendar.yaml")
    items = yaml.safe_load((DATA / "calendar.yaml").read_text(encoding="utf-8"))
    for it in items:
        if it["slug"] == "bergbus-saisonende-2026":
            it["note_de"] = "Geändert."
    changed = tmp_path / "calendar.yaml"
    changed.write_text(yaml.safe_dump(items, allow_unicode=True), encoding="utf-8")

    assert await load_calendar(db_session, changed) == 10
    rows = (await db_session.execute(select(Event))).scalars().all()
    assert len(rows) == 11  # ten seeded + the extracted one, untouched
    by_slug = {e.slug: e for e in rows}
    assert by_slug["bergbus-saisonende-2026"].note_de == "Geändert."
    extracted = by_slug[None]
    assert extracted.origin == "signal" and extracted.signal_id == sig.id


async def test_malformed_entry_is_refused(db_session, tmp_path):
    # A window without an end would sit on the calendar for ever; a typo'd kind would
    # silently become an "event". Both must fail the load, not slip in.
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.safe_dump([{"slug": "x", "kind": "window", "start": date(2026, 11, 1),
                                    "name_de": "X", "name_en": "X"}]), encoding="utf-8")
    with pytest.raises(ValueError, match="x"):
        await load_calendar(db_session, bad)
    bad.write_text(yaml.safe_dump([{"slug": "y", "kind": "meeting", "start": date(2026, 11, 1),
                                    "name_de": "Y", "name_en": "Y"}]), encoding="utf-8")
    with pytest.raises(ValueError, match="meeting"):
        await load_calendar(db_session, bad)


@pytest.fixture
async def client(db_session):
    from fastapi import FastAPI

    from mhs.api import auth, routes

    app = FastAPI()
    app.include_router(auth.router, prefix="/api")
    app.include_router(routes.router, prefix="/api")

    async def _override():
        yield db_session

    app.dependency_overrides[get_session] = _override
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        assert (await c.post("/api/login", json={"password": settings.app_password})).status_code == 200
        yield c


async def test_events_api_shows_an_open_window_inside_the_range(client, db_session):
    # Wrong: filtering on the window's start date only — the Nov–Mar budget window would
    # vanish from December although it is the thing to watch in December.
    await load_calendar(db_session, DATA / "calendar.yaml")
    r = await client.get("/api/events", params={"from": "2026-12-15", "to": "2026-12-31"})
    assert r.status_code == 200
    items = {e["slug"]: e for e in r.json()["items"]}
    assert "haushalte-2027-landkreis-gemeinden" in items and "bezirk-haushalt-2027" in items
    assert "bergbus-saisonende-2026" not in items and "pflegesonah-frist-2026" not in items
    assert "waakirchen-gr-2026-12-08" not in items  # a one-day event before the range stays out
    w = items["haushalte-2027-landkreis-gemeinden"]
    assert w["kind"] == "window" and w["origin"] == "report" and w["signal_id"] is None
    assert w["end_date"] == "2027-03-31" and w["name_en"] == "Landkreis and municipal 2027 budget cycle"
    assert w["note_de"] and w["note_en"] and w["place"] == "landkreis-miesbach" and w["brief_ref"] == "calendar"
    assert "programme" in w and items["haushalte-2027-landkreis-gemeinden"]["programme"] is None


async def test_events_api_still_finds_a_one_day_event_and_a_deadline(client, db_session):
    await load_calendar(db_session, DATA / "calendar.yaml")
    r = await client.get("/api/events", params={"from": "2026-10-20", "to": "2026-10-31"})
    slugs = {e["slug"] for e in r.json()["items"]}
    assert {"bergbus-saisonende-2026", "pflegesonah-frist-2026"} <= slugs
    assert "waakirchen-gr-2026-10-13" not in slugs and "waakirchen-gr-2026-11-10" not in slugs
    today = date.today()
    r2 = await client.get("/api/events", params={"from": (today + timedelta(days=4000)).isoformat()})
    assert r2.json()["items"] == []
