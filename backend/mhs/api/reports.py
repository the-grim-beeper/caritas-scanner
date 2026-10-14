"""The weekly Lagebericht (spec §6): list, latest, one report with its citations resolved,
and the manual trigger. Mounted under /api by main.py, behind the session cookie."""
from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from mhs.api.auth import require_session
from mhs.api.serializers import event_out
from mhs.db.engine import get_session
from mhs.db.models import Digest, Event, Judgement, Signal

log = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_session)])

# One report at a time: a second click while Opus is writing must not start a second call.
_run_lock = asyncio.Lock()

_SIGNAL_LOAD = (selectinload(Signal.source), selectinload(Signal.feed_item))


def _uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="not found") from exc


def _cited_signal(s: Signal) -> dict:
    return {
        "id": str(s.id),
        "headline_de": s.headline_de,
        "headline_en": s.headline_en,
        "layer": s.source.layer if s.source else None,
        "source_name": s.source.name if s.source else None,
        "url": s.feed_item.url if s.feed_item else None,
        "published_at": s.published_at.isoformat() if s.published_at else None,
    }


def _judgement_out(j: Judgement, signal: Signal | None) -> dict:
    return {
        "id": str(j.id), "question_id": j.question_id, "direction": j.direction, "strength": j.strength,
        "weight": j.weight, "quote": j.quote, "rationale_de": j.rationale_de, "rationale_en": j.rationale_en,
        "model": j.model, "created_at": j.created_at.isoformat() if j.created_at else None,
        "signal": _cited_signal(signal) if signal is not None else None,
    }


def _brief(d: Digest) -> dict:
    return {"id": str(d.id), "week": d.week.isoformat() if d.week else None, "created_at": d.created_at.isoformat(),
            "model": d.model, "lead_de": d.lead_de, "lead_en": d.lead_en}


def _uuids(ids: set[str]) -> list[UUID]:
    out = []
    for i in ids:
        try:
            out.append(UUID(i))
        except ValueError:
            log.warning("report cites a non-uuid id %r", i)
    return out


async def _full(session: AsyncSession, d: Digest) -> dict:
    payload = d.payload or {}
    sig_ids: set[str] = set(payload.get("friday_signal_ids", []))
    for sec in payload.get("sections", []):
        sig_ids |= {i["signal_id"] for i in sec.get("items", [])}
    for ch in payload.get("chains", []):
        sig_ids |= set(ch.get("signal_ids", []))
    ev_ids = {w["event_id"] for w in payload.get("watch", [])}
    j_ids = {jid for q in payload.get("questions", []) for jid in q.get("judgement_ids", [])}

    signals: dict[str, dict] = {}
    if sig_ids:
        rows = (await session.execute(select(Signal).options(*_SIGNAL_LOAD).where(Signal.id.in_(_uuids(sig_ids))))).scalars()
        signals = {str(s.id): _cited_signal(s) for s in rows}
    events: dict[str, dict] = {}
    if ev_ids:
        rows = (await session.execute(
            select(Event).options(selectinload(Event.signal).selectinload(Signal.source),
                                  selectinload(Event.signal).selectinload(Signal.feed_item))
            .where(Event.id.in_(_uuids(ev_ids))))).scalars()
        events = {str(e.id): event_out(e, e.signal) for e in rows}
    judgements: dict[str, dict] = {}
    if j_ids:
        rows = (await session.execute(
            select(Judgement, Signal).join(Signal, Signal.id == Judgement.signal_id)
            .options(*_SIGNAL_LOAD)
            .where(Judgement.id.in_(_uuids(j_ids))))).all()
        judgements = {str(j.id): _judgement_out(j, s) for j, s in rows}

    return {
        **payload,
        **_brief(d),
        "friday_de": d.friday_de if d.friday_de is not None else payload.get("friday_de"),
        "friday_en": d.friday_en if d.friday_en is not None else payload.get("friday_en"),
        "friday_signal_ids": payload.get("friday_signal_ids", []),
        "signals": signals,
        "events": events,
        "judgements": judgements,
    }


def _reports():
    # Rows without a week are the template's daily digests, not Lageberichte.
    return select(Digest).where(Digest.week.is_not(None)).order_by(desc(Digest.created_at))


@router.get("/reports")
async def list_reports(session: AsyncSession = Depends(get_session)) -> dict:
    rows = (await session.execute(_reports().limit(60))).scalars().all()
    return {"items": [_brief(d) for d in rows]}


@router.get("/reports/latest")
async def latest_report(session: AsyncSession = Depends(get_session)) -> dict:
    d = (await session.execute(_reports().limit(1))).scalar_one_or_none()
    if d is None:
        raise HTTPException(status_code=404, detail="no report yet")
    return await _full(session, d)


@router.get("/reports/{report_id}")
async def get_report(report_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    d = await session.get(Digest, _uuid(report_id))
    if d is None or d.week is None:
        raise HTTPException(status_code=404, detail="not found")
    return await _full(session, d)


@router.post("/report/run")
async def run_report(session: AsyncSession = Depends(get_session)) -> dict:
    from mhs.report.run import founders_in_window, write_report

    if _run_lock.locked():
        raise HTTPException(status_code=409, detail="a report is already being written")
    async with _run_lock:
        d = await write_report(session)
        if d is not None:
            return {"ok": True, "id": str(d.id)}
        reason = "failed" if await founders_in_window(session) else "no_signals"
        return {"ok": False, "id": None, "reason": reason}
