"""The digest may only cite what it was given. Provenance is a build invariant."""
import pytest

from rns.digest.validate import DigestProvenanceError, validate_digest

GOOD = {
    "lead_en": "Two developments moved.", "lead_de": "Zwei Entwicklungen.",
    "sections": [{"layer": "corporate", "items": [{"signal_id": "s1", "note_en": "n", "note_de": "n"}]}],
    "chains": [{"title_en": "Lab to market", "title_de": "Labor zu Markt", "signal_ids": ["s1", "s2"]}],
    "watch": [{"event_id": "e1", "why_en": "deadline", "why_de": "Frist"}],
}


def test_accepts_valid_payload():
    out = validate_digest(GOOD, signal_ids={"s1", "s2"}, event_ids={"e1"})
    assert out.lead_en and out.sections[0].items[0].signal_id == "s1"


def test_rejects_unknown_signal_id_anywhere_including_chains():
    # Wrong: only checking sections, letting a chain cite an invented id.
    bad = {**GOOD, "chains": [{"title_en": "x", "title_de": "y", "signal_ids": ["s1", "ghost"]}]}
    with pytest.raises(DigestProvenanceError) as exc:
        validate_digest(bad, signal_ids={"s1", "s2"}, event_ids={"e1"})
    assert "ghost" in str(exc.value)


def test_rejects_unknown_event_id_and_unknown_layer():
    bad = {**GOOD, "watch": [{"event_id": "e9", "why_en": "a", "why_de": "b"}]}
    with pytest.raises(DigestProvenanceError):
        validate_digest(bad, signal_ids={"s1", "s2"}, event_ids={"e1"})
    bad2 = {**GOOD, "sections": [{"layer": "media", "items": []}]}
    with pytest.raises(DigestProvenanceError):
        validate_digest(bad2, signal_ids={"s1", "s2"}, event_ids={"e1"})


def test_rejects_missing_german_field():
    bad = {**GOOD, "lead_de": ""}
    with pytest.raises(DigestProvenanceError):
        validate_digest(bad, signal_ids={"s1", "s2"}, event_ids={"e1"})
