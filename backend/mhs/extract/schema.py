"""What one extraction returns — the same shape from Claude and from the mock."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from mhs import vocab

_DATE = {"type": ["string", "null"], "description": "ISO date YYYY-MM-DD, or null"}

EVENT_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "organizer": {"type": ["string", "null"]},
        "location": {"type": ["string", "null"]},
        "start_date": _DATE,
        "end_date": _DATE,
        "deadline": {**_DATE, "description": "Application/consultation/tender deadline — distinct from the event date"},
        "topic": {"type": ["string", "null"], "description": "One of the topic codes, or null"},
        "registration_url": {"type": ["string", "null"]},
        "funding_program": {"type": ["string", "null"]},
        "target_audience": {"type": ["string", "null"]},
    },
    "required": ["name", "organizer", "location", "start_date", "end_date", "deadline", "topic",
                 "registration_url", "funding_program", "target_audience"],
    "additionalProperties": False,
}

RELATION_SCHEMA = {
    "type": "object",
    "properties": {
        "a": {"type": "string", "description": "First actor, as named in the text"},
        "b": {"type": "string", "description": "Second actor, as named in the text"},
        "relation": {"type": "string", "enum": list(vocab.RELATIONS), "description": "Reads: a <relation> b"},
        "quote": {"type": "string", "description": "The verbatim phrase of the text that states the relation"},
    },
    "required": ["a", "b", "relation", "quote"],
    "additionalProperties": False,
}

_NAMES = {"type": "array", "items": {"type": "string"}}

EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "is_signal": {"type": "boolean"},
        "headline_en": {"type": "string", "description": "One factual sentence in English."},
        "headline_de": {"type": "string", "description": "One factual sentence in German."},
        "summary_en": {"type": "string", "description": "2–3 sentences of substance, English."},
        "summary_de": {"type": "string", "description": "2–3 sentences of substance, German."},
        "signal_type": {"type": "string", "enum": vocab.SIGNAL_TYPES},
        "topics": {"type": "array", "items": {"type": "string", "enum": list(vocab.TOPICS)}},
        "places": _NAMES,
        "organisations": _NAMES,
        "forums": _NAMES,
        "programmes": _NAMES,
        "offices": {**_NAMES, "description": "Roles only (e.g. Erster Bürgermeister Waakirchen), never a person's name"},
        # No minimum/maximum/maxItems: structured outputs reject them; from_payload clamps and caps.
        "regional_relevance": {"type": "number", "description": "0–1"},
        "consequence": {"type": "number", "description": "0–1"},
        "forward_lag": {"type": "number", "description": "0–1"},
        "item_date": {**_DATE, "description": "The date the item itself states for its publication or, failing that, for the development it reports; YYYY-MM-DD, or null"},
        "events": {"type": "array", "items": EVENT_SCHEMA},
        "relations": {"type": "array", "items": RELATION_SCHEMA},
    },
    "required": ["is_signal", "headline_en", "headline_de", "summary_en", "summary_de", "signal_type",
                 "topics", "places", "organisations", "forums", "programmes", "offices",
                 "regional_relevance", "consequence", "forward_lag", "item_date", "events", "relations"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class EventDraft:
    name: str
    organizer: str | None = None
    location: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    deadline: date | None = None
    topic: str | None = None
    registration_url: str | None = None
    funding_program: str | None = None
    target_audience: str | None = None


@dataclass(frozen=True)
class RelationDraft:
    a: str
    b: str
    relation: str
    quote: str


@dataclass(frozen=True)
class ExtractionResult:
    is_signal: bool
    headline_en: str = ""
    headline_de: str = ""
    summary_en: str = ""
    summary_de: str = ""
    signal_type: str = "announcement"
    topics: tuple[str, ...] = ()
    places: tuple[str, ...] = ()
    organisations: tuple[str, ...] = ()
    forums: tuple[str, ...] = ()
    programmes: tuple[str, ...] = ()
    offices: tuple[str, ...] = ()
    regional_relevance: float = 0.0
    consequence: float = 0.0
    forward_lag: float = 0.0
    item_date: date | None = None
    events: tuple[EventDraft, ...] = field(default_factory=tuple)
    relations: tuple[RelationDraft, ...] = field(default_factory=tuple)


def _date(value) -> date | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _clamp(x) -> float:
    try:
        return max(0.0, min(1.0, float(x)))
    except (TypeError, ValueError):
        return 0.0


MAX_NAMES = 10
MAX_RELATIONS = 8

# An office is a role. A string with none of these stems names a person, and persons are
# never entities (spec §1, non-goals), whatever the model was told.
_ROLE_STEMS = (
    "bürgermeister", "landrat", "landrät", "dekan", "direktor", "leitung", "leiter", "vorsitz", "vorstand",
    "geschäftsführ", "präsident", "minister", "beauftragt", "referent", "kämmer", "pfarrer", "sprecher",
    "abgeordnet", "koordinator", "manager", "lotse", "lotsin", "seelsorge", "chef", "head", "mayor",
    "director",
)
# Kreisrat, Gemeinderätin, Stadträte — "rat" closing a compound, so neither "Strathmann" nor
# "Murat" is a role.
_COUNCILLOR = re.compile(r"\w{3,}r[aä]t(?:in|innen|e)?\b")


def _names(data: dict, key: str) -> tuple[str, ...]:
    out = [str(p).strip() for p in (data.get(key) or []) if p is not None and str(p).strip()]
    return tuple(dict.fromkeys(out))[:MAX_NAMES]


def _is_office(name: str) -> bool:
    low = name.lower()
    return any(stem in low for stem in _ROLE_STEMS) or _COUNCILLOR.search(low) is not None


def _relations(data: dict) -> tuple[RelationDraft, ...]:
    out: list[RelationDraft] = []
    for r in data.get("relations") or []:
        if not isinstance(r, dict) or r.get("relation") not in vocab.RELATIONS:
            continue
        a, b, quote = (str(r.get(k) or "").strip() for k in ("a", "b", "quote"))
        # A relation without both ends, or without the words that state it, is not evidence.
        if not a or not b or not quote:
            continue
        out.append(RelationDraft(a=a[:300], b=b[:300], relation=r["relation"], quote=quote))
    return tuple(out[:MAX_RELATIONS])


def from_payload(data: dict) -> ExtractionResult:
    """Coerce a model payload defensively: tagging degrades, it never crashes."""
    topics = tuple(t for t in (data.get("topics") or []) if t in vocab.TOPICS)
    signal_type = data.get("signal_type") if data.get("signal_type") in vocab.SIGNAL_TYPES else "announcement"
    events = tuple(
        EventDraft(
            name=str(e.get("name") or "")[:400],
            organizer=e.get("organizer"),
            location=e.get("location"),
            start_date=_date(e.get("start_date")),
            end_date=_date(e.get("end_date")),
            deadline=_date(e.get("deadline")),
            topic=e.get("topic") if e.get("topic") in vocab.TOPICS else None,
            registration_url=e.get("registration_url"),
            funding_program=e.get("funding_program"),
            target_audience=e.get("target_audience"),
        )
        for e in (data.get("events") or [])
        if isinstance(e, dict) and e.get("name")
    )
    return ExtractionResult(
        is_signal=bool(data.get("is_signal")),
        headline_en=str(data.get("headline_en") or "")[:600],
        headline_de=str(data.get("headline_de") or "")[:600],
        summary_en=str(data.get("summary_en") or ""),
        summary_de=str(data.get("summary_de") or ""),
        signal_type=signal_type,
        topics=topics,
        places=_names(data, "places"),
        organisations=_names(data, "organisations"),
        forums=_names(data, "forums"),
        programmes=_names(data, "programmes"),
        offices=tuple(o for o in _names(data, "offices") if _is_office(o)),
        regional_relevance=_clamp(data.get("regional_relevance")),
        consequence=_clamp(data.get("consequence")),
        forward_lag=_clamp(data.get("forward_lag")),
        item_date=_date(data.get("item_date")),
        events=events,
        relations=_relations(data),
    )
