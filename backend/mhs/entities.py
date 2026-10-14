"""Entity dictionary: seed loading and the resolver that maps extracted names onto it.

Five kinds (spec §2.4). Places are a closed set; organisations, forums, programmes and
offices grow as extraction meets new names. Offices are roles, never people."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhs import vocab
from mhs.db.models import Entity

_SECTION_TO_KIND = {
    "places": "place",
    "organisations": "organisation",
    "forums": "forum",
    "programmes": "programme",
    "offices": "office",
}


@dataclass(frozen=True)
class EntitySeed:
    slug: str
    kind: str
    name: str
    aliases: tuple[str, ...] = ()
    actor_kind: str | None = None


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
            actor_kind = item.get("actor_kind")
            if actor_kind is not None and actor_kind not in vocab.ACTOR_KINDS:
                raise ValueError(f"{slug}: unknown actor_kind {actor_kind!r}; expected one of {vocab.ACTOR_KINDS}")
            seeds.append(
                EntitySeed(
                    slug=slug,
                    kind=kind,
                    name=item["name"],
                    aliases=tuple(item.get("aliases", []) or []),
                    actor_kind=actor_kind,
                )
            )
    return seeds


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------
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

    Places are a closed set: an unknown place is dropped. The open kinds
    (vocab.OPEN_ENTITY_KINDS) are matched across each other before anything is created —
    the extractor often files a body under "forums" one day and "organisations" the next,
    and that must not split one actor in two. An unknown open-kind name is created,
    unseeded, so it can accumulate a timeline."""
    if not names:
        return []
    open_kind = kind in vocab.OPEN_ENTITY_KINDS
    others = [k for k in vocab.ENTITY_KINDS if k in vocab.OPEN_ENTITY_KINDS and k != kind]
    kinds = [kind, *others] if open_kind else [kind]
    rows = (await session.execute(select(Entity).where(Entity.kind.in_(kinds)))).scalars().all()
    # Precedence: same kind before other kinds; within a kind, a name before an alias.
    index: dict[str, Entity] = {}
    for k in kinds:
        group = [e for e in rows if e.kind == k]
        for e in group:
            index.setdefault(_norm(e.name), e)
            index.setdefault(e.slug, e)
        for e in group:
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
            # Slugs are unique across all kinds: look the slug up unfiltered before creating.
            ent = (await session.execute(select(Entity).where(Entity.slug == slug))).scalar_one_or_none()
        if ent is None and open_kind:
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
