"""The Lagebericht may only cite what it was given, and the Friday note must be the
short prose update it claims to be. Provenance is a build invariant."""
import pytest

from mhs.report.validate import ReportProvenanceError, friday_paragraphs, validate_report

IDS = {"signal_ids": {"s1", "s2"}, "event_ids": {"e1"}, "judgement_ids": {"j1"}, "question_ids": {"q03", "q12"}}

GOOD = {
    "lead_de": "Zwei Entwicklungen.", "lead_en": "Two developments.",
    "questions": [{"question_id": "q03", "movement": "for", "note_de": "n", "note_en": "n", "judgement_ids": ["j1"]}],
    "sections": [{"layer": "landkreis", "items": [{"signal_id": "s1", "note_de": "n", "note_en": "n"}]}],
    "chains": [{"title_de": "Umlage zu Kürzung", "title_en": "Levy to cut", "signal_ids": ["s1", "s2"]}],
    "watch": [{"event_id": "e1", "why_de": "Frist", "why_en": "deadline"}],
    "friday_de": "Diese Woche beschloss der Kreistag den Haushalt.\n\nFür die Lotsen heißt das wenig.",
    "friday_en": "This week the Kreistag adopted the budget.\n\nFor the Lotsen it means little.",
    "friday_signal_ids": ["s1"],
}


def _with(**kw):
    return {**GOOD, **kw}


def _problems(raw, **ids) -> str:
    with pytest.raises(ReportProvenanceError) as exc:
        validate_report(raw, **{**IDS, **ids})
    assert exc.value.problems
    return str(exc.value)


def test_accepts_valid_payload_and_returns_a_plain_dict():
    out = validate_report(GOOD, **IDS)
    assert isinstance(out, dict)
    assert out["friday_signal_ids"] == ["s1"] and out["questions"][0]["judgement_ids"] == ["j1"]


def test_unknown_judgement_id_rejected():
    bad = _with(questions=[{**GOOD["questions"][0], "judgement_ids": ["j1", "j-old"]}])
    assert "j-old" in _problems(bad)


def test_unknown_question_and_unknown_movement_rejected():
    assert "q99" in _problems(_with(questions=[{**GOOD["questions"][0], "question_id": "q99"}]))
    assert "rising" in _problems(_with(questions=[{**GOOD["questions"][0], "movement": "rising"}]))


def test_unknown_ids_rejected_in_sections_chains_and_watch():
    assert "ghost" in _problems(_with(chains=[{"title_de": "x", "title_en": "x", "signal_ids": ["s1", "ghost"]}]))
    assert "s9" in _problems(_with(sections=[{"layer": "landkreis", "items": [{"signal_id": "s9", "note_de": "n", "note_en": "n"}]}]))
    assert "e9" in _problems(_with(watch=[{"event_id": "e9", "why_de": "a", "why_en": "b"}]))
    assert "media" in _problems(_with(sections=[{"layer": "media", "items": []}]))


def test_empty_friday_signal_ids_rejected():
    assert "friday_signal_ids" in _problems(_with(friday_signal_ids=[]))


def test_friday_signal_ids_must_be_input_signals():
    # Wrong: checking only non-emptiness, so the note can rest on an event or an invented id.
    assert "e1" in _problems(_with(friday_signal_ids=["s1", "e1"]))


def test_one_paragraph_friday_rejected():
    assert "friday_de" in _problems(_with(friday_de="Nur ein Absatz."))
    out = validate_report(_with(friday_de="A.\n\nB."), **IDS)
    assert out["friday_de"] == "A.\n\nB."


def test_friday_en_is_checked_too_and_five_paragraphs_is_too_many():
    assert "friday_en" in _problems(_with(friday_en="One paragraph only."))
    assert "friday_de" in _problems(_with(friday_de="A.\n\nB.\n\nC.\n\nD.\n\nE."))
    assert validate_report(_with(friday_de="A.\n\nB.\n\nC.\n\nD."), **IDS)


def test_paragraphs_split_on_blank_lines_not_single_newlines():
    # Wrong: counting lines — a paragraph wrapped over two lines is still one paragraph.
    assert friday_paragraphs("Erster Satz\nweiter im selben Absatz.") == ["Erster Satz\nweiter im selben Absatz."]
    assert len(friday_paragraphs("A.\n \n\nB.\n\n\n")) == 2
    assert "friday_de" in _problems(_with(friday_de="Erster Satz\nweiter im selben Absatz."))


def test_friday_note_is_prose_without_headings_or_bullets():
    assert "friday_de" in _problems(_with(friday_de="## Diese Woche\n\nDer Kreistag tagte."))
    assert "friday_de" in _problems(_with(friday_de="Diese Woche:\n\n- Kreistag\n- Bezirk"))
    assert "friday_en" in _problems(_with(friday_en="This week:\n\n1. Kreistag met.\n2. Bezirk met."))
    # A German date opening a paragraph is not a numbered list.
    assert validate_report(_with(friday_de="Der Kreistag tagte.\n\n31. Oktober ist die Antragsfrist."), **IDS)


def test_missing_language_rejected():
    assert "lead_de" in _problems(_with(lead_de=" "))
    assert "s1" in _problems(_with(sections=[{"layer": "landkreis", "items": [{"signal_id": "s1", "note_de": "", "note_en": "n"}]}]))


def test_wrong_shape_rejected():
    raw = dict(GOOD)
    del raw["friday_de"]
    assert "friday_de" in _problems(raw)


def test_numbers_in_the_friday_note_must_come_from_the_input():
    # Wrong: trusting the model's figures — a Friday note to the client with an invented
    # percentage is the most damaging thing this scanner could send.
    note = "Die Kreisumlage steigt auf 52 Prozent.\n\nDas betrifft 2027."
    raw = _with(friday_de=note)
    assert validate_report(raw, **IDS, numbers={"52", "2027"})
    assert "47" in _problems(_with(friday_de=note.replace("52", "47")), numbers={"52", "2027"})
    # single digits are words in disguise ("zwei Signale"), not checked
    assert validate_report(_with(friday_de="Zwei, 3 Signale.\n\nMehr nicht."), **IDS, numbers=set())
