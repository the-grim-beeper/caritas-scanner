"""Provenance validator: every id the digest cites must be one it was given, every
layer must be real, and both languages must be present. The digest is rejected
otherwise — never stored with a dangling claim."""
from __future__ import annotations

from pydantic import BaseModel, ValidationError

from mhs import vocab


class DigestProvenanceError(ValueError):
    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("; ".join(problems))


class DigestItem(BaseModel):
    signal_id: str
    note_en: str
    note_de: str


class DigestSection(BaseModel):
    layer: str
    items: list[DigestItem]


class DigestChain(BaseModel):
    title_en: str
    title_de: str
    signal_ids: list[str]


class DigestWatch(BaseModel):
    event_id: str
    why_en: str
    why_de: str


class DigestPayload(BaseModel):
    lead_en: str
    lead_de: str
    sections: list[DigestSection]
    chains: list[DigestChain]
    watch: list[DigestWatch]


def validate_digest(payload: dict, *, signal_ids: set[str], event_ids: set[str]) -> DigestPayload:
    try:
        parsed = DigestPayload.model_validate(payload)
    except ValidationError as exc:
        raise DigestProvenanceError([f"shape: {e['loc']} {e['msg']}" for e in exc.errors()]) from exc

    problems: list[str] = []
    if not parsed.lead_en.strip():
        problems.append("lead_en is empty")
    if not parsed.lead_de.strip():
        problems.append("lead_de is empty")
    for sec in parsed.sections:
        if sec.layer not in vocab.LAYERS:
            problems.append(f"unknown layer {sec.layer!r}")
        for item in sec.items:
            if item.signal_id not in signal_ids:
                problems.append(f"section {sec.layer} cites unknown signal {item.signal_id!r}")
            if not item.note_en.strip() or not item.note_de.strip():
                problems.append(f"note for {item.signal_id} missing a language")
    for chain in parsed.chains:
        for sid in chain.signal_ids:
            if sid not in signal_ids:
                problems.append(f"chain {chain.title_en!r} cites unknown signal {sid!r}")
        if not chain.title_de.strip():
            problems.append(f"chain {chain.title_en!r} missing German title")
    for w in parsed.watch:
        if w.event_id not in event_ids:
            problems.append(f"watch cites unknown event {w.event_id!r}")
        if not w.why_de.strip() or not w.why_en.strip():
            problems.append(f"watch {w.event_id} missing a language")
    if problems:
        raise DigestProvenanceError(problems)
    return parsed
