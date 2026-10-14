"""Controlled vocabularies (spec §2), transcribed from the source-architecture brief
(docs/brief/source-architecture.txt): the report's nine layers, its six signal
families and the topic codes grouped under them, the relation types of its evidence
graph and the authority tiers. The extractor, the judge and the UI may not invent a
code outside these tables."""
from __future__ import annotations

from typing import NamedTuple


class Label(NamedTuple):
    en: str
    de: str


# --- layers (a source belongs to exactly one) ---------------------------------
LAYERS: dict[str, Label] = {
    "gemeinden": Label("Municipalities", "Gemeinden"),
    "landkreis": Label("County & local services", "Landkreis & Dienste"),
    "wohlfahrt": Label("Welfare & civil society", "Wohlfahrt & Zivilgesellschaft"),
    "kirche": Label("Church", "Kirche"),
    "bezirk": Label("District of Upper Bavaria", "Bezirk Oberbayern"),
    "freistaat": Label("State of Bavaria", "Freistaat Bayern"),
    "bund": Label("Federal", "Bund"),
    "medien": Label("Media & research", "Medien & Forschung"),
    "vergleich": Label("Peer cases", "Vergleichsfälle"),
}

# --- topics, grouped under the report's six signal families --------------------
FAMILIES: dict[str, Label] = {
    "struktur": Label("Structure", "Struktur"),
    "personal": Label("People", "Personal"),
    "bedarf": Label("Demand & supply", "Bedarf & Angebot"),
    "geld": Label("Money", "Geld"),
    "regeln": Label("Rules", "Regeln"),
    "stimmung": Label("Sentiment", "Stimmung"),
}

_TOPICS_BY_FAMILY: dict[str, dict[str, Label]] = {
    "struktur": {
        "koordination": Label("Coordination & networks", "Koordination & Netzwerke"),
        "steuerung": Label("Steering, mandate & sponsorship", "Steuerung, Mandat & Trägerschaft"),
        "verstetigung": Label("Mainstreaming & regular funding", "Verstetigung & Regelfinanzierung"),
        "interkommunal": Label("Inter-municipal cooperation", "Interkommunale Zusammenarbeit"),
        "quartier": Label("Neighbourhood & social space", "Quartier & Sozialraum"),
        "daten": Label("Data & social reporting", "Daten & Sozialberichterstattung"),
        "kirchenstruktur": Label("Church structures", "Kirchliche Strukturen"),
        "traegerwandel": Label("Provider change (merger, closure, founding)",
                               "Trägerwandel (Fusion, Schließung, Neugründung)"),
    },
    "personal": {
        "fachkraefte": Label("Skilled workers", "Fachkräfte"),
        "stellen": Label("Posts & refilling", "Stellen & Nachbesetzung"),
        "leitung": Label("Leadership changes & offices", "Leitungswechsel & Ämter"),
        "ehrenamt": Label("Volunteering", "Ehrenamt"),
    },
    "bedarf": {
        "pflege": Label("Care & old age", "Pflege & Alter"),
        "jugend-familie": Label("Youth, family & childcare", "Jugend, Familie & Kita"),
        "eingliederung": Label("Disability support & inclusion", "Eingliederung & Inklusion"),
        "psyche": Label("Mental health & addiction", "Psychische Gesundheit & Sucht"),
        "armut": Label("Poverty & basic income support", "Armut & Grundsicherung"),
        "wohnen": Label("Housing & housing shortage", "Wohnen & Wohnungsnot"),
        "integration": Label("Migration & integration", "Migration & Integration"),
        "teilhabe": Label("Loneliness & participation", "Einsamkeit & Teilhabe"),
        "gesundheit": Label("Health care", "Gesundheitsversorgung"),
        "mobilitaet": Label("Mobility & access", "Mobilität & Erreichbarkeit"),
        "demografie": Label("Demography", "Demografie"),
    },
    "geld": {
        "haushalt": Label("Municipal budget", "Kommunalhaushalt"),
        "umlagen": Label("County & district levies", "Kreis- & Bezirksumlage"),
        "foerderung": Label("Funding & grants", "Förderung & Zuschüsse"),
        "foerderende": Label("Grant expiry & follow-on funding", "Förderende & Anschlussfinanzierung"),
        "vereinbarungen": Label("Service & remuneration agreements", "Leistungs- & Vergütungsvereinbarungen"),
    },
    "regeln": {
        "gesetzgebung": Label("Legislation & regulation", "Gesetzgebung & Verordnung"),
        "sgb": Label("Social code (SGB) reforms", "SGB-Reformen"),
        "landesprogramm": Label("State programmes", "Landesprogramme"),
    },
    "stimmung": {
        "politik": Label("Political change", "Politischer Wechsel"),
        "kontroverse": Label("Controversy & protest", "Kontroverse & Protest"),
    },
}

TOPICS: dict[str, Label] = {code: lbl for topics in _TOPICS_BY_FAMILY.values() for code, lbl in topics.items()}
TOPIC_FAMILY: dict[str, str] = {code: fam for fam, topics in _TOPICS_BY_FAMILY.items() for code in topics}

# --- signal types (the form of the development; one per signal) ---------------
SIGNAL_TYPE_LABELS: dict[str, Label] = {
    "decision": Label("Decision", "Beschluss"),
    "announcement": Label("Announcement", "Ankündigung"),
    "budget": Label("Budget", "Haushalt"),
    "funding_call": Label("Funding call", "Förderaufruf"),
    # openings, closures, Aufnahmestopp, reduced hours
    "service_change": Label("Service change", "Angebotsänderung"),
    # vacancies, leadership changes, recruitment failures
    "staffing": Label("Staffing", "Personal"),
    "planning": Label("Planning", "Planung"),
    "disruption": Label("Disruption", "Störung"),
    "research": Label("Research", "Forschung"),
    "event": Label("Event", "Veranstaltung"),
    "position": Label("Position statement", "Positionierung"),
    "data_release": Label("Data release", "Datenveröffentlichung"),
}
SIGNAL_TYPES: list[str] = list(SIGNAL_TYPE_LABELS)

# --- sources ------------------------------------------------------------------
AUTHORITY_WEIGHTS: dict[str, float] = {"high": 1.0, "medium": 0.7, "low": 0.4}
SCOPES: list[str] = ["gemeinde", "landkreis", "bezirk", "land", "bund", "eu", "extern"]
METHODS: list[str] = ["rss", "page", "query", "diff", "pdf", "newsletter", "api", "social"]
COLLECTED_METHODS: tuple[str, ...] = ("rss", "page", "query", "diff", "pdf")
PRIORITIES: list[str] = ["core", "thematic"]

# --- entities and the evidence graph ------------------------------------------
ENTITY_KINDS: list[str] = ["place", "organisation", "forum", "programme", "office"]
# Places are a closed set; every other kind grows as extraction meets new names.
OPEN_ENTITY_KINDS: set[str] = {"organisation", "forum", "programme", "office"}
ACTOR_KINDS: list[str] = ["authority", "provider", "forum", "church", "funder", "programme", "media", "peer", "other"]

# Direction reads "a <relation> b".
RELATIONS: dict[str, Label] = {
    "funding": Label("Funding", "Förderung"),
    "commissioning": Label("Commissioning", "Beauftragung"),
    "membership": Label("Membership", "Mitgliedschaft"),
    "coordination": Label("Coordination", "Koordination"),
    "supervision": Label("Supervision", "Aufsicht"),
    "cooperation": Label("Cooperation", "Kooperation"),
    "consultation": Label("Consultation", "Beratung"),
    "transfer": Label("Transfer of responsibility", "Übertragung"),
}

# --- monitoring questions -------------------------------------------------------
DIRECTIONS: list[str] = ["for", "against"]
STRENGTH_WEIGHTS: dict[str, int] = {"weak": 1, "moderate": 2, "strong": 3}

# --- calendar -------------------------------------------------------------------
EVENT_KINDS: list[str] = ["event", "deadline", "window"]
