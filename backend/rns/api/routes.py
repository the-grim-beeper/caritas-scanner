"""Read API (spec §6). Everything but /health is behind the session cookie."""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from rns import vocab
from rns.analyse import trends
from rns.api.auth import require_session
from rns.api.serializers import (
    entity_brief, event_out, signal_member, signal_summary, source_out, story_brief,
)
from rns.config import settings
from rns.db.engine import get_session, session_factory
from rns.db.models import (
    Cycle, Digest, Entity, Event, FeedItem, Signal, SignalEntity, SignalTopic, Source, Story,
    TrendCell,
)

log = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_session)])
open_router = APIRouter()

_SIGNAL_LOAD = (
    selectinload(Signal.topics),
    selectinload(Signal.story),
    selectinload(Signal.source),
    selectinload(Signal.feed_item),
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="not found") from exc


@open_router.get("/health")
async def health() -> dict:
    return {"ok": True}


# ---------------------------------------------------------------------------
# meta / overview
# ---------------------------------------------------------------------------
@router.get("/meta")
async def meta(session: AsyncSession = Depends(get_session)) -> dict:
    last = (await session.execute(select(Cycle).order_by(desc(Cycle.started_at)).limit(1))).scalar_one_or_none()
    return {
        "mode": "live" if settings.llm_enabled else "mock",
        "extraction_model": settings.extraction_model if settings.llm_enabled else "mock",
        "digest_model": settings.digest_model if settings.llm_enabled else "mock",
        "embedding_model": settings.embedding_model,
        "languages": ["en", "de"],
        "layers": {k: {"en": v.en, "de": v.de} for k, v in vocab.LAYERS.items()},
        "topics": {k: {"en": v.en, "de": v.de} for k, v in vocab.TOPICS.items()},
        "signal_types": {k: {"en": v.en, "de": v.de} for k, v in vocab.SIGNAL_TYPE_LABELS.items()},
        "last_cycle": _cycle_out(last) if last else None,
        "cycle_hour_utc": settings.cycle_hour_utc,
    }


def _cycle_out(c: Cycle) -> dict:
    return {
        "id": str(c.id), "mode": c.mode,
        "started_at": c.started_at.isoformat() if c.started_at else None,
        "finished_at": c.finished_at.isoformat() if c.finished_at else None,
        "items_fetched": c.items_fetched, "items_new": c.items_new, "extracted": c.extracted,
        "signals": c.signals, "stories_new": c.stories_new, "corroborations": c.corroborations,
        "failed_sources": c.failed_sources, "digest_ok": c.digest_ok, "error": c.error,
    }


async def _layer_volumes(session: AsyncSession) -> list[dict]:
    now = _now()
    out = []
    for layer in vocab.LAYERS:
        base = select(func.count(Signal.id)).join(Source, Source.id == Signal.source_id).where(
            Source.layer == layer, Signal.is_founder.is_(True))
        c7 = (await session.execute(base.where(Signal.published_at >= now - timedelta(days=7)))).scalar_one()
        c30 = (await session.execute(base.where(Signal.published_at >= now - timedelta(days=30)))).scalar_one()
        out.append({"layer": layer, "count_7d": int(c7), "count_30d": int(c30)})
    return out


@router.get("/overview")
async def overview(session: AsyncSession = Depends(get_session)) -> dict:
    now = _now()
    last = (await session.execute(select(Cycle).order_by(desc(Cycle.started_at)).limit(1))).scalar_one_or_none()
    top = (
        await session.execute(
            select(Signal).options(*_SIGNAL_LOAD)
            .where(Signal.is_founder.is_(True), Signal.published_at >= now - timedelta(days=7))
            .order_by(desc(Signal.score)).limit(12)
        )
    ).scalars().all()
    if len(top) < 6:  # thin week: fall back to the best of the last 30 days
        top = (
            await session.execute(
                select(Signal).options(*_SIGNAL_LOAD)
                .where(Signal.is_founder.is_(True), Signal.published_at >= now - timedelta(days=30))
                .order_by(desc(Signal.score)).limit(12)
            )
        ).scalars().all()
    today = now.date()
    events = (
        await session.execute(
            select(Event).options(selectinload(Event.signal).selectinload(Signal.source),
                                  selectinload(Event.signal).selectinload(Signal.feed_item))
            .where(func.coalesce(Event.deadline, Event.start_date) >= today)
            .order_by(func.coalesce(Event.deadline, Event.start_date)).limit(6)
        )
    ).scalars().all()
    digest = (await session.execute(select(Digest).order_by(desc(Digest.created_at)).limit(1))).scalar_one_or_none()
    movers = await trends.movers(session)
    return {
        "last_cycle": _cycle_out(last) if last else None,
        "top_stories": [signal_summary(s) for s in top],
        "layers": await _layer_volumes(session),
        "next_events": [event_out(e, e.signal) for e in events],
        "latest_digest": {"id": str(digest.id), "lead_en": digest.lead_en, "lead_de": digest.lead_de,
                          "created_at": digest.created_at.isoformat(), "model": digest.model} if digest else None,
        "movers": [m.__dict__ for m in movers[:8]],
        "totals": {
            "signals": int((await session.execute(select(func.count(Signal.id)).where(Signal.is_founder.is_(True)))).scalar_one()),
            "stories": int((await session.execute(select(func.count(Story.id)))).scalar_one()),
            "items": int((await session.execute(select(func.count(FeedItem.id)))).scalar_one()),
            "sources_collected": int((await session.execute(select(func.count(Source.id)).where(Source.collect.is_(True)))).scalar_one()),
        },
    }


# ---------------------------------------------------------------------------
# signals / stories
# ---------------------------------------------------------------------------
@router.get("/signals")
async def list_signals(
    session: AsyncSession = Depends(get_session),
    layer: str | None = None,
    topic: str | None = None,
    place: str | None = None,
    entity: str | None = None,
    type: str | None = None,  # noqa: A002
    min_score: float | None = None,
    q: str | None = None,
    since: date | None = None,
    sort: str = Query("published", pattern="^(published|score)$"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
) -> dict:
    stmt = select(Signal).join(Source, Source.id == Signal.source_id).where(Signal.is_founder.is_(True))
    if layer:
        stmt = stmt.where(Source.layer == layer)
    if topic:
        stmt = stmt.where(Signal.id.in_(select(SignalTopic.signal_id).where(SignalTopic.topic_code == topic)))
    if place:
        stmt = stmt.where(Signal.places_text.any(place))
    if entity:
        stmt = stmt.where(Signal.id.in_(
            select(SignalEntity.signal_id).join(Entity, Entity.id == SignalEntity.entity_id).where(Entity.slug == entity)))
    if type:
        stmt = stmt.where(Signal.signal_type == type)
    if min_score is not None:
        stmt = stmt.where(Signal.score >= min_score)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Signal.headline_en.ilike(like), Signal.headline_de.ilike(like),
                              Signal.summary_de.ilike(like), Signal.summary_en.ilike(like)))
    if since:
        stmt = stmt.where(Signal.published_at >= datetime.combine(since, datetime.min.time(), tzinfo=timezone.utc))
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (
        await session.execute(
            stmt.options(*_SIGNAL_LOAD)
            .order_by(desc(Signal.score) if sort == "score" else desc(Signal.published_at), desc(Signal.published_at))
            .offset((page - 1) * per_page).limit(per_page)
        )
    ).scalars().all()
    return {"total": int(total), "page": page, "per_page": per_page, "items": [signal_summary(s) for s in rows]}


async def _story_members(session: AsyncSession, story_id: UUID) -> list[Signal]:
    return (
        await session.execute(
            select(Signal).options(selectinload(Signal.source), selectinload(Signal.feed_item))
            .where(Signal.story_id == story_id).order_by(desc(Signal.is_founder), Signal.published_at)
        )
    ).scalars().all()


@router.get("/signals/{signal_id}")
async def get_signal(signal_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    sid = _uuid(signal_id)
    s = (
        await session.execute(
            select(Signal).options(*_SIGNAL_LOAD, selectinload(Signal.entity_links).selectinload(SignalEntity.entity),
                                   selectinload(Signal.events)).where(Signal.id == sid)
        )
    ).scalar_one_or_none()
    if s is None:
        raise HTTPException(status_code=404, detail="not found")
    out = signal_summary(s)
    out["entities"] = [entity_brief(link.entity) for link in s.entity_links]
    out["events"] = [event_out(e) for e in s.events]
    if s.story_id:
        out["story"] = {**(out["story"] or {}), "members": [signal_member(m) for m in await _story_members(session, s.story_id)]}
    return out


@router.get("/stories/{story_id}")
async def get_story(story_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    st = await session.get(Story, _uuid(story_id))
    if st is None:
        raise HTTPException(status_code=404, detail="not found")
    members = await _story_members(session, st.id)
    founder = next((m for m in members if m.is_founder), members[0] if members else None)
    out = story_brief(st) or {}
    out["members"] = [signal_member(m) for m in members]
    if founder is not None:
        f = (await session.execute(select(Signal).options(*_SIGNAL_LOAD).where(Signal.id == founder.id))).scalar_one()
        out["founder"] = signal_summary(f)
    return out


# ---------------------------------------------------------------------------
# entities
# ---------------------------------------------------------------------------
async def _entity_counts(session: AsyncSession, days: int) -> dict[UUID, int]:
    since = _now() - timedelta(days=days)
    rows = (
        await session.execute(
            select(SignalEntity.entity_id, func.count(SignalEntity.signal_id))
            .join(Signal, Signal.id == SignalEntity.signal_id)
            .where(Signal.is_founder.is_(True), Signal.published_at >= since)
            .group_by(SignalEntity.entity_id)
        )
    ).all()
    return {eid: int(n) for eid, n in rows}


@router.get("/entities")
async def list_entities(kind: str | None = None, session: AsyncSession = Depends(get_session)) -> dict:
    stmt = select(Entity)
    if kind:
        stmt = stmt.where(Entity.kind == kind)
    ents = (await session.execute(stmt)).scalars().all()
    c30, c90 = await _entity_counts(session, 30), await _entity_counts(session, 90)
    items = [{**entity_brief(e), "count_30d": c30.get(e.id, 0), "count_90d": c90.get(e.id, 0)} for e in ents]
    items.sort(key=lambda x: (-x["count_90d"], -x["count_30d"], x["name"]))
    return {"items": items[:300]}


@router.get("/entities/{slug}")
async def get_entity(slug: str, session: AsyncSession = Depends(get_session)) -> dict:
    e = (await session.execute(select(Entity).where(Entity.slug == slug))).scalar_one_or_none()
    if e is None:
        raise HTTPException(status_code=404, detail="not found")
    sigs = (
        await session.execute(
            select(Signal).options(*_SIGNAL_LOAD)
            .join(SignalEntity, SignalEntity.signal_id == Signal.id)
            .where(SignalEntity.entity_id == e.id, Signal.is_founder.is_(True))
            .order_by(desc(Signal.published_at)).limit(100)
        )
    ).scalars().all()
    weeks: dict[str, int] = {}
    for s in sigs:
        wk = (s.published_at.date() - timedelta(days=s.published_at.weekday())).isoformat()
        weeks[wk] = weeks.get(wk, 0) + 1
    return {**entity_brief(e), "aliases": list(e.aliases or []), "timeline": [signal_summary(s) for s in sigs],
            "weekly": sorted(weeks.items())}


# ---------------------------------------------------------------------------
# events
# ---------------------------------------------------------------------------
@router.get("/events")
async def list_events(
    session: AsyncSession = Depends(get_session),
    from_: date | None = Query(None, alias="from"),
    to: date | None = None,
) -> dict:
    start = from_ or _now().date()
    end = to or (start + timedelta(days=90))
    key = func.coalesce(Event.deadline, Event.start_date)
    rows = (
        await session.execute(
            select(Event).options(selectinload(Event.signal).selectinload(Signal.source),
                                  selectinload(Event.signal).selectinload(Signal.feed_item))
            .where(key >= start, key <= end).order_by(key)
        )
    ).scalars().all()
    return {"from": start.isoformat(), "to": end.isoformat(), "items": [event_out(e, e.signal) for e in rows]}


# ---------------------------------------------------------------------------
# digests
# ---------------------------------------------------------------------------
async def _digest_full(session: AsyncSession, d: Digest) -> dict:
    payload = d.payload or {}
    ids: set[str] = set()
    for sec in payload.get("sections", []):
        ids |= {i["signal_id"] for i in sec.get("items", [])}
    for ch in payload.get("chains", []):
        ids |= set(ch.get("signal_ids", []))
    ev_ids = {w["event_id"] for w in payload.get("watch", [])}
    sigs = {}
    if ids:
        rows = (await session.execute(select(Signal).options(*_SIGNAL_LOAD).where(Signal.id.in_([UUID(i) for i in ids])))).scalars()
        sigs = {str(s.id): signal_summary(s) for s in rows}
    evs = {}
    if ev_ids:
        rows = (await session.execute(
            select(Event).options(selectinload(Event.signal).selectinload(Signal.source),
                                  selectinload(Event.signal).selectinload(Signal.feed_item))
            .where(Event.id.in_([UUID(i) for i in ev_ids])))).scalars()
        evs = {str(e.id): event_out(e, e.signal) for e in rows}
    return {
        "id": str(d.id), "created_at": d.created_at.isoformat(), "model": d.model,
        "lead_en": d.lead_en, "lead_de": d.lead_de,
        "sections": [
            {"layer": sec["layer"], "items": [
                {"signal": sigs.get(i["signal_id"]), "note_en": i["note_en"], "note_de": i["note_de"]}
                for i in sec.get("items", []) if i["signal_id"] in sigs]}
            for sec in payload.get("sections", [])
        ],
        "chains": [
            {"title_en": ch["title_en"], "title_de": ch["title_de"],
             "signals": [sigs[i] for i in ch.get("signal_ids", []) if i in sigs]}
            for ch in payload.get("chains", [])
        ],
        "watch": [
            {"event": evs.get(w["event_id"]), "why_en": w["why_en"], "why_de": w["why_de"]}
            for w in payload.get("watch", []) if w["event_id"] in evs
        ],
    }


@router.get("/digests")
async def list_digests(session: AsyncSession = Depends(get_session)) -> dict:
    rows = (await session.execute(select(Digest).order_by(desc(Digest.created_at)).limit(60))).scalars().all()
    return {"items": [{"id": str(d.id), "created_at": d.created_at.isoformat(), "lead_en": d.lead_en,
                       "lead_de": d.lead_de, "model": d.model} for d in rows]}


@router.get("/digests/latest")
async def latest_digest(session: AsyncSession = Depends(get_session)) -> dict:
    d = (await session.execute(select(Digest).order_by(desc(Digest.created_at)).limit(1))).scalar_one_or_none()
    if d is None:
        raise HTTPException(status_code=404, detail="no digest yet")
    return await _digest_full(session, d)


@router.get("/digests/{digest_id}")
async def get_digest(digest_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    d = await session.get(Digest, _uuid(digest_id))
    if d is None:
        raise HTTPException(status_code=404, detail="not found")
    return await _digest_full(session, d)


# ---------------------------------------------------------------------------
# trends / sources / cycles
# ---------------------------------------------------------------------------
@router.get("/trends")
async def get_trends(weeks: int = Query(12, ge=1, le=52), session: AsyncSession = Depends(get_session)) -> dict:
    today = _now().date()
    since = today - timedelta(weeks=weeks)
    cells = (await session.execute(select(TrendCell).where(TrendCell.week >= since).order_by(TrendCell.week))).scalars().all()
    movers = await trends.movers(session)
    return {
        "weeks": weeks,
        "cells": [{"week": c.week.isoformat(), "topic": c.topic, "layer": c.layer, "count": c.count} for c in cells],
        "movers": [m.__dict__ for m in movers[:20]],
    }


@router.get("/sources")
async def list_sources(session: AsyncSession = Depends(get_session)) -> dict:
    since = _now() - timedelta(days=7)
    items7 = dict((await session.execute(
        select(FeedItem.source_id, func.count(FeedItem.id)).where(FeedItem.created_at >= since).group_by(FeedItem.source_id))).all())
    sig7 = dict((await session.execute(
        select(Signal.source_id, func.count(Signal.id)).where(Signal.created_at >= since, Signal.is_founder.is_(True)).group_by(Signal.source_id))).all())
    rows = (await session.execute(select(Source).order_by(Source.layer, desc(Source.collect), Source.name))).scalars().all()
    return {"items": [source_out(s, int(items7.get(s.id, 0)), int(sig7.get(s.id, 0))) for s in rows]}


@router.get("/cycles")
async def list_cycles(session: AsyncSession = Depends(get_session)) -> dict:
    rows = (await session.execute(select(Cycle).order_by(desc(Cycle.started_at)).limit(30))).scalars().all()
    return {"items": [_cycle_out(c) for c in rows]}


_running: dict[str, asyncio.Task] = {}


def _spawn(name: str, coro) -> dict:
    task = _running.get(name)
    if task and not task.done():
        return {"started": False, "reason": f"{name} already running"}
    _running[name] = asyncio.create_task(coro)
    return {"started": True}


@router.post("/cycle/run")
async def trigger_cycle() -> dict:
    from rns.cycle import run_cycle

    return _spawn("cycle", run_cycle(session_factory()))


@router.post("/cycle/digest")
async def trigger_digest() -> dict:
    from rns.cycle import run_digest_only

    return _spawn("digest", run_digest_only(session_factory()))
