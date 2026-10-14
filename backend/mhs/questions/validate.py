"""Provenance validator for the judge. A judgement is kept only if it cites a signal of
its own batch and a real question, uses the controlled direction and strength, carries
both languages, and its quote lies wholly within ONE of that signal's texts (headline,
summary, source title, source text …) — compared after normalising case, whitespace,
quotation marks and dashes, nothing else. A paraphrase, a translation, a quote stitched
together with an ellipsis or glued across two fields is dropped and reported.

What is stored is the source's own span — its characters, case and quotation marks — not
the model's rendering of it: the reader is shown the quote as verbatim evidence."""
from __future__ import annotations

import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

from mhs import vocab

# A clause, not a keyword hit: "DES LANDKREISES" is neither evidence nor a quote.
MIN_QUOTE_CHARS = 20
MIN_QUOTE_WORDS = 3

_QUOTE_CHARS = "„“”‟\"'‚‘’‛«»‹›"
_DASH_CHARS = "–—‒―‐‑−"
_TRANSLATE = str.maketrans({**{c: '"' for c in _QUOTE_CHARS}, **{c: "-" for c in _DASH_CHARS}})
# Soft hyphens and zero-width characters survive copy-paste from PDFs and CMS pages.
_INVISIBLE = set("­​‌‍⁠﻿")
# End punctuation the model may add or drop around a quote.
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


def _normalise_mapped(s: str) -> tuple[str, list[tuple[int, int]]]:
    """The normalised text and, for each of its characters, the [start, end) span of the
    original characters it came from — so a match can be cut back out of the original."""
    chars: list[str] = []
    spans: list[tuple[int, int]] = []
    i, n = 0, len(s or "")
    while i < n:
        # A base character with its combining marks is one unit: "a" + U+0308 composes to "ä".
        j = i + 1
        while j < n and unicodedata.combining(s[j]):
            j += 1
        for c in unicodedata.normalize("NFKC", s[i:j]):  # ligatures, NBSP, composed umlauts
            if c in _INVISIBLE:
                continue
            for d in c.translate(_TRANSLATE).casefold():  # ß → ss maps both s to the ß
                chars.append(d)
                spans.append((i, j))
        i = j
    out: list[str] = []
    out_spans: list[tuple[int, int]] = []
    gap: tuple[int, int] | None = None
    for c, span in zip(chars, spans):
        if c.isspace():
            if out:  # leading whitespace dropped, inner runs collapse to one space
                gap = gap or span
            continue
        if gap is not None:
            out.append(" ")
            out_spans.append(gap)
            gap = None
        out.append(c)
        out_spans.append(span)
    return "".join(out), out_spans


def normalise(s: str) -> str:
    return _normalise_mapped(s)[0]


def _text(item: dict, key: str) -> str:
    value = item.get(key)
    return value.strip() if isinstance(value, str) else ""


def _fields(value: str | Sequence[str]) -> list[str]:
    return [value] if isinstance(value, str) else [f for f in value if f]


def _find_span(quote: str, fields: list[tuple[str, str, list[tuple[int, int]]]]) -> str | None:
    """The original slice of the first field that contains the quote, or None. Tried as given,
    then without wrapping quotation marks, then without edge punctuation as well — so a quote
    that carries the source's own „…“ keeps them, and one the model wrapped does not."""
    full = normalise(quote)
    candidates = list(dict.fromkeys(c for c in (full, full.strip('" '), full.strip(_EDGE)) if c))
    for needle in candidates:
        for original, hay, spans in fields:
            pos = hay.find(needle)
            if pos >= 0:
                return original[spans[pos][0]:spans[pos + len(needle) - 1][1]]
    return None


def validate_judgements(
    raw: dict, *, signal_texts: dict[str, str | Sequence[str]], question_ids: set[str]
) -> tuple[list[JudgementDraft], list[str]]:
    """`signal_texts` maps each batch id to the signal's text — a string, or the list of its
    separate fields (a quote must lie wholly within one field)."""
    if not isinstance(raw, dict) or not isinstance(raw.get("judgements"), list):
        raise JudgementShapeError(f"expected {{'judgements': [...]}}, got {type(raw).__name__}")

    normalised: dict[str, list[tuple[str, str, list[tuple[int, int]]]]] = {}
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
        core = normalise(quote).strip(_EDGE)
        if len(core) < MIN_QUOTE_CHARS or len(core.split()) < MIN_QUOTE_WORDS:
            problems.append(f"{tag}: quote too short to be evidence (needs {MIN_QUOTE_WORDS} words, "
                            f"{MIN_QUOTE_CHARS} characters): {quote!r}")
            continue
        if sid not in normalised:
            normalised[sid] = [(f, *_normalise_mapped(f)) for f in _fields(signal_texts[sid])]
        span = _find_span(quote, normalised[sid])
        if span is None:
            problems.append(f"{tag}: quote not found verbatim in any one text of the signal: {quote[:160]!r}")
            continue
        if (sid, qid) in seen:
            problems.append(f"{tag}: second judgement on the same signal and question")
            continue
        seen.add((sid, qid))
        kept.append(JudgementDraft(signal_id=sid, question_id=qid, direction=direction, strength=strength,
                                   quote=span, rationale_de=rationale_de, rationale_en=rationale_en))
    return kept, problems
