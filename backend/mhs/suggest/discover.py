"""The weekly scout: one web-searching model call that proposes new sources against the
scanner's coverage gaps (port of Sandglass's _discovery_messages, with web search instead of
recall, so the model proposes pages it has actually seen).

Not complete_json: the call needs the server-side web_search tool, whose response interleaves
thinking / server_tool_use / web_search_tool_result / code_execution_tool_result blocks before
the final text; the JSON answer is the LAST text block. A server-side loop that hits its
iteration limit stops with pause_turn and is resumed by re-sending the paused turn.

Without an API key the scout proposes nothing (mock mode never invents sources)."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from anthropic import APIStatusError, AuthenticationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhs import vocab
from mhs.config import settings
from mhs.db.models import Entity, Question, Signal, Source
from mhs.llm.client import LLMAuthError, LLMEmptyCompletion, LLMRequestError, client
from mhs.suggest.validate import known_urls

log = logging.getLogger(__name__)

# The county's 17 municipalities, as named in data/entities.yaml (places).
MUNICIPALITIES: tuple[str, ...] = (
    "Bad Wiessee", "Bayrischzell", "Fischbachau", "Gmund a. Tegernsee", "Hausham", "Holzkirchen",
    "Irschenberg", "Kreuth", "Miesbach", "Otterfing", "Rottach-Egern", "Schliersee", "Tegernsee",
    "Valley", "Waakirchen", "Warngau", "Weyarn",
)
MAX_HEADLINES = 30
MAX_CONTINUATIONS = 2
MAX_TOKENS = 8000
MAX_URL_LENGTH = 2048

# No minItems/maxItems/length keywords: the structured-output API rejects them. Counts are in
# the prompt and capped in code (parse_candidates).
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "url": {"type": "string"},
                    "layer": {"type": "string", "enum": list(vocab.LAYERS)},
                    "scope": {"type": "string", "enum": list(vocab.SCOPES)},
                    "places": {"type": "array", "items": {"type": "string"}},
                    "rationale_de": {"type": "string"},
                    "rationale_en": {"type": "string"},
                },
                "required": ["name", "url", "layer", "scope", "places", "rationale_de", "rationale_en"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["candidates"],
    "additionalProperties": False,
}


@dataclass
class Candidate:
    name: str
    url: str
    layer: str
    scope: str
    places: list[str]
    rationale_de: str
    rationale_en: str


# ---------------------------------------------------------------------------
# parse
# ---------------------------------------------------------------------------
def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _http_url(url: str) -> bool:
    if not url or len(url) > MAX_URL_LENGTH or any(c.isspace() for c in url):
        return False
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return parts.scheme in ("http", "https") and bool(parts.hostname)


def parse_candidates(payload: Any, place_index: dict[str, str], *, limit: int | None = None) -> list[Candidate]:
    """Candidates whose layer and scope are in the vocabulary, with an http(s) URL and a name;
    places reduced to seeded place names (place_index: normalised name/alias → name).
    At most `limit` (default settings.suggest_max_candidates)."""
    limit = settings.suggest_max_candidates if limit is None else limit
    raw = payload.get("candidates") if isinstance(payload, dict) else None
    if not isinstance(raw, list):
        return []
    out: list[Candidate] = []
    for c in raw:
        if len(out) >= limit:
            break
        if not isinstance(c, dict):
            continue
        name, url = _text(c.get("name")), _text(c.get("url"))
        layer, scope = c.get("layer"), c.get("scope")
        rationale_de = _text(c.get("rationale_de"))
        if not name or not rationale_de or layer not in vocab.LAYERS or scope not in vocab.SCOPES or not _http_url(url):
            log.info("suggest: dropped candidate %r (%s, %s, %s)", name, url[:200], layer, scope)
            continue
        places: list[str] = []
        for p in c.get("places") or []:
            hit = place_index.get(_norm(p)) if isinstance(p, str) else None
            if hit and hit not in places:
                places.append(hit)
        out.append(Candidate(name=name[:300], url=url, layer=layer, scope=scope, places=places,
                             rationale_de=rationale_de[:2000], rationale_en=_text(c.get("rationale_en"))[:2000]))
    return out


# ---------------------------------------------------------------------------
# prompt
# ---------------------------------------------------------------------------
async def _place_index(session: AsyncSession) -> dict[str, str]:
    index: dict[str, str] = {}
    for name, aliases in (await session.execute(select(Entity.name, Entity.aliases).where(Entity.kind == "place"))).all():
        index.setdefault(_norm(name), name)
        for a in aliases or []:
            index.setdefault(_norm(a), name)
    for m in MUNICIPALITIES:  # the municipalities are known even before the seed is loaded
        index.setdefault(_norm(m), m)
    return index


_LAYER_LINES = "\n".join(f"  {code} — {lbl.en} / {lbl.de}" for code, lbl in vocab.LAYERS.items())


def _system(place_names: list[str]) -> str:
    return f"""You are the source scout of the Horizont-Scanner Landkreis Miesbach, a horizon scanner for
SOCIAL PROVISION in Landkreis Miesbach, Upper Bavaria, run for Caritas-Zentrum Miesbach. It watches
mandates, money, staffing, rules and legitimacy around social provision in the county's 17
municipalities and at the levels that bind them (Bezirk Oberbayern, Freistaat Bayern, Bund). It
collects automatically from RSS/Atom feeds and from list pages.

Once a week you look for NEW sources that close its coverage gaps. Use web search to find
candidates and to check that each one exists and is current. Propose only pages you have seen in
search results.

What qualifies — durable listing endpoints that publish again and again:
- RSS/Atom feeds;
- list pages: "Aktuelles", "Neuigkeiten", "Pressemitteilungen", "Bekanntmachungen" /
  "Amtsblatt" / "Amtliche Bekanntmachungen", "Sitzungskalender" / Ratsinformationssystem (RIS),
  the news pages of welfare associations, churches and services.
Give the URL of the feed or of the listing page itself, not the homepage, when you can find it.

Official or established sources only: municipalities and their councils, the Landratsamt and its
services, Bezirk Oberbayern, Bavarian and federal ministries and agencies, welfare associations
(Caritas, Diakonie, AWO, BRK, Lebenshilfe, Paritätischer), churches, established local and
regional media, research institutes, the social planning of comparable counties.

Never propose: social media (Facebook, Instagram, X, YouTube, LinkedIn, …), single articles,
single PDF documents, search-result or tag pages, aggregators, paywalled pages, pages behind a
login, tourism or leisure event portals. German-language sites are preferred.

Every URL you propose is fetched and verified: it must be a feed with items or a list page with at
least three linked entries; anything else is discarded. Propose at most
{settings.suggest_max_candidates} candidates. Fewer good candidates beat many weak ones; an empty
list is a valid answer.

For each candidate:
- name: publisher and page, in German as on the site (e.g. "Gemeinde Weyarn – Aktuelles");
- url: the feed or listing page;
- layer: exactly one of
{_LAYER_LINES}
- scope: the level the source speaks for, one of {", ".join(vocab.SCOPES)};
- places: the places it covers, using ONLY names from this closed list (empty if none applies):
  {", ".join(place_names)};
- rationale_de and rationale_en: one sentence each, the same content in German and in English —
  what the source publishes and which gap or monitoring question it serves.

Return only the JSON object."""


async def build_prompt(session: AsyncSession) -> tuple[str, str]:
    system, user, _index = await _build(session)
    return system, user


async def _build(session: AsyncSession) -> tuple[str, str, dict[str, str]]:
    index = await _place_index(session)
    place_names = sorted(set(index.values()), key=lambda n: (n not in MUNICIPALITIES, n))

    per_layer = dict((await session.execute(
        select(Source.layer, func.count(Source.id)).where(Source.collect.is_(True)).group_by(Source.layer))).all())
    per_place: dict[str, int] = dict.fromkeys(MUNICIPALITIES, 0)
    for (places,) in (await session.execute(select(Source.places).where(Source.collect.is_(True)))).all():
        for name in {index.get(_norm(p)) for p in places or [] if isinstance(p, str)}:
            if name in per_place:
                per_place[name] += 1
    zero = [m for m, n in per_place.items() if n == 0]

    questions = (await session.execute(select(Question.id, Question.title_de).order_by(Question.sort))).all()
    headlines = (await session.execute(
        select(Signal.headline_de).where(Signal.is_founder.is_(True))
        .order_by(Signal.published_at.desc()).limit(MAX_HEADLINES))).scalars().all()
    known = sorted(await known_urls(session))

    lines = ["COVERAGE — collected sources per layer:"]
    lines += [f"  {code}: {int(per_layer.get(code, 0))} ({lbl.en} / {lbl.de})" for code, lbl in vocab.LAYERS.items()]
    lines += ["", "COVERAGE — collected sources per municipality:"]
    lines += [f"  {m}: {n}" for m, n in per_place.items()]
    lines.append("Municipalities with NO collected source: " + (", ".join(zero) if zero else "none"))
    lines += ["", "WHAT THE SCANNER IS FOR — its monitoring questions:"]
    lines += [f"  {qid}: {title}" for qid, title in questions] or ["  (not loaded)"]
    lines += ["", "RECENT HEADLINES — what the current sources deliver:"]
    lines += [f"  - {h}" for h in headlines] or ["  (none yet)"]
    lines += ["", "KNOWN URLS — already in the catalogue or already suggested, declined or rejected. NEVER",
              "propose any of these or a trivial variant (www., trailing slash, http/https, tracking parameters):"]
    lines += [f"  - {u}" for u in known] or ["  (none yet)"]
    lines += ["", "Find new sources that close the gaps above — municipalities without a source first, then",
              "thin layers, then sources that would answer a monitoring question the headlines do not touch."]
    return _system(place_names), "\n".join(lines), index


# ---------------------------------------------------------------------------
# live call
# ---------------------------------------------------------------------------
def _tools() -> list[dict]:
    return [{
        "type": settings.suggest_web_search_tool,
        "name": "web_search",
        "max_uses": settings.suggest_web_search_max_uses,
        "user_location": {"type": "approximate", "country": "DE", "region": "Bavaria", "city": "Miesbach",
                          "timezone": "Europe/Berlin"},
    }]


def _last_text(message: Any) -> str | None:
    for block in reversed(getattr(message, "content", None) or []):
        if getattr(block, "type", None) == "text":
            text = (getattr(block, "text", None) or "").strip()
            if text:
                return text
    return None


async def _call_live(system: str, user: str) -> dict | None:
    """The parsed JSON answer, or None on a refusal. Raises LLMAuthError / LLMRequestError
    (same classes as mhs.llm.client) and LLMEmptyCompletion when no usable answer arrives."""
    output_config = {"format": {"type": "json_schema", "schema": SCHEMA}}
    tools = _tools()
    messages: list[dict] = [{"role": "user", "content": user}]
    for _ in range(MAX_CONTINUATIONS + 1):
        try:
            message = await client().messages.create(
                model=settings.suggest_model,
                max_tokens=MAX_TOKENS,
                system=system,
                messages=messages,
                tools=tools,
                output_config=output_config,
            )
        except AuthenticationError as exc:
            raise LLMAuthError(str(exc)) from exc
        except APIStatusError as exc:
            if exc.status_code == 400:
                raise LLMRequestError(str(exc)) from exc
            raise
        stop = getattr(message, "stop_reason", None)
        if stop == "refusal":
            log.warning("suggest: %s refused the discovery request", settings.suggest_model)
            return None
        if stop == "pause_turn":
            # Resume: re-send the paused assistant turn, no extra user message.
            messages = [*messages, {"role": "assistant", "content": message.content}]
            continue
        text = _last_text(message)
        if text is None:
            raise LLMEmptyCompletion(f"{settings.suggest_model} returned no text (stop_reason={stop})")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMEmptyCompletion(f"unparseable JSON from {settings.suggest_model} (stop_reason={stop}): {exc}") from exc
    raise LLMEmptyCompletion(f"{settings.suggest_model}: turn still paused after {MAX_CONTINUATIONS} continuations")


async def propose(session: AsyncSession) -> list[Candidate]:
    if not settings.llm_enabled:
        return []
    system, user, index = await _build(session)
    payload = await _call_live(system, user)
    if payload is None:
        return []
    return parse_candidates(payload, index)
