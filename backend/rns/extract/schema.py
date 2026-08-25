"""What one extraction returns — the same shape from Claude and from the mock."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from rns import vocab

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
        "topic": {"type": ["string", "null"], "enum": [*vocab.TOPICS, None]},
        "registration_url": {"type": ["string", "null"]},
        "funding_program": {"type": ["string", "null"]},
        "target_audience": {"type": ["string", "null"]},
    },
    "required": ["name", "organizer", "location", "start_date", "end_date", "deadline", "topic",
                 "registration_url", "funding_program", "target_audience"],
    "additionalProperties": False,
}

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
        "places": {"type": "array", "items": {"type": "string"}},
        "organisations": {"type": "array", "items": {"type": "string"}},
        "projects": {"type": "array", "items": {"type": "string"}},
        "regional_relevance": {"type": "number", "minimum": 0, "maximum": 1},
        "economic_materiality": {"type": "number", "minimum": 0, "maximum": 1},
        "forward_lag": {"type": "number", "minimum": 0, "maximum": 1},
        "events": {"type": "array", "items": EVENT_SCHEMA},
    },
    "required": ["is_signal", "headline_en", "headline_de", "summary_en", "summary_de", "signal_type",
                 "topics", "places", "organisations", "projects", "regional_relevance",
                 "economic_materiality", "forward_lag", "events"],
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
    projects: tuple[str, ...] = ()
    regional_relevance: float = 0.0
    economic_materiality: float = 0.0
    forward_lag: float = 0.0
    events: tuple[EventDraft, ...] = field(default_factory=tuple)


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
        places=tuple(str(p) for p in (data.get("places") or []))[:10],
        organisations=tuple(str(p) for p in (data.get("organisations") or []))[:10],
        projects=tuple(str(p) for p in (data.get("projects") or []))[:10],
        regional_relevance=_clamp(data.get("regional_relevance")),
        economic_materiality=_clamp(data.get("economic_materiality")),
        forward_lag=_clamp(data.get("forward_lag")),
        events=events,
    )
