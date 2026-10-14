"""Turn extracted `RelationCandidate` rows into provenance-carrying edges.

Each candidate's two ends are free text read by the extractor. `mhs.entities.resolve`
matches free text onto an entity across the open kinds (organisation, forum, programme,
office — in that order, since `resolve(..., kind="organisation")` tries that kind first
and falls back through the rest) and, finding none, creates a new organisation. That
"create if nothing matches" behaviour is right for an unrecognised body but wrong for a
place: a county or a municipality is never an actor, so a relation naming one as an
endpoint must drop, not mint a shadow organisation with the place's name. This module
therefore checks seeded places first, before handing the text to `resolve`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhs.db.models import Edge, Entity, RelationCandidate
from mhs.entities import resolve


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


@dataclass
class NetworkStats:
    candidates: int = 0
    edges_new: int = 0
    dropped: int = 0


async def _place_keys(session: AsyncSession) -> set[str]:
    places = (await session.execute(select(Entity).where(Entity.kind == "place"))).scalars().all()
    keys: set[str] = set()
    for p in places:
        keys.add(_norm(p.name))
        for alias in p.aliases or []:
            keys.add(_norm(alias))
    return keys


async def _resolve_end(session: AsyncSession, text: str, place_keys: set[str]) -> Entity | None:
    if not text or not text.strip():
        return None
    if _norm(text) in place_keys:
        return None  # a place is never an actor
    ents = await resolve(session, [text], kind="organisation")
    return ents[0] if ents else None


async def resolve_candidates(session: AsyncSession) -> NetworkStats:
    stats = NetworkStats()
    pending = (
        await session.execute(select(RelationCandidate).where(RelationCandidate.processed.is_(False)))
    ).scalars().all()
    if not pending:
        return stats
    place_keys = await _place_keys(session)

    for cand in pending:
        stats.candidates += 1
        a = await _resolve_end(session, cand.a_text, place_keys)
        b = await _resolve_end(session, cand.b_text, place_keys)
        cand.processed = True

        if a is None or b is None or a.id == b.id:
            stats.dropped += 1
            continue

        duplicate = (
            await session.execute(
                select(Edge).where(
                    Edge.a_entity_id == a.id,
                    Edge.b_entity_id == b.id,
                    Edge.relation == cand.relation,
                    Edge.signal_id == cand.signal_id,
                )
            )
        ).scalar_one_or_none()
        if duplicate is not None:
            stats.dropped += 1
            continue

        session.add(
            Edge(
                a_entity_id=a.id,
                b_entity_id=b.id,
                relation=cand.relation,
                origin="signal",
                signal_id=cand.signal_id,
                quote=cand.quote,
                confidence="medium",
            )
        )
        stats.edges_new += 1

    await session.flush()
    return stats
