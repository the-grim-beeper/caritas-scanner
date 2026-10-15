# Horizont-Scanner Landkreis Miesbach — design

**Date:** 2026-10-14
**Status:** approved by Nicklas in chat (2026-10-14); spec review waived for the 15 Oct deadline
**Client:** Caritas-Zentrum Miesbach, via the TUM Strategic Foresight Clinic, Team 1.
Subproject "Horizon scanner" (two team members), agreed 2026-10-06.
**Template:** fork of `the-grim-beeper/rhein-neckar-scanner` at `372deb1` (history kept as lineage).
**Brief:** `docs/brief/source-architecture.pdf` (ChatGPT deep research, cut 2026-10-08) with its text
(`source-architecture.txt`) and link list (`source-architecture-links.txt`). The three CSVs the report
mentions (61-row register, actor edges, calendar) only ever existed in ChatGPT's sandbox and are lost;
everything here is rebuilt from the PDF.
**Deadline:** a live URL for the team session on Thursday 15 October 2026, 15:00.

## 1. Purpose

The question the whole Caritas project serves: *how can an inter-municipal structure for social
provision in Landkreis Miesbach (the "Interkommunale Sozialraumlotsen") be designed and anchored so
that it still works in 2035 and 2040?*

The scanner's job, as agreed on 6 October: condense developments in the field into **a few weekly
insights** that give Caritas an overview and give the team a baseline for the foresight work. It must
earn trust the way the Rhein-Neckar scanner did: by being right, sourced and useful every week.

The report's sharpest finding sets the scanner's focus. The county already has many *named*
coordination structures (Sozialbeirat, Netzwerk Ehrenamt, Netzwerk Quartiersmanagement, Netzwerk
Integration, Verbund Psychische Gesundheit Region 17, GesundheitsregionPlus "im Aufbau",
Pflegestützpunkt). The unknown is whether they connect, hold decision rights, keep stable attendance
and move information. So "change" means change in **mandates, money, staffing, rules and
legitimacy** around social provision, not general local news.

Audience: the student team first (German-speaking, TUM), then the Caritas contact and colleagues.
**German first**; the English toggle is kept from the template.

### Non-goals (v1)

- Persons as entities. *Offices* (Landrat, Erster Bürgermeister Waakirchen, Dekan) are tracked;
  individuals' timelines are not built. Office-holders named in the brief stay in the brief.
- Protected or internal data (Caritas internals, service-user data, AI interviews). The scanner reads
  only the public record and says so; gaps the report assigns to interviews stay listed as gaps.
- Newsletter and social-media ingestion (catalogued, not collected, as in the template).
- Paywalled full text. Teasers and headlines only.
- Multi-user accounts. One shared password.

## 2. Domain model

### 2.1 Layers (the report's nine; a source belongs to exactly one)

| code | DE | EN |
|---|---|---|
| `gemeinden` | Gemeinden | Municipalities |
| `landkreis` | Landkreis & Dienste | County & local services |
| `wohlfahrt` | Wohlfahrt & Zivilgesellschaft | Welfare & civil society |
| `kirche` | Kirche | Church |
| `bezirk` | Bezirk Oberbayern | District of Upper Bavaria |
| `freistaat` | Freistaat Bayern | State of Bavaria |
| `bund` | Bund | Federal |
| `medien` | Medien & Forschung | Media & research |
| `vergleich` | Vergleichsfälle | Peer cases |

### 2.2 Topic vocabulary (fixed; grouped under the report's six signal families)

Families: `struktur` (Structure), `personal` (People), `bedarf` (Demand/supply), `geld` (Money),
`regeln` (Rules), `stimmung` (Sentiment). Each topic has a family and DE/EN labels; the extractor may
not invent a code.

- **struktur:** `koordination` Koordination & Netzwerke · `steuerung` Steuerung, Mandat & Trägerschaft ·
  `verstetigung` Verstetigung & Regelfinanzierung · `interkommunal` Interkommunale Zusammenarbeit ·
  `quartier` Quartier & Sozialraum · `daten` Daten & Sozialberichterstattung ·
  `kirchenstruktur` Kirchliche Strukturen · `traegerwandel` Trägerwandel (Fusion, Schließung, Neugründung)
- **personal:** `fachkraefte` Fachkräfte · `stellen` Stellen & Nachbesetzung · `leitung` Leitungswechsel & Ämter ·
  `ehrenamt` Ehrenamt
- **bedarf:** `pflege` Pflege & Alter · `jugend-familie` Jugend, Familie & Kita · `eingliederung` Eingliederung & Inklusion ·
  `psyche` Psychische Gesundheit & Sucht · `armut` Armut & Grundsicherung · `wohnen` Wohnen & Wohnungsnot ·
  `integration` Migration & Integration · `teilhabe` Einsamkeit & Teilhabe · `gesundheit` Gesundheitsversorgung ·
  `mobilitaet` Mobilität & Erreichbarkeit · `demografie` Demografie
- **geld:** `haushalt` Kommunalhaushalt · `umlagen` Kreis- & Bezirksumlage · `foerderung` Förderung & Zuschüsse ·
  `foerderende` Förderende & Anschlussfinanzierung · `vereinbarungen` Leistungs- & Vergütungsvereinbarungen
- **regeln:** `gesetzgebung` Gesetzgebung & Verordnung · `sgb` SGB-Reformen · `landesprogramm` Landesprogramme
- **stimmung:** `politik` Politischer Wechsel · `kontroverse` Kontroverse & Protest

### 2.3 Signal types (form of the development; one per signal)

`decision, announcement, budget, funding_call, service_change, staffing, planning, disruption,
research, event, position, data_release` — `service_change` covers openings, closures, Aufnahmestopp,
reduced hours; `staffing` covers vacancies, leadership changes, recruitment failures.

### 2.4 Entities

Kinds: `place | organisation | forum | programme | office`.

- **places** (closed set): the 17 municipalities (Bad Wiessee, Bayrischzell, Fischbachau, Gmund a.
  Tegernsee, Hausham, Holzkirchen, Irschenberg, Kreuth, Miesbach, Otterfing, Rottach-Egern,
  Schliersee, Tegernsee, Valley, Waakirchen, Warngau, Weyarn) plus Landkreis Miesbach, Tegernseer Tal,
  Leitzachtal, Oberland, Region 17, Bezirk Oberbayern, Bayern, Rheinland-Pfalz, Österreich.
- **organisations**: Caritas-Zentrum Miesbach, Caritasverband München-Freising, Landratsamt, Jugendamt,
  Jobcenter, Pflegestützpunkt, Diakonie Rosenheim, BRK Kreisverband Miesbach, Lebenshilfe Miesbach,
  AWO, Krankenhaus Agatharied, Erzbistum München und Freising, Dekanat Miesbach, Evang.-Luth. Dekanat
  Bad Tölz, StMAS, StMGP, StMFH, BMAS, BMBFSFJ, MVV, Regionalentwicklung Oberland … (grows by extraction)
- **forums**: Sozialbeirat, Netzwerk Ehrenamt, Netzwerk Quartiersmanagement, Netzwerk Integration,
  Verbund Psychische Gesundheit Region 17, Jugendhilfeausschuss, GesundheitsregionPlus, GSV-Gremium,
  Kreistag, Bezirkstag, the 17 councils (grows by extraction)
- **programmes**: Interkommunale Sozialraumlotsen, SeLA, PflegesoNah, LEADER, ESF Plus,
  Gemeindeschwester plus, Community Nursing, Präventionsketten, BergBus, Mobilitätskonzept (grows)
- **offices**: Landrat, Erster Bürgermeister/Bürgermeisterin <Gemeinde>, Dekan, Caritasdirektor,
  Jugendamtsleitung, Jobcenterleitung (grows; never a personal name)

Extraction returns free text; the template's resolver maps names onto the dictionary by exact/alias
match, creating non-seeded entries for organisation/forum/programme/office. Places stay closed.

### 2.5 Score

`signal_score = authority × regional_relevance × novelty × consequence × forward_lag`

`consequence` replaces the template's `economic_materiality`: consequence for social provision and
coordination in Landkreis Miesbach (a new statutory duty, a budget line cut, a service closure, a
new coordination body, a grant ending = 0.8+; a single event or a small grant = 0.3). The other four
factors and the story/novelty/confidence mechanics are unchanged from the template.

## 3. Sources

### 3.1 Catalogue

`data/sources.yaml` is rebuilt from the report:

- the **38-source v1 core** (its table "Recommended v1 core");
- the **extended verified set** it deliberately kept out of the weekly core (Krankenhaus Agatharied
  Presse, Caritas München-Freising Geschäftsberichte, AWO Seniorenzentrum, Hospizkreis,
  Nachbarschaftshilfe Warngau, Bezirk publications, Landesamt für Statistik, Landkreis
  Pressemitteilungen);
- its **"plausible, unverified"** bundle: BR24 Oberbayern, Tegernseer Stimme, Das Gelbe Blatt, Merkur
  Region Miesbach; Thünen-Institut, BBSR, DZA, IAB, DJI, Berlin-Institut, Wegweiser Kommune; neue
  caritas, NDV, Sozialwirtschaft; Bayerischer Landkreistag, Bayerischer Gemeindetag, Freie
  Wohlfahrtspflege Bayern, Landes-Caritasverband Bayern, Deutscher Verein, BAGFW, Deutscher
  Caritasverband, Deutscher Landkreistag, BMG;
- **municipal endpoint discovery**: durable council/news/finance pages (Sitzungskalender,
  Ratsinformationssystem, Gemeindeblatt) for Rottach-Egern and Weyarn (missing in the report) and for
  the six municipalities whose only source is an election page (Bad Wiessee, Fischbachau, Gmund,
  Hausham, Miesbach, Valley).

Every entry keeps `brief_ref` (the report's footnote number, or `discovery`/`unverified`).

### 3.2 Verification is a build step (unchanged principle)

`scripts/check_sources.py` decides what is collected; only verified entries are ever active.
Extended for the new methods (below): `query` is live if the search feed returns ≥1 item, `diff` if
the page yields ≥200 characters of main text, `pdf` if the listing page links ≥1 PDF on an allowed host.

### 3.3 Methods

`rss | page | query | diff | pdf | newsletter | api | social`. Collected: `rss, page, query, diff, pdf`.

- **`query`** — Google News RSS search
  (`https://news.google.com/rss/search?q=<q>+when:60d&hl=de&gl=DE&ceid=DE:de`). One query per
  municipality (`"Waakirchen" (Gemeinderat OR Haushalt OR Pflege OR Sozial OR Kita OR Zuschuss OR Caritas)`)
  plus about ten county-level thematic queries built from the report's lexicon (Pflege, Kreisumlage/
  Haushalt, Jugendhilfe/Kita, ÖPNV/Rufbus, Fachkräfte, Ehrenamt/Quartier, Jobcenter/Grundsicherung,
  Caritas Miesbach, Sozialraumlotse, Krankenhaus Agatharied). Layer `medien`, authority `medium`.
  Item titles arrive as "Headline - Outlet": the outlet is split off and kept. **Dedup:** Google
  redirect URLs never match a direct source's URL, so a query item whose normalised headline
  (casefolded, whitespace-collapsed, outlet suffix removed) equals an item already stored in the last
  60 days is credited to that item (`also_seen_in`) instead of becoming a new one.
- **`diff`** — structural pages that matter more for what changes than for news (Fachstelle für
  Soziales und Senioren, Pflegestützpunkt, GesundheitsregionPlus, Dekanat Miesbach, Bezirk
  Sozialberichterstattung, Sozialplanung). The main text is normalised and stored on the source. First
  sight stores a baseline and emits nothing. A later change emits **one** feed item: title
  "Änderung: <source>", summary = only the added and removed lines (capped at 6,000 chars). The
  extraction stage then decides whether the change is a signal.
- **`pdf`** — listing pages whose content lives in PDFs (Landkreis Amtsblatt, Irschenberg
  Sitzungsprotokolle, Schliersee/Otterfing Haushalt listings, Bezirk publications). New PDF links
  (same registrable domain) are downloaded (≤15 MB), text-extracted with `pypdf` (first 12 pages,
  ≤20,000 chars), at most 5 new PDFs per source per cycle. `published_at` from PDF metadata when
  present, so the 60-day freshness window still applies.

### 3.4 Cadence

Collection runs **daily** (05:00 UTC). The **first run backfills 60 days** (the template's freshness
window) so the questions have evidence on day one. Low-frequency structural pages are diffed daily,
which costs nothing when the hash is unchanged.

## 4. Pipeline

`collect → extract → analyse (embed, stories, score) → judge → network → trends`, daily;
**Lagebericht** weekly. Stages stay separately callable and idempotent.

### 4.1 Extract (per new item)

The template's schema with: `consequence` instead of `economic_materiality`; `forums`, `programmes`,
`offices` instead of `projects`; and `relations: [{a, b, relation, quote}]` where `relation ∈
{funding, commissioning, membership, coordination, supervision, cooperation, consultation, transfer}`.
The prompt is rewritten for the Caritas domain: what counts as a signal (decisions, budgets, mandates,
staffing, service changes, rules, funding calls, controversy around social provision in the county or
upstream levels that bind it); what does not (sport, culture listings, police blotter, tourism,
generic church services). Event/deadline extraction unchanged.

### 4.2 Judge — the 15 monitoring questions

`data/questions.yaml` holds the report's 15 standing questions verbatim (DE/EN), each with its driver,
"evidence for the concern" and "evidence against / stabilising" from the report:

q01 municipal discretionary capacity · q02 Kreis-/Bezirksumlage crowding out · q03 Sozialraumlotsen
into regular governance before grant expiry · q04 coordination formalised vs personal · q05 2026
political change · q06 skilled-worker scarcity as capacity constraint · q07 demand outgrowing supply ·
q08 mobility barriers · q09 youth/family needs shifting · q10 church restructuring · q11 provider
consolidation · q12 next funding cliff · q13 shared data vs separate platforms · q14 local legitimacy
of preventive coordination · q15 which peer models survived project funding.

For each founding signal with `regional_relevance ≥ 0.3` (or layer `vergleich`/`bund`/`freistaat`)
not yet judged by the current judge model: batches of 10 signals per call. The model returns, per
signal, only the questions the signal genuinely bears on (empty allowed):
`{signal_id, question_id, direction: for|against, strength: weak|moderate|strong, quote,
rationale_de, rationale_en}`.

**Provenance (build-enforced):** `signal_id` must be in the batch, `question_id` must exist, and
`quote` must be a verbatim substring (whitespace-normalised) of that signal's headline, summary or
source item text. Invalid judgements are dropped and counted; a batch with a wrong-shape payload is
retried once.

**Balance** per question, per ISO week: `net_w = Σ sign × weight(strength)` (weak 1, moderate 2,
strong 3), clipped to ±3 and scaled by `n/(n+2)` (n = judgements that week), so one week's flood
cannot outweigh a strong single signal by volume alone. The running balance is
`b_w = 0.85 · b_{w−1} + net_w`, so a question with no new evidence drifts back toward zero. The UI
shows the direction with each question's own label for each side (the report's "evidence for the concern or transition" vs "evidence against / stabilising"; for q03 "for" is good news, for q01 bad), "gemischt" or "ruhig", the 12-week sparkline and the
evidence quotes, never a bare number.

### 4.3 Network

`data/network.yaml` seeds the evidence graph from the report: actors (with kind), the 14
evidence-backed edges (relation, evidence text, report footnote, confidence), the eight standing
coordination forums (convener, attendance visible?, public minutes?) and the **gaps**, above all the
missing *Caritas-Zentrum ↔ Sozialraumlotsen ↔ Landkreis ↔ municipalities* edge, plus forum unknowns.
Extracted `relations` become candidate edges with `origin = signal`; an edge with `origin = signal`
**must** carry its `signal_id` and quote (enforced). Endpoints resolve through the entity resolver;
an unresolved endpoint drops the edge.

### 4.4 Lagebericht (weekly; replaces the template's daily digest)

Scheduled **Thursday 18:00 Europe/Berlin** (ready for the Friday report), plus a manual trigger.
One Opus-class call over: the week's founding signals ranked by score (cap 80), the per-question
movement with candidate judgement ids, the next 30 days of events/deadlines (seeded and extracted),
new edges, trend movers and a source-health summary. Output (DE and EN):

```
lead_de, lead_en                                   # 3–4 sentences: what moved this week
questions: [{question_id, movement, note_de, note_en, judgement_ids[]}]
sections:  [{layer, items: [{signal_id, note_de, note_en}]}]
chains:    [{title_de, title_en, signal_ids[]}]
watch:     [{event_id, why_de, why_en}]
friday_de, friday_en                               # the 2–3 paragraph update to the Caritas contact
friday_signal_ids: [..]                            # what the Friday note rests on
```

Provenance validator (template's, extended): every signal/event/judgement/question id must exist in
the input; `friday_signal_ids` non-empty; Friday note 2–4 paragraphs. One retry with the errors,
then the stage fails without failing the cycle. The UI shows the Friday note with a copy button and
the cited signals underneath.

### 4.5 Calendar

`data/calendar.yaml` seeds the report's scheduled dates and watch windows: Waakirchen Gemeinderat
13 Oct / 10 Nov / 8 Dec 2026; BergBus season end 25 Oct 2026; PflegesoNah deadline 31 Oct 2026;
Landkreis and municipal 2027 budget cycle Nov 2026–Mar 2027 (window); Bezirk 2027 budget/
Bezirksumlage Nov–Dec 2026 (window); SeLA rolling; Landtag calendar through 2027; SGB II stage two
1 Aug 2027. Events gain `origin (report|signal)`, `kind (event|deadline|window)` and a nullable
`signal_id`.

## 5. Data model changes (vs template)

- `signals.economic_materiality` → `consequence`.
- `sources`: `query` (text), `snapshot_text` (text), `snapshot_hash`.
- `feed_items`: `title_key` (normalised headline, indexed) for query dedup.
- `events`: `signal_id` nullable, `origin`, `kind`, `note_de`, `note_en`.
- new `questions` (id, title_de/en, driver, concern_de/en, stabilising_de/en, sort).
- new `judgements` (id, signal_id, question_id, direction, strength, weight, quote, rationale_de/en,
  model, created_at; unique (signal_id, question_id, model)).
- new `edges` (id, a_entity_id, b_entity_id, relation, origin, signal_id nullable, evidence, quote,
  confidence, brief_ref, created_at) and `network_gaps` (id, title_de/en, detail_de/en, kind).
- `entities.kind` gains `forum | programme | office`; `entities.actor_kind` (authority, provider,
  forum, church, funder, programme, municipality, media, peer) for the graph.
- `digests` keeps the template table (served as the Lagebericht) plus `week` (ISO Monday), `friday_de/en`.

## 6. API (FastAPI, `/api`; template routes kept and adapted)

- `GET /api/overview` — counts, top stories, question tilt summary, next deadlines, latest report lead.
- `GET /api/questions` — the 15 with balance, 12-week series, latest evidence; `GET /api/questions/{id}`.
- `GET /api/network` — nodes (entities in graph) + edges + gaps; `GET /api/entities/{slug}` timeline.
- `GET /api/reports`, `/api/reports/latest`, `/api/reports/{id}`; `POST /api/report/run`.
- `GET /api/signals`, `/api/signals/{id}` (now with judgements and edges), `/api/events`,
  `/api/trends`, `/api/sources` (with the 17-municipality coverage grid), `POST /api/cycle/run`.

## 7. Frontend

React 19 + Vite + Tailwind v4 (template). **German default.** Seven views:

1. **Lage** (landing): the nine layer bands with the week's stories, the questions that moved,
   next deadlines.
2. **Fragen**: the 15 questions as a ledger, with tilt, sparkline and evidence for and against
   (quote + link).
3. **Netz**: the evidence graph (seeded vs extracted edges styled differently, gaps drawn as dashed
   "missing" edges and listed), with an actor panel showing the entity timeline.
4. **Lagebericht**: the weekly report as a broadsheet, plus the **Freitagsnotiz** with a copy button.
5. **Signale**: filterable table (template).
6. **Kalender**: events, deadlines and watch windows (windows as bars).
7. **Quellen**: coverage incl. the 17-municipality grid (verified endpoint? items 30 d? method).

Look: typographic broadsheet like the template, palette distinct from Rhein-Neckar's river teal,
no Caritas brand marks (no flame, no Caritas red). Executed with the frontend-design skill.

## 8. Models, cost

Verified live on 2026-10-14 against `models.list` (newest: `claude-haiku-5-5` 2026-10-07,
`claude-sonnet-5-5` 2026-09-28, `claude-opus-5-5` 2026-09-21). Defaults: extraction
`claude-haiku-5-5`; judge `claude-sonnet-5-5` (it beat Opus on over-inclusion in the Szenario-Wache
comparison); Lagebericht `claude-opus-5-5`, fallback `claude-sonnet-5-5`. Each is exercised with a
structured-output call by `scripts/check_models.py` before it is shipped; the check date is written
next to the defaults. Caps: `MAX_EXTRACTIONS_PER_CYCLE=600`, judge only above the relevance floor.

## 9. Testing

Template tests are ported. New tests, each written against a plausible wrong implementation:

- query: a Google-News item whose headline matches a stored direct item becomes `also_seen_in`, not a
  row; the outlet suffix is split; two different headlines both store.
- diff: first sight stores a baseline and emits nothing; unchanged hash emits nothing; a change emits
  one item containing the added line and the removed line but not unchanged lines.
- pdf: only PDF links on the allowed domain; ≤5 per cycle; an already-seen PDF URL is not refetched.
- judge validator: unknown question id rejected; signal id outside the batch rejected; a quote not in
  the signal text rejected; a valid judgement passes.
- balance: no evidence → |b| decays; ten weak concern judgements in one week cannot exceed the cap;
  sign follows direction.
- network: an `origin=signal` edge without `signal_id` is refused; unresolved endpoint drops the edge;
  seeded edges load with `origin=report`.
- report validator: unknown judgement id rejected; empty `friday_signal_ids` rejected; one-paragraph
  Friday note rejected.
- calendar: a seeded window loads with no signal; extracted deadline still stored separately from start.
- mock end-to-end cycle over fixtures writes signals, judgements and a report.

Verification before completion: mock cycle; live source check against the real catalogue; one live
cycle with the 60-day backfill; then the deployed URL is smoke-tested in a browser.

## 10. Deployment

New Railway project `caritas-scanner`: `web` (repo Dockerfile, as the template) + `postgres`
(`pgvector/pgvector:pg16`, volume). Pre-deploy: `alembic upgrade head && python scripts/load_sources.py`.
`APP_PASSWORD` (set on the service, never in the repo). The Anthropic key is set by Nicklas with a `! railway variable set` command
(auto mode blocks secret writes). Local Postgres on host port **5441** (5438 is the Rhein-Neckar
scanner's).

## 11. Decisions made in this build (for review)

1. Fork, not generalise (a config-driven multi-region engine is the right move once there is a third
   regional scanner).
2. Fifteen monitoring questions, not thirteen: the report lists fifteen.
3. Weekly Lagebericht on Thursday evening instead of a daily digest; collection stays daily.
4. Google News RSS as the "wider local net": an uncontracted public endpoint; Coverage shows its
   yield honestly, and the direct sources do not depend on it.
5. Offices tracked, persons not.
6. Working name "Horizont-Scanner Landkreis Miesbach"; no Caritas branding.
