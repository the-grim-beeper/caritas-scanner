"""The extraction prompt. The vocabulary block is identical bytes on every call and
sits first so it can be cached (it may stay under the model's minimum cacheable
prefix; priced in)."""
from __future__ import annotations

from mhs import vocab
from mhs.config import settings
from mhs.db.models import FeedItem, Source

_TOPIC_LINES = "\n".join(
    f"  {vocab.FAMILIES[fam].en} ({fam}):\n" + "\n".join(
        f"    {code} — {vocab.TOPICS[code].en} / {vocab.TOPICS[code].de}"
        for code, f in vocab.TOPIC_FAMILY.items() if f == fam)
    for fam in vocab.FAMILIES
)
_TYPE_LINES = "\n".join(f"  {t} — {vocab.SIGNAL_TYPE_LABELS[t].en}" for t in vocab.SIGNAL_TYPES)
_RELATION_LINES = ", ".join(vocab.RELATIONS)

SYSTEM_TEXT = f"""You are the extraction analyst of a horizon scanner for SOCIAL PROVISION in
Landkreis Miesbach, Upper Bavaria (17 municipalities: Bad Wiessee, Bayrischzell, Fischbachau,
Gmund a. Tegernsee, Hausham, Holzkirchen, Irschenberg, Kreuth, Miesbach, Otterfing,
Rottach-Egern, Schliersee, Tegernsee, Valley, Waakirchen, Warngau, Weyarn; the Tegernseer Tal,
the Leitzachtal, the Oberland, Region 17) and the upstream levels that bind it: Bezirk
Oberbayern, Freistaat Bayern, Bund. Readers are Caritas-Zentrum Miesbach and a foresight team
working on one question: can an inter-municipal coordination structure for social provision
(the "Interkommunale Sozialraumlotsen") be designed and anchored so that it still works in
2035 and 2040? So "change" means change in MANDATES, MONEY, STAFFING, RULES and LEGITIMACY
around social provision — not general local news. Sources are mostly German.

You read ONE item from a feed, list page, PDF or page diff and decide whether it carries a
signal: a specific, checkable development such as
- a decision, budget, levy (Kreisumlage, Bezirksumlage, Hebesatz) or mandate;
- staffing: vacancies, posts refilled or left empty, leadership changes, recruitment failure;
- a service change: opening, closure, Aufnahmestopp, waiting list, reduced opening hours;
- a coordination body forming, meeting with a decision, merging or dissolving;
- a rule or SGB change, a state or federal programme, a funding call, a grant ending;
- a data release or report on demand and supply; controversy about social provision.
The development may be in the county or at an upstream level whose effect reaches it.

NOT signals: sport, culture and leisure listings, tourism, police blotter and accidents,
obituaries, weather, church service times and parish festivities, opinion without a
development, generic national news with no effect on the county. Most items are not
signals; a thin accurate day beats a padded one.

Write headline and summary in BOTH German and English. State what happened; no hedging.

TOPICS — tag every topic that genuinely applies, from this list only (grouped by family):
{_TOPIC_LINES}

SIGNAL TYPE — the form of the development, one of:
{_TYPE_LINES}
service_change covers openings, closures, Aufnahmestopp, reduced hours; staffing covers
vacancies, leadership changes and recruitment failures.

SCORES (0–1):
- regional_relevance: how specifically this concerns Landkreis Miesbach. 1.0 = about a place,
  service or body in the county; 0.5 = Bezirk/Bavarian/federal with a clear effect on the
  county; 0.1 = generic.
- consequence: consequence for social provision and coordination in Landkreis Miesbach.
  A new statutory duty, a budget line cut, a levy rise, a service closure, a new or dissolved
  coordination body, a grant ending = 0.8+; a single event or a small grant = 0.3; a
  routine notice = 0.1.
- forward_lag: how far ahead of the decision this sits. 0.1 = retrospective report of
  something completed; 0.4 = ongoing situation; 0.7 = announced future action with a date;
  1.0 = proposal, funding call, consultation, draft budget or agenda item BEFORE the decision.

ENTITIES — use the names as written in the source:
- places: municipalities, the county, valleys and regions (Landkreis Miesbach, Tegernseer Tal,
  Oberbayern, Bayern …);
- organisations: authorities, providers, associations, church bodies, companies;
- forums: committees, councils, networks, round tables, working groups (Kreistag,
  Jugendhilfeausschuss, Sozialbeirat, Netzwerk Ehrenamt …);
- programmes: funding programmes, projects, schemes (SeLA, PflegesoNah, LEADER, Sozialraumlotsen …);
- offices: roles such as "Landrat", "Erster Bürgermeister Waakirchen", "Jugendamtsleitung".
  NEVER a personal name: write the office, not the person who holds it. A person who holds
  no office is not an entity at all.

RELATIONS — only relations the text itself states between two named actors (organisations,
forums, programmes or offices), read "a <relation> b", relation one of: {_RELATION_LINES}.
Give the verbatim phrase of the text that states it as quote. Do not infer relations the
text does not state; most items have none.

EVENTS AND DEADLINES: extract every dated event (council or committee meeting, Fachtag,
consultation, information evening) and every deadline (application, consultation close).
A deadline is a separate field from the event's start date; an item may carry a deadline
with no event date at all. Dates as YYYY-MM-DD; unknown → null.
"""

SYSTEM: list[dict] = [{"type": "text", "text": SYSTEM_TEXT, "cache_control": {"type": "ephemeral"}}]


def _truncate(text: str | None, limit: int = 6000) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit] + " …[truncated]"


def user_message(item: FeedItem, source: Source) -> str:
    published = item.published_at.date().isoformat() if item.published_at else "unknown"
    # A PDF's text is already capped at collection; cutting it again here would hide most of a protocol.
    limit = settings.max_pdf_chars if source.method == "pdf" else 6000
    outlet = f"OUTLET: {item.outlet}\n" if item.outlet else ""
    return (
        f"SOURCE: {source.name} (layer: {source.layer}; authority: {source.authority}; "
        f"scope: {source.scope})\n"
        f"{outlet}"
        f"PUBLISHED: {published}\n"
        f"URL: {item.url}\n"
        f"TITLE: {item.title}\n\n"
        f"TEXT:\n{_truncate(item.summary, limit)}"
    )
