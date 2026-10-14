"""Vocabulary is transcribed from the brief; these tests defend against drift."""
from mhs import vocab


def test_topics_are_exactly_the_brief_vocabulary():
    # Wrong implementation: a hand-typed list that drops or renames a tag.
    assert len(vocab.TOPICS) == 31
    for code in ("CCS", "district-heating", "planning-permit", "research-infrastructure"):
        assert code in vocab.TOPICS
    assert all(lbl.en and lbl.de for lbl in vocab.TOPICS.values())


def test_layers_are_the_six_from_the_report_in_order():
    assert list(vocab.LAYERS) == [
        "policy", "editorial", "innovation", "corporate", "infrastructure", "funding",
    ]


def test_signal_types_are_the_eleven_from_the_spec():
    assert len(vocab.SIGNAL_TYPES) == 11
    assert "funding_call" in vocab.SIGNAL_TYPES and "tender" in vocab.SIGNAL_TYPES


def test_authority_weights():
    assert vocab.AUTHORITY_WEIGHTS == {"high": 1.0, "medium": 0.7, "low": 0.4}
