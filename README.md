# Rhein-Neckar Horizon Scanner

A standalone, bilingual (EN/DE) horizon scanner for the Metropolregion Rhein-Neckar —
Mannheim, Heidelberg, Ludwigshafen and the surrounding Rhein-Neckar-Kreis, Bergstraße,
Pfalz and Odenwald, across Baden-Württemberg, Rheinland-Pfalz and Hessen.

**Live:** https://web-production-bd635b.up.railway.app — password `kurpfalz`

Built from two briefs (in `docs/brief/`): a four-pillar source architecture and a
six-layer source map with a recommended pipeline, scoring formula, topic vocabulary and
entity dictionary. The scanner implements that blueprint end to end:

```
sources (6 layers) → collection (RSS first, list-page monitor second)
  → canonical URL + content hash dedup
  → entity extraction (place / organisation / project / fund)
  → topic classification (the brief's fixed 31-tag vocabulary)
  → stories (corroboration across outlets) · novelty × authority scoring
  → event and deadline extraction
  → daily digest · trend database · watchlist
```

## What the brief asked for, and where it lives

| Brief | Implementation |
|---|---|
| Six collection layers (policy, editorial, innovation, corporate, infrastructure, funding) | `backend/rns/vocab.py`; every source in `data/sources.yaml` belongs to one |
| "Direct RSS/API first, structured page monitoring second" | `rns/collect/rss.py`, `rns/collect/page.py`; the check script tries feed autodiscovery before falling back to a page monitor |
| Canonical URL + content-hash deduplication | `rns/collect/canonical.py`; one URL arriving via two feeds is one item with `also_seen_in` |
| Entity dictionary (places, projects, organisations) | `data/entities.yaml`, resolver in `rns/entities.py`; places are a closed set, the rest grow |
| Normalised topic tags (31) | `rns/vocab.py` — the extractor cannot invent a tag |
| `signal_score = authority × regional_relevance × novelty × economic_materiality × forward_lag` | `rns/analyse/scoring.py`, verbatim and multiplicative; all five factors stored and shown |
| "Secondary confirmation raises confidence without making the story appear as several signals" | `rns/analyse/stories.py`: near-duplicates join a story as corroborations (novelty 0) |
| A deadline is a separate field from the event date | `events.deadline` vs `events.start_date`, kept apart through to the Calendar |
| Daily digest, trend database | `rns/digest/` (provenance-validated), `rns/analyse/trends.py` (pure SQL, founders only) |

## Sources: verified, not trusted

`data/sources.yaml` transcribes every source in both briefs (101 entries). Only the ones
that **actually resolved** at check time are collected:

```
backend/.venv/bin/python scripts/check_sources.py
```

writes `data/sources-live.json` (what resolved, how, how many items) and
`data/sources-check-report.json` (what did not, and why). The loader reads only the live
file. Newsletter, API and social sources are catalogued so the Coverage view can name
them, but not collected in v1.

Last check (2026-08-25): **67 of 84 rss/page sources live (80 %)**. 14 of the 17 misses
are honest — no feed and a JavaScript-rendered list page (BASF, rnv, Uni Mannheim,
MAFINEX), 403/503 (HTGF, RNF), or a page that resolved to a feed another entry already
covers (Heidelberg Baustellen → the general press feed; three Ludwigshafen entries → one
`news.xml`). Several endpoints the brief could only describe ("site-linked RSS") resolved
by autodiscovery: Ludwigshafen, W.E.G., Rhein-Neckar-Kreis, MWSP, NEXT Mannheim, Hafen
Mannheim, HITS, DKTK, PALATINA, SWR's regional Atom feed.

## Pipeline

One `cycle` runs daily (05:00 UTC, APScheduler) or on demand (`POST /api/cycle/run`,
`python scripts/run_cycle.py`). Stages:

1. **Collect** — 67 sources concurrently; items older than 60 days on first sight are
   archive, not news, and are skipped (MVV's feed carries ~1,700 items going back years).
2. **Extract** — one Claude Haiku 4.5 call per item, structured output: bilingual
   headline/summary, signal type, topics, entities, the three judgement scores
   (regional relevance, economic materiality, forward lag — rubric in
   `rns/extract/prompt.py`), events and deadlines. Most items are not signals; the
   extractor is told so, and told that a road closure counts only when it names one of
   the region's critical arteries.
3. **Analyse** — multilingual sentence embeddings (local, `paraphrase-multilingual-
   MiniLM-L12-v2`), story assignment within a 14-day window, novelty, score.
4. **Trends** — founder counts by topic × layer × ISO week; movers = last 4 weeks vs
   the 4 before.
5. **Digest** — one Claude Opus 5 call (Sonnet 5 fallback) over the cycle's founding
   signals, upcoming deadlines and movers → lead, per-layer notes, cross-layer *chains*,
   watch list — in both languages. A validator rejects any digest that cites an id it was
   not given; the model gets one corrected retry, then the stage fails loudly.

Without `ANTHROPIC_API_KEY` the whole pipeline runs on a deterministic rule-based mock
(keyword vocabulary + entity dictionary + the forward-lag rubric), the header shows a
**Mock** badge, and every digest sentence is prefixed `[mock]` so placeholder text can
never pass for analysis.

## Interface

Six views, EN/DE toggle in the masthead (chrome strings and content both switch; the
German original title is always shown).

- **Radar** — the six layers as a fixed rhythm, each with the month's top stories ranked
  by score; movers; next deadlines; the latest digest's lead.
- **Digest** — the reading page: lead, chains drawn as a connected sequence, per-layer
  notes beside the signal they cite, watch list, archive.
- **Signals** — filter by layer, topic, type, minimum score, search; every row expands to
  its five score factors and the outlets that corroborated it.
- **Watchlist** — places, projects, organisations and funds by story count; entity pages
  with a timeline.
- **Calendar** — events and deadlines, next 90 days, deadlines visually distinct.
- **Coverage** — every catalogued source, collected or not, with the reason, items and
  signals in 7 days, last success, quarantine state; recent cycles.

The score glyph next to every signal is a *Pegellatte* — the striped river-gauge post
on the Rhine and Neckar banks — reading the five factors of the brief's formula.

## Local

```bash
docker compose up -d                                   # pgvector on :5438
cd backend
python3.12 -m venv .venv && .venv/bin/pip install -e ".[test]"
.venv/bin/alembic upgrade head
.venv/bin/python scripts/load_sources.py               # catalogue ∩ live results + entities
.venv/bin/python scripts/run_cycle.py                  # one cycle (mock unless a key is set)
.venv/bin/uvicorn rns.main:app --reload --port 8471    # API + built UI at /
cd ../frontend && npm install && npm run dev           # :3001, proxies /api → :8471
```

`backend/.env` (see `.env.example`): `ANTHROPIC_API_KEY`, `APP_PASSWORD` (default
`kurpfalz`), `SECRET_KEY`, `MAX_EXTRACTIONS_PER_CYCLE`, `MAX_ITEM_AGE_DAYS`.

## Tests

```bash
cd backend && .venv/bin/python -m pytest -q      # 66 tests
cd frontend && npm run build && npx oxlint src
```

Every test names the wrong implementation it defends against — canonical URLs that
strip real query strings, a page monitor that picks nav links, a dedup that misses the
same URL across feeds, a corroboration that gets counted as a new trend hit, a digest
that cites an invented id, an extraction queue that starves undated page items.

## Deploy

Multi-stage `Dockerfile` (Vite build → Python runtime with the embedding model warmed
into the image), `railway.json` with `alembic upgrade head && load_sources` as the
pre-deploy command and `/api/health` as the healthcheck.

Deployed on Railway (project `rhein-neckar-scanner`, services `web` + `postgres`): Postgres
is the `pgvector/pgvector:pg16` image with a volume at `/var/lib/postgresql/data`;
`DATABASE_URL` on `web` references the postgres service's password and private domain.
`ANTHROPIC_API_KEY` is set, so it runs **live**, with `MAX_EXTRACTIONS_PER_CYCLE=500` as
the daily cost ceiling (~500 Haiku calls + one Opus digest ≈ under €1/day). Deploy with
`railway up --service web` from the repo root; GitHub auto-deploy is not wired.

## Decisions taken while building (see spec §10)

`docs/superpowers/specs/2026-08-25-rhein-neckar-scanner-design.md` — same stack family
as the other Pharos scanners but fresh code; bilingual from the start; persons excluded
as an entity type; newsletter/API/social sources catalogued but not collected; digest on
Opus 5, extraction on Haiku 4.5; the raw multiplicative score kept as the brief specifies
rather than pretending it is a calibrated percentage.
