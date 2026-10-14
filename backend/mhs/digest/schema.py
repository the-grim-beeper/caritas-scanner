"""Digest payload shape — the same from Claude and from the mock."""
from __future__ import annotations

from mhs import vocab

DIGEST_SCHEMA = {
    "type": "object",
    "properties": {
        "lead_en": {"type": "string", "description": "3–4 sentences: what moved this cycle and why it matters for social provision in the county. English."},
        "lead_de": {"type": "string", "description": "Same lead in German."},
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "layer": {"type": "string", "enum": list(vocab.LAYERS)},
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "signal_id": {"type": "string"},
                                "note_en": {"type": "string", "description": "One or two sentences: why this matters, not a restatement."},
                                "note_de": {"type": "string"},
                            },
                            "required": ["signal_id", "note_en", "note_de"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["layer", "items"],
                "additionalProperties": False,
            },
        },
        "chains": {
            "type": "array",
            "description": "Cross-layer links the analyst sees between signals (e.g. Bezirksumlage → county budget → municipal grant cut).",
            "items": {
                "type": "object",
                "properties": {
                    "title_en": {"type": "string"},
                    "title_de": {"type": "string"},
                    "signal_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["title_en", "title_de", "signal_ids"],
                "additionalProperties": False,
            },
        },
        "watch": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "event_id": {"type": "string"},
                    "why_en": {"type": "string"},
                    "why_de": {"type": "string"},
                },
                "required": ["event_id", "why_en", "why_de"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["lead_en", "lead_de", "sections", "chains", "watch"],
    "additionalProperties": False,
}
