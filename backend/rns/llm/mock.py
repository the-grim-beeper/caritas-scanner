"""Deterministic mock extraction and digest, used when no API key is set and by
the tests. Rules, not guesses: vocabulary keywords, the entity dictionary, the
forward-lag rubric and the police-blotter rule from the brief."""
from __future__ import annotations

import re
from datetime import date
from functools import lru_cache

from rns.config import settings
from rns.entities import load_seed
from rns.extract.schema import EventDraft, ExtractionResult

# --- topic keywords (lower-cased substring match, DE + EN) ----------------------
TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "CAPEX": ("investiert", "investition", "capex", "neue anlage", "neubau", "ausbau", "errichtet"),
    "FDI": ("ausländische", "foreign investment", "ansiedlung", "siedelt sich an", "headquarter"),
    "corporate-expansion": ("expansion", "erweitert", "expandiert", "neuer standort", "vergrößert", "wächst"),
    "corporate-contraction": ("stellenabbau", "abgebaut", "schließt", "schließung", "verkauft", "divestment", "veräußert", "stilllegung"),
    "jobs": ("arbeitsplätze", "stellen", "beschäftigte", "jobs", "fachkräfte", "mitarbeiter"),
    "startup": ("start-up", "startup", "gründer", "gründung", "spin-off", "ausgründung", "inkubator", "accelerator", "roadshow"),
    "funding-round": ("finanzierungsrunde", "seed", "series a", "series b", "venture", "investoren", "wagniskapital", "business angel"),
    "grant": ("zuschuss", "förderung", "fördermittel", "gefördert", "förderprogramm", "stipendium", "preis "),
    "EU-funding": ("eu-förder", "efre", "horizon europe", "eic ", "cordis", "europäische kommission", "eu-mittel"),
    "public-procurement": ("ausschreibung", "vergabe", "auftrag vergeben", "tender", "procurement"),
    "commercial-real-estate": ("gewerbefläche", "büro", "logistikimmobilie", "gewerbegebiet", "immobilienmarkt", "mietfläche", "gewerbeimmobilie"),
    "housing": ("wohnungen", "wohnungsbau", "wohnraum", "mieten", "housing"),
    "planning-permit": ("bebauungsplan", "genehmigung", "planfeststellung", "flächennutzungsplan", "baugenehmigung", "planverfahren"),
    "brownfield": ("konversion", "brachfläche", "patrick-henry", "franklin", "phv", "ehemalige kaserne", "conversion"),
    "rail": ("bahn", "schiene", "gleis", "riedbahn", "s-bahn", "ice", "bahnhof"),
    "road": ("autobahn", "bundesstraße", "b37", "b38", "a5", "a6", "a61", "a65", "straßenbau"),
    "bridge": ("brücke", "bruecke", "bridge"),
    "public-transport": ("öpnv", "straßenbahn", "stadtbahn", "rnv", "vrn", "buslinie", "nahverkehr"),
    "port-logistics": ("hafen", "logistik", "umschlag", "binnenschiff", "container"),
    "energy": ("energie", "strom", "gaskraftwerk", "solar", "windkraft", "erneuerbare", "energy", "netzausbau"),
    "hydrogen": ("wasserstoff", "hydrogen", "elektrolyse", "h2 "),
    "CCS": ("ccs", "ccus", "co2-abscheidung", "carbon capture", "kohlenstoffabscheidung"),
    "district-heating": ("fernwärme", "wärmenetz", "flusswärmepumpe", "district heating", "wärmeplanung"),
    "digital-infrastructure": ("glasfaser", "breitband", "rechenzentrum", "5g", "digitalisierung", "smart region", "data center"),
    "life-sciences": ("biotech", "pharma", "klinische", "onkologie", "krebs", "life science", "medizin", "therapie", "labor"),
    "chemicals": ("chemie", "basf", "chemiekonzern", "verbund", "chemical"),
    "AI": ("künstliche intelligenz", "ki-", "ki ", " ki", "artificial intelligence", " ai ", "machine learning"),
    "public-policy": ("gesetz", "verordnung", "regulierung", "bundesregierung", "landesregierung", "politik", "gemeinderat", "kreistag", "beschließt", "beschluss", "haushalt"),
    "tax": ("steuer", "gewerbesteuer", "abgabe", "tax"),
    "skills": ("ausbildung", "fachkräftemangel", "qualifizierung", "weiterbildung", "hochschule", "studiengang", "upskilling"),
    "research-infrastructure": ("forschungszentrum", "forschungsbau", "labor", "institut", "exzellenz", "reallabor", "campus"),
}

# Road/bridge/disruption items count only when they name an artery on the project list.
_CONDITIONAL_TOPICS = {"road", "bridge"}
_LEISURE = ("krimi", "spiel", "konzert", "festival", "fußball", "fussball", "derby", "kino", "theater",
            "wandern", "tanzen", "sprechstunde", "ausstellung", "fest ", "kirmes", "weihnacht")
_DISRUPTION = ("gesperrt", "sperrung", "vollsperrung", "störung", "ausfall", "unfall", "brand")
_PAST = ("rückblick", "bilanz", "hat ", "hatte", "wurde", "wurden", "abgeschlossen", "eröffnet worden")

_DATE_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})")
_DEADLINE_CUES = ("bewerbungsschluss", "bewerbungsfrist", "frist", "bis zum", "deadline", "einsendeschluss", "anmeldeschluss", "endet am")
_EVENT_CUES = ("roadshow", "veranstaltung", "konferenz", "kongress", "messe", "tag ", "investor", "pitch", "sitzung", "forum", "summit", "workshop")


def _has(text: str, kw: str) -> bool:
    """Prefix-bounded: "bahn" matches "Bahnhof" but not "Fahrbahn" or "Autobahn"."""
    return re.search(rf"(?<![\wäöüß]){re.escape(kw.strip())}", text) is not None


def _any(text: str, kws) -> bool:
    return any(_has(text, k) for k in kws)


@lru_cache
def _dictionary() -> dict[str, list[tuple[str, str]]]:
    """kind -> [(lowercased alias, canonical name)], longest alias first."""
    out: dict[str, list[tuple[str, str]]] = {}
    for seed in load_seed(settings.resolved_data_dir() / "entities.yaml"):
        names = [seed.name, *seed.aliases]
        for n in names:
            out.setdefault(seed.kind, []).append((n.lower(), seed.name))
    for kind in out:
        out[kind].sort(key=lambda t: -len(t[0]))
    return out


def _find_entities(text: str, kind: str) -> list[str]:
    """Aliases are lower-cased; match against lower-cased text, word-bounded."""
    text = text.lower()
    found: list[str] = []
    for alias, name in _dictionary().get(kind, []):
        if len(alias) < 3:
            continue
        if re.search(rf"(?<![\w-]){re.escape(alias)}(?![\w-])", text):
            if name not in found:
                found.append(name)
    return found


def _dates(text: str) -> list[tuple[int, date]]:
    out: list[tuple[int, date]] = []
    for m in _DATE_RE.finditer(text):
        d, mth, y = (int(g) for g in m.groups())
        try:
            out.append((m.start(), date(y, mth, d)))
        except ValueError:
            continue
    return out


def _events(text_lower: str, text_orig: str, title: str) -> tuple[EventDraft, ...]:
    dates = _dates(text_orig)
    if not dates:
        return ()
    deadline: date | None = None
    start: date | None = None
    for pos, d in dates:
        window = text_lower[max(0, pos - 40):pos]
        if any(c in window for c in _DEADLINE_CUES) and deadline is None:
            deadline = d
        elif start is None:
            start = d
    if start is None and deadline is None:
        return ()
    is_eventish = any(c in text_lower for c in _EVENT_CUES)
    if not is_eventish and deadline is None:
        return ()
    return (EventDraft(name=title[:400], start_date=start, deadline=deadline),)


def mock_extract(title: str, summary: str, source_layer: str) -> ExtractionResult:
    text_orig = f"{title}\n{summary or ''}"
    text = text_orig.lower()

    hits = [code for code, kws in TOPIC_KEYWORDS.items() if _any(text, kws)]
    projects = _find_entities(text_orig, "project")
    places = _find_entities(text_orig, "place")
    organisations = _find_entities(text_orig, "organisation")

    # The police-blotter rule: road/bridge/disruption items need a named artery.
    if not projects:
        hits = [h for h in hits if h not in _CONDITIONAL_TOPICS]
    disrupted = _any(text, _DISRUPTION)
    leisure = _any(text, _LEISURE)
    substantive = [h for h in hits if h not in ("public-policy",)] or projects
    is_signal = bool(substantive) and not (leisure and len(hits) <= 1 and not projects)
    if disrupted and not projects and not [h for h in hits if h not in _CONDITIONAL_TOPICS]:
        is_signal = False
    if not is_signal:
        return ExtractionResult(is_signal=False)

    # signal type
    if _any(text, ("förderaufruf", "bewerbungsfrist", "bewerbungsschluss", "call for", "stipendium", "ausschreibung der förderung")):
        stype, lag = "funding_call", 1.0
    elif _any(text, ("ausschreibung", "vergabe", "tender")):
        stype, lag = "tender", 1.0
    elif _any(text, ("bebauungsplan", "planfeststellung", "planverfahren", "genehmigung")):
        stype, lag = "planning", 0.9
    elif _any(text, ("beschließt", "beschluss", "gemeinderat", "kreistag", "verabschiedet")):
        stype, lag = "decision", 0.6
    elif disrupted:
        stype, lag = "disruption", 0.4
    elif _any(text, ("investiert", "investition", "millionen", "milliarden")):
        stype, lag = "investment", 0.7
    elif _any(text, _EVENT_CUES) and _dates(text_orig):
        stype, lag = "event", 0.7
    elif _any(text, ("studie", "forschung", "forscher", "wissenschaftler", "veröffentlicht in")):
        stype, lag = "research", 0.4
    elif _any(text, ("warnt", "fordert", "kritisiert", "positionspapier")):
        stype, lag = "position", 0.5
    elif _any(text, ("konjunktur", "umfrage", "bericht", "zahlen", "statistik")):
        stype, lag = "data_release", 0.3
    else:
        stype, lag = "announcement", 0.5
    if _any(text, _PAST) and stype in ("announcement", "investment", "research", "data_release"):
        lag = 0.1

    regional = 1.0 if (places or projects) else (0.6 if source_layer in ("policy", "editorial", "infrastructure") else 0.4)
    materiality = 0.8 if _any(text, ("millionen", "milliarden", "million")) else min(0.9, 0.35 + 0.1 * len(hits))

    return ExtractionResult(
        is_signal=True,
        headline_en=title.strip(),
        headline_de=title.strip(),
        summary_en=(summary or "").strip()[:600],
        summary_de=(summary or "").strip()[:600],
        signal_type=stype,
        topics=tuple(hits),
        places=tuple(places),
        organisations=tuple(organisations),
        projects=tuple(projects),
        regional_relevance=regional,
        economic_materiality=materiality,
        forward_lag=lag,
        events=_events(text, text_orig, title),
    )


def mock_digest(signals: list[dict], events: list[dict], movers: list[dict]) -> dict:
    """A digest shaped exactly like the live one, citing only real ids."""
    by_layer: dict[str, list[dict]] = {}
    for s in signals:
        by_layer.setdefault(s["layer"], []).append(s)
    sections = [
        {"layer": layer, "items": [
            {"signal_id": s["id"],
             "note_en": f"[mock] {s['headline_en'][:120]}",
             "note_de": f"[mock] {s['headline_de'][:120]}"}
            for s in items[:5]
        ]}
        for layer, items in by_layer.items()
    ]
    top = signals[:3]
    n = len(signals)
    return {
        "lead_en": f"[mock] {n} founding signals this cycle across {len(by_layer)} layers; "
                   f"strongest: {'; '.join(s['headline_en'][:80] for s in top)}.",
        "lead_de": f"[mock] {n} neue Signale in diesem Zyklus über {len(by_layer)} Ebenen; "
                   f"stärkste: {'; '.join(s['headline_de'][:80] for s in top)}.",
        "sections": sections,
        "chains": [],
        "watch": [{"event_id": e["id"], "why_en": "[mock] upcoming deadline", "why_de": "[mock] anstehende Frist"}
                  for e in events[:5]],
    }
