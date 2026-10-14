"""Provenance validator for the judge. A judgement is kept only if it cites a signal of
its own batch and a real question, uses the controlled direction and strength, carries
both languages, and its quote is a verbatim piece of that signal's text — compared after
normalising case, whitespace, quotation marks and dashes, nothing else. A paraphrase,
a translation or a quote stitched together with an ellipsis is dropped and reported."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from mhs import vocab

MIN_QUOTE_CHARS = 12

_QUOTE_CHARS = "„“”‟\"'‚‘’‛«»‹›"
_DASH_CHARS = "–—‒―‐‑−"
_TRANSLATE = str.maketrans({**{c: '"' for c in _QUOTE_CHARS}, **{c: "-" for c in _DASH_CHARS}})
# Soft hyphens and zero-width characters survive copy-paste from PDFs and CMS pages.
_INVISIBLE = re.compile("[­​‌‍⁠﻿]")
# Wrapping marks and end punctuation are not part of what the quote claims.
_EDGE = ' ".,;:'


class JudgementShapeError(ValueError):
    """The payload is not {"judgements": [...]} at all — distinct from a list of bad items."""


@dataclass
class JudgementDraft:
    signal_id: str
    question_id: str
    direction: str
    strength: str
    quote: str
    rationale_de: str
    rationale_en: str


def normalise(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")  # ligatures, NBSP, composed umlauts
    s = _INVISIBLE.sub("", s)
    s = s.translate(_TRANSLATE).casefold()
    return " ".join(s.split())


def _clean_quote(q: str) -> str:
    """The quote as stored: one line, without the quotation marks the model wrapped it in."""
    return " ".join(q.split()).strip(_QUOTE_CHARS + " ")


def _text(item: dict, key: str) -> str:
    value = item.get(key)
    return value.strip() if isinstance(value, str) else ""


def validate_judgements(
    raw: dict, *, signal_texts: dict[str, str], question_ids: set[str]
) -> tuple[list[JudgementDraft], list[str]]:
    if not isinstance(raw, dict) or not isinstance(raw.get("judgements"), list):
        raise JudgementShapeError(f"expected {{'judgements': [...]}}, got {type(raw).__name__}")

    normalised: dict[str, str] = {}
    kept: list[JudgementDraft] = []
    problems: list[str] = []
    seen: set[tuple[str, str]] = set()

    for i, item in enumerate(raw["judgements"]):
        if not isinstance(item, dict):
            problems.append(f"#{i}: not an object")
            continue
        sid = str(item.get("signal_id") or "").strip()
        qid = str(item.get("question_id") or "").strip()
        tag = f"#{i} ({sid or '?'}/{qid or '?'})"
        direction = _text(item, "direction").lower()
        strength = _text(item, "strength").lower()
        quote = _text(item, "quote")
        rationale_de = _text(item, "rationale_de")
        rationale_en = _text(item, "rationale_en")

        if sid not in signal_texts:
            problems.append(f"{tag}: signal {sid!r} is not in this batch")
            continue
        if qid not in question_ids:
            problems.append(f"{tag}: unknown question {qid!r}")
            continue
        if direction not in vocab.DIRECTIONS:
            problems.append(f"{tag}: direction {direction!r} not in {vocab.DIRECTIONS}")
            continue
        if strength not in vocab.STRENGTH_WEIGHTS:
            problems.append(f"{tag}: strength {strength!r} not in {list(vocab.STRENGTH_WEIGHTS)}")
            continue
        if not rationale_de or not rationale_en:
            problems.append(f"{tag}: rationale missing in {'German' if not rationale_de else 'English'}")
            continue
        needle = normalise(quote).strip(_EDGE)
        if len(needle) < MIN_QUOTE_CHARS:
            problems.append(f"{tag}: quote too short to be evidence: {quote!r}")
            continue
        if sid not in normalised:
            normalised[sid] = normalise(signal_texts[sid])
        if needle not in normalised[sid]:
            problems.append(f"{tag}: quote not found verbatim in the signal text: {quote[:160]!r}")
            continue
        if (sid, qid) in seen:
            problems.append(f"{tag}: second judgement on the same signal and question")
            continue
        seen.add((sid, qid))
        kept.append(JudgementDraft(signal_id=sid, question_id=qid, direction=direction, strength=strength,
                                   quote=_clean_quote(quote), rationale_de=rationale_de, rationale_en=rationale_en))
    return kept, problems
