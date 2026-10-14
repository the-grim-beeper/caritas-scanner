"""The judge's provenance validator: a judgement is stored only if its quote is a verbatim
(normalised) piece of the signal it cites, in the batch it was given, on a real question."""
import pytest

from mhs.questions.schema import JUDGE_SCHEMA
from mhs.questions.validate import JudgementShapeError, normalise, validate_judgements

TEXT = "Die Gemeinde verhängt eine Haushaltssperre für freiwillige Leistungen."


def _j(**over):
    j = {"signal_id": "s1", "question_id": "q01", "direction": "for", "strength": "strong",
         "quote": "Haushaltssperre für freiwillige Leistungen", "rationale_de": "Spielraum schrumpft.",
         "rationale_en": "Room shrinks."}
    j.update(over)
    return j


def test_quote_must_be_in_signal_text():
    raw = {"judgements": [{"signal_id": "s1", "question_id": "q01", "direction": "for", "strength": "strong",
            "quote": "Haushaltssperre für freiwillige Leistungen", "rationale_de": "x", "rationale_en": "x"}]}
    kept, problems = validate_judgements(raw, signal_texts={"s1": TEXT}, question_ids={"q01"})
    assert len(kept) == 1 and not problems
    raw["judgements"][0]["quote"] = "Gemeinde kürzt Sozialausgaben"   # paraphrase
    kept, problems = validate_judgements(raw, signal_texts={"s1": TEXT}, question_ids={"q01"})
    assert kept == [] and problems


def test_unknown_question_and_foreign_signal_rejected():
    # Wrong: trusting the model's ids — a judgement on "q99" or on a signal from another batch
    # (or a hallucinated one) would be written against the wrong evidence.
    raw = {"judgements": [_j(question_id="q99"), _j(signal_id="s9"), _j()]}
    kept, problems = validate_judgements(raw, signal_texts={"s1": TEXT}, question_ids={"q01", "q02"})
    assert [(k.signal_id, k.question_id) for k in kept] == [("s1", "q01")]
    assert len(problems) == 2
    assert any("q99" in p for p in problems) and any("s9" in p for p in problems)


def test_quote_from_another_signal_in_the_batch_rejected():
    # Wrong: checking the quote against the whole batch's text instead of the cited signal's.
    texts = {"s1": TEXT, "s2": "Der Kreistag erhöht die Kreisumlage um zwei Punkte."}
    raw = {"judgements": [_j(signal_id="s2")]}
    kept, problems = validate_judgements(raw, signal_texts=texts, question_ids={"q01"})
    assert kept == [] and len(problems) == 1


def test_typographic_quotes_normalise():
    # Source uses straight quotes; the model renders German typographic ones.
    text = 'Der Kreistag nennt das Projekt "Sozialraumlotsen" unverzichtbar für den Landkreis.'
    raw = {"judgements": [_j(question_id="q03", quote="nennt das Projekt „Sozialraumlotsen“ unverzichtbar")]}
    kept, problems = validate_judgements(raw, signal_texts={"s1": text}, question_ids={"q03"})
    assert len(kept) == 1 and not problems


def test_whitespace_case_and_dashes_normalise():
    # PDFs and feeds break lines mid-sentence and use en dashes; the model writes one line.
    text = "Die Stelle der Koordinatorin\nbleibt  seit März –  trotz zweier Ausschreibungen – unbesetzt."
    raw = {"judgements": [_j(question_id="q06",
                            quote="bleibt seit März - trotz zweier Ausschreibungen - unbesetzt")]}
    kept, _ = validate_judgements(raw, signal_texts={"s1": text}, question_ids={"q06"})
    assert len(kept) == 1
    assert normalise("  „A“  –\tB C ") == '"a" - b c'


def test_wrapping_quote_marks_are_not_part_of_the_quote():
    raw = {"judgements": [_j(quote="„Haushaltssperre für freiwillige Leistungen.“")]}
    kept, problems = validate_judgements(raw, signal_texts={"s1": TEXT}, question_ids={"q01"})
    assert len(kept) == 1 and not problems
    assert kept[0].quote == "Haushaltssperre für freiwillige Leistungen."


def test_ellipsis_stitched_quote_rejected():
    # Wrong: accepting a quote stitched from two pieces — it is no longer a verbatim passage.
    raw = {"judgements": [_j(quote="Haushaltssperre … Leistungen")]}
    kept, problems = validate_judgements(raw, signal_texts={"s1": TEXT}, question_ids={"q01"})
    assert kept == [] and problems


def test_too_short_quote_rejected():
    # A single word is a keyword hit, not evidence: at least a clause (>= 12 characters).
    raw = {"judgements": [_j(quote="Haushaltssperre"[:11])]}
    kept, problems = validate_judgements(raw, signal_texts={"s1": TEXT}, question_ids={"q01"})
    assert kept == [] and problems


def test_bad_direction_strength_and_missing_language_rejected():
    raw = {"judgements": [_j(direction="up"), _j(strength="huge"), _j(rationale_de=" "), _j(rationale_en="")]}
    kept, problems = validate_judgements(raw, signal_texts={"s1": TEXT}, question_ids={"q01"})
    assert kept == [] and len(problems) == 4


def test_second_judgement_on_the_same_signal_and_question_dropped():
    # The table holds one reading per (signal, question, model); a duplicate would sink the write.
    raw = {"judgements": [_j(), _j(direction="against", strength="weak")]}
    kept, problems = validate_judgements(raw, signal_texts={"s1": TEXT}, question_ids={"q01"})
    assert len(kept) == 1 and kept[0].direction == "for" and len(problems) == 1


def test_empty_list_is_a_valid_payload():
    kept, problems = validate_judgements({"judgements": []}, signal_texts={"s1": TEXT}, question_ids={"q01"})
    assert kept == [] and problems == []


@pytest.mark.parametrize("raw", [None, [], {"answers": []}, {"judgements": "none"}])
def test_wrong_shape_raises(raw):
    # The judge retries a wrong-shape payload once; it must be distinguishable from "no judgements".
    with pytest.raises(JudgementShapeError):
        validate_judgements(raw, signal_texts={"s1": TEXT}, question_ids={"q01"})


def _keys(node):
    if isinstance(node, dict):
        for k, v in node.items():
            yield k
            yield from _keys(v)
    elif isinstance(node, list):
        for v in node:
            yield from _keys(v)


def test_schema_has_no_unsupported_keywords_and_enumerates_the_fifteen():
    assert not {"minimum", "maximum", "minItems", "maxItems"} & set(_keys(JUDGE_SCHEMA))
    item = JUDGE_SCHEMA["properties"]["judgements"]["items"]
    assert item["properties"]["question_id"]["enum"] == [f"q{i:02d}" for i in range(1, 16)]
    assert item["properties"]["direction"]["enum"] == ["for", "against"]
    assert item["properties"]["strength"]["enum"] == ["weak", "moderate", "strong"]
    assert set(item["required"]) == {"signal_id", "question_id", "direction", "strength", "quote",
                                     "rationale_de", "rationale_en"}
