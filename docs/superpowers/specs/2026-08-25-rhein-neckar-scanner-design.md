# Rhein-Neckar Horizon Scanner — design

**Date:** 2026-08-25
**Status:** approved for implementation (autonomous build; decisions flagged in §10)
**Brief:** `docs/brief/01-sources-and-pillars.md` (four pillars, feed catalogue) and
`docs/brief/02-source-map-deep-research.md` (six-layer source map, architecture,
scoring formula, topic vocabulary, entity dictionary, priority implementation set).

## 1. Purpose

A dedicated, standalone horizon scanner for the Metropolregion Rhein-Neckar (MRN):
Mannheim, Heidelberg, Ludwigshafen and the surrounding Rhein-Neckar-Kreis, Bergstraße,
Pfalz and Odenwald areas, across Baden-Württemberg, Rheinland-Pfalz and Hessen.

It implements the brief's architecture end to end:

```
sources (6 layers) → collection (RSS first, list-page monitor second)
  → canonical URL + content hash dedup
  → entity extraction (place / organisation / project / fund)
  → topic classification (fixed 31-tag vocabulary)
  → novelty × authority scoring
  → event and deadline extraction
  → daily digest · trend database · watchlist
```

The product claim is the brief's own: economic shifts in the MRN cascade across
layers, and the scanner's value is *intersectional* — a research finding (EMBL) becomes
a Technologiepark tenant, a NEXT Mannheim investor-roadshow pitch, then a corporate
acquisition. The scanner must make that chain visible and auditable, not just list news.

Audience: the same as *Rhein-Neckar 2040* — regional economic-development and investor
stakeholders — so content and interface are bilingual (EN/DE).

### Non-goals (v1)

- **Email/newsletter ingestion.** The brief ranks it third and it needs a mailbox. The
  catalogue *records* newsletter-only sources so Coverage can show them as
  "catalogued, not collected"; nothing is silently dropped.
- Social media collection (brief: discovery pointers only, not system of record).
- GIS/BORIS land-value services, CORDIS API, DB BauInfoPortal queries — catalogued as
  `api`/`data` method, not collected in v1.
- Paywalled full text (RNZ+, MM+, Rheinpfalz). Headlines and teasers from free feeds only.
- Multi-user accounts. One shared password, as with every Pharos demonstrator.
- Persons as an entity type. The brief lists them; a demonstrator has no need to
  build person timelines from regional press.

## 2. Domain model (from the brief)

**Layers** (the report's six-layer collection system; a source belongs to exactly one):

| code | label EN | label DE |
|---|---|---|
| `policy` | Policy & public sector | Politik & Verwaltung |
| `editorial` | Editorial detection | Redaktionelle Medien |
| `innovation` | Innovation & clusters | Innovation & Cluster |
| `corporate` | Corporate investment | Unternehmen & Investitionen |
| `infrastructure` | Infrastructure & property | Infrastruktur & Immobilien |
| `funding` | Funding & capital | Förderung & Kapital |

**Topic tags** — the report's normalised vocabulary, fixed, 31 codes:
`CAPEX, FDI, corporate-expansion, corporate-contraction, jobs, startup, funding-round,
grant, EU-funding, public-procurement, commercial-real-estate, housing, planning-permit,
brownfield, rail, road, bridge, public-transport, port-logistics, energy, hydrogen, CCS,
district-heating, digital-infrastructure, life-sciences, chemicals, AI, public-policy,
tax, skills, research-infrastructure`. Each carries EN/DE labels. Signals tag against
any subset; the extractor may not invent a tag.

**Signal types** (form of the development; one per signal):
`decision, announcement, investment, funding_call, tender, planning, disruption,
research, event, position, data_release`.

**Entity dictionary** — seeded from the report, extensible by extraction:
- places: Mannheim, Heidelberg, Ludwigshafen, Rhein-Neckar-Kreis, Bergstraße, Viernheim,
  Weinheim, Walldorf, Schwetzingen, Sinsheim, Speyer, Frankenthal, Worms, Heppenheim,
  Bensheim, Wiesloch, Hockenheim, Rhein-Neckar (region)
- projects: FRANKLIN, Patrick-Henry-Village, Bahnstadt, Hochstraße, Kurt-Schumacher-Brücke,
  Riedbahn, Hospital-Areal, Heidelberg Innovation Park, LAB22, KI Lab Kurpfalz
- organisations: the catalogue's issuers (BASF, SAP, Heidelberg Materials, MVV, IHK
  Rhein-Neckar, IHK Pfalz, BioRN, DKFZ, EMBL, ZEW, VRRN, MRN GmbH, …)

Entity kinds: `place | organisation | project | fund`. Each has `slug`, `name`, `kind`,
`aliases[]`. Extraction returns free-text names; a resolver maps them onto dictionary
entries by exact/alias match, creating new `organisation`/`project` entries when unmatched
(places are closed: unknown places are kept as text on the signal but not as entities).

**Geographic scope** of a source: `city | district | region | state | national | eu`.

**Authority** of a source: `high | medium | low` → weights 1.0 / 0.7 / 0.4 (the brief's
three-tier rating; low-authority sources are not in the v1 catalogue).

## 3. Source catalogue and verification

`data/sources.yaml` is the human-authored catalogue transcribed from both briefs. One
entry per source:

```yaml
- slug: mannheim-presse
  name: Stadt Mannheim — Pressemeldungen
  layer: policy
  authority: high
  scope: city
  places: [Mannheim]
  language: de
  method: rss              # rss | page | newsletter | api | social
  url: https://www.mannheim.de/de/rss/pressemeldungen
  homepage: https://www.mannheim.de/de/presse
  priority: core           # core (always-on) | thematic
  cadence: daily
  notes: "One of the highest-priority feeds."
  brief_ref: "02 §core"
```

`method: page` entries carry the list-page URL the report says to monitor. `newsletter`,
`api`, `social` entries are catalogued only.

**Verification is a build step, not a flag.** `scripts/check_sources.py` fetches every
`rss` and `page` entry, parses it, and writes `data/sources-live.json` containing only
those that returned ≥1 item (rss) or ≥3 extracted items (page), with the observed item
count and the resolved final URL. The loader (`scripts/load_sources.py`) reads *only*
`sources-live.json` plus the non-collected entries (so Coverage can list them). A URL that
never resolved is never in the database as an active source.

Lesson carried over from Fathom: an LLM-authored `validated` flag meant "plausible", not
"resolves" (79/261). The report itself marks several endpoints "validate before
production" (SWR feed, Heidelberg construction-site feed).

Some catalogued RSS URLs were only *described* in the brief (RNZ directory "12+ feeds",
Ludwigshafen "site-linked RSS", W.E.G. "site-linked RSS"). The check script also tries
feed autodiscovery (`<link rel="alternate" type="application/rss+xml">`) on `homepage`
so those resolve without hand-guessing.

## 4. Pipeline

One `cycle` runs daily (APScheduler, 05:00 UTC) or on demand. Stages are separately
callable and idempotent.

### 4.1 Collect

- **RSS/Atom** via `feedparser` over `httpx` (timeout 20 s, concurrency 12, a plain
  browser-ish User-Agent).
- **Page monitor** for `method: page`: fetch the list page, extract candidate items with
  a generic heuristic — anchors inside `article`, `li`, `h1–h4`, or `.news/.teaser/.list`
  containers; same host; title ≥ 20 chars after whitespace collapse; not a nav/footer link
  (excluded ancestors `nav, footer, header[role=banner]`); dedup by canonical URL. A
  page-level content hash short-circuits unchanged pages. A per-source optional CSS
  `item_selector` in the catalogue overrides the heuristic when a site needs it.
- Every item is stored as a `feed_item` with `canonical_url` (scheme+host lowercased,
  `utm_*`/`fbclid`/`ref` stripped, fragment dropped, trailing slash normalised) and a
  `content_hash` (sha256 of title + summary text). Uniqueness: `(source_id, external_id)`
  and a global index on `canonical_url` — the same URL arriving via two feeds (MM
  Wirtschaft + MM Unternehmen der Region) is one item, credited to the first source and
  recorded as `also_seen_in[]`.
- Source health: `consecutive_failures`, `last_ok_at`, `last_error`; quarantine after 5
  consecutive failures; never deleted (a dead feed is coverage evidence).

### 4.2 Extract (one Claude call per new item; Haiku 4.5)

Structured JSON output (`output_config.format = json_schema`). Schema:

```
is_signal: bool
headline_en, headline_de: str      # one factual sentence
summary_en, summary_de: str        # 2–3 sentences of substance
signal_type: enum
topics: [enum(31)]                 # any subset; empty allowed
places: [str]                      # free text, resolved against dictionary
organisations: [str]
projects: [str]
regional_relevance: 0–1            # how much this concerns the MRN specifically
economic_materiality: 0–1          # size/consequence for the regional economy
forward_lag: 0–1                   # rubric below
events: [{name, organizer, location, start, end, deadline, topic, registration_url,
          funding_program, target_audience}]
```

`forward_lag` rubric in the prompt (the brief's central idea — "an unpublished committee
proposal, new funding call, permit, capex announcement or tender gets higher forward-lag
value than retrospective reporting"): 0.1 retrospective report of something completed;
0.4 ongoing situation; 0.7 announced future action with a date; 1.0 proposal, call,
tender, consultation or agenda item *before* the decision.

`is_signal=false` for opinion, explainers, sport, crime/accident reports without
economic consequence, entertainment listings. The brief's warning about MRN-News: "do
not let police/incident volume swamp economic signals" — so the extractor is told that
a road closure is a signal only when it names a bridge/artery on the project list or an
industrial site.

**Deadline is a separate field from event date** (brief). Events are stored in their own
table, linked to the signal.

Cost guard: `max_extractions_per_cycle` (default 1500); concurrency 8.

**Mock extractor** when `ANTHROPIC_API_KEY` is unset: deterministic keyword rules over
the topic vocabulary and entity dictionary, `is_signal` when ≥1 topic or ≥1 project
matches, fixed scores derived from rule hits, headline = title. Exercised by tests; the
UI shows a "Mock" badge so placeholder text cannot pass for analysis.

### 4.3 Embed, corroborate, score

- Embedding: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (384-d,
  fastembed, local). Text = `headline_de + " " + summary_de` (German, the corpus
  language; EN fields are translations, not evidence).
- **Stories.** For each new signal, nearest prior signal by cosine distance among signals
  published within 14 days. If distance < `story_threshold` → the new signal *joins* that
  story as a corroboration (row kept; `story_id` set; story `corroboration_count` and
  `distinct_sources` updated). Otherwise it founds a new story. The brief: "Secondary
  newspaper confirmation can then raise confidence without making the duplicated story
  appear as several separate signals." Threshold is derived from this corpus
  (`scripts/derive_threshold.py`: the 10th percentile of distances between pairs from
  *different* stories on hand-labelled examples), not inherited — Fathom's finding that
  thresholds do not port between corpora.
- **Novelty** of a founding signal = `min(1, nearest_distance / novelty_span)` where
  `novelty_span` = 2 × story_threshold; corroborations inherit novelty 0 for scoring
  and never appear as separate digest items.
- **Score** (the brief's formula, verbatim, all components stored):

  `signal_score = authority × regional_relevance × novelty × economic_materiality × forward_lag`

  Story score = max over member signals; story `confidence` = 1 − 0.5^distinct_sources
  (one source 0.5, two 0.75, three 0.875 …). The UI always shows the five factors, never
  just the product.

### 4.4 Trend database

Pure SQL, recomputed per cycle: signal counts by `topic × layer × ISO-week` and
`entity × week`, over a rolling 26 weeks. No LLM.

### 4.5 Digest (Claude Opus 5, one call per cycle, EN and DE in one response)

Input: the cycle's founding signals ranked by score (cap 60) with IDs, plus upcoming
events/deadlines (next 30 days) and the trend deltas (topics whose 4-week volume moved
most vs the prior 4). Output JSON:

```
lead_en, lead_de                       # 3–4 sentences: what moved this cycle
sections: [{layer, items: [{signal_id, note_en, note_de}]}]
chains: [{title_en, title_de, signal_ids[]}]   # cross-layer links the analyst sees
watch: [{event_id, why_en, why_de}]
```

**Provenance invariant** (build-enforced): every `signal_id`/`event_id` must exist in the
input set; the validator rejects the digest and retries once with the error, then fails
the digest stage (the cycle still completes). No free-text claims outside `lead` and
`note`, and notes are displayed next to the signal they cite. Empty-completion retry and
model fallback (Sonnet 5) as in the LLM client pattern already proven in Hivemind/Fathom.

## 5. Data model

Postgres + pgvector. Tables:

- `sources` — catalogue fields (§3) + health fields (§4.1)
- `feed_items` — raw items; `canonical_url` (unique), `content_hash`, `also_seen_in`
  (array of source ids), `processed`, `discarded`
- `signals` — extraction fields (§4.2), `embedding`, `story_id`, score components +
  `score`, `published_at`, `source_id`, `feed_item_id`
- `stories` — `founding_signal_id`, `corroboration_count`, `distinct_sources`,
  `confidence`, `score`, `first_seen`, `last_seen`
- `entities` — `slug`, `kind`, `name`, `aliases[]`, `seeded` (bool)
- `signal_entities` — (signal_id, entity_id, role) many-to-many
- `signal_topics` — (signal_id, topic_code)
- `events` — `signal_id`, name, organizer, location, start, end, deadline, topic,
  registration_url, funding_program, target_audience
- `digests` — `cycle_id`, `lead_en/de`, `payload` (JSONB, validated), `model`, `created_at`
- `cycles` — id, started/finished, per-stage counts (`items_fetched`, `items_new`,
  `extracted`, `signals`, `stories_new`, `corroborations`, `digest_ok`), `mode` (live|mock)
- `trend_cells` — `week`, `topic`, `layer`, `count` (materialised per cycle)

Alembic migrations; every datetime timezone-aware.

## 6. API (FastAPI, `/api`)

Auth: `POST /api/login {password}` → signed cookie (itsdangerous, 7 days); every other
route except `/api/health` requires it. Password from `APP_PASSWORD`.

- `GET /api/meta` — mode (live|mock), models, last cycle, language labels
- `GET /api/overview` — last-cycle counts, top 10 stories, volume by layer (7d/30d),
  next 5 deadlines, latest digest lead
- `GET /api/signals` — filters `layer, topic, place, kind/entity, type, min_score, q,
  since, page, per_page`; returns founding signals with story stats
- `GET /api/signals/{id}` — full record, score decomposition, story members, feed item
- `GET /api/stories/{id}`
- `GET /api/entities?kind=` — with 30d/90d counts; `GET /api/entities/{slug}` — timeline
  of stories
- `GET /api/events?from=&to=` — events and deadlines; `deadline` and `start` separate
- `GET /api/digests`, `/api/digests/latest`, `/api/digests/{id}`
- `GET /api/trends?weeks=12` — topic × layer × week cells + top movers
- `GET /api/sources` — coverage table incl. catalogued-not-collected, items 7d, signals
  7d, last_ok, status, method
- `POST /api/cycle/run`, `POST /api/cycle/digest` — trigger; return cycle record

## 7. Frontend

React 19 + Vite + TypeScript + Tailwind v4 + react-router. Six views:

1. **Radar** (landing) — the six layers as a fixed horizontal rhythm; within each, the
   week's stories as ranked rows sized by score, with the five score factors as a
   compact glyph; top movers strip from trends; next deadlines rail.
2. **Digest** — the latest digest as a broadsheet page: lead, per-layer sections whose
   notes sit beside the cited signal cards, **chains** (cross-layer links) drawn as a
   short vertical sequence, watch list. Archive of prior digests.
3. **Signals** — filterable table (layer, topic, place, type, authority, score, search),
   each row expandable to score decomposition + corroborating outlets + original link.
4. **Watchlist** — entities by kind with sparkline of story counts; entity page = timeline.
5. **Calendar** — events and deadlines by week; deadlines visually distinct from events.
6. **Coverage** — the honesty view: every catalogued source, method, layer, authority,
   status, items/signals in 7 days; not-collected sources listed with the reason.

Language toggle EN/DE in the masthead: swaps chrome strings (a single `i18n.ts`
dictionary) and picks `_en`/`_de` content fields. Original German source titles are
always shown alongside.

Aesthetic direction (to be executed with the frontend-design skill): a regional
broadsheet's economy pages rather than a dashboard — typographic, dense, tabular, ivory
ground, ink text, one restrained accent; the six layers get a stable, muted six-colour
key used consistently across all views. Pharos-adjacent, not Pharos-branded.

## 8. Testing

Backend `pytest` (asyncio), each test written against a specific wrong implementation:

- canonical URL: `utm_*`/fragment stripped, host lowercased, but *path case preserved*
  and query params that are not tracking params kept (a wrong impl strips all queries)
- page monitor: extracts article links from a fixture page and **not** nav/footer links;
  returns nothing for an unchanged page hash
- dedup: same canonical URL from two sources → one feed item with `also_seen_in`
- mock extractor: only vocabulary topics; unknown place stays text, not an entity
- entity resolver: alias match (e.g. "PHV" → Patrick-Henry-Village), case-insensitive;
  unknown organisation creates a non-seeded entity; unknown place does not
- scoring: multiplicative (any zero factor → 0); corroboration gets novelty 0 and does not
  raise story score above the founder's unless its own score is higher
- stories: near-duplicate joins existing story and raises `distinct_sources` only when the
  source differs; far signal founds a new story
- digest validator: rejects unknown `signal_id`; accepts a valid payload; missing DE field
  rejected
- sources loader: refuses an `rss` source absent from `sources-live.json`; loads
  newsletter entries as `not_collected`
- events: `deadline` and `start` stored separately; an event with only a deadline is valid
- API: unauthenticated request → 401; `/api/signals?layer=funding` returns only that layer
- cycle in mock mode over fixture feeds completes end to end and writes a digest

Frontend: `tsc -b` + `vite build` clean; oxlint.

Verification before completion: a full mock cycle on fixtures, then a live source check
against the real catalogue, then (if a key is available locally) one bounded live
extraction run so the shipped database holds real signals.

## 9. Packaging and deployment

- `docker-compose.yml` — pgvector Postgres on host port **5438** (5433–5437 are taken by
  sibling projects).
- Multi-stage `Dockerfile` (node build → python runtime, fastembed model warmed into the
  image), `railway.json` with `preDeployCommand: alembic upgrade head`, healthcheck
  `/api/health`, `sh -c` `$PORT` expansion.
- Env: `DATABASE_URL`, `ANTHROPIC_API_KEY` (optional → mock), `APP_PASSWORD`,
  `SECRET_KEY`, `SCHEDULER_ENABLED`, `CYCLE_HOUR_UTC`.
- Not deployed in this build; Railway-ready.

## 10. Decisions made autonomously (for review)

1. **Same stack family as Fathom/Meridian**, fresh code. Alternative considered: SQLite +
   in-process vectors for a lighter standalone. Rejected: corroboration/novelty are core
   to the brief and pgvector + Railway's pgvector image is a proven path here.
2. **Bilingual from the start** (EN/DE content fields + chrome dictionary). Adds ~15%
   surface but the Rhein-Neckar 2040 precedent says the client reads German.
3. **Persons excluded** from entity extraction.
4. **Newsletter/API/social sources catalogued but not collected**; Coverage says so.
5. **Digest on Opus 5, extraction on Haiku 4.5**; both are single env vars.
6. **Product name**: "Rhein-Neckar Horizon Scanner" (working name only; no invented brand).
7. **Score display**: raw multiplicative score kept as the brief specifies; the UI ranks
   and shows factors rather than pretending the product is a calibrated percentage.
