"""Entity dictionary: seed loading (resolver is added with extraction)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from rns import vocab

_SECTION_TO_KIND = {
    "places": "place",
    "organisations": "organisation",
    "projects": "project",
    "funds": "fund",
}


@dataclass(frozen=True)
class EntitySeed:
    slug: str
    kind: str
    name: str
    aliases: tuple[str, ...] = field(default_factory=tuple)


def load_seed(path: Path) -> list[EntitySeed]:
    raw = yaml.safe_load(Path(path).read_text()) or {}
    seeds: list[EntitySeed] = []
    seen: set[str] = set()
    for section, kind in _SECTION_TO_KIND.items():
        assert kind in vocab.ENTITY_KINDS
        for item in raw.get(section, []) or []:
            slug = item["slug"]
            if slug in seen:
                raise ValueError(f"duplicate entity slug {slug!r}")
            seen.add(slug)
            seeds.append(
                EntitySeed(
                    slug=slug,
                    kind=kind,
                    name=item["name"],
                    aliases=tuple(item.get("aliases", []) or []),
                )
            )
    return seeds


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------
import re  # noqa: E402
import unicodedata  # noqa: E402

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from rns.db.models import Entity  # noqa: E402

_OPEN_KINDS = {"organisation", "project", "fund"}


def slugify(name: str) -> str:
    text = unicodedata.normalize("NFKD", name)
    text = text.replace("ß", "ss")
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return text[:150] or "entity"


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


async def resolve(session: AsyncSession, names: list[str], *, kind: str) -> list[Entity]:
    """Map free-text names onto dictionary entities by name/alias (case-insensitive).

    Places are a closed set: an unknown place is dropped. Organisations, projects and
    funds are open: an unknown one is created, unseeded, so it can accumulate a timeline."""
    if not names:
        return []
    rows = (await session.execute(select(Entity).where(Entity.kind == kind))).scalars().all()
    index: dict[str, Entity] = {}
    for e in rows:
        index[_norm(e.name)] = e
        index[e.slug] = e
        for a in e.aliases or []:
            index.setdefault(_norm(a), e)
    out: list[Entity] = []
    seen: set = set()
    for raw in names:
        if not raw or not raw.strip():
            continue
        key = _norm(raw)
        slug = slugify(raw)
        ent = index.get(key) or index.get(slug)
        if ent is None:
            # An entity is one thing whatever kind the extractor guessed this time:
            # slugs are unique across kinds, so look the slug up unfiltered before creating.
            ent = (await session.execute(select(Entity).where(Entity.slug == slug))).scalar_one_or_none()
        if ent is None and kind in _OPEN_KINDS:
            ent = Entity(slug=slug, kind=kind, name=raw.strip()[:300], aliases=[], seeded=False)
            session.add(ent)
            await session.flush()
        if ent is not None:
            index[key] = ent
            index[ent.slug] = ent
        if ent is None or ent.id in seen:
            continue
        seen.add(ent.id)
        out.append(ent)
    return out
