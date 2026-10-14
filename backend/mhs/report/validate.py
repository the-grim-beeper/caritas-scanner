"""Provenance validator for the Lagebericht: every signal, event, judgement and question id
it cites must be one it was given, every layer and movement must be real, both languages
must be present, and the Friday note must be the 2–4 paragraphs of plain prose it claims
to be, resting on at least one signal. When the caller passes the numbers found in the
input, a figure in the Friday note that the input does not contain is rejected too. The
report is never stored with a dangling claim."""
from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ValidationError

from mhs import vocab
from mhs.report.schema import MOVEMENTS

MIN_FRIDAY_PARAGRAPHS = 2
MAX_FRIDAY_PARAGRAPHS = 4

_PARAGRAPH_BREAK = re.compile(r"\n[ \t]*\n")
_HEADING = re.compile(r"^\s*#")
_BULLET = re.compile(r"^\s*[-*•–]\s")
_NUMBERED = re.compile(r"^\s*\d+[.)]\s")
# Single digits are left alone: "drei" and "3" are the same word, and counting what is in
# the input is not inventing. Two digits and more are figures, dates and years.
_FIGURE = re.compile(r"\d{2,}")
_ID_KEY = re.compile(r"(^id$|_id$|_ids$)")


class ReportProvenanceError(ValueError):
    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("; ".join(problems))


class ReportQuestion(BaseModel):
    question_id: str
    movement: str
    note_de: str
    note_en: str
    judgement_ids: list[str]


class ReportItem(BaseModel):
    signal_id: str
    note_de: str
    note_en: str


class ReportSection(BaseModel):
    layer: str
    items: list[ReportItem]


class ReportChain(BaseModel):
    title_de: str
    title_en: str
    signal_ids: list[str]


class ReportWatch(BaseModel):
    event_id: str
    why_de: str
    why_en: str


class ReportPayload(BaseModel):
    lead_de: str
    lead_en: str
    questions: list[ReportQuestion]
    sections: list[ReportSection]
    chains: list[ReportChain]
    watch: list[ReportWatch]
    friday_de: str
    friday_en: str
    friday_signal_ids: list[str]


def friday_paragraphs(text: str) -> list[str]:
    """Paragraphs are separated by a blank line; a single newline wraps within one."""
    return [p.strip() for p in _PARAGRAPH_BREAK.split(text.strip()) if p.strip()]


def figures(text: str) -> set[str]:
    return set(_FIGURE.findall(text))


def input_numbers(obj: Any) -> set[str]:
    """Every figure the model was shown, skipping ids (a UUID is full of digits that mean
    nothing) and float scores (internal, not something to quote to a client)."""
    out: set[str] = set()

    def walk(value: Any, key: str = "") -> None:
        if _ID_KEY.search(key):
            return
        if isinstance(value, dict):
            for k, v in value.items():
                walk(v, str(k))
        elif isinstance(value, (list, tuple)):
            for v in value:
                walk(v, key)
        elif isinstance(value, str):
            out.update(figures(value))
        elif isinstance(value, int) and not isinstance(value, bool):
            out.update(figures(str(value)))

    walk(obj)
    return out


def _friday_problems(field: str, text: str, numbers: set[str] | None) -> list[str]:
    problems: list[str] = []
    paras = friday_paragraphs(text)
    if not MIN_FRIDAY_PARAGRAPHS <= len(paras) <= MAX_FRIDAY_PARAGRAPHS:
        problems.append(f"{field} has {len(paras)} paragraph(s); write {MIN_FRIDAY_PARAGRAPHS}–"
                        f"{MAX_FRIDAY_PARAGRAPHS} paragraphs separated by a blank line")
    lines = text.splitlines()
    if any(_HEADING.match(ln) or _BULLET.match(ln) for ln in lines) or \
            sum(1 for ln in lines if _NUMBERED.match(ln)) >= 2:
        problems.append(f"{field} contains a heading or a list; write plain paragraphs")
    if numbers is not None:
        for n in sorted(figures(text) - numbers):
            problems.append(f"{field}: the number {n} does not appear in the input; use only figures from the input")
    return problems


def _dedupe(ids: list[str]) -> list[str]:
    return list(dict.fromkeys(ids))


def validate_report(
    raw: dict,
    *,
    signal_ids: set[str],
    event_ids: set[str],
    judgement_ids: set[str],
    question_ids: set[str],
    numbers: set[str] | None = None,
) -> dict:
    try:
        parsed = ReportPayload.model_validate(raw)
    except ValidationError as exc:
        raise ReportProvenanceError([f"shape: {'.'.join(map(str, e['loc']))} {e['msg']}" for e in exc.errors()]) from exc

    problems: list[str] = []
    for field in ("lead_de", "lead_en"):
        if not getattr(parsed, field).strip():
            problems.append(f"{field} is empty")

    for q in parsed.questions:
        if q.question_id not in question_ids:
            problems.append(f"unknown question {q.question_id!r}")
        if q.movement not in MOVEMENTS:
            problems.append(f"question {q.question_id}: movement {q.movement!r} not in {list(MOVEMENTS)}")
        for jid in q.judgement_ids:
            if jid not in judgement_ids:
                problems.append(f"question {q.question_id} cites unknown judgement {jid!r}")
        if not q.note_de.strip() or not q.note_en.strip():
            problems.append(f"question {q.question_id} note missing a language")

    for sec in parsed.sections:
        if sec.layer not in vocab.LAYERS:
            problems.append(f"unknown layer {sec.layer!r}")
        for item in sec.items:
            if item.signal_id not in signal_ids:
                problems.append(f"section {sec.layer} cites unknown signal {item.signal_id!r}")
            if not item.note_de.strip() or not item.note_en.strip():
                problems.append(f"note for {item.signal_id} missing a language")

    for chain in parsed.chains:
        for sid in chain.signal_ids:
            if sid not in signal_ids:
                problems.append(f"chain {chain.title_de!r} cites unknown signal {sid!r}")
        if not chain.title_de.strip() or not chain.title_en.strip():
            problems.append(f"chain {chain.title_de or chain.title_en!r} missing a language")

    for w in parsed.watch:
        if w.event_id not in event_ids:
            problems.append(f"watch cites unknown event {w.event_id!r}")
        if not w.why_de.strip() or not w.why_en.strip():
            problems.append(f"watch {w.event_id} missing a language")

    if not parsed.friday_signal_ids:
        problems.append("friday_signal_ids is empty; the Friday note must rest on at least one signal")
    for sid in parsed.friday_signal_ids:
        if sid not in signal_ids:
            problems.append(f"friday_signal_ids cites unknown signal {sid!r}")
    problems += _friday_problems("friday_de", parsed.friday_de, numbers)
    problems += _friday_problems("friday_en", parsed.friday_en, numbers)

    if problems:
        raise ReportProvenanceError(problems)

    out = parsed.model_dump()
    for field in ("friday_de", "friday_en"):
        out[field] = "\n\n".join(friday_paragraphs(out[field]))
    out["friday_signal_ids"] = _dedupe(out["friday_signal_ids"])
    for q in out["questions"]:
        q["judgement_ids"] = _dedupe(q["judgement_ids"])
    return out
