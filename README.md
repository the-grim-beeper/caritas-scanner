# Horizont-Scanner Landkreis Miesbach

Ein Horizont-Scanner für soziale Versorgung im Landkreis Miesbach, gebaut für das
Caritas-Zentrum Miesbach im Rahmen der TUM Strategic Foresight Clinic (Team 1). Er dient der
Leitfrage des Projekts: *Wie kann eine interkommunale Struktur für soziale Versorgung im
Landkreis – die „Interkommunalen Sozialraumlotsen“ – so gestaltet und verankert werden, dass
sie 2035 und 2040 noch trägt?* Der Scanner verdichtet, was sich dafür bewegt, zu wenigen
belegten Erkenntnissen pro Woche. „Bewegung“ heißt hier: Mandate, Geld, Personal, Regeln und
Legitimität rund um soziale Versorgung – nicht allgemeine Lokalnachrichten. Deutsch zuerst;
die Oberfläche lässt sich auf Englisch umschalten.

**Live:** https://web-production-3e84e.up.railway.app — das Passwort wird separat mitgeteilt.

## Was er tut

- **Neun Ebenen.** Gemeinden · Landkreis & Dienste · Wohlfahrt & Zivilgesellschaft · Kirche ·
  Bezirk Oberbayern · Freistaat Bayern · Bund · Medien & Forschung · Vergleichsfälle. Jede
  Quelle gehört zu genau einer (`backend/mhs/vocab.py`).
- **Quellen: geprüft, nicht geglaubt.** Der Katalog `data/sources.yaml` umfasst 168 Quellen;
  155 davon waren bei der Live-Prüfung vom 14. Oktober 2026 erreichbar (`checked_at` in
  `data/sources-live.json`; was nicht erreichbar war, steht mit Grund in
  `data/sources-check-report.json`). Gesammelt wird nur, was die Prüfung bestanden hat.
  Newsletter, APIs und soziale Medien sind katalogisiert, werden aber nicht gesammelt.
- **Sammeln** mit fünf Methoden: `rss` (Feeds), `page` (Listen-Seiten), `query`
  (Google-News-Suche), `diff` (Strukturseiten – gemeldet wird die Änderung gegenüber dem
  letzten Stand), `pdf` (PDF-Links auf Listen-Seiten, z. B. Sitzungsvorlagen). Kanonische URL
  und Inhalts-Hash verhindern Doppelungen; was beim ersten Sehen älter als 60 Tage ist, gilt
  als Archiv.
- **Extraktion.** Ein Modellaufruf pro Eintrag mit strukturierter Ausgabe: Schlagzeile und
  Zusammenfassung (DE/EN), Signaltyp, Themen aus festem Vokabular, Orte, Organisationen,
  Gremien, Programme und Ämter, Termine und Fristen, Beziehungen mit Zitat. Ein Signal ist nie
  später datiert als sein Eintrag gesammelt wurde.
- **Analyse.** Lokale Embeddings, Stories (dieselbe Entwicklung aus mehreren Quellen zählt
  einmal, mit Bestätigungen), Score, Trends nach Thema × Ebene × Woche.
- **15 Beobachtungsfragen** (`data/questions.yaml`, aus dem Brief). Jedes Signal wird gegen
  die Fragen gelesen; eine Einschätzung wird nur gespeichert, wenn ihr Zitat wörtlich in einem
  Text dieses Signals steht (`backend/mhs/questions/validate.py`). Paraphrasen und
  Übersetzungen fallen heraus.
- **Evidenznetz.** Finanzierung, Beauftragung, Mitgliedschaft, Koordination, Aufsicht,
  Kooperation – gesät aus dem Brief (`data/network.yaml`), erweitert um Beziehungen, die die
  Extraktion mit Zitat belegt (`backend/mhs/network/resolve.py`).
- **Kalender.** Termine und Beobachtungsfenster aus dem Brief (`data/calendar.yaml`) plus
  extrahierte Termine und Fristen; Fristen bleiben von Terminen getrennt.
- **Wöchentlicher Lagebericht**, donnerstags 18:00 (Europe/Berlin), mit der Freitagsnotiz –
  dem wöchentlichen schriftlichen Update des Teams an das Caritas-Zentrum. Der Bericht darf nur
  Signale zitieren, die ihm übergeben wurden; ein Validator prüft das.
- **Sich selbst pflegende Quellen.** Montags 06:00 (Europe/Berlin) schlägt ein Modell mit
  Websuche neue Quellen vor; jede wird live geprüft. Vorschläge werden nach 7 Tagen
  übernommen, sofern niemand sie ablehnt (Ansicht *Quellen*).
- **Täglicher Zyklus**, 05:00 UTC: fällige Vorschläge übernehmen → sammeln → extrahieren →
  analysieren → Fragen beurteilen → Netz → Trends. Es läuft immer nur ein Zyklus und ein
  Lagebericht zugleich, ob aus der Oberfläche, dem Scheduler oder der Kommandozeile gestartet
  (Postgres-Advisory-Lock, `backend/mhs/cycle.py`).

Ansichten: Lage · Fragen · Netz · Lagebericht · Signale · Kalender · Quellen.

Ohne `ANTHROPIC_API_KEY` läuft die ganze Pipeline auf einem deterministischen Mock
(Stichwort-Vokabular + Entitätenverzeichnis); die Oberfläche zeigt dann ein **Mock**-Abzeichen.

## Modelle

Modell-IDs stehen ausschließlich in `backend/mhs/config.py` (Extraktion, Fragen-Richter,
Lagebericht mit Ersatzmodell, Quellenvorschläge mit Websuche-Werkzeug), zuletzt am
14. Oktober 2026 gegen die Modellliste und mit je einem echten Aufruf geprüft. Vor jeder
Änderung erneut prüfen:

```bash
cd backend && .venv/bin/python scripts/check_models.py
```

## Lokal

```bash
docker compose up -d                                   # Postgres (pgvector) auf :5441
cd backend
python3.12 -m venv .venv && .venv/bin/pip install -e ".[test]"
cp .env.example .env                                   # ohne ANTHROPIC_API_KEY: Mock-Modus
.venv/bin/alembic upgrade head
.venv/bin/python scripts/check_sources.py              # Katalog live prüfen → data/sources-live.json
.venv/bin/python scripts/load_sources.py               # Katalog ∩ Live-Ergebnis, Entitäten, Netz, Kalender, Fragen
.venv/bin/python scripts/run_cycle.py                  # ein Tageszyklus
.venv/bin/python scripts/run_cycle.py --report         # den Wochen-Lagebericht schreiben
.venv/bin/uvicorn mhs.main:app --reload --port 8471    # API + gebaute Oberfläche
cd ../frontend && npm install && npm run dev           # :3001, leitet /api an :8471 weiter
```

`backend/.env` (siehe `.env.example`): `DATABASE_URL`, `ANTHROPIC_API_KEY`, `APP_PASSWORD`,
`SECRET_KEY`, `SCHEDULER_ENABLED`, `CYCLE_HOUR_UTC`, optional `MAX_EXTRACTIONS_PER_CYCLE`.

## Tests

```bash
cd backend && .venv/bin/python -m pytest -q            # braucht das lokale Postgres auf :5441
cd frontend && npm run build && npm run lint
```

Die Tests legen ihre eigene Datenbank `mhs_test` an und laufen immer im Mock-Modus: ein
Schlüssel in `backend/.env` kann sie nicht live schalten, sie kosten nie Geld. Die meisten
Tests benennen die falsche Implementierung, gegen die sie schützen („Wrong: …“).

## Deploy

Railway-Projekt `caritas-scanner`: der Dienst `web` (Dockerfile: Vite-Build → Python mit
vorgeladenem Embedding-Modell) und ein Postgres-Dienst (`pgvector/pgvector:pg16` mit Volume).
Deployt wird mit `railway up` aus einem sauberen Abzug des committeten Stands, nicht aus dem
Arbeitsverzeichnis – etwa so, im verknüpften Repo-Verzeichnis:

```bash
snap=$(mktemp -d) && git archive HEAD | tar -x -C "$snap"
railway up "$snap" --path-as-root --service web --detach
```

Beim Start führt `backend/scripts/start.sh` aus:

1. `scripts/reset_if_empty.py` – ein No-op, außer `RESET_EMPTY_SCHEMA=yes` ist gesetzt **und**
   die Datenbank enthält kein einziges Signal (einmalig für die erste Produktionsdatenbank
   genutzt; die Variable ist wieder entfernt);
2. `alembic upgrade head`;
3. `scripts/load_sources.py` (idempotent);

dann `uvicorn`. **Ab jetzt braucht jede Schemaänderung eine eigene Alembic-Migration (ab
`0002`)**: `0001_initial` baut die Tabellen aus den Modellen und läuft auf der
Produktionsdatenbank nicht noch einmal.

## Unterlagen

- Brief: `docs/brief/source-architecture.pdf` (mit Text- und Linkliste daneben)
- Design: `docs/superpowers/specs/2026-10-14-caritas-scanner-design.md`
- Umsetzungsplan: `docs/superpowers/plans/2026-10-14-caritas-scanner.md`
