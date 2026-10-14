"""Lagebericht payload shape — the same from Claude and from the mock. Structured-output
schema: no minimum/maximum/minItems/maxItems (the API rejects them); counts and lengths
are stated in descriptions and enforced by report/validate.py."""
from __future__ import annotations

from mhs import vocab

MOVEMENTS: tuple[str, ...] = ("for", "against", "mixed", "quiet")


def _obj(properties: dict, description: str | None = None) -> dict:
    out = {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}
    if description:
        out["description"] = description
    return out


def _str(description: str | None = None) -> dict:
    return {"type": "string", "description": description} if description else {"type": "string"}


def _ids(description: str) -> dict:
    return {"type": "array", "items": {"type": "string"}, "description": description}


REPORT_SCHEMA = _obj({
    "lead_de": _str("3–4 sentences, German: what moved this week for whether an inter-municipal coordination "
                    "structure can be anchored to 2035/2040."),
    "lead_en": _str("The same lead in English."),
    "questions": {
        "type": "array",
        "description": "Only questions with judgements this week.",
        "items": _obj({
            "question_id": _str("A question id from the input."),
            "movement": {"type": "string", "enum": list(MOVEMENTS),
                         "description": "Copy the movement given for this question in the input."},
            "note_de": _str("One or two sentences, German: what this week's evidence shows."),
            "note_en": _str("The same note in English."),
            "judgement_ids": _ids("Ids of the judgements (from this question's input list) the note rests on."),
        }),
    },
    "sections": {
        "type": "array",
        "items": _obj({
            "layer": {"type": "string", "enum": list(vocab.LAYERS)},
            "items": {
                "type": "array",
                "items": _obj({
                    "signal_id": _str(),
                    "note_de": _str("One or two sentences, German: why this matters, not a restatement."),
                    "note_en": _str("The same note in English."),
                }),
            },
        }),
    },
    "chains": {
        "type": "array",
        "description": "Links across layers between signals in this batch; two or more signal ids each.",
        "items": _obj({"title_de": _str(), "title_en": _str(), "signal_ids": _ids("Signal ids from the input.")}),
    },
    "watch": {
        "type": "array",
        "items": _obj({"event_id": _str("An event id from the input."), "why_de": _str(), "why_en": _str()}),
    },
    "friday_de": _str("The weekly note to Florian Rausch, German: two or three short paragraphs separated by a "
                      "blank line; plain prose, no headings, no lists, no greeting, no signature."),
    "friday_en": _str("The same note in English, same paragraphs."),
    "friday_signal_ids": _ids("Every signal id the Friday note draws on; at least one."),
})
