"""Load the catalogue ∩ live results into the sources table, and seed entities.
Idempotent on slug; never deletes a source."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mhs.calendar import load_calendar  # noqa: E402
from mhs.db.engine import session_factory  # noqa: E402
from mhs.db.models import Entity, Source  # noqa: E402
from mhs.entities import load_seed  # noqa: E402
from mhs.sources.catalogue import SourceRow, load_catalogue, load_live, merge_for_load  # noqa: E402

DATA = Path(__file__).resolve().parents[2] / "data"

_FIELDS = (
    "name", "layer", "authority", "scope", "places", "language", "method", "url", "homepage",
    "priority", "cadence", "notes", "brief_ref", "item_selector", "collect",
    "not_collected_reason", "items_at_check",
)


async def upsert_sources(session: AsyncSession, rows: list[SourceRow]) -> tuple[int, int]:
    existing = {s.slug: s for s in (await session.execute(select(Source))).scalars()}
    created = updated = 0
    for row in rows:
        src = existing.get(row.slug)
        if src is None:
            src = Source(slug=row.slug)
            session.add(src)
            created += 1
        else:
            updated += 1
        for f in _FIELDS:
            setattr(src, f, getattr(row, f))
        # A source that has just been re-verified gets a clean bill of health.
        if row.collect and src.status == "quarantined":
            src.status = "active"
            src.consecutive_failures = 0
    await session.commit()
    return created, updated


async def upsert_entities(session: AsyncSession, seeds) -> int:
    existing = {e.slug: e for e in (await session.execute(select(Entity))).scalars()}
    n = 0
    for s in seeds:
        ent = existing.get(s.slug)
        if ent is None:
            ent = Entity(slug=s.slug)
            session.add(ent)
            n += 1
        ent.kind, ent.name, ent.aliases, ent.seeded = s.kind, s.name, list(s.aliases), True
    await session.commit()
    return n


async def main() -> None:
    rows = merge_for_load(load_catalogue(DATA / "sources.yaml"), load_live(DATA / "sources-live.json"))
    seeds = load_seed(DATA / "entities.yaml")
    async with session_factory()() as session:
        c, u = await upsert_sources(session, rows)
        e = await upsert_entities(session, seeds)
        print(f"calendar: {await load_calendar(session, DATA / 'calendar.yaml')} entries loaded")
    collected = sum(1 for r in rows if r.collect)
    print(f"sources: {c} created, {u} updated, {collected}/{len(rows)} collected; entities seeded: {e} new of {len(seeds)}")


if __name__ == "__main__":
    asyncio.run(main())
