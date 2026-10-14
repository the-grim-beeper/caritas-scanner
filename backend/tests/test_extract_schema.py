"""The extraction payload is coerced defensively: tagging degrades, it never crashes,
and nothing outside the vocabulary gets through."""
from mhs import vocab
from mhs.extract.schema import EXTRACTION_SCHEMA, RelationDraft, from_payload

_REL = {"a": "Jugendamt", "b": "Diakonie Rosenheim", "relation": "commissioning", "quote": "im Auftrag des Jugendamts"}


def _walk_keys(node):
    if isinstance(node, dict):
        for k, v in node.items():
            yield k
            yield from _walk_keys(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk_keys(v)


def test_schema_has_no_keywords_structured_outputs_reject():
    # Wrong: "minimum": 0 on a score, which the API answers with a 400 on every item.
    assert not {"minimum", "maximum", "minItems", "maxItems"} & set(_walk_keys(EXTRACTION_SCHEMA))


def test_schema_lists_the_five_entity_kinds_consequence_and_relations():
    props = EXTRACTION_SCHEMA["properties"]
    for key in ("places", "organisations", "forums", "programmes", "offices", "consequence", "relations"):
        assert key in props and key in EXTRACTION_SCHEMA["required"]
    assert "economic_materiality" not in props and "projects" not in props
    assert props["relations"]["items"]["properties"]["relation"]["enum"] == list(vocab.RELATIONS)
    assert props["topics"]["items"]["enum"] == list(vocab.TOPICS)


def test_from_payload_keeps_valid_relations_and_drops_invalid_ones():
    # Wrong: trusting the model's relation label, or keeping a relation with a blank end.
    r = from_payload({"is_signal": True, "relations": [
        _REL,
        {**_REL, "relation": "likes"},
        {**_REL, "a": "  "},
        {**_REL, "b": ""},
        {**_REL, "quote": ""},
        "not a dict",
    ]})
    assert r.relations == (RelationDraft(a="Jugendamt", b="Diakonie Rosenheim", relation="commissioning",
                                         quote="im Auftrag des Jugendamts"),)


def test_from_payload_caps_relations_at_eight():
    r = from_payload({"is_signal": True, "relations": [{**_REL, "b": f"Träger {i}"} for i in range(12)]})
    assert len(r.relations) == 8


def test_from_payload_clamps_scores_and_filters_topics():
    r = from_payload({"is_signal": True, "consequence": 7, "regional_relevance": -1, "forward_lag": "x",
                      "topics": ["umlagen", "CAPEX"], "signal_type": "investment"})
    assert r.consequence == 1.0 and r.regional_relevance == 0.0 and r.forward_lag == 0.0
    assert r.topics == ("umlagen",) and r.signal_type == "announcement"


def test_from_payload_reads_forums_programmes_offices_and_drops_personal_names_from_offices():
    # Persons are never entities: an "office" that names no role is a person, not an office.
    r = from_payload({"is_signal": True, "forums": ["Jugendhilfeausschuss"], "programmes": ["SeLA"],
                      "offices": ["Erster Bürgermeister Waakirchen", "Max Mustermann", "Jugendamtsleitung"]})
    assert r.forums == ("Jugendhilfeausschuss",) and r.programmes == ("SeLA",)
    assert r.offices == ("Erster Bürgermeister Waakirchen", "Jugendamtsleitung")
