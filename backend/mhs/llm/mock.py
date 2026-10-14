"""Deterministic mock extraction and digest, used when no API key is set and by
the tests. Rules, not guesses: keywords from the brief's German filter lexicon
(docs/brief/source-architecture.txt, pp. 14–16), the entity dictionary, and the
not-a-signal guard (sport, leisure, police blotter, weather, church services)."""
from __future__ import annotations

import re
from datetime import date
from functools import lru_cache

from mhs.config import settings
from mhs.entities import load_seed
from mhs.extract.schema import EventDraft, ExtractionResult

# --- topic keywords (lower-cased, prefix-bounded: see _has) ---------------------
# A keyword matches at the start of a word, so compounds that END in it need their own
# entry ("kreisumlage" beside "umlage"); in return "kita" does not fire inside "Skitag".
_TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    # struktur
    "koordination": ("koordination", "koordinierung", "vernetzung", "netzwerk", "runder tisch", "runden tisch",
                     "arbeitskreis", "sozialbeirat", "steuerungsgruppe", "lenkungsgruppe", "versorgungskonferenz",
                     "pflegekonferenz", "psag"),
    "steuerung": ("trägerschaft", "mandat", "zweckvereinbarung", "kooperationsvereinbarung", "geschäftsordnung",
                  "federführend", "institutionelle verankerung"),
    "verstetigung": ("verstetig", "regelfinanzierung", "dauerhaft", "überführt", "regelangebot"),
    "interkommunal": ("interkommunal", "gemeindeübergreifend", "trägerübergreifend", "ressortübergreifend",
                      "zweckverband"),
    "quartier": ("quartier", "sozialraum", "nachbarschaft", "dorfgemeinschaft"),
    "daten": ("sozialbericht", "sozialplanung", "statistik", "bedarfsanalyse", "bedarfsplanung", "erhebung",
              "monitoring"),
    "kirchenstruktur": ("dekanat", "pfarrverband", "pfarrverbände", "pfarrei", "seelsorgsraum", "kirchenimmobilie",
                        "pfarrheim", "kirchensteuer"),
    "traegerwandel": ("fusion", "fusioniert", "zusammengelegt", "zusammenlegung", "schließung", "schließt",
                      "insolvenz", "neugründung", "aufgelöst", "trägerwechsel"),
    # personal
    "fachkraefte": ("fachkräfte", "fachkraft", "personalmangel", "personalengpass", "pflegefachkraft",
                    "pflegefachkräfte", "sozialpädagog", "erzieher", "krankheitsausfall", "fluktuation"),
    "stellen": ("stellenanzeige", "stellenausschreibung", "stellenplan", "stellenstreichung", "vakant", "unbesetzt",
                "nachbesetzung", "neu besetzt", "projektstelle"),
    "leitung": ("leitungswechsel", "neue leitung", "geschäftsführung", "geschäftsführer", "einrichtungsleitung",
                "bereichsleitung", "ruhestand", "amtsantritt", "nachfolger"),
    "ehrenamt": ("ehrenamt", "nachbarschaftshilfe", "freiwillig", "bürgerschaftlich"),
    # bedarf
    "pflege": ("pflege", "senioren", "tagespflege", "kurzzeitpflege", "pflegestützpunkt", "pflegeheim",
               "altenheim", "demenz", "pflegende angehörige", "häusliche pflege", "ambulante pflege", "hospiz"),
    "jugend-familie": ("jugendhilfe", "jugendamt", "kita", "kinderbetreuung", "hilfen zur erziehung",
                       "erziehungsberatung", "familienstützpunkt", "jugendarbeit", "schulbegleitung",
                       "kindergarten", "krippe"),
    "eingliederung": ("eingliederungshilfe", "inklusion", "inklusiv", "behinderung", "behindertenarbeit", "bthg"),
    "psyche": ("psychisch", "psychiatr", "psychosozial", "suchtberatung", "suchthilfe", "suchtkrank",
               "krisendienst", "depression"),
    "armut": ("armut", "altersarmut", "grundsicherung", "bürgergeld", "tafel", "schuldnerberatung",
              "sozialhilfe", "wohngeld"),
    "wohnen": ("wohnungsnot", "wohnraum", "sozialwohnung", "wohnungsbau", "obdachlos", "wohnungslos",
               "betreutes wohnen"),
    "integration": ("integration", "migration", "geflüchtete", "flüchtling", "asyl", "zuwander", "sprachkurs"),
    "teilhabe": ("teilhabe", "einsamkeit", "einsam", "begegnungsstätte", "seniorentreff", "mehrgenerationenhaus"),
    "gesundheit": ("krankenhaus", "klinik", "hausarzt", "hausärzt", "ärztemangel", "gesundheitsversorgung",
                   "gesundheitsregion", "notaufnahme", "community nurs", "gemeindeschwester"),
    "mobilitaet": ("öpnv", "buslinie", "rufbus", "mvv", "bergbus", "fahrdienst", "barrierefrei", "bürgerbus",
                   "mitfahrbank", "fahrplan", "taktverdichtung", "fahrtausfall", "on-demand", "erreichbarkeit"),
    "demografie": ("demograf", "demograph", "bevölkerungsentwicklung", "bevölkerungsprognose", "alterung",
                   "überalterung", "geburtenzahl"),
    # geld
    "haushalt": ("haushalt", "kreishaushalt", "nachtragshaushalt", "defizit", "konsolidierung", "kürzung",
                 "kürzt", "kürzen", "gekürzt", "einsparung", "deckungslücke", "freiwillige leistung"),
    "umlagen": ("kreisumlage", "bezirksumlage", "umlage", "hebesatz", "hebesätz", "schlüsselzuweisung",
                "finanzausgleich"),
    "foerderung": ("förder", "zuschuss", "zuschüss", "zuwendung", "sela", "pflegesonah", "leader", "esf",
                   "aktion mensch", "kofinanzierung", "eigenanteil"),
    "foerderende": ("förderende", "auslauf", "läuft aus", "anschlussförderung", "anschlussfinanzierung",
                    "befristet", "förderperiode"),
    "vereinbarungen": ("leistungsvereinbarung", "vergütungsvereinbarung", "vergütung", "pflegesatz", "pflegesätze",
                       "rahmenvertrag", "entgelt"),
    # regeln
    "gesetzgebung": ("gesetz", "referentenentwurf", "verordnung", "richtlinie", "inkrafttreten", "tritt in kraft",
                     "rechtsanspruch", "konnexität", "kabinettsbeschluss", "bundestag", "bundesrat"),
    "sgb": ("sgb", "bürgergeld", "grundsicherung", "sozialgesetzbuch", "pflegereform", "bthg"),
    "landesprogramm": ("landesprogramm", "staatsministerium", "stmas", "stmgp", "sela", "pflegesonah"),
    # stimmung
    "politik": ("kommunalwahl", "bürgermeisterwahl", "landratswahl", "stichwahl", "gewählt", "wahlkampf",
                "fraktion"),
    "kontroverse": ("bürgerinitiative", "bürgerbegehren", "petition", "protest", "widerstand", "kritik",
                    "kritisiert", "umstritten", "streit", "kontrovers", "abgelehnt", "vertagt"),
}

# Any of these and the item is not a signal, whatever else it mentions.
_NOT_A_SIGNAL = ("fußball", "fussball", "tsv ", "derby", "konzert", "festival", "polizei", "unfall", "wetter",
                 "gottesdienst")

# Ahead of the decision (forward_lag 0.7) rather than an ongoing or past matter (0.4).
_FORWARD = ("beschließt", "plant", "soll", "künftig", "ab 2027", "antrag", "frist")
_FORWARD_YEAR = re.compile(r"\bab 20\d\d\b")

# The form of the development; first match wins.
_TYPE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("funding_call", ("förderaufruf", "antragsfrist", "bewerbungsfrist", "bewerbungsschluss", "förderrichtlinie")),
    ("budget", ("haushalt", "kreishaushalt", "nachtragshaushalt", "kreisumlage", "bezirksumlage", "umlage",
                "hebesatz")),
    ("service_change", ("öffnungszeit", "aufnahmestopp", "warteliste", "verkürzt", "schließt", "schließung",
                        "eröffnet", "eröffnung", "neues angebot", "eingestellt")),
    ("staffing", ("personalmangel", "fachkräftemangel", "stellenanzeige", "stellenausschreibung", "nachbesetzung",
                  "vakant", "unbesetzt", "neue leitung", "leitungswechsel", "ruhestand", "nachfolger")),
    ("decision", ("beschließt", "beschluss", "beschlossen", "verabschiedet", "genehmigt", "abgelehnt")),
    ("planning", ("plant", "planung", "konzept", "entwurf")),
    ("disruption", ("fahrtausfall", "ausfall", "streik", "störung", "notstand")),
    ("data_release", ("sozialbericht", "statistik", "zahlen", "bericht", "erhebung")),
    ("research", ("studie", "forschung", "untersuchung", "evaluation")),
    ("position", ("fordert", "warnt", "kritisiert", "positionspapier", "stellungnahme", "appell")),
)

_DATE_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})")
_DEADLINE_CUES = ("anmeldeschluss", "antragsfrist", "bewerbungsfrist", "bewerbungsschluss", "einsendeschluss",
                  "frist", "bis zum", "endet am", "deadline")
_EVENT_CUES = ("sitzung", "tagt", "fachtag", "veranstaltung", "konferenz", "workshop", "infoabend",
               "informationsabend", "bürgerversammlung", "versammlung", "treffen", "forum")


def _has(text: str, kw: str) -> bool:
    """Prefix-bounded: "pflege" matches "Pflegestützpunkt" but not "Landschaftspflege"."""
    return re.search(rf"(?<![\wäöüß]){re.escape(kw.strip())}", text) is not None


def _any(text: str, kws) -> bool:
    return any(_has(text, k) for k in kws)


@lru_cache
def _dictionary() -> list[tuple[str, str, str]]:
    """[(lower-cased name or alias, kind, canonical name)] across all kinds, longest first."""
    out: list[tuple[str, str, str]] = []
    for seed in load_seed(settings.resolved_data_dir() / "entities.yaml"):
        for n in (seed.name, *seed.aliases):
            if len(n) >= 3:
                out.append((n.lower(), seed.kind, seed.name))
    out.sort(key=lambda t: -len(t[0]))
    return out


def _find_entities(text: str) -> dict[str, list[str]]:
    """Exact name/alias matches, word-bounded. Longest first, and a matched span is blanked
    so "Miesbach" is not found again inside "Landkreis Miesbach" or "Caritas-Zentrum Miesbach"."""
    text = text.lower()
    found: dict[str, list[str]] = {}
    for alias, kind, name in _dictionary():
        pattern = rf"(?<![\w-]){re.escape(alias)}(?![\w-])"
        if re.search(pattern, text):
            if name not in found.setdefault(kind, []):
                found[kind].append(name)
            text = re.sub(pattern, lambda m: " " * len(m.group(0)), text)
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
        if any(c in window for c in _DEADLINE_CUES):
            deadline = deadline or d
        elif start is None:
            start = d
    if start is None and deadline is None:
        return ()
    if deadline is None and not _any(text_lower, _EVENT_CUES):
        return ()
    return (EventDraft(name=title[:400], start_date=start, deadline=deadline),)


def mock_extract(title: str, summary: str, source_layer: str) -> ExtractionResult:
    text_orig = f"{title}\n{summary or ''}"
    text = text_orig.lower()

    topics = [code for code, kws in _TOPIC_KEYWORDS.items() if _any(text, kws)]
    if not topics or _any(text, _NOT_A_SIGNAL):
        return ExtractionResult(is_signal=False)

    entities = _find_entities(text_orig)
    places = entities.get("place", [])
    events = _events(text, text_orig, title)
    if any(ev.start_date for ev in events) and _any(text, _EVENT_CUES):
        stype = "event"
    else:
        stype = next((t for t, kws in _TYPE_RULES if _any(text, kws)), "announcement")
    if stype == "event" and _any(text, _TYPE_RULES[0][1]):
        stype = "funding_call"  # a call with a date is still a call
    forward = _any(text, _FORWARD) or _FORWARD_YEAR.search(text) is not None

    return ExtractionResult(
        is_signal=True,
        headline_en=title.strip(),
        headline_de=title.strip(),
        summary_en=(summary or "").strip()[:600],
        summary_de=(summary or "").strip()[:600],
        signal_type=stype,
        topics=tuple(topics),
        places=tuple(places),
        organisations=tuple(entities.get("organisation", [])),
        forums=tuple(entities.get("forum", [])),
        programmes=tuple(entities.get("programme", [])),
        offices=tuple(entities.get("office", [])),
        regional_relevance=1.0 if places else 0.4,
        consequence=min(1.0, 0.3 + 0.15 * len(topics)),
        forward_lag=0.7 if forward else 0.4,
        events=events,
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
    top = signals[:2]
    n = len(signals)
    return {
        "lead_en": f"[mock] {n} founding signals this cycle across {len(by_layer)} layers. "
                   f"Highest-scoring: {' — '.join(s['headline_en'][:70] for s in top)}. "
                   "Set ANTHROPIC_API_KEY for an analyst-written lead.",
        "lead_de": f"[mock] {n} neue Signale in diesem Zyklus über {len(by_layer)} Ebenen. "
                   f"Höchster Score: {' — '.join(s['headline_de'][:70] for s in top)}. "
                   "ANTHROPIC_API_KEY setzen für ein analytisch verfasstes Lagebild.",
        "sections": sections,
        "chains": [],
        "watch": [{"event_id": e["id"], "why_en": "[mock] upcoming deadline", "why_de": "[mock] anstehende Frist"}
                  for e in events[:5]],
    }
