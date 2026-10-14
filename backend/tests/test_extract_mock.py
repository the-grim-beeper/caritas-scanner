"""The mock extractor is what the offline pipeline and the tests run on. It must
behave like a strict extractor, not a generous one."""
from mhs import vocab
from mhs.llm.mock import _TOPIC_KEYWORDS, mock_extract


def test_mock_tags_kreisumlage_as_umlagen_and_is_signal():
    r = mock_extract("Kreistag beschließt höhere Kreisumlage", "Die Gemeinden im Landkreis Miesbach zahlen 2027 mehr.", "landkreis")
    assert r.is_signal and "umlagen" in r.topics and "Landkreis Miesbach" in r.places


def test_mock_ignores_sport():
    r = mock_extract("TSV Miesbach gewinnt Derby", "Fußball am Sonntag.", "medien")
    assert not r.is_signal


def test_mock_ignores_items_without_a_vocabulary_topic():
    # Wrong: every item from a county source counts — the guard alone is not the filter.
    r = mock_extract("Landratsamt Miesbach: neue Telefonnummer der Zulassungsstelle", "", "landkreis")
    assert not r.is_signal


def test_mock_only_vocabulary_topics():
    r = mock_extract("Pflegestützpunkt verkürzt Öffnungszeiten wegen Personalmangel", "", "landkreis")
    assert set(r.topics) <= set(vocab.TOPICS) and {"pflege", "fachkraefte"} <= set(r.topics)
    assert r.signal_type == "service_change"


def test_every_topic_has_at_least_two_keywords():
    assert set(_TOPIC_KEYWORDS) == set(vocab.TOPICS)
    assert all(len(kws) >= 2 for kws in _TOPIC_KEYWORDS.values())


def test_mock_finds_all_five_entity_kinds_and_not_the_town_inside_the_county_name():
    # Wrong: matching "Miesbach" inside "Landkreis Miesbach" and tagging the town too.
    r = mock_extract(
        "Sozialbeirat: Landrat will Sozialraumlotsen im Landkreis Miesbach verstetigen",
        "Das Caritas-Zentrum Miesbach soll die Koordination übernehmen.", "landkreis")
    assert r.places == ("Landkreis Miesbach",)
    assert "Caritas-Zentrum Miesbach" in r.organisations
    assert "Sozialbeirat des Landkreises Miesbach" in r.forums
    assert "Interkommunale Sozialraumlotsen" in r.programmes
    assert "Landrat (Landkreis Miesbach)" in r.offices
    assert {"koordination", "verstetigung"} <= set(r.topics)


def test_mock_consequence_grows_with_topics_and_relevance_needs_a_place():
    one = mock_extract("Netzwerk Ehrenamt sucht Freiwillige", "", "wohlfahrt")
    many = mock_extract("Kreisumlage steigt, Haushaltssperre droht, Förderende für Projekte",
                        "Die Gemeinden im Landkreis Miesbach kürzen den Zuschuss.", "landkreis")
    assert one.is_signal and many.is_signal
    assert many.consequence > one.consequence and many.consequence <= 1.0
    assert many.regional_relevance == 1.0 and one.regional_relevance == 0.4


def test_mock_forward_lag_ranks_a_pending_decision_above_a_report():
    ahead = mock_extract("Kreistag soll Anschlussförderung für Sozialraumlotsen beschließen", "", "landkreis")
    behind = mock_extract("Sozialbericht: Zahl der Pflegebedürftigen gestiegen", "", "landkreis")
    assert ahead.is_signal and behind.is_signal
    assert ahead.forward_lag > behind.forward_lag


def test_mock_extracts_deadline_separately_from_start_date():
    r = mock_extract("Fachtag Pflege am 12.11.2026 im Landratsamt — Anmeldeschluss 30.10.2026",
                     "Anmeldung bis zum 30.10.2026.", "landkreis")
    assert r.events
    ev = r.events[0]
    assert str(ev.start_date) == "2026-11-12"
    assert str(ev.deadline) == "2026-10-30"


def test_mock_returns_german_and_english_headlines_and_no_relations():
    r = mock_extract("Jobcenter Miesbach: Bürgergeld wird Grundsicherungsgeld", "", "landkreis")
    assert r.headline_de == "Jobcenter Miesbach: Bürgergeld wird Grundsicherungsgeld" and r.headline_en
    assert r.relations == ()
