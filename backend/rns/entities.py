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
