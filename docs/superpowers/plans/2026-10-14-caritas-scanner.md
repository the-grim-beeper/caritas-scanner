# Horizont-Scanner Landkreis Miesbach — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the forked Rhein-Neckar scanner into a German-first horizon scanner for Caritas-Zentrum Miesbach with 15 monitoring questions, an evidence network, three new collection methods and a weekly Lagebericht with a Friday note — live on Railway by 15 Oct 2026, 15:00.

**Architecture:** Same spine as the template (FastAPI + Postgres/pgvector + React/Vite): collect → extract → analyse → **judge** → **network** → trends daily; **Lagebericht** weekly. Task 2 lays the whole schema and vocabulary at once so Tasks 3–7 can run in parallel in separate modules and separate router files; the orchestrator wires `cycle.py`, `main.py` and deploys (Task 8).

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 async, asyncpg, pgvector, Alembic (0001 builds from ORM metadata), feedparser, selectolax<1.0, pypdf, fastembed, anthropic SDK (structured outputs via `output_config.format`), APScheduler; React 19, Vite, TypeScript, Tailwind v4, react-router.

**Spec:** `docs/superpowers/specs/2026-10-14-caritas-scanner-design.md`. Domain data already committed: `data/questions.yaml` (15), `data/entities.yaml`, `data/network.yaml`, `data/calendar.yaml`. `data/sources.yaml` is being rebuilt by a research agent (do not edit it in Tasks 2–7).

## Global Constraints

- Package `mhs` (renamed from `rns`); backend at `backend/`, run tests with `cd backend && .venv/bin/python -m pytest -q`. Local Postgres: `docker compose up -d` → host port **5441**, user/pass/db `mhs`, test db `mhs_test`.
- **German first.** UI default language `de`; every model-written text field exists as `_de` and `_en`.
- **Persons are never entities.** Offices only (e.g. "Erster Bürgermeister Waakirchen"); never store a personal name as an entity.
- **Provenance is enforced in code, not trusted from the model:** judgement quotes must be substrings of the signal text; network edges from signals must carry `signal_id`; reports may only cite ids present in their input.
- **Models (verified 2026-10-14 against models.list):** extraction `claude-haiku-5-5`, judge `claude-sonnet-5-5`, report `claude-opus-5-5`, fallback `claude-sonnet-5-5`. Never write other model ids from memory.
- Tests never spend money: `conftest.py` forces mock mode. Every new LLM stage has a deterministic mock with the same output shape.
- Structured-output JSON schemas: no `minimum`/`maximum`/`minItems`/`maxItems`>1 (the API rejects them); clamp in code.
- No Caritas brand marks (no flame logo, no Caritas red) in the UI.
- Commit after each task with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`; never `git add -A` (parallel workers share the repo) — add the files you touched.

## Review Focus

1. **A Google-News item and the direct source's item for the same story** — expected: one feed item (`also_seen_in`), not two signals. Test in Task 3.
2. **A structural page whose only change is a timestamp/cookie banner/visitor counter** — expected: no change item. Task 3 normalises text (strip digits-only lines, collapse whitespace) before hashing; test pins "only a date changed → no item".
3. **The judge model paraphrases instead of quoting** — expected: the judgement is dropped and counted, never stored with a fake quote. Test in Task 4.
4. **A week with no judgements at all for a question** — expected: the balance decays toward 0 and the UI says "ruhig", not a stale tilt. Test in Task 4.
5. **The report model cites a judgement id from last week or invents one** — expected: provenance error, one retry, then the stage fails without failing the cycle. Test in Task 6.

---

## Task 1 (DONE): Rename and infrastructure

Package `rns` → `mhs`, Postgres 5441, `selectolax<1.0` pinned (1.0 removed the Modest backend), `pypdf` added, password `oberland`. Commit `8cb315f`. Six template tests fail only because they assert Rhein-Neckar entities — Task 2 replaces them.

---

## Task 2: Domain core — vocabulary, schema for every feature, extraction, entities

**Files:**
- Modify: `backend/mhs/vocab.py` (full rewrite), `backend/mhs/db/models.py`, `backend/mhs/extract/schema.py`, `backend/mhs/extract/prompt.py`, `backend/mhs/extract/run.py`, `backend/mhs/llm/mock.py` (`mock_extract` only), `backend/mhs/entities.py`, `backend/mhs/analyse/scoring.py`, `backend/mhs/analyse/stories.py` (field rename only), `backend/mhs/api/serializers.py` (rename), `backend/mhs/sources/catalogue.py` (methods, `query` field), `backend/scripts/load_sources.py` (entities `actor_kind`), `backend/mhs/config.py` (models)
- Create: `backend/scripts/check_models.py`
- Test: rewrite `backend/tests/test_vocab.py`, `test_entities.py`, `test_extract_mock.py`, `test_extract_run.py`, `test_catalogue.py` (real-dictionary test), `test_scoring.py`; fix `test_cycle_mock.py` fixtures to Caritas content (`tests/fixtures/feed_a.xml`, `feed_b.xml` → two German items about Landkreis Miesbach, e.g. Kreisumlage rise and a Pflegestützpunkt service change).

**Interfaces — Produces (everything later tasks rely on):**

`mhs/vocab.py`:
```python
class Label(NamedTuple): en: str; de: str
LAYERS: dict[str, Label]          # gemeinden landkreis wohlfahrt kirche bezirk freistaat bund medien vergleich (spec §2.1, DE/EN labels)
FAMILIES: dict[str, Label]        # struktur personal bedarf geld regeln stimmung
TOPICS: dict[str, Label]          # 33 codes exactly as spec §2.2
TOPIC_FAMILY: dict[str, str]      # topic code -> family code
SIGNAL_TYPES: list[str]           # decision announcement budget funding_call service_change staffing planning disruption research event position data_release
SIGNAL_TYPE_LABELS: dict[str, Label]
AUTHORITY_WEIGHTS = {"high": 1.0, "medium": 0.7, "low": 0.4}
SCOPES = ["gemeinde", "landkreis", "bezirk", "land", "bund", "eu", "extern"]
METHODS = ["rss", "page", "query", "diff", "pdf", "newsletter", "api", "social"]
COLLECTED_METHODS = ("rss", "page", "query", "diff", "pdf")
PRIORITIES = ["core", "thematic"]
ENTITY_KINDS = ["place", "organisation", "forum", "programme", "office"]
OPEN_ENTITY_KINDS = {"organisation", "forum", "programme", "office"}
ACTOR_KINDS = ["authority", "provider", "forum", "church", "funder", "programme", "media", "peer", "other"]
RELATIONS: dict[str, Label]       # funding commissioning membership coordination supervision cooperation consultation transfer
DIRECTIONS = ["for", "against"]
STRENGTH_WEIGHTS = {"weak": 1, "moderate": 2, "strong": 3}
EVENT_KINDS = ["event", "deadline", "window"]
```
(`catalogue.COLLECTED_METHODS` re-exports `vocab.COLLECTED_METHODS`.)

`mhs/db/models.py` — changes (0001 migration builds from metadata, so no new migration files):
```python
class Source:      # + query: Text|None, snapshot_text: Text|None, snapshot_hash: String(64)|None
class FeedItem:    # + title_key: String(512)|None (index=True), outlet: String(200)|None
class Signal:      # economic_materiality -> consequence; + judged_by: String(64)|None, judged_at: datetime|None
class Entity:      # + actor_kind: String(16)|None
class Event:       # signal_id nullable; + slug String(160) unique nullable, origin String(8) default "signal",
                   #   kind String(10) default "event", name_en String(400)|None, place String(160)|None,
                   #   programme String(160)|None, note_de Text|None, note_en Text|None, brief_ref String(32)|None
class Cycle:       # + judged int=0, judgements int=0, edges_new int=0
class Digest:      # + week: date|None, friday_de: Text|None, friday_en: Text|None
class Question(Base):        # __tablename__="questions"; id String(8) PK; sort int; title_de/title_en Text;
                             # driver_de/driver_en Text; sources_de Text; for_label_de/en String(120); for_de/for_en Text;
                             # against_label_de/en String(120); against_de/against_en Text
class Judgement(Base):       # "judgements"; id uuid PK; signal_id FK signals CASCADE index; question_id FK questions index;
                             # direction String(8) ('for'|'against'); strength String(10); weight int; quote Text;
                             # rationale_de/rationale_en Text; model String(64); created_at;
                             # UniqueConstraint(signal_id, question_id, model, name="uq_judgement")
class RelationCandidate(Base): # "relation_candidates"; id uuid; signal_id FK CASCADE index; a_text String(300);
                             # b_text String(300); relation String(16); quote Text; processed bool=False index
class Edge(Base):            # "edges"; id uuid; a_entity_id FK entities CASCADE; b_entity_id FK entities CASCADE;
                             # relation String(16); origin String(8) ('report'|'signal'); signal_id FK signals CASCADE nullable;
                             # evidence_de/evidence_en Text|None; quote Text|None; confidence String(8) default "medium";
                             # brief_ref String(32)|None; created_at;
                             # CheckConstraint("origin <> 'signal' OR signal_id IS NOT NULL", name="ck_edge_signal_provenance")
class ForumProfile(Base):    # "forum_profiles"; entity_id FK entities PK; convener_de String(300); attendance_visible bool;
                             # public_minutes bool; treatment_de/treatment_en Text; brief_ref String(32)|None
class NetworkGap(Base):      # "network_gaps"; id uuid; sort int; kind String(16); title_de/title_en Text;
                             # detail_de/detail_en Text; actor_slugs ARRAY(String)
```

`mhs/extract/schema.py`:
```python
@dataclass(frozen=True)
class RelationDraft: a: str; b: str; relation: str; quote: str
@dataclass(frozen=True)
class ExtractionResult:   # fields: is_signal, headline_en/de, summary_en/de, signal_type, topics, places,
                          # organisations, forums, programmes, offices (tuple[str,...]), regional_relevance,
                          # consequence, forward_lag, events, relations: tuple[RelationDraft, ...]
EXTRACTION_SCHEMA         # matching JSON schema; relation enum = list(vocab.RELATIONS)
def from_payload(data: dict) -> ExtractionResult   # drops relations whose relation not in vocab or a/b empty; caps 8
```

`mhs/entities.py`:
```python
@dataclass(frozen=True)
class EntitySeed: slug: str; kind: str; name: str; aliases: tuple[str, ...] = (); actor_kind: str | None = None
def load_seed(path) -> list[EntitySeed]          # sections places/organisations/forums/programmes/offices
async def resolve(session, names: list[str], *, kind: str) -> list[Entity]   # open kinds = vocab.OPEN_ENTITY_KINDS
```

`mhs/extract/run.py` `_persist` writes `consequence`, resolves the five kinds (role "mentioned"), writes events with `origin="signal"`, `kind="deadline"` if only a deadline else `"event"`, and writes one `RelationCandidate` per `RelationDraft`.

`mhs/config.py`:
```python
extraction_model: str = "claude-haiku-5-5"   # verified 2026-10-14 (models.list + structured call)
judge_model: str = "claude-sonnet-5-5"       # verified 2026-10-14
digest_model: str = "claude-opus-5-5"        # verified 2026-10-14
digest_fallback_model: str = "claude-sonnet-5-5"
max_extractions_per_cycle: int = 600
judge_batch_size: int = 10
judge_min_relevance: float = 0.3
report_weekday: str = "thu"; report_hour_local: int = 18; report_timezone: str = "Europe/Berlin"
query_url_template: str = "https://news.google.com/rss/search?q={q}+when:60d&hl=de&gl=DE&ceid=DE:de"
max_pdfs_per_source: int = 5; max_pdf_bytes: int = 15_000_000; max_pdf_pages: int = 12; max_pdf_chars: int = 20_000
max_diff_chars: int = 6000
```

- [ ] **Step 1: Write failing tests** — `test_vocab.py`:
```python
from mhs import vocab
def test_nine_layers_in_brief_order():
    assert list(vocab.LAYERS) == ["gemeinden","landkreis","wohlfahrt","kirche","bezirk","freistaat","bund","medien","vergleich"]
def test_every_topic_has_a_family_and_33_topics():
    assert len(vocab.TOPICS) == 33
    assert set(vocab.TOPIC_FAMILY) == set(vocab.TOPICS)
    assert set(vocab.TOPIC_FAMILY.values()) == set(vocab.FAMILIES)
def test_collected_methods_include_new_ones():
    assert {"query","diff","pdf"} <= set(vocab.COLLECTED_METHODS)
```
`test_entities.py` (replace the PHV tests):
```python
async def test_resolver_alias_maps_case_insensitively(db_session):
    await upsert_entities(db_session, load_seed(DATA / "entities.yaml"))
    [e] = await resolve(db_session, ["sozialraumlotsen"], kind="programme")
    assert e.slug == "sozialraumlotsen"
async def test_unknown_place_is_not_created(db_session):
    await upsert_entities(db_session, load_seed(DATA / "entities.yaml"))
    assert await resolve(db_session, ["Bad Tölz"], kind="place") == []
async def test_unknown_forum_is_created_unseeded(db_session):
    [e] = await resolve(db_session, ["Runder Tisch Pflege Holzkirchen"], kind="forum")
    assert e.kind == "forum" and e.seeded is False
async def test_seed_carries_actor_kind(db_session):
    seeds = {s.slug: s for s in load_seed(DATA / "entities.yaml")}
    assert seeds["caritas-zentrum-miesbach"].actor_kind == "provider"
    assert seeds["landrat-miesbach"].kind == "office"
```
`test_extract_mock.py`:
```python
def test_mock_tags_kreisumlage_as_umlagen_and_is_signal():
    r = mock_extract("Kreistag beschließt höhere Kreisumlage", "Die Gemeinden im Landkreis Miesbach zahlen 2027 mehr.", "landkreis")
    assert r.is_signal and "umlagen" in r.topics and "Landkreis Miesbach" in r.places
def test_mock_ignores_sport():
    r = mock_extract("TSV Miesbach gewinnt Derby", "Fußball am Sonntag.", "medien")
    assert not r.is_signal
def test_mock_only_vocabulary_topics():
    r = mock_extract("Pflegestützpunkt verkürzt Öffnungszeiten wegen Personalmangel", "", "landkreis")
    assert set(r.topics) <= set(vocab.TOPICS) and {"pflege","fachkraefte"} <= set(r.topics)
```
`test_extract_run.py`: persisting a live-shaped payload with `relations=[{"a":"Jugendamt","b":"Diakonie Rosenheim","relation":"commissioning","quote":"im Auftrag des Jugendamts"}]` writes one `RelationCandidate`, a forum entity link for "Jugendhilfeausschuss", and `signal.consequence` equals the payload value; a payload relation with `relation:"likes"` writes none.

- [ ] **Step 2: Run** `cd backend && .venv/bin/python -m pytest -q tests/test_vocab.py tests/test_entities.py tests/test_extract_mock.py tests/test_extract_run.py` → FAIL.
- [ ] **Step 3: Implement** vocab, models, schema, prompt, run, entities, mock, scoring/serializer renames, catalogue (accept `query` field; `query` method needs `query`, `diff`/`pdf` need `url`; `CatalogueEntry.query: str | None = None`; `SourceRow.query`; `merge_for_load` passes `query`), `load_sources.upsert_entities` sets `actor_kind`, `_FIELDS` += `"query"`.
  - Prompt (`SYSTEM_TEXT`, German-aware, written in English for the model): the analyst of a horizon scanner for **social provision in Landkreis Miesbach** (17 municipalities, Tegernseer Tal, Oberland) and the upstream levels that bind it (Bezirk Oberbayern, Freistaat Bayern, Bund); readers are Caritas-Zentrum Miesbach and a foresight team working on whether an inter-municipal coordination structure ("Interkommunale Sozialraumlotsen") can be anchored to 2035/2040. Signals: decisions, budgets, levies, mandates, staffing and vacancies, openings/closures/Aufnahmestopp, coordination bodies forming or dissolving, rules and SGB changes, funding calls and grant ends, data releases, controversy about social provision. NOT signals: sport, culture/leisure listings, tourism, police blotter, obituaries, weather, church service times, generic national news with no effect on the county. Explain `consequence` (spec §2.5) and `forward_lag` (template rubric). Entities: places, organisations, forums (committees, networks, councils), programmes (funding programmes, projects), offices (roles, NEVER personal names). Relations: only relations the text states between two named actors, with the verbatim phrase as `quote`.
  - `mock_extract(title, summary, layer)`: keyword rules over a `_TOPIC_KEYWORDS: dict[str, tuple[str,...]]` drawn from the brief's lexicon (pp. 14–16), e.g. `"umlagen": ("kreisumlage","bezirksumlage","hebesatz")`, `"haushalt": ("haushalt","haushaltsplan","nachtragshaushalt","haushaltssperre","defizit")`, `"foerderung": ("förder","zuschuss","zuwendung","sela","pflegesonah","leader")`, `"pflege": ("pflege","senioren","tagespflege","kurzzeitpflege","pflegestützpunkt")`, `"fachkraefte": ("fachkräfte","personalmangel","personalengpass","pflegefachkraft","sozialpädagog")`, `"stellen": ("stellenanzeige","stellenausschreibung","vakant","unbesetzt","nachbesetzung")`, `"jugend-familie": ("jugendhilfe","jugendamt","kita","kinderbetreuung","hilfen zur erziehung")`, `"mobilitaet": ("öpnv","buslinie","rufbus","mvv","bergbus","fahrdienst","barrierefrei")`, `"koordination": ("netzwerk","vernetzung","koordination","runder tisch","arbeitskreis","sozialbeirat")`, `"verstetigung": ("verstetig","regelfinanzierung","anschlussförderung","förderende")`, `"sgb": ("sgb","bürgergeld","grundsicherung")`, `"kontroverse": ("bürgerinitiative","petition","protest","umstritten","kritik")`, `"kirchenstruktur": ("dekanat","pfarrverband","pfarrei","kirchenimmobilie")`, `"ehrenamt": ("ehrenamt","nachbarschaftshilfe","freiwillig")` — every topic gets ≥2 keywords. Not-signal guard: `("fußball","tsv ","derby","konzert","festival","polizei","unfall","wetter","gottesdienst")`. `is_signal` when ≥1 topic and no guard word. Places/entities by exact name/alias match against the dictionary terms; `consequence=min(1,0.3+0.15*topic_hits)`; `regional_relevance=1.0` if a place matched else 0.4; `forward_lag=0.7` if any of `("beschließt","plant","soll","künftig","ab 2027","antrag","frist")` else 0.4.
  - `scripts/check_models.py`: for each configured model, one `complete_json` call with a tiny schema `{"type":"object","properties":{"ok":{"type":"boolean"}},"required":["ok"],"additionalProperties":false}`; prints `model OK/FAIL` and exits 1 on any failure. Header comment: "Re-run before changing model defaults (CLAUDE.md)."
- [ ] **Step 4: Run** the full suite `.venv/bin/python -m pytest -q` → all PASS (fix `test_cycle_mock.py` fixtures to German Caritas items; `test_api.py` filter test uses `layer=landkreis`).
- [ ] **Step 5: Commit** the touched files: `git commit -m "Domain core: nine layers, 33 topics, five entity kinds, consequence factor, full schema for questions/network/calendar/report"`.

---

## Task 3: Collection methods — query, diff, pdf (+ verifier support)

**Files:**
- Create: `backend/mhs/collect/query.py`, `backend/mhs/collect/diff.py`, `backend/mhs/collect/pdf.py`
- Modify: `backend/mhs/collect/run.py` (dispatch + title_key dedup), `backend/scripts/check_sources.py` (query/diff/pdf liveness)
- Test: `backend/tests/test_query.py`, `test_diff.py`, `test_pdf.py`, fixtures `tests/fixtures/gnews.xml`, `diff_v1.html`, `diff_v2.html`, `pdf_list.html`, `tiny.pdf` (generate with pypdf in the test via a helper writing a one-page PDF with text — or commit a 1-page PDF made with `reportlab`-free method: `pypdf.PdfWriter().add_blank_page` cannot hold text; instead commit a small fixture PDF generated once with macOS `cupsfilter` or Python `fpdf2` dev-only).

**Interfaces:**
- Consumes: `Source.query/snapshot_text/snapshot_hash/url/last_page_hash`, `FeedItem.title_key/outlet`, `settings.query_url_template`, `settings.max_pdfs_per_source/max_pdf_bytes/max_pdf_pages/max_pdf_chars/max_diff_chars`, `RawItem` from `mhs.collect.canonical`.
- Produces:
```python
# collect/query.py
def build_query_url(q: str) -> str                       # urllib.parse.quote_plus on q into settings.query_url_template
def split_outlet(title: str) -> tuple[str, str | None]   # "Kreistag erhöht Umlage - Merkur" -> ("Kreistag erhöht Umlage", "Merkur")
def title_key(title: str) -> str                         # casefold, strip outlet, collapse whitespace, strip punctuation at ends
async def fetch_query(http, source) -> list[RawItem]     # uses fetch_rss on build_query_url(source.query); title without outlet; RawItem.outlet set
# collect/diff.py
def main_text(html: bytes) -> str                        # selectolax: drop script/style/nav/header/footer/form; text of <main> or <article> or body; lines stripped; drop empty lines and lines that are only digits/dates/punctuation
def snapshot_hash(text: str) -> str                      # sha256 of text
def change_summary(old: str, new: str, limit: int) -> str | None   # difflib.ndiff on lines; "+ line"/"- line" only; None if no +/- lines
async def fetch_diff(http, source) -> tuple[list[RawItem], str, str]   # (items, new_text, new_hash); items == [] on first sight or unchanged
# collect/pdf.py
def pdf_links(html: bytes, base_url: str) -> list[tuple[str, str]]     # (absolute url, link text) for hrefs ending .pdf (case-insens., query allowed) on the same registrable domain, document order, dedup
def pdf_text(data: bytes, max_pages: int, max_chars: int) -> tuple[str, datetime | None]   # pypdf; metadata /CreationDate → aware datetime
async def fetch_pdf(http, source, seen_urls: set[str]) -> list[RawItem]  # ≤ settings.max_pdfs_per_source new PDFs; skips seen canonical urls; skips > max_pdf_bytes
```
`RawItem` gains optional `outlet: str | None = None` (in `canonical.py`). In `collect/run.py`: `_fetch_one` dispatches `query/diff/pdf`; for `diff` the result carries new snapshot text/hash and `_store` is skipped when no items; `_store` sets `title_key` for every item and, **for query sources only**, credits an existing FeedItem with the same `title_key` created within 60 days (append `source.id` to `also_seen_in`) instead of inserting.

- [ ] **Step 1: Failing tests** (`test_query.py`):
```python
def test_split_outlet():
    assert split_outlet("Kreistag erhöht Kreisumlage - Merkur") == ("Kreistag erhöht Kreisumlage", "Merkur")
    assert split_outlet("Ohne Quelle") == ("Ohne Quelle", None)
def test_title_key_ignores_case_outlet_and_spacing():
    assert title_key("Kreistag  erhöht Kreisumlage - Merkur") == title_key("kreistag erhöht kreisumlage")
async def test_query_item_matching_direct_item_is_credited_not_duplicated(db_session):
    direct = Source(slug="lk-presse", name="LK Presse", layer="landkreis", authority="high", scope="landkreis", method="rss", url="https://lk.test/rss", collect=True)
    q = Source(slug="q-lk", name="Q LK", layer="medien", authority="medium", scope="landkreis", method="query", query='"Landkreis Miesbach"', collect=True)
    db_session.add_all([direct, q]); await db_session.flush()
    await _store(db_session, direct, [RawItem(external_id="1", title="Kreistag erhöht Kreisumlage", url="https://lk.test/a", summary="", published_at=None)])
    n = await _store(db_session, q, [RawItem(external_id="g1", title="Kreistag erhöht Kreisumlage", url="https://news.google.com/rss/articles/X", summary="", published_at=None, outlet="Merkur")])
    rows = (await db_session.execute(select(FeedItem))).scalars().all()
    assert n == 0 and len(rows) == 1 and q.id in rows[0].also_seen_in
async def test_two_different_query_headlines_both_store(db_session): ...  # two distinct titles → 2 rows
```
(`test_diff.py`):
```python
async def test_first_sight_is_baseline_only(): items, text, h = await fetch_diff(http_returning(V1), src_without_snapshot); assert items == [] and text and h
async def test_unchanged_page_emits_nothing(): src.snapshot_text, src.snapshot_hash = text, h; items, *_ = await fetch_diff(http_returning(V1), src); assert items == []
async def test_only_a_date_changed_emits_nothing(): # V1 vs V1 with "Stand: 12.10.2026" → "Stand: 13.10.2026" on a line of its own
def test_change_summary_has_added_and_removed_lines_only():
    s = change_summary("A\nB\nC", "A\nB2\nC", 6000)
    assert "+ B2" in s and "- B" in s and "A" not in s.replace("B","")
```
Note: lines like `Stand: 13.10.2026` must normalise — `main_text` replaces date-like tokens `\d{1,2}\.\d{1,2}\.\d{2,4}` and times with `·` before hashing *and* diffing.
(`test_pdf.py`): `pdf_links` keeps `/dokumente/Amtsblatt_42.pdf` and `https://www.landkreis-miesbach.de/x.PDF?v=2`, drops `https://other.example/x.pdf` and `/seite.html`; `fetch_pdf` with `seen_urls` containing the first link fetches only the remaining ones and at most `max_pdfs_per_source`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** full suite → PASS.
- [ ] **Step 5:** `check_sources.py`: `query` live if `fetch_rss(build_query_url(q))` ≥1 item (resolved_url = built URL, method query); `diff` live if `main_text` ≥ 200 chars (method diff); `pdf` live if `pdf_links` ≥1 (method pdf). Keep rss/page logic. Write `data/sources-live.json` and `data/sources-check-report.json` as before.
- [ ] **Step 6: Commit.**

---

## Task 4: The fifteen questions — judge, provenance, balance, API

**Files:**
- Create: `backend/mhs/questions/__init__.py`, `questions/load.py`, `questions/schema.py`, `questions/prompt.py`, `questions/validate.py`, `questions/judge.py`, `questions/balance.py`, `questions/mock.py`, `backend/mhs/api/questions.py` (APIRouter)
- Modify: `backend/scripts/load_sources.py` (call `upsert_questions`)
- Test: `backend/tests/test_questions_validate.py`, `test_questions_balance.py`, `test_questions_judge.py`, `test_questions_api.py`

**Interfaces:**
- Consumes: `Question`, `Judgement`, `Signal.judged_by/judged_at`, `Signal.regional_relevance`, `Source.layer`, `vocab.DIRECTIONS/STRENGTH_WEIGHTS`, `settings.judge_model/judge_batch_size/judge_min_relevance`, `mhs.llm.client.complete_json`, `LLMAuthError/LLMRequestError`.
- Produces:
```python
# questions/load.py
def load_questions(path) -> list[dict]                       # yaml list; validates 15 unique ids q01..q15
async def upsert_questions(session, items: list[dict]) -> int
# questions/validate.py
def normalise(s: str) -> str                                 # casefold, collapse whitespace, normalise quotes „“”"' → ", – — → -
@dataclass class JudgementDraft: signal_id: str; question_id: str; direction: str; strength: str; quote: str; rationale_de: str; rationale_en: str
def validate_judgements(raw: dict, *, signal_texts: dict[str, str], question_ids: set[str]) -> tuple[list[JudgementDraft], list[str]]
    # keeps a judgement only if signal_id in signal_texts, question_id in question_ids, direction in DIRECTIONS,
    # strength in STRENGTH_WEIGHTS, len(normalise(quote)) >= 12 and normalise(quote) in normalise(signal_texts[signal_id]);
    # returns (kept, problems) — problems are human-readable strings, one per dropped judgement
# questions/judge.py
@dataclass class JudgeStats: judged: int = 0; judgements: int = 0; dropped: int = 0; aborted: str | None = None
async def judge_pending(session, *, limit: int | None = None) -> JudgeStats
    # founders with judged_by IS NULL (or != current model) and (regional_relevance >= judge_min_relevance or layer in {"vergleich","bund","freistaat"});
    # signal text = headline_de + summary_de + headline_en + summary_en + feed item title + feed item summary;
    # batches of judge_batch_size; live or mock; persists Judgement rows (weight = STRENGTH_WEIGHTS[strength], model = judge model or "mock");
    # sets judged_by/judged_at on every signal in a batch that returned a valid payload, even with zero judgements
# questions/balance.py
@dataclass class WeekPoint: week: date; net: float; balance: float; n: int
def weekly_net(weights_signs: list[int]) -> float            # sum, clipped to ±3, times n/(n+2); [] -> 0.0
def balance_series(judgements: list[tuple[date, str, int]], *, weeks: int, today: date) -> list[WeekPoint]
    # judgements = (published date of signal, direction, weight); ISO-week Mondays; b_w = 0.85*b_{w-1} + net_w
def movement(series: list[WeekPoint]) -> str                 # "for" | "against" | "mixed" | "quiet": last 4 weeks; quiet if no n; mixed if both signs present and |balance| < 1
```
API (`api/questions.py`, router mounted under `/api` with auth by the orchestrator):
```
GET /api/questions -> [{id, sort, title_de, title_en, driver_de, driver_en, for_label_de, for_label_en, against_label_de, against_label_en,
                        balance: float, movement: "for"|"against"|"mixed"|"quiet", series: [{week, net, balance, n}] (12 weeks),
                        counts: {for: int, against: int}, latest: [JudgementOut] (≤3)}]
GET /api/questions/{id} -> same + for_de/for_en/against_de/against_en/sources_de + evidence: [JudgementOut] (all, newest first, ≤100)
JudgementOut = {id, question_id, direction, strength, weight, quote, rationale_de, rationale_en, model, created_at,
                signal: {id, headline_de, headline_en, layer, source_name, url, published_at}}
```
- [ ] **Step 1: Failing tests:**
```python
def test_quote_must_be_in_signal_text():
    raw = {"judgements": [{"signal_id": "s1", "question_id": "q01", "direction": "for", "strength": "strong",
            "quote": "Haushaltssperre für freiwillige Leistungen", "rationale_de": "x", "rationale_en": "x"}]}
    kept, problems = validate_judgements(raw, signal_texts={"s1": "Die Gemeinde verhängt eine Haushaltssperre für freiwillige Leistungen."}, question_ids={"q01"})
    assert len(kept) == 1 and not problems
    raw["judgements"][0]["quote"] = "Gemeinde kürzt Sozialausgaben"   # paraphrase
    kept, problems = validate_judgements(raw, signal_texts={"s1": "Die Gemeinde verhängt eine Haushaltssperre für freiwillige Leistungen."}, question_ids={"q01"})
    assert kept == [] and problems
def test_unknown_question_and_foreign_signal_rejected(): ...   # q99 -> dropped; signal_id "s9" not in batch -> dropped
def test_typographic_quotes_normalise(): # model returns „…“ where source has "…" → kept
def test_weekly_net_is_capped():
    assert weekly_net([1]*10) == pytest.approx(3 * 10/12)
    assert weekly_net([3]) == pytest.approx(3 * 1/3)
    assert weekly_net([]) == 0.0
def test_balance_decays_without_evidence():
    s = balance_series([(date(2026,8,24), "for", 3)], weeks=8, today=date(2026,10,14))
    peak = max(p.balance for p in s)
    assert peak > 0 and s[-1].balance < peak and s[-1].balance > 0
    assert movement(s) == "quiet"
def test_against_is_negative():
    s = balance_series([(date(2026,10,12), "against", 2)], weeks=4, today=date(2026,10,14))
    assert s[-1].balance < 0 and movement(s) == "against"
```
`test_questions_judge.py` (mock mode): a founder with a Kreisumlage headline and `regional_relevance=1.0` gets ≥1 judgement for q02 with a quote that is a substring of its headline/summary; running `judge_pending` twice writes no duplicates; a founder with `regional_relevance=0.1` in layer `gemeinden` is not judged. Mock judge rules (`questions/mock.py`): per question 2–4 trigger phrases (e.g. q02 `("kreisumlage","bezirksumlage","hebesatz")`→for; q03 `("sozialraumlots","lotsen")`→for if `("verstetig","dauerhaft","stellenplan")` present else against if `("befristet","auslauf","förderende")`; q06 `("personalmangel","fachkräftemangel","unbesetzt","vakant")`→for; q07 `("warteliste","aufnahmestopp","engpass")`→for; q08 `("buslinie","rufbus","fahrdienst","takt")`→for if `("eingestellt","gestrichen","ausfall")` else against; q12 `("förderende","auslauf","befristet")`→for, `("regelfinanzierung","verstetig")`→against; q05 `("bürgermeister","landrat","stadtrat","gemeinderat")`+`("streit","abgelehnt","kontrovers")`→for); quote = the matching sentence of the signal text (split on `. `), strength moderate.
- [ ] **Step 2–4:** run → FAIL → implement → PASS (full suite).
- [ ] **Step 5: Commit.**

Judge prompt (`questions/prompt.py`), in English, cached system block: lists the 15 questions with for/against evidence descriptions (from DB rows); rules: "Judge only what the signal text states. Return a judgement only where the signal is evidence for or against a question as the brief defines it. Most signals bear on zero or one question. `quote` must be copied verbatim from the signal text (German), at least a clause, no ellipses. Strength: weak = indirect/one actor's claim; moderate = concrete local development; strong = a decision, budget line, closure or formal agreement." Schema: `{"judgements": [{signal_id, question_id (enum q01..q15), direction (enum), strength (enum), quote, rationale_de, rationale_en}]}`.

---

## Task 5: Network — seed, resolve candidates into edges, API

**Files:**
- Create: `backend/mhs/network/__init__.py`, `network/load.py`, `network/resolve.py`, `backend/mhs/api/network.py`
- Modify: `backend/scripts/load_sources.py` (call `load_network` after entities)
- Test: `backend/tests/test_network.py`

**Interfaces:**
- Consumes: `Edge`, `ForumProfile`, `NetworkGap`, `RelationCandidate`, `Entity.actor_kind`, `mhs.entities.resolve`, `vocab.RELATIONS`.
- Produces:
```python
# network/load.py
async def load_network(session, path) -> dict[str, int]
    # upsert report edges by (a_slug, b_slug, relation, origin="report"); forum profiles by entity slug; replace gaps (sort = file order);
    # raises ValueError naming the slug if an endpoint slug is not in entities
# network/resolve.py
@dataclass class NetworkStats: candidates: int = 0; edges_new: int = 0; dropped: int = 0
async def resolve_candidates(session) -> NetworkStats
    # for each unprocessed RelationCandidate: resolve a_text and b_text across kinds organisation/forum/programme/office
    # (try each kind; take the first hit; open kinds may be created — use kind "organisation" when nothing matches);
    # drop (count) if either end unresolved or a == b; else insert Edge(origin="signal", signal_id=…, quote=…, confidence="medium")
    # unless an identical (a, b, relation, signal_id) edge exists; mark processed
```
API (`api/network.py`):
```
GET /api/network -> {nodes: [{id, slug, name, kind, actor_kind, seeded, degree, signals_30d}],
                     edges: [{id, a: slug, b: slug, relation, origin, confidence, evidence_de, evidence_en, quote, brief_ref,
                              signal: {id, headline_de, headline_en, url, published_at} | null}],
                     forums: [{slug, name, convener_de, attendance_visible, public_minutes, treatment_de, treatment_en, brief_ref}],
                     gaps: [{id, kind, title_de, title_en, detail_de, detail_en, actor_slugs}]}
    # nodes = every entity that is an endpoint of an edge, every forum-profile entity, and every entity named in a gap
```
- [ ] **Step 1: Failing tests:**
```python
async def test_report_edges_load_with_report_origin(db_session):
    await upsert_entities(db_session, load_seed(DATA/"entities.yaml"))
    stats = await load_network(db_session, DATA/"network.yaml")
    edges = (await db_session.execute(select(Edge))).scalars().all()
    assert stats["edges"] == len(edges) == 18 and all(e.origin == "report" and e.signal_id is None for e in edges)
    assert (await load_network(db_session, DATA/"network.yaml"))["edges"] == 18   # idempotent: still 18 rows
async def test_signal_edge_without_signal_id_is_refused(db_session):
    a, b = Entity(slug="x", kind="organisation", name="X"), Entity(slug="y", kind="organisation", name="Y")
    db_session.add_all([a, b]); await db_session.flush()
    db_session.add(Edge(a_entity_id=a.id, b_entity_id=b.id, relation="funding", origin="signal", signal_id=None))
    with pytest.raises(IntegrityError): await db_session.flush()
async def test_candidate_resolves_to_edge_with_provenance(db_session): # seeded Jugendamt + Diakonie; candidate on a stored signal → 1 edge origin signal with that signal_id and quote
async def test_unresolvable_place_endpoint_drops(db_session):          # a_text "Bad Tölz" (not an org; closed place) … → dropped
```
Note for the last test: `resolve` on kind "organisation" CREATES unknown orgs. To keep "drop" meaningful, `resolve_candidates` first checks whether the text matches a seeded *place* (closed set) — a place is never an actor → drop.
- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5: Commit.**

---

## Task 6: Calendar seed + weekly Lagebericht with Freitagsnotiz

**Files:**
- Create: `backend/mhs/calendar.py`, `backend/mhs/report/__init__.py`, `report/schema.py`, `report/validate.py`, `report/run.py`, `report/mock.py`, `backend/mhs/api/reports.py`
- Modify: `backend/scripts/load_sources.py` (call `load_calendar`), `backend/mhs/digest/*` stays for reference but `write_digest` is no longer called by the cycle (the orchestrator switches `cycle.py` to `write_report`)
- Test: `backend/tests/test_calendar.py`, `test_report_validate.py`, `test_report_run.py`

**Interfaces:**
- Consumes: `Event` (new columns), `Digest` (+week, friday_de/en), `Judgement`, `Question`, `Edge`, `mhs.questions.balance.balance_series/movement`, `trends.movers`, `settings.digest_model/digest_fallback_model`.
- Produces:
```python
# calendar.py
async def load_calendar(session, path) -> int     # upsert Event by slug, origin="report", signal_id None; name=name_de; name_en; kind; start_date/end_date/deadline; place; programme; note_de/en; brief_ref
# report/validate.py
class ReportProvenanceError(ValueError): problems: list[str]
def validate_report(raw: dict, *, signal_ids: set[str], event_ids: set[str], judgement_ids: set[str], question_ids: set[str]) -> dict
    # all cited ids exist; friday_signal_ids non-empty; friday_de and friday_en each have 2–4 paragraphs (split on blank lines);
    # questions[].movement in {"for","against","mixed","quiet"}; raises ReportProvenanceError(problems) else returns cleaned dict
# report/run.py
async def write_report(session, *, today: date | None = None) -> Digest | None
    # inputs: founders created in the last 7 days ranked by score (cap 80) with layer/source/type/topics/headlines/summaries;
    # per question: movement + up to 6 judgement ids with direction/strength/quote/headline from the last 7 days;
    # events/deadlines/windows overlapping the next 30 days (seeded and extracted); edges created in the last 7 days; trends.movers top 10;
    # source health: {collected, ok_last_cycle, failing} ; live (digest_model, fallback) or mock; validate; one retry with problems; store
    # Digest(week=ISO Monday of today, lead_de/en, payload, friday_de/en, model); returns None if no founders in 7 days
```
Report JSON schema (`report/schema.py`):
```
{lead_de, lead_en, questions: [{question_id, movement, note_de, note_en, judgement_ids: [str]}],
 sections: [{layer (enum LAYERS), items: [{signal_id, note_de, note_en}]}],
 chains: [{title_de, title_en, signal_ids: [str]}], watch: [{event_id, why_de, why_en}],
 friday_de, friday_en, friday_signal_ids: [str]}
```
Report system prompt (English, for the model): you write the weekly Lagebericht of a horizon scanner for social provision in Landkreis Miesbach, read by Caritas-Zentrum Miesbach (Florian Rausch) and a TUM foresight student team; German is the primary language, write German first and an English version. lead: 3–4 sentences, what moved this week for the question of whether an inter-municipal coordination structure can be anchored to 2035/2040. questions: only questions with evidence this week, movement + one or two sentences, cite judgement ids. sections by layer, chains across layers, watch list. **friday_de**: the team's weekly written update to Florian — two or three short paragraphs, plain prose, no headings, no bullet lists, no greeting or signature, sober, Strunk-&-White brevity; what the scanner saw this week, what it may mean for the Sozialraumlotsen question, one open question for Florian if the evidence raises one. Cite only ids in the input; never invent numbers, names or dates.
- [ ] **Step 1: Failing tests:**
```python
async def test_seeded_window_loads_without_signal(db_session):
    n = await load_calendar(db_session, DATA/"calendar.yaml")
    ev = (await db_session.execute(select(Event).where(Event.slug=="haushalte-2027-landkreis-gemeinden"))).scalar_one()
    assert n == 10 and ev.kind == "window" and ev.signal_id is None and ev.origin == "report" and ev.end_date == date(2027,3,31)
    assert await load_calendar(db_session, DATA/"calendar.yaml") == 10 and len((await db_session.execute(select(Event))).scalars().all()) == 10
def test_unknown_judgement_id_rejected(): ...       # judgement_ids ["j-old"] not in set → ReportProvenanceError
def test_empty_friday_signal_ids_rejected(): ...
def test_one_paragraph_friday_rejected(): ...       # "Nur ein Absatz." → rejected; "A.\n\nB." → ok
async def test_mock_report_written_with_friday(db_session):  # one founder + one judgement this week → Digest with week Monday, friday_de has ≥2 paragraphs, friday_signal_ids ⊆ founders
```
- [ ] **Step 2–4:** FAIL → implement → PASS. Mock report (`report/mock.py`): deterministic: lead from top-3 headlines; questions from judgements; friday_de = two paragraphs ("Diese Woche …" listing top headlines; "Für die Frage der Sozialraumlotsen …" naming the question with most judgements).
- [ ] API (`api/reports.py`): `GET /api/reports` (list: id, week, created_at, model, lead_de, lead_en), `GET /api/reports/latest`, `GET /api/reports/{id}` → full payload + `friday_de/en` + resolved citations: `signals: {id: {headline_de, headline_en, layer, source_name, url, published_at}}`, `events: {id: {...}}`, `judgements: {id: JudgementOut}`; `POST /api/report/run` → runs `write_report`, returns `{ok, id}`.
- [ ] **Step 5: Commit.**

---

## Task 7: Frontend — German first, seven views

**Files:** `frontend/src/**` (types, api, i18n, App routes, views: `Lage.tsx` (replaces Radar), `Fragen.tsx`, `Netz.tsx`, `Lagebericht.tsx` (replaces Digest), `Signale.tsx`, `Kalender.tsx`, `Quellen.tsx`; remove `Watchlist.tsx` from routes), `frontend/index.html` (title), `frontend/package.json` (name), `frontend/src/index.css` (palette), `frontend/public/favicon.svg`.

**Interfaces — Consumes** the API shapes in Tasks 4–6 plus template routes (`/api/overview`, `/api/signals`, `/api/signals/{id}`, `/api/entities/{slug}`, `/api/events`, `/api/trends`, `/api/sources`, `/api/meta`, `/api/cycles`, `/api/login`). `Factors.consequence` replaces `economic_materiality`. Layers are the nine codes; `LAYER_COLOR` gets nine muted hues. Events now have `kind`, `origin`, `name_en`, `note_de/en`, `end_date`, nullable `signal_id`.

Requirements:
- Use the **frontend-design** skill for the look. Typographic broadsheet; German default (`lang` initial state `"de"`, persisted in localStorage); palette distinct from Rhein-Neckar teal — suggest Oberland: warm paper, ink, one fir/moss-green accent and a rust secondary for "for/against" tilt; no Caritas red, no flame. IBM Plex Sans + a serif display (e.g. Fraunces or Source Serif) as in the template.
- **Lage**: masthead with week, nine layer bands with the week's top stories (score glyph shows the five factors), a "Fragen in Bewegung" strip (questions whose movement ≠ quiet, tilt arrows with the side's label), next deadlines rail (seeded + extracted, windows shown as spans).
- **Fragen**: ledger of the 15 (number, title, driver, tilt bar between `against_label` and `for_label`, 12-week sparkline of balance, counts); detail page with both evidence columns (for / against) — each card: quote in quotation marks, rationale, signal headline linking out, source and date.
- **Netz**: SVG force layout (d3-force from npm is fine) of nodes coloured by `actor_kind`; report edges solid, signal edges dashed-dot with a dot marker; relation label on hover; side panel for a selected node (name, kind, edges with evidence, entity timeline from `/api/entities/{slug}`); below the graph: forums table (convener, attendance visible?, public minutes?, treatment) and **Lücken** list (gaps, the missing Caritas↔Lotsen↔Landkreis edge first, styled as dashed red-free "missing" edge in the graph between the named actors).
- **Lagebericht**: latest report as broadsheet (lead, questions block, sections with notes beside cited signal cards, chains, watch) + a framed **Freitagsnotiz an Florian** with "Kopieren" button (copies `friday_de` or `friday_en` per language) and the cited signals under it; archive list; button "Lagebericht jetzt erstellen" (POST /api/report/run).
- **Kalender**: by week; deadlines distinct from events; windows as horizontal bars; seeded items marked "aus dem Bericht".
- **Quellen**: template coverage table + a 17-municipality grid (each tile: municipality, number of collected sources, items in 30 days, methods) from `/api/sources` (`places` field per source).
- `npm run build` clean (`tsc -b` + vite), `npx oxlint` clean.
- [ ] Steps: implement views against the typed API; build; commit.

---

## Task 8 (orchestrator): wiring, live run, deploy

- [ ] `cycle.py`: collect → extract → analyse → `judge_pending` → `resolve_candidates` → trends; record `cycle.judged/judgements/edges_new`; the daily cycle no longer writes a digest.
- [ ] `main.py`: include routers `api/questions.py`, `api/network.py`, `api/reports.py` with the auth dependency used by `routes.router`; scheduler: daily cycle 05:00 UTC + `write_report` cron `day_of_week="thu", hour=18, timezone="Europe/Berlin"`.
- [ ] `/api/overview` adds `questions_moving: [{id, title_de, title_en, movement, balance, for_label_*, against_label_*}]` and `report_lead` from the latest Digest.
- [ ] `/api/sources` adds per-source `places`.
- [ ] Full test suite green; `scripts/check_models.py` OK; `scripts/check_sources.py` on the researched catalogue; `alembic upgrade head` on a fresh DB; `load_sources.py`; one live cycle with backfill (local, `MAX_EXTRACTIONS_PER_CYCLE` 600); `POST /api/report/run`; inspect output quality (questions, quotes, Friday note) and fix prompts if needed.
- [ ] Railway: new project `caritas-scanner`, `postgres` from `pgvector/pgvector:pg16` + volume, `web` from repo Dockerfile; variables `DATABASE_URL`, `APP_PASSWORD=oberland`, `SECRET_KEY`, `SCHEDULER_ENABLED=true`; Nicklas sets `ANTHROPIC_API_KEY` via `! railway variable set`; deploy; run a cycle + report in production; browser smoke test of all seven views.
- [ ] README rewritten for this project; memory updated; push.
