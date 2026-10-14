"""The report's calendar (data/calendar.yaml, spec §4.5): scheduled dates, deadlines and
watch windows, stored as events with origin "report" and no signal, keyed by slug.
Also the one definition of "an event falls in a date range", shared by the events API
and the Lagebericht, so a window shows on every day it is open, not only its first."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhs import vocab
from mhs.db.models import Event


def overlaps(start: date, end: date):
    """Events touching [start, end]: a deadline inside it, or a span (one day when there is
    no end date) that intersects it. An extracted event can carry both a deadline and a
    start; either one inside the range is enough."""
    return or_(
        and_(Event.deadline >= start, Event.deadline <= end),
        and_(Event.start_date <= end, func.coalesce(Event.end_date, Event.start_date) >= start),
    )


def _date(value, field: str, slug: str) -> date | None:
    if value is None or isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"calendar entry {slug!r}: {field} {value!r} is not a date") from exc


def _check(item: dict) -> dict:
    slug = item.get("slug")
    if not slug:
        raise ValueError(f"calendar entry without slug: {item!r}")
    kind = item.get("kind")
    if kind not in vocab.EVENT_KINDS:
        raise ValueError(f"calendar entry {slug!r}: kind {kind!r} not in {vocab.EVENT_KINDS}")
    start, end = _date(item.get("start"), "start", slug), _date(item.get("end"), "end", slug)
    deadline = _date(item.get("deadline"), "deadline", slug)
    if kind == "window" and not (start and end and start <= end):
        raise ValueError(f"calendar entry {slug!r}: a window needs start <= end")
    if kind == "deadline" and not deadline:
        raise ValueError(f"calendar entry {slug!r}: a deadline needs a deadline date")
    if kind == "event" and not start:
        raise ValueError(f"calendar entry {slug!r}: an event needs a start date")
    if not item.get("name_de"):
        raise ValueError(f"calendar entry {slug!r}: name_de is required")
    return {"slug": slug, "kind": kind, "start": start, "end": end, "deadline": deadline}


async def load_calendar(session: AsyncSession, path: Path | str) -> int:
    """Upsert every entry by slug; returns the number of entries in the file. Extracted
    events (slug NULL) are never touched. The whole file is checked before anything is
    written, so a malformed entry cannot leave half a calendar behind."""
    items = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or []
    checked = [(item, _check(item)) for item in items]
    slugs = [c["slug"] for _, c in checked]
    if len(set(slugs)) != len(slugs):
        raise ValueError("calendar has duplicate slugs")
    existing = {
        e.slug: e for e in (await session.execute(select(Event).where(Event.slug.in_(slugs)))).scalars()
    } if slugs else {}
    for item, c in checked:
        ev = existing.get(c["slug"])
        if ev is None:
            ev = Event(slug=c["slug"])
            session.add(ev)
        ev.origin = "report"
        ev.signal_id = None
        ev.kind = c["kind"]
        ev.name = item["name_de"]
        ev.name_en = item.get("name_en")
        ev.start_date, ev.end_date, ev.deadline = c["start"], c["end"], c["deadline"]
        ev.place = item.get("place")
        ev.programme = item.get("programme")
        ev.note_de = item.get("note_de")
        ev.note_en = item.get("note_en")
        ev.brief_ref = str(item["brief_ref"]) if item.get("brief_ref") is not None else None
    await session.commit()
    return len(checked)
