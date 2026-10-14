"""The evidence graph API (spec §4.3, §6): `GET /api/network`."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from mhs.api.auth import require_session
from mhs.api.serializers import entity_brief
from mhs.db.engine import get_session
from mhs.db.models import Edge, Entity, ForumProfile, NetworkGap, Signal, SignalEntity

router = APIRouter(dependencies=[Depends(require_session)])


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _signals_30d(session: AsyncSession, entity_ids: list[UUID]) -> dict[UUID, int]:
    if not entity_ids:
        return {}
    since = _now() - timedelta(days=30)
    rows = (
        await session.execute(
            select(SignalEntity.entity_id, func.count(func.distinct(SignalEntity.signal_id)))
            .join(Signal, Signal.id == SignalEntity.signal_id)
            .where(Signal.published_at >= since, SignalEntity.entity_id.in_(entity_ids))
            .group_by(SignalEntity.entity_id)
        )
    ).all()
    return {eid: int(n) for eid, n in rows}


@router.get("/network")
async def get_network(session: AsyncSession = Depends(get_session)) -> dict:
    edges = (await session.execute(select(Edge))).scalars().all()
    forums = (await session.execute(select(ForumProfile))).scalars().all()
    gaps = (await session.execute(select(NetworkGap).order_by(NetworkGap.sort))).scalars().all()

    # Nodes: every entity that is an edge endpoint, every forum-profile entity, and every
    # entity actually named in a gap (an unresolved gap actor slug is dropped, not a node).
    entity_ids: set[UUID] = set()
    for e in edges:
        entity_ids.add(e.a_entity_id)
        entity_ids.add(e.b_entity_id)
    for f in forums:
        entity_ids.add(f.entity_id)

    entities_by_id: dict[UUID, Entity] = {}
    if entity_ids:
        rows = (await session.execute(select(Entity).where(Entity.id.in_(entity_ids)))).scalars().all()
        entities_by_id = {e.id: e for e in rows}
    entities_by_slug = {e.slug: e for e in entities_by_id.values()}

    gap_slugs = {slug for g in gaps for slug in (g.actor_slugs or [])}
    missing = gap_slugs - set(entities_by_slug)
    if missing:
        rows = (await session.execute(select(Entity).where(Entity.slug.in_(missing)))).scalars().all()
        for e in rows:
            entities_by_id[e.id] = e
            entities_by_slug[e.slug] = e

    degree: dict[UUID, int] = {}
    for e in edges:
        degree[e.a_entity_id] = degree.get(e.a_entity_id, 0) + 1
        degree[e.b_entity_id] = degree.get(e.b_entity_id, 0) + 1

    counts = await _signals_30d(session, list(entities_by_id.keys()))

    nodes = [
        {**entity_brief(e), "degree": degree.get(e.id, 0), "signals_30d": counts.get(e.id, 0)}
        for e in entities_by_id.values()
    ]

    signal_ids = [e.signal_id for e in edges if e.signal_id is not None]
    signals_by_id: dict[UUID, Signal] = {}
    if signal_ids:
        rows = (
            await session.execute(
                select(Signal).options(selectinload(Signal.feed_item)).where(Signal.id.in_(signal_ids))
            )
        ).scalars().all()
        signals_by_id = {s.id: s for s in rows}

    def _edge_out(e: Edge) -> dict:
        a = entities_by_id.get(e.a_entity_id)
        b = entities_by_id.get(e.b_entity_id)
        sig = signals_by_id.get(e.signal_id) if e.signal_id else None
        return {
            "id": str(e.id),
            "a": a.slug if a else None,
            "b": b.slug if b else None,
            "relation": e.relation,
            "origin": e.origin,
            "confidence": e.confidence,
            "evidence_de": e.evidence_de,
            "evidence_en": e.evidence_en,
            "quote": e.quote,
            "brief_ref": e.brief_ref,
            "signal": (
                {
                    "id": str(sig.id),
                    "headline_de": sig.headline_de,
                    "headline_en": sig.headline_en,
                    "url": sig.feed_item.url if sig.feed_item else None,
                    "published_at": sig.published_at.isoformat() if sig.published_at else None,
                }
                if sig is not None
                else None
            ),
        }

    def _forum_out(f: ForumProfile) -> dict:
        ent = entities_by_id.get(f.entity_id)
        return {
            "slug": ent.slug if ent else None,
            "name": ent.name if ent else None,
            "convener_de": f.convener_de,
            "attendance_visible": f.attendance_visible,
            "public_minutes": f.public_minutes,
            "treatment_de": f.treatment_de,
            "treatment_en": f.treatment_en,
            "brief_ref": f.brief_ref,
        }

    def _gap_out(g: NetworkGap) -> dict:
        return {
            "id": str(g.id),
            "kind": g.kind,
            "title_de": g.title_de,
            "title_en": g.title_en,
            "detail_de": g.detail_de,
            "detail_en": g.detail_en,
            "actor_slugs": [slug for slug in (g.actor_slugs or []) if slug in entities_by_slug],
        }

    return {
        "nodes": nodes,
        "edges": [_edge_out(e) for e in edges],
        "forums": [_forum_out(f) for f in forums],
        "gaps": [_gap_out(g) for g in gaps],
    }
