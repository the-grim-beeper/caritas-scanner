"""Source catalogue: the brief's intent (sources.yaml) merged with what actually
resolved (sources-live.json). Only the intersection is collected; nothing catalogued
is dropped, so Coverage can name every source that is *not* being watched, and why."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml
from pydantic import BaseModel, ValidationError, field_validator, model_validator

from mhs import vocab

COLLECTED_METHODS = vocab.COLLECTED_METHODS


class CatalogueError(ValueError):
    pass


class CatalogueEntry(BaseModel):
    slug: str
    name: str
    layer: str
    authority: str
    scope: str
    places: list[str] = []
    language: str = "de"
    method: str
    url: str | None = None
    homepage: str | None = None
    priority: str = "thematic"
    cadence: str | None = None
    notes: str | None = None
    brief_ref: str | None = None
    item_selector: str | None = None
    query: str | None = None

    @field_validator("layer")
    @classmethod
    def _layer(cls, v: str) -> str:
        if v not in vocab.LAYERS:
            raise ValueError(f"unknown layer {v!r}; expected one of {list(vocab.LAYERS)}")
        return v

    @field_validator("authority")
    @classmethod
    def _authority(cls, v: str) -> str:
        if v not in vocab.AUTHORITY_WEIGHTS:
            raise ValueError(f"unknown authority {v!r}")
        return v

    @field_validator("scope")
    @classmethod
    def _scope(cls, v: str) -> str:
        if v not in vocab.SCOPES:
            raise ValueError(f"unknown scope {v!r}")
        return v

    @field_validator("method")
    @classmethod
    def _method(cls, v: str) -> str:
        if v not in vocab.METHODS:
            raise ValueError(f"unknown method {v!r}")
        return v

    @field_validator("priority")
    @classmethod
    def _priority(cls, v: str) -> str:
        if v not in vocab.PRIORITIES:
            raise ValueError(f"unknown priority {v!r}")
        return v

    @model_validator(mode="after")
    def _needs_a_target(self) -> "CatalogueEntry":
        # query searches for its expression; diff and pdf watch one exact page; rss and page
        # may still be autodiscovered from a homepage.
        if self.method == "query":
            if not (self.query and self.query.strip()):
                raise ValueError(f"{self.slug}: query source needs a query")
        elif self.method in ("diff", "pdf"):
            if not self.url:
                raise ValueError(f"{self.slug}: {self.method} source needs a url")
        elif self.method in COLLECTED_METHODS and not (self.url or self.homepage):
            raise ValueError(f"{self.slug}: {self.method} source needs a url or a homepage")
        return self


@dataclass(frozen=True)
class LiveResult:
    slug: str
    method: str  # what actually resolved
    resolved_url: str
    item_count: int
    checked_at: datetime | None = None


@dataclass
class SourceRow:
    """What goes into the `sources` table."""

    slug: str
    name: str
    layer: str
    authority: str
    scope: str
    places: list[str]
    language: str
    method: str
    url: str | None
    homepage: str | None
    priority: str
    cadence: str | None
    notes: str | None
    brief_ref: str | None
    item_selector: str | None
    query: str | None
    collect: bool
    not_collected_reason: str | None
    items_at_check: int | None


def load_catalogue(path: Path) -> list[CatalogueEntry]:
    raw = yaml.safe_load(Path(path).read_text()) or []
    if not isinstance(raw, list):
        raise CatalogueError("catalogue must be a list of sources")
    entries: list[CatalogueEntry] = []
    seen: set[str] = set()
    for i, item in enumerate(raw):
        try:
            entry = CatalogueEntry.model_validate(item)
        except ValidationError as exc:
            raise CatalogueError(f"entry {i} ({item.get('slug', '?')}): {exc}") from exc
        if entry.slug in seen:
            raise CatalogueError(f"duplicate slug {entry.slug!r}")
        seen.add(entry.slug)
        entries.append(entry)
    return entries


def load_live(path: Path) -> dict[str, LiveResult]:
    path = Path(path)
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    checked = data.get("checked_at")
    checked_at = datetime.fromisoformat(checked.replace("Z", "+00:00")) if checked else None
    out: dict[str, LiveResult] = {}
    for r in data.get("results", []):
        out[r["slug"]] = LiveResult(
            slug=r["slug"],
            method=r["method"],
            resolved_url=r["resolved_url"],
            item_count=int(r.get("item_count", 0)),
            checked_at=checked_at,
        )
    return out


def merge_for_load(entries: list[CatalogueEntry], live: dict[str, LiveResult]) -> list[SourceRow]:
    rows: list[SourceRow] = []
    for e in entries:
        common = dict(
            slug=e.slug, name=e.name, layer=e.layer, authority=e.authority, scope=e.scope,
            places=list(e.places), language=e.language, homepage=e.homepage, priority=e.priority,
            cadence=e.cadence, notes=e.notes, brief_ref=e.brief_ref, item_selector=e.item_selector,
            query=e.query,
        )
        if e.method not in COLLECTED_METHODS:
            rows.append(SourceRow(**common, method=e.method, url=e.url, collect=False,
                                  not_collected_reason=f"{e.method} sources are catalogued, not collected (v1)",
                                  items_at_check=None))
            continue
        hit = live.get(e.slug)
        if hit is None:
            rows.append(SourceRow(**common, method=e.method, url=e.url, collect=False,
                                  not_collected_reason="not verified live: no parseable feed or list page at check time",
                                  items_at_check=None))
            continue
        rows.append(SourceRow(**common, method=hit.method, url=hit.resolved_url, collect=True,
                              not_collected_reason=None, items_at_check=hit.item_count))
    return rows
