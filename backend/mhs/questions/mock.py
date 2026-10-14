"""Deterministic stand-in for the judge when no API key is set: a few trigger phrases per
question from the report's evidence columns. The quote is the sentence of the signal text
that holds the deciding phrase, so mock judgements pass the same provenance check as live
ones. Strength is always moderate. Good enough to exercise the pipeline and the UI; not
an analyst."""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class _Rule:
    question_id: str
    # The signal must mention one of these to bear on the question at all.
    topic: tuple[str, ...]
    # Checked in order; the first group with a hit decides the direction.
    cues: tuple[tuple[str, tuple[str, ...]], ...] = field(default=())
    # Direction when the topic matches and no cue does; None = no judgement.
    default: str | None = None


RULES: tuple[_Rule, ...] = (
    _Rule("q01", ("haushaltssperre", "freiwillige leistung", "sparliste"), default="for"),
    _Rule("q02", ("kreisumlage", "bezirksumlage", "hebesatz"), default="for"),
    _Rule("q03", ("sozialraumlots", "lotsen"),
          (("for", ("verstetig", "dauerhaft", "stellenplan")), ("against", ("befristet", "auslauf", "förderende")))),
    _Rule("q04", ("geschäftsordnung", "kooperationsvereinbarung", "arbeitsprogramm", "bei bedarf"),
          (("against", ("bei bedarf",)),), default="for"),
    _Rule("q05", ("bürgermeister", "landrat", "stadtrat", "gemeinderat"),
          (("for", ("streit", "abgelehnt", "kontrovers")),)),
    _Rule("q06", ("personalmangel", "fachkräftemangel", "unbesetzt", "vakant"), default="for"),
    _Rule("q07", ("warteliste", "aufnahmestopp", "engpass"), default="for"),
    _Rule("q08", ("buslinie", "rufbus", "fahrdienst", "takt"),
          (("for", ("eingestellt", "gestrichen", "ausfall")),), default="against"),
    _Rule("q09", ("hilfen zur erziehung", "schulvermeid", "jugendhilfebedarf"), default="for"),
    _Rule("q10", ("pfarrei", "pfarrheim", "pfarrverband"),
          (("against", ("umgenutzt", "umnutzung")),
           ("for", ("verkauf", "zusammengelegt", "zusammenlegung", "pfarreizusammenleg", "schließ")))),
    _Rule("q11", ("insolvenz", "trägerwechsel", "fusion", "leistungsvereinbarung"),
          (("against", ("leistungsvereinbarung",)),), default="for"),
    _Rule("q12", ("förderende", "auslauf", "befristet", "regelfinanzierung", "verstetig"),
          (("against", ("regelfinanzierung", "verstetig")), ("for", ("förderende", "auslauf", "befristet")))),
    _Rule("q13", ("sozialbericht", "datenvereinbarung", "gemeinsame indikatoren", "doppelte portale"),
          (("against", ("doppelte portale",)),), default="for"),
    _Rule("q14", ("koordination", "vernetzung", "prävention"),
          (("for", ("bürokratie", "doppelstruktur")), ("against", ("parteiübergreifend",)))),
    _Rule("q15", ("gemeindeschwester", "community nursing", "präventionskette"),
          (("for", ("regelfinanzierung", "verstetig", "dauerhaft")), ("against", ("ausgelaufen", "eingestellt", "beendet")))),
)


def _hit(phrase: str, text: str) -> bool:
    # At the start of a word: "takt" must not fire inside "Kontakt", nor "befristet" inside "unbefristet".
    return re.search(r"(?<!\w)" + re.escape(phrase), text) is not None


def _sentences(text: str) -> list[str]:
    out: list[str] = []
    for line in text.splitlines():
        out.extend(s.strip() for s in line.split(". ") if s.strip())
    return out


def _sentence_with(phrases: tuple[str, ...], sentences: list[str]) -> str | None:
    for s in sentences:
        low = s.lower()
        if any(_hit(p, low) for p in phrases):
            return s
    return None


def _judge_one(signal_id: str, text: str) -> list[dict]:
    low = text.lower()
    sentences = _sentences(text)
    out = []
    for rule in RULES:
        if not any(_hit(p, low) for p in rule.topic):
            continue
        direction, phrases = rule.default, rule.topic
        for d, cue_words in rule.cues:
            if any(_hit(c, low) for c in cue_words):
                direction, phrases = d, cue_words
                break
        if direction is None:
            continue
        quote = _sentence_with(phrases, sentences) or _sentence_with(rule.topic, sentences)
        if not quote:
            continue
        out.append({
            "signal_id": signal_id, "question_id": rule.question_id, "direction": direction,
            "strength": "moderate", "quote": quote,
            "rationale_de": f"Testmodus: Schlüsselbegriff für {rule.question_id} im Text gefunden.",
            "rationale_en": f"Mock mode: a trigger phrase for {rule.question_id} appears in the text.",
        })
    return out


def mock_judge(signal_texts: dict[str, str]) -> dict:
    """Same shape as the live judge's payload: {"judgements": [...]}."""
    return {"judgements": [j for sid, text in signal_texts.items() for j in _judge_one(sid, text)]}
