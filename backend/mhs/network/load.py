"""Load `data/network.yaml` (spec §4.3): the report's own edges, the standing
coordination forums and the known gaps. Idempotent — safe to re-run on every
`scripts/load_sources.py` pass alongside the entity seed it depends on.

Edges from the report carry no signal (origin "report"); they are upserted on
(a, b, relation, origin="report") so a second load updates evidence text in place
rather than duplicating rows. Forum profiles are upserted by entity id. Gaps have
no natural key in the report beyond their position, so they are replaced wholesale
on every load with `sort` set to file order.
"""
from __future__ import annotations

from pathlib import Path

import yaml
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhs.db.models import Edge, Entity, ForumProfile, NetworkGap


async def _entities_by_slug(session: AsyncSession) -> dict[str, Entity]:
    return {e.slug: e for e in (await session.execute(select(Entity))).scalars()}


async def load_network(session: AsyncSession, path: Path) -> dict[str, int]:
    raw = yaml.safe_load(Path(path).read_text()) or {}
    by_slug = await _entities_by_slug(session)

    def _entity(slug: str) -> Entity:
        ent = by_slug.get(slug)
        if ent is None:
            raise ValueError(f"network.yaml: unknown entity slug {slug!r}")
        return ent

    edge_rows = raw.get("edges", []) or []
    for row in edge_rows:
        a, b = _entity(row["a"]), _entity(row["b"])
        edge = (
            await session.execute(
                select(Edge).where(
                    Edge.a_entity_id == a.id,
                    Edge.b_entity_id == b.id,
                    Edge.relation == row["relation"],
                    Edge.origin == "report",
                )
            )
        ).scalar_one_or_none()
        if edge is None:
            edge = Edge(a_entity_id=a.id, b_entity_id=b.id, relation=row["relation"], origin="report")
            session.add(edge)
        edge.confidence = row.get("confidence", "medium")
        edge.brief_ref = row.get("brief_ref")
        edge.evidence_de = row.get("evidence_de")
        edge.evidence_en = row.get("evidence_en")
    await session.flush()

    forum_rows = raw.get("forums", []) or []
    for row in forum_rows:
        ent = _entity(row["slug"])
        profile = await session.get(ForumProfile, ent.id)
        if profile is None:
            profile = ForumProfile(entity_id=ent.id)
            session.add(profile)
        profile.convener_de = row["convener_de"]
        profile.attendance_visible = bool(row.get("attendance_visible", False))
        profile.public_minutes = bool(row.get("public_minutes", False))
        profile.treatment_de = row["treatment_de"]
        profile.treatment_en = row["treatment_en"]
        profile.brief_ref = row.get("brief_ref")
    await session.flush()

    gap_rows = raw.get("gaps", []) or []
    await session.execute(delete(NetworkGap))
    for sort, row in enumerate(gap_rows):
        session.add(
            NetworkGap(
                sort=sort,
                kind=row["kind"],
                title_de=row["title_de"],
                title_en=row["title_en"],
                detail_de=row["detail_de"],
                detail_en=row["detail_en"],
                actor_slugs=list(row.get("actors", []) or []),
            )
        )
    await session.flush()
    await session.commit()

    return {"edges": len(edge_rows), "forums": len(forum_rows), "gaps": len(gap_rows)}
