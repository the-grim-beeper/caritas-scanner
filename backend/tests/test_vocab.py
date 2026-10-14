"""Vocabulary is transcribed from the spec (§2) and the brief; these tests defend against drift."""
from pathlib import Path

import yaml

from mhs import vocab

DATA = Path(__file__).resolve().parents[2] / "data"


def test_nine_layers_in_brief_order():
    assert list(vocab.LAYERS) == ["gemeinden", "landkreis", "wohlfahrt", "kirche", "bezirk", "freistaat",
                                  "bund", "medien", "vergleich"]
    assert vocab.LAYERS["landkreis"].de == "Landkreis & Dienste"


def test_every_topic_has_a_family_and_33_topics():
    # Wrong: a hand-typed list that drops a tag, or a topic left out of the family map.
    assert len(vocab.TOPICS) == 33
    assert set(vocab.TOPIC_FAMILY) == set(vocab.TOPICS)
    assert set(vocab.TOPIC_FAMILY.values()) == set(vocab.FAMILIES)
    assert list(vocab.FAMILIES) == ["struktur", "personal", "bedarf", "geld", "regeln", "stimmung"]
    assert vocab.TOPIC_FAMILY["umlagen"] == "geld" and vocab.TOPIC_FAMILY["sgb"] == "regeln"
    assert vocab.TOPICS["jugend-familie"].de == "Jugend, Familie & Kita"


def test_every_label_is_bilingual():
    for table in (vocab.LAYERS, vocab.FAMILIES, vocab.TOPICS, vocab.SIGNAL_TYPE_LABELS, vocab.RELATIONS):
        assert all(lbl.en.strip() and lbl.de.strip() for lbl in table.values())


def test_signal_types_are_the_twelve_from_the_spec_and_all_labelled():
    assert vocab.SIGNAL_TYPES == ["decision", "announcement", "budget", "funding_call", "service_change",
                                  "staffing", "planning", "disruption", "research", "event", "position",
                                  "data_release"]
    assert list(vocab.SIGNAL_TYPE_LABELS) == vocab.SIGNAL_TYPES


def test_collected_methods_include_new_ones():
    assert {"query", "diff", "pdf"} <= set(vocab.COLLECTED_METHODS)
    assert set(vocab.COLLECTED_METHODS) <= set(vocab.METHODS)
    assert not {"newsletter", "api", "social"} & set(vocab.COLLECTED_METHODS)


def test_entity_kinds_and_open_kinds():
    assert vocab.ENTITY_KINDS == ["place", "organisation", "forum", "programme", "office"]
    # Places are a closed set; everything else grows by extraction.
    assert vocab.OPEN_ENTITY_KINDS == set(vocab.ENTITY_KINDS) - {"place"}


def test_relations_directions_strengths():
    assert list(vocab.RELATIONS) == ["funding", "commissioning", "membership", "coordination", "supervision",
                                     "cooperation", "consultation", "transfer"]
    assert vocab.DIRECTIONS == ["for", "against"]
    assert vocab.STRENGTH_WEIGHTS == {"weak": 1, "moderate": 2, "strong": 3}
    assert vocab.EVENT_KINDS == ["event", "deadline", "window"]


def test_scopes_and_authority_weights():
    assert vocab.SCOPES == ["gemeinde", "landkreis", "bezirk", "land", "bund", "eu", "extern"]
    assert vocab.AUTHORITY_WEIGHTS == {"high": 1.0, "medium": 0.7, "low": 0.4}


def test_actor_kinds_cover_the_entity_dictionary_and_the_network_seed():
    # Wrong: a vocabulary that the committed data already violates.
    raw = yaml.safe_load((DATA / "entities.yaml").read_text())
    used = {e["actor_kind"] for sec in raw.values() for e in sec if e.get("actor_kind")}
    assert used and used <= set(vocab.ACTOR_KINDS)
    network = yaml.safe_load((DATA / "network.yaml").read_text())
    assert {e["relation"] for e in network["edges"]} <= set(vocab.RELATIONS)
