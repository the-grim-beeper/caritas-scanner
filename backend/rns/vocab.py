"""Controlled vocabularies, transcribed from the brief (docs/brief/02, "Recommended
horizon-scanner architecture"). Nothing here is invented: the six layers, the thirty
topic tags and the authority tiers are the report's own. Signal types are the spec's."""
from __future__ import annotations

from typing import NamedTuple


class Label(NamedTuple):
    en: str
    de: str


LAYERS: dict[str, Label] = {
    "policy": Label("Policy & public sector", "Politik & Verwaltung"),
    "editorial": Label("Editorial detection", "Redaktionelle Medien"),
    "innovation": Label("Innovation & clusters", "Innovation & Cluster"),
    "corporate": Label("Corporate investment", "Unternehmen & Investitionen"),
    "infrastructure": Label("Infrastructure & property", "Infrastruktur & Immobilien"),
    "funding": Label("Funding & capital", "Förderung & Kapital"),
}

TOPICS: dict[str, Label] = {
    "CAPEX": Label("Capital expenditure", "Investitionsausgaben"),
    "FDI": Label("Foreign direct investment", "Ausländische Direktinvestitionen"),
    "corporate-expansion": Label("Corporate expansion", "Unternehmensexpansion"),
    "corporate-contraction": Label("Corporate contraction", "Unternehmensrückzug"),
    "jobs": Label("Jobs", "Arbeitsplätze"),
    "startup": Label("Startups", "Start-ups"),
    "funding-round": Label("Funding round", "Finanzierungsrunde"),
    "grant": Label("Grant", "Zuschuss"),
    "EU-funding": Label("EU funding", "EU-Förderung"),
    "public-procurement": Label("Public procurement", "Öffentliche Vergabe"),
    "commercial-real-estate": Label("Commercial real estate", "Gewerbeimmobilien"),
    "housing": Label("Housing", "Wohnen"),
    "planning-permit": Label("Planning & permits", "Planung & Genehmigung"),
    "brownfield": Label("Brownfield / conversion", "Konversion & Brachflächen"),
    "rail": Label("Rail", "Schiene"),
    "road": Label("Road", "Straße"),
    "bridge": Label("Bridges", "Brücken"),
    "public-transport": Label("Public transport", "ÖPNV"),
    "port-logistics": Label("Port & logistics", "Hafen & Logistik"),
    "energy": Label("Energy", "Energie"),
    "hydrogen": Label("Hydrogen", "Wasserstoff"),
    "CCS": Label("Carbon capture & storage", "CO₂-Abscheidung & -Speicherung"),
    "district-heating": Label("District heating", "Fernwärme"),
    "digital-infrastructure": Label("Digital infrastructure", "Digitale Infrastruktur"),
    "life-sciences": Label("Life sciences", "Life Sciences"),
    "chemicals": Label("Chemicals", "Chemie"),
    "AI": Label("Artificial intelligence", "Künstliche Intelligenz"),
    "public-policy": Label("Public policy", "Politik & Regulierung"),
    "tax": Label("Tax", "Steuern"),
    "skills": Label("Skills & workforce", "Fachkräfte"),
    "research-infrastructure": Label("Research infrastructure", "Forschungsinfrastruktur"),
}

SIGNAL_TYPES: list[str] = [
    "decision",
    "announcement",
    "investment",
    "funding_call",
    "tender",
    "planning",
    "disruption",
    "research",
    "event",
    "position",
    "data_release",
]

SIGNAL_TYPE_LABELS: dict[str, Label] = {
    "decision": Label("Decision", "Beschluss"),
    "announcement": Label("Announcement", "Ankündigung"),
    "investment": Label("Investment", "Investition"),
    "funding_call": Label("Funding call", "Förderaufruf"),
    "tender": Label("Tender", "Ausschreibung"),
    "planning": Label("Planning / permit", "Planung / Genehmigung"),
    "disruption": Label("Disruption", "Störung"),
    "research": Label("Research", "Forschung"),
    "event": Label("Event", "Veranstaltung"),
    "position": Label("Position statement", "Positionierung"),
    "data_release": Label("Data release", "Datenveröffentlichung"),
}

AUTHORITY_WEIGHTS: dict[str, float] = {"high": 1.0, "medium": 0.7, "low": 0.4}

SCOPES: list[str] = ["city", "district", "region", "state", "national", "eu"]
METHODS: list[str] = ["rss", "page", "newsletter", "api", "social"]
PRIORITIES: list[str] = ["core", "thematic"]
ENTITY_KINDS: list[str] = ["place", "organisation", "project", "fund"]
