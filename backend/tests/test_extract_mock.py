"""The mock extractor is what the offline pipeline and the tests run on. It must
behave like a strict extractor, not a generous one."""
from rns.llm.mock import mock_extract
from rns import vocab


def test_mock_only_emits_vocabulary_topics():
    # Wrong: free-text topics ("Chemie", "Infrastruktur") that are not in the 31.
    r = mock_extract("BASF investiert 300 Millionen Euro in neue Anlage in Ludwigshafen",
                     "Der Chemiekonzern baut den Verbundstandort aus. Wasserstoff soll ...", "corporate")
    assert r.is_signal
    assert r.topics and all(t in vocab.TOPICS for t in r.topics)
    assert "chemicals" in r.topics and "hydrogen" in r.topics


def test_mock_flags_bridge_closure_only_when_named_artery():
    # Wrong: every "Sperrung" is a signal (police-blotter volume swamps the scanner).
    named = mock_extract("Kurt-Schumacher-Brücke ab Montag voll gesperrt", "", "editorial")
    generic = mock_extract("Unfall auf Landstraße: Fahrbahn zwei Stunden gesperrt", "", "editorial")
    assert named.is_signal and "bridge" in named.topics and "Kurt-Schumacher-Brücke" in named.projects
    assert not generic.is_signal


def test_mock_forward_lag_rubric_ranks_call_above_report():
    call = mock_extract("Förderaufruf: Bewerbungsfrist für EXIST-Gründerstipendium endet am 30. September",
                        "", "funding")
    report = mock_extract("Rückblick: BASF hat 2025 in Ludwigshafen 200 Stellen abgebaut", "", "editorial")
    assert call.is_signal and report.is_signal
    assert call.forward_lag > report.forward_lag
    assert call.signal_type == "funding_call"


def test_mock_extracts_deadline_separately_from_start_date():
    r = mock_extract("Investor Roadshow am 12.10.2026 im CUBEX — Bewerbungsschluss 30.09.2026",
                     "Startups können sich bis zum 30.09.2026 bewerben.", "innovation")
    assert r.events
    ev = r.events[0]
    assert str(ev.start_date) == "2026-10-12"
    assert str(ev.deadline) == "2026-09-30"


def test_mock_returns_german_and_english_headlines():
    r = mock_extract("SAP kündigt neues KI-Rechenzentrum in Walldorf an", "", "corporate")
    assert r.headline_de and r.headline_en
    assert r.headline_de == "SAP kündigt neues KI-Rechenzentrum in Walldorf an"
