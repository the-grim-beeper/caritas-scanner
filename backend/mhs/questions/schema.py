"""The judge's structured-output schema. Static on purpose: identical bytes on every call.
No minimum/maximum/minItems/maxItems — structured outputs reject them; the validator
enforces everything the schema cannot."""
from __future__ import annotations

from mhs import vocab
from mhs.questions.load import QUESTION_IDS

JUDGEMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "signal_id": {"type": "string", "description": "The id of the signal as given in the batch (s1, s2, …)"},
        "question_id": {"type": "string", "enum": QUESTION_IDS},
        # The evidence comes before the verdict, so the verdict is written from the quote.
        "quote": {"type": "string",
                  "description": "A contiguous passage copied verbatim from the signal's text that itself shows the evidence"},
        "direction": {"type": "string", "enum": list(vocab.DIRECTIONS),
                      "description": "for = evidence for the concern or transition; against = evidence against / stabilising"},
        "strength": {"type": "string", "enum": list(vocab.STRENGTH_WEIGHTS)},
        "rationale_de": {"type": "string", "description": "Ein bis zwei Sätze, Deutsch"},
        "rationale_en": {"type": "string", "description": "One or two sentences, English"},
    },
    "required": ["signal_id", "question_id", "quote", "direction", "strength", "rationale_de", "rationale_en"],
    "additionalProperties": False,
}

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {"judgements": {"type": "array", "items": JUDGEMENT_SCHEMA}},
    "required": ["judgements"],
    "additionalProperties": False,
}
