# Rhein-Neckar Horizon Scanner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A standalone, bilingual (EN/DE) horizon scanner for the Metropolregion Rhein-Neckar that collects the brief's six-layer source catalogue, extracts and scores signals with Claude, groups corroborating coverage into stories, extracts events/deadlines, and writes a provenance-checked daily digest.

**Architecture:** FastAPI backend with Postgres/pgvector; a `cycle` pipeline of independently callable stages (collect → extract → embed/story/score → trends → digest); a mock LLM path so the whole pipeline runs offline; React/Vite/Tailwind v4 frontend served as static files by the backend in production. Sources are verified live before they are ever loaded.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 async + asyncpg, Alembic, pgvector, fastembed (`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`), feedparser, httpx, selectolax (HTML), anthropic SDK (structured outputs), APScheduler, itsdangerous; React 19, Vite, TypeScript, Tailwind v4, react-router 7.

**Spec:** `docs/superpowers/specs/2026-08-25-rhein-neckar-scanner-design.md`

## Global Constraints

- Python `>=3.12,<3.13`; backend package name `rns`, importable as `rns.*`.
- Every datetime column timezone-aware (`DateTime(timezone=True)` via `type_annotation_map`).
- Postgres host port **5438** in docker-compose.
- Embedding model: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, dim **384**.
- Extraction model env `EXTRACTION_MODEL` default `claude-haiku-4-5`; digest model env `DIGEST_MODEL` default `claude-opus-5`, fallback `claude-sonnet-5`.
- Topic vocabulary is exactly the 30 codes in spec §2; layer codes exactly the six in spec §2; signal types exactly the eleven in spec §2.
- Only `data/sources-live.json` entries become active collected sources.
- Score formula verbatim: `authority × regional_relevance × novelty × economic_materiality × forward_lag`.
- Digest payload must pass the provenance validator before being stored.
- Every test is written against a named wrong implementation (see spec §8).
- Commit after each task; commit messages end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

## File structure

```
backend/
  pyproject.toml
  alembic.ini, alembic/env.py, alembic/versions/0001_initial.py
  rns/
    config.py            settings (pydantic-settings)
    main.py              FastAPI app, static mount, scheduler start
    db/engine.py         async engine/session factory
    db/models.py         ORM (spec §5)
    vocab.py             LAYERS, TOPICS, SIGNAL_TYPES with EN/DE labels; AUTHORITY_WEIGHTS
    entities.py          seed dictionary + resolver
    sources/catalogue.py load sources.yaml + sources-live.json; validation
    collect/canonical.py canonical_url(), content_hash()
    collect/rss.py       fetch_rss(source) -> list[RawItem]
    collect/page.py      fetch_page(source) -> list[RawItem]
    collect/run.py       collect_all(session, http) -> CollectStats
    llm/client.py        complete_json() with empty-completion + fallback handling
    llm/mock.py          mock_extract(), mock_digest()
    extract/schema.py    EXTRACTION_SCHEMA, ExtractionResult dataclass
    extract/prompt.py    system prompt (vocab block, forward_lag rubric)
    extract/run.py       extract_pending(session) -> ExtractStats
    analyse/embedding.py embed_texts()
    analyse/stories.py   assign_story(session, signal) -> StoryDecision
    analyse/scoring.py   score(components) ; ScoreComponents
    analyse/trends.py    rebuild_trends(session)
    digest/schema.py     DIGEST_SCHEMA
    digest/validate.py   validate_digest(payload, signal_ids, event_ids)
    digest/run.py        write_digest(session, cycle)
    cycle.py             run_cycle(), run_digest()
    api/auth.py          login/session dependency
    api/routes.py        all GET/POST routes (spec §6)
    api/serializers.py   pydantic response models
  scripts/check_sources.py, load_sources.py, derive_threshold.py, run_cycle.py
  tests/conftest.py + test_*.py (one per task)
data/sources.yaml, data/sources-live.json, data/entities.yaml
frontend/ (Vite app; src/api.ts, src/i18n.ts, src/views/*.tsx, src/components/*.tsx)
Dockerfile, docker-compose.yml, railway.json, README.md
```

---

### Task 1: Backend scaffold, settings, DB, vocabulary

**Files:** `backend/pyproject.toml`, `backend/rns/{config,main,vocab}.py`, `backend/rns/db/{engine,models}.py`, `backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/versions/0001_initial.py`, `docker-compose.yml`, `backend/tests/conftest.py`, `backend/tests/test_vocab.py`

**Interfaces produced:**
- `rns.config.settings` (fields: `database_url`, `anthropic_api_key|None`, `extraction_model`, `digest_model`, `digest_fallback_model`, `max_extractions_per_cycle=1500`, `extraction_concurrency=8`, `feed_timeout_seconds=20.0`, `feed_concurrency=12`, `max_consecutive_failures=5`, `story_threshold=0.22`, `app_password`, `secret_key`, `scheduler_enabled`, `cycle_hour_utc=5`, property `llm_enabled`).
- `rns.vocab`: `LAYERS: dict[str, Label]`, `TOPICS: dict[str, Label]`, `SIGNAL_TYPES: list[str]`, `AUTHORITY_WEIGHTS = {"high":1.0,"medium":0.7,"low":0.4}`, `SCOPES`, `METHODS`, `Label = NamedTuple(en, de)`.
- ORM classes in `rns.db.models`: `Source, FeedItem, Signal, Story, Entity, SignalEntity, SignalTopic, Event, Digest, Cycle, TrendCell` with columns per spec §5.
- `rns.db.engine.session_factory()`, `get_session()` dependency.

- [ ] Step 1: write `tests/test_vocab.py`:
```python
from rns import vocab
def test_topics_are_exactly_the_brief_vocabulary():
    # wrong impl: a hand-typed list that drifts from the brief
    assert len(vocab.TOPICS) == 30
    assert "CCS" in vocab.TOPICS and "district-heating" in vocab.TOPICS
    assert all(lbl.en and lbl.de for lbl in vocab.TOPICS.values())
def test_layers_are_the_six_from_the_report():
    assert list(vocab.LAYERS) == ["policy","editorial","innovation","corporate","infrastructure","funding"]
def test_authority_weights():
    assert vocab.AUTHORITY_WEIGHTS == {"high":1.0,"medium":0.7,"low":0.4}
```
- [ ] Step 2: run, fails (module missing).
- [ ] Step 3: create pyproject (deps as in Tech Stack + `selectolax`, `pyyaml`), `vocab.py`, `config.py`, models, engine, alembic env (async, `sys.path` fix, pgvector import in migration), migration `0001_initial.py` written by hand (not autogenerate) including `CREATE EXTENSION IF NOT EXISTS vector` and an HNSW index on `signals.embedding`.
- [ ] Step 4: `docker compose up -d`, `alembic upgrade head`, `pytest tests/test_vocab.py` passes.
- [ ] Step 5: commit.

### Task 2: Source catalogue, verification script, loader

**Files:** `data/sources.yaml`, `data/entities.yaml`, `backend/rns/sources/catalogue.py`, `backend/scripts/check_sources.py`, `backend/scripts/load_sources.py`, `backend/tests/test_catalogue.py`, `backend/tests/fixtures/sources_small.yaml`, `backend/tests/fixtures/sources_live_small.json`

**Interfaces produced:**
- `catalogue.load_catalogue(path) -> list[CatalogueEntry]` (pydantic model with spec §3 fields; validation errors for unknown layer/method/authority).
- `catalogue.load_live(path) -> dict[slug, LiveResult]` where `LiveResult(slug, resolved_url, method, item_count, checked_at)`.
- `catalogue.merge_for_load(entries, live) -> list[SourceRow]` with `collect: bool` and `not_collected_reason: str|None`. Raises `UnverifiedSourceError` if an `rss`/`page` entry is *marked* `collect=True` without a live result — by construction only live-verified rows get `collect=True`.
- `load_sources.upsert(session, rows)` idempotent on slug.

- [ ] Step 1: tests:
```python
def test_rss_source_without_live_result_is_not_collected(tmp_path): ...  # wrong impl: trusts the yaml
def test_newsletter_source_is_loaded_as_not_collected(): ...            # wrong impl: drops it
def test_unknown_layer_rejected(): ...
def test_live_result_overrides_url_with_resolved_feed(): ...            # autodiscovery result wins
```
- [ ] Step 2: run, fail.
- [ ] Step 3: transcribe **every** source from both briefs into `data/sources.yaml` (≈75 entries) with layer/authority/scope/method/priority; transcribe entity dictionary to `data/entities.yaml`. Implement catalogue.py, check_sources.py (httpx fetch, feedparser parse, autodiscovery on homepage, page extraction via Task 3's `page.extract_items`— so check_sources imports from `rns.collect.page`; write it after Task 3 or stub page checks until then), load_sources.py.
- [ ] Step 4: tests pass; run `check_sources.py` against the real catalogue → `data/sources-live.json`; record hit-rate in README later.
- [ ] Step 5: commit.

### Task 3: Collection — canonical URLs, RSS, page monitor, dedup

**Files:** `backend/rns/collect/{canonical,rss,page,run}.py`, tests `test_canonical.py`, `test_page.py`, `test_collect.py`, fixtures `page_list.html`, `feed_a.xml`, `feed_b.xml`

**Interfaces produced:**
- `canonical.canonical_url(url: str) -> str`; `canonical.content_hash(title, summary) -> str`.
- `RawItem(external_id, title, url, canonical_url, summary, published_at|None, content_hash)` dataclass.
- `rss.parse_feed(bytes, source_url) -> list[RawItem]`; `rss.fetch_rss(http, source) -> list[RawItem]`.
- `page.extract_items(html, base_url, item_selector=None) -> list[RawItem]`; `page.fetch_page(http, source) -> tuple[list[RawItem], page_hash]`.
- `run.collect_all(session, http) -> CollectStats(fetched, new_items, failed_sources)`; updates source health; global dedup on `canonical_url` with `also_seen_in`.

- [ ] Step 1 tests:
```python
def test_canonical_strips_tracking_but_keeps_real_query():
    assert canonical_url("HTTPS://WWW.Example.de/Pfad/?id=42&utm_source=x#top") == "https://www.example.de/Pfad/?id=42"
def test_canonical_trailing_slash_and_default_port(): ...
def test_page_extractor_skips_nav_and_footer_links(): ...      # fixture has nav links with long titles
def test_page_extractor_returns_empty_when_hash_unchanged(): ...
def test_same_canonical_url_from_two_sources_is_one_item_with_also_seen_in(db_session): ...
def test_failed_source_increments_and_quarantines_after_max(db_session): ...
```
- [ ] Step 2–5 as pattern; commit.

### Task 4: LLM client, extraction (live + mock), entity resolver, events

**Files:** `backend/rns/llm/{client,mock}.py`, `backend/rns/extract/{schema,prompt,run}.py`, `backend/rns/entities.py`, tests `test_extract_mock.py`, `test_entities.py`, `test_llm_client.py`

**Interfaces produced:**
- `client.complete_json(*, model, system, user, schema, max_tokens, fallback_model, attempts) -> dict`; raises `LLMUnavailable`, `LLMEmptyCompletion`.
- `schema.EXTRACTION_SCHEMA`, `schema.ExtractionResult` (fields per spec §4.2; `events: tuple[EventDraft,...]`).
- `prompt.SYSTEM` (list of blocks with `cache_control` on the vocabulary prefix), `prompt.user_message(item) -> str`.
- `mock.mock_extract(title, summary, source_layer) -> ExtractionResult` — deterministic keyword rules.
- `entities.load_seed(path) -> list[EntitySeed]`; `entities.resolve(session, names, kind) -> list[Entity]` (alias match; creates non-seeded organisation/project; never creates place).
- `extract.run.extract_pending(session, *, limit) -> ExtractStats(processed, signals, discarded, failed)`: marks items processed/discarded, writes `Signal`, `SignalTopic`, `SignalEntity`, `Event`.

- [ ] Tests (wrong impls in comments):
```python
def test_mock_only_emits_vocabulary_topics(): ...
def test_mock_flags_bridge_closure_only_when_named_artery(): ...  # "Kurt-Schumacher-Brücke gesperrt" → signal; "Unfall auf Landstraße" → not
def test_resolver_alias_phv_maps_to_patrick_henry_village(db_session): ...
def test_resolver_unknown_place_is_not_created(db_session): ...
def test_resolver_unknown_org_created_unseeded(db_session): ...
def test_event_with_only_deadline_is_stored(db_session): ...
def test_extraction_marks_non_signal_as_discarded_not_unprocessed(db_session): ...
def test_client_retries_empty_completion_then_falls_back(monkeypatch): ...  # fake AsyncAnthropic
```
- [ ] Implement; mock path used when `not settings.llm_enabled`; commit.

### Task 5: Embedding, stories, scoring, trends

**Files:** `backend/rns/analyse/{embedding,stories,scoring,trends}.py`, `backend/scripts/derive_threshold.py`, tests `test_scoring.py`, `test_stories.py`, `test_trends.py`

**Interfaces produced:**
- `embedding.embed_texts(texts: list[str]) -> list[list[float]]` (lazy singleton model; tests monkeypatch with a fake that maps known strings to fixed vectors).
- `scoring.ScoreComponents(authority, regional_relevance, novelty, economic_materiality, forward_lag)`; `scoring.score(c) -> float`; `scoring.story_confidence(distinct_sources) -> float`.
- `stories.assign(session, signal, *, threshold, window_days=14) -> StoryDecision(story_id, founded: bool, distance: float|None)`; updates story stats.
- `stories.novelty(distance, threshold) -> float` = `min(1, distance/(2*threshold))`.
- `trends.rebuild(session, weeks=26)`; `trends.movers(session, window=4) -> list[Mover(topic, layer, current, previous, delta)]`.

- [ ] Tests:
```python
def test_score_is_multiplicative_zero_when_forward_lag_zero(): ...
def test_confidence_one_source_half_two_three_quarters(): ...
def test_near_signal_joins_story_and_distinct_sources_counts_only_new_source(db_session): ...
def test_far_signal_founds_new_story(db_session): ...
def test_corroboration_novelty_is_zero_and_story_score_is_max(db_session): ...
def test_trend_cells_group_by_iso_week_topic_layer(db_session): ...
```
- [ ] Implement; commit.

### Task 6: Digest schema, validator, writer; cycle orchestration; scheduler

**Files:** `backend/rns/digest/{schema,validate,run}.py`, `backend/rns/cycle.py`, `backend/rns/llm/mock.py` (add `mock_digest`), `backend/scripts/run_cycle.py`, tests `test_digest_validate.py`, `test_cycle_mock.py`

**Interfaces produced:**
- `validate.validate_digest(payload: dict, *, signal_ids: set[str], event_ids: set[str]) -> DigestPayload` raising `DigestProvenanceError(list[str])`.
- `run.write_digest(session, cycle_id) -> Digest|None` (retries once with the validator's errors appended to the user message; returns None and marks `cycle.digest_ok=False` on second failure).
- `cycle.run_cycle(session_factory, *, http=None) -> Cycle`; `cycle.run_digest_only(session_factory) -> Digest|None`.
- `main.py` starts APScheduler when `settings.scheduler_enabled`.

- [ ] Tests:
```python
def test_validator_rejects_unknown_signal_id(): ...
def test_validator_rejects_missing_german_note(): ...
def test_validator_accepts_valid_payload(): ...
def test_mock_cycle_over_fixture_feeds_produces_signals_stories_trends_and_digest(db_session, respx_mock): ...
```
- [ ] Implement; commit.

### Task 7: API

**Files:** `backend/rns/api/{auth,routes,serializers}.py`, `backend/rns/main.py`, tests `test_api.py`

**Interfaces produced:** every route in spec §6, response models in `serializers.py`. `GET /api/meta` returns `{mode, extraction_model, digest_model, last_cycle, languages:["en","de"]}`.

- [ ] Tests:
```python
async def test_unauthenticated_signals_is_401(client): ...
async def test_login_sets_cookie_and_signals_filter_by_layer(client, seeded): ...
async def test_signal_detail_includes_five_score_factors_and_story_members(client, seeded): ...
async def test_events_separate_deadline_from_start(client, seeded): ...
async def test_sources_lists_not_collected_with_reason(client, seeded): ...
async def test_trends_returns_movers(client, seeded): ...
```
- [ ] Implement; commit.

### Task 8: Frontend

**Files:** `frontend/` (Vite scaffold), `src/{main,App,api,i18n,types}.tsx|ts`, `src/components/{Masthead,LayerKey,ScoreGlyph,SignalCard,StoryRow,Sparkline,LangToggle,Login}.tsx`, `src/views/{Radar,Digest,Signals,Watchlist,Calendar,Coverage}.tsx`, `src/index.css`

- [ ] Use the frontend-design skill for direction before writing CSS. Build against the running backend in mock mode. Vite build outputs to `backend/static`.
- [ ] Verification: `npm run build` (tsc + vite) clean, `npx oxlint` clean, each view loads with data in the browser.
- [ ] Commit.

### Task 9: Packaging, README, end-to-end verification

**Files:** `Dockerfile`, `railway.json`, `.dockerignore`, `README.md`, `.gitignore` (no bare `data/`!)

- [ ] `docker build` succeeds; container serves `/api/health` and the built UI.
- [ ] Full mock cycle on the real live sources; then, if an API key is available locally, one bounded live cycle (`MAX_EXTRACTIONS_PER_CYCLE=400`) and one digest.
- [ ] README: what it is, the brief, how the pipeline maps to the brief, source hit-rate, run/test/deploy instructions, decisions §10.
- [ ] Commit.

## Self-review

- Spec coverage: §3 → T2; §4.1 → T3; §4.2 → T4; §4.3–4.4 → T5; §4.5 → T6; §6 → T7; §7 → T8; §9 → T9; §8 tests distributed per task. Newsletter "not collected" → T2 + T7 `/api/sources`.
- Names consistent: `extract_pending`, `assign`, `validate_digest`, `run_cycle`, `collect_all` used identically across tasks.
