import { createContext, useContext } from "react";
import type { Lang } from "./types";

const STRINGS = {
  // masthead / nav
  app_title: { de: "Horizont-Scanner Landkreis Miesbach", en: "Horizon Scanner Landkreis Miesbach" },
  app_short: { de: "Horizont-Scanner Miesbach", en: "Horizon Scanner Miesbach" },
  app_sub: {
    de: "Soziale Versorgung im Landkreis: was sich bewegt, wer mit wem, welche Fristen kommen",
    en: "Social provision in the county: what is moving, who works with whom, which deadlines are coming",
  },
  nav_lage: { de: "Lage", en: "Overview" },
  nav_fragen: { de: "Fragen", en: "Questions" },
  nav_netz: { de: "Netz", en: "Network" },
  nav_bericht: { de: "Lagebericht", en: "Weekly report" },
  nav_signale: { de: "Signale", en: "Signals" },
  nav_kalender: { de: "Kalender", en: "Calendar" },
  nav_quellen: { de: "Quellen", en: "Sources" },
  mode_mock: { de: "Testbetrieb", en: "Mock mode" },
  mode_live: { de: "Live", en: "Live" },
  mode_mock_hint: {
    de: "Kein API-Schlüssel gesetzt: Auswertung, Fragen und Lagebericht sind regelbasierte Platzhalter, keine Analyse.",
    en: "No API key set: extraction, questions and report are rule-based placeholders, not analysis.",
  },
  password: { de: "Passwort", en: "Password" },
  sign_in: { de: "Anmelden", en: "Sign in" },
  wrong_password: { de: "Das Passwort stimmt nicht.", en: "That password is not right." },
  loading: { de: "Lädt …", en: "Loading …" },
  error: { de: "Diese Ansicht konnte nicht geladen werden.", en: "Could not load this view." },
  retry: { de: "Erneut versuchen", en: "Try again" },
  none_yet: {
    de: "Noch nichts gesammelt. Ein Zyklus sammelt und wertet die Quellen aus.",
    en: "Nothing collected yet. A cycle collects and reads the sources.",
  },
  none_week: { de: "Noch keine Belege diese Woche.", en: "No evidence yet this week." },
  week_short: { de: "KW", en: "Week" },
  last_cycle: { de: "Letzter Zyklus", en: "Last cycle" },
  from_report: { de: "aus dem Bericht", en: "from the report" },
  from_signal: { de: "aus einem Signal", en: "from a signal" },
  footnote: { de: "Fn.", en: "fn." },
  back: { de: "Zurück", en: "Back" },
  open: { de: "Quelle öffnen", en: "Open source" },
  all: { de: "Alle", en: "All" },
  yes: { de: "ja", en: "yes" },
  no: { de: "nein", en: "no" },

  // score glyph
  score: { de: "Score", en: "Score" },
  factors: { de: "Score-Faktoren", en: "Score factors" },
  f_authority: { de: "Autorität", en: "Authority" },
  f_regional_relevance: { de: "Regionalbezug", en: "Regional relevance" },
  f_novelty: { de: "Neuheit", en: "Novelty" },
  f_consequence: { de: "Tragweite", en: "Consequence" },
  f_forward_lag: { de: "Vorlauf", en: "Forward lag" },

  // signal row
  corroborations: { de: "Bestätigungen", en: "corroborations" },
  sources_n: { de: "Quellen", en: "sources" },
  confidence: { de: "Konfidenz", en: "Confidence" },
  original: { de: "Originaltitel", en: "Original title" },
  topics: { de: "Themen", en: "Topics" },
  actors: { de: "Akteure", en: "Actors" },
  story_members: { de: "Berichtet von", en: "Reported by" },
  founder: { de: "zuerst", en: "first" },
  bears_on: { de: "Belegt für die Fragen", en: "Evidence for the questions" },
  relations_seen: { de: "Beziehungen in dieser Meldung", en: "Relations in this item" },

  // Lage
  lage_layers: { de: "Die neun Ebenen diese Woche", en: "The nine layers this week" },
  lage_layers_hint: { de: "nach Score, höchster zuerst", en: "by score, highest first" },
  lage_fallback_30: { de: "Diese Woche nichts Neues; die stärksten der letzten 30 Tage", en: "Nothing new this week; the strongest of the last 30 days" },
  more_in_layer: { de: "Alle Signale dieser Ebene", en: "All signals in this layer" },
  moving: { de: "Fragen in Bewegung", en: "Questions on the move" },
  moving_none: { de: "Keine der 15 Fragen hat sich in den letzten vier Wochen bewegt.", en: "None of the 15 questions moved in the last four weeks." },
  all_questions: { de: "Alle 15 Fragen", en: "All 15 questions" },
  next_dates: { de: "Nächste Fristen und Termine", en: "Next deadlines and dates" },
  report_lead: { de: "Aus dem Lagebericht", en: "From the weekly report" },
  read_report: { de: "Lagebericht lesen", en: "Read the report" },
  run_cycle: { de: "Zyklus jetzt starten", en: "Run a cycle now" },
  cycle_started: { de: "Zyklus gestartet. Das dauert einige Minuten; danach neu laden.", en: "Cycle started. It takes a few minutes; reload afterwards." },
  cycle_running: { de: "Ein Zyklus läuft bereits.", en: "A cycle is already running." },
  items_fetched: { de: "Einträge geholt", en: "items fetched" },
  new_items: { de: "neu", en: "new" },
  signals_n: { de: "Signale", en: "signals" },
  judgements_n: { de: "Bewertungen", en: "judgements" },
  no_cycle: { de: "Noch kein Zyklus gelaufen.", en: "No cycle has run yet." },
  layer_counts: { de: "{a} in 7 Tagen, {b} in 30 Tagen", en: "{a} in 7 days, {b} in 30 days" },

  // movement
  mv_mixed: { de: "gemischt", en: "mixed" },
  mv_quiet: { de: "ruhig", en: "quiet" },
  st_weak: { de: "schwach", en: "weak" },
  st_moderate: { de: "mittel", en: "moderate" },
  st_strong: { de: "stark", en: "strong" },

  // Fragen
  q_lead: {
    de: "Die fünfzehn Beobachtungsfragen des Berichts. Jede Seite hat ihr eigenes Etikett: ob „dafür“ gute oder schlechte Nachricht ist, hängt von der Frage ab.",
    en: "The report's fifteen monitoring questions. Each side carries its own label: whether “for” is good or bad news depends on the question.",
  },
  q_no: { de: "Nr.", en: "No." },
  q_question: { de: "Frage", en: "Question" },
  q_tilt: { de: "Neigung", en: "Tilt" },
  q_weeks: { de: "12 Wochen", en: "12 weeks" },
  q_evidence: { de: "Belege", en: "Evidence" },
  q_of: { de: "Frage {n} von 15", en: "Question {n} of 15" },
  q_counts_title: { de: "Belege dafür / dagegen", en: "Evidence for / against" },
  q_counts: { de: "{f} dafür, {a} dagegen", en: "{f} for, {a} against" },
  q_n_for: { de: "{n} dafür", en: "{n} for" },
  q_n_against: { de: "{n} dagegen", en: "{n} against" },
  q_what_counts: { de: "Was als Beleg zählt", en: "What counts as evidence" },
  q_where: { de: "Wo das sichtbar wird", en: "Where it shows up" },
  q_driver: { de: "Treiber", en: "Driver" },
  q_no_evidence: { de: "Noch keine Belege.", en: "No evidence yet." },
  q_balance_hint: {
    de: "Wöchentliche Bilanz der Belege; ohne neue Belege klingt sie ab.",
    en: "Weekly balance of the evidence; without new evidence it decays.",
  },
  q_all: { de: "Alle Fragen", en: "All questions" },
  q_none: { de: "Die Fragen sind noch nicht geladen. Sobald der Bewerter gelaufen ist, erscheinen sie hier.", en: "The questions are not loaded yet. They appear once the judge has run." },
  q_movement_4w: { de: "Bewegung, 4 Wochen", en: "Movement, 4 weeks" },

  // Netz
  net_lead: {
    de: "Belegte Beziehungen zwischen Akteuren. Durchgezogen: aus dem Bericht. Strich-Punkt: aus einer Meldung. Gestrichelt: eine Verbindung, die fehlt.",
    en: "Evidenced relations between actors. Solid: from the report. Dash-dot: from a news item. Dashed: a link that is missing.",
  },
  net_edge_report: { de: "Beziehung aus dem Bericht", en: "Relation from the report" },
  net_edge_signal: { de: "Beziehung aus einer Meldung", en: "Relation from a news item" },
  net_edge_missing: { de: "Fehlende Verbindung (nicht öffentlich belegt)", en: "Missing link (not publicly evidenced)" },
  net_missing: { de: "fehlt", en: "missing" },
  net_pick: { de: "Einen Akteur im Netz anklicken, um seine Verbindungen und Meldungen zu sehen.", en: "Click an actor to see its links and news items." },
  net_links: { de: "Verbindungen", en: "Links" },
  net_no_links: { de: "Keine belegten Verbindungen.", en: "No evidenced links." },
  net_timeline: { de: "Meldungen", en: "News items" },
  net_no_timeline: { de: "Noch keine Meldungen zu diesem Akteur.", en: "No news items about this actor yet." },
  net_gaps_of: { de: "Offene Fragen", en: "Open questions" },
  net_forums: { de: "Gremien", en: "Standing forums" },
  net_forum: { de: "Gremium", en: "Forum" },
  net_convener: { de: "Einberufen von", en: "Convened by" },
  net_attendance: { de: "Teilnahme sichtbar", en: "Attendance visible" },
  net_minutes: { de: "Öffentliche Protokolle", en: "Public minutes" },
  net_treatment: { de: "Umgang im Scanner", en: "How the scanner treats it" },
  net_gaps: { de: "Lücken", en: "Gaps" },
  net_gaps_lead: {
    de: "Was der Bericht nicht öffentlich belegen konnte. Das sind Fragen für Gespräche, keine Fakten zum Nachtragen.",
    en: "What the report could not evidence publicly. These are questions for interviews, not facts to backfill.",
  },
  net_close: { de: "Auswahl aufheben", en: "Clear selection" },
  net_empty: { de: "Das Netz ist noch leer. Es wird beim Laden der Stammdaten angelegt.", en: "The network is empty. It is created when the seed data is loaded." },
  net_discovered: { de: "entdeckt", en: "discovered" },
  net_seeded: { de: "aus dem Bericht", en: "from the report" },
  net_n_items: { de: "{n} Meldungen in 30 Tagen", en: "{n} items in 30 days" },
  gap_missing_edge: { de: "Fehlende Verbindung", en: "Missing link" },
  gap_not_found: { de: "Nicht gefunden", en: "Not found" },
  gap_interview: { de: "Für Gespräche", en: "For interviews" },

  // Lagebericht
  rep_title: { de: "Lagebericht", en: "Weekly report" },
  rep_archive: { de: "Frühere Lageberichte", en: "Earlier reports" },
  rep_none: {
    de: "Noch kein Lagebericht. Er entsteht donnerstags um 18 Uhr aus den Signalen der Woche, oder jetzt per Knopfdruck.",
    en: "No report yet. It is written on Thursdays at 18:00 from the week's signals, or now on demand.",
  },
  rep_archive_empty: { de: "Keine früheren Lageberichte.", en: "No earlier reports." },
  rep_run: { de: "Lagebericht jetzt erstellen", en: "Write the report now" },
  rep_running: { de: "Wird erstellt, das kann eine Minute dauern …", en: "Writing, this can take a minute …" },
  rep_no_signals: { de: "Kein Bericht erstellt: in den letzten 7 Tagen gab es keine neuen Signale.", en: "No report written: there were no new signals in the last 7 days." },
  rep_written_by: { de: "verfasst von", en: "written by" },
  rep_questions: { de: "Die Fragen diese Woche", en: "The questions this week" },
  rep_chains: { de: "Ketten über Ebenen", en: "Chains across layers" },
  rep_chains_hint: { de: "Wo eine Entwicklung die nächste speist.", en: "Where one development feeds the next." },
  rep_watch: { de: "Im Blick behalten", en: "Watch" },
  friday: { de: "Freitagsnotiz", en: "Friday note" },
  friday_to: { de: "Wochennotiz an das Caritas-Zentrum Miesbach", en: "Weekly note to Caritas-Zentrum Miesbach" },
  friday_basis: { de: "Worauf die Notiz beruht", en: "What the note rests on" },
  copy: { de: "Kopieren", en: "Copy" },
  copied: { de: "Kopiert", en: "Copied" },
  copy_failed: { de: "Kopieren nicht möglich; Text markieren und kopieren.", en: "Could not copy; select the text and copy it." },

  // Signale
  layer: { de: "Ebene", en: "Layer" },
  type: { de: "Art", en: "Type" },
  search: { de: "Überschriften durchsuchen", en: "Search headlines" },
  min_score: { de: "Mindest-Score", en: "Min score" },
  results: { de: "Treffer", en: "results" },
  page: { de: "Seite", en: "Page" },
  prev: { de: "Zurück", en: "Previous" },
  next: { de: "Weiter", en: "Next" },
  sort_published: { de: "neueste", en: "newest" },
  sort_score: { de: "höchster Score", en: "highest score" },
  entity_filter: { de: "Akteur", en: "Actor" },

  // Kalender
  cal_lead: {
    de: "Fristen, Termine und Zeitfenster. Was aus dem Bericht stammt, ist markiert; der Rest kommt aus Meldungen.",
    en: "Deadlines, dates and watch windows. Items from the report are marked; the rest come from news items.",
  },
  cal_windows: { de: "Zeitfenster", en: "Watch windows" },
  cal_by_week: { de: "Nach Woche", en: "By week" },
  cal_today: { de: "heute", en: "today" },
  cal_deadlines_row: { de: "Fristen", en: "Deadlines" },
  events_row: { de: "Termine", en: "Dates" },
  deadline: { de: "Frist", en: "Deadline" },
  event: { de: "Termin", en: "Date" },
  window: { de: "Zeitfenster", en: "Window" },
  window_starts: { de: "beginnt", en: "starts" },
  window_ends: { de: "endet", en: "ends" },
  running: { de: "läuft", en: "running" },
  until: { de: "bis", en: "until" },
  programme: { de: "Programm", en: "Programme" },
  register: { de: "Anmeldung", en: "Registration" },
  no_events: { de: "Keine datierten Termine oder Fristen in diesem Zeitraum.", en: "No dated events or deadlines in this period." },

  // Quellen
  src_lead: {
    de: "Jede katalogisierte Quelle, ob sie gesammelt wird und was sie lieferte.",
    en: "Every catalogued source, whether it is collected and what it produced.",
  },
  src_collected: { de: "gesammelt", en: "collected" },
  src_not_collected: { de: "nicht gesammelt", en: "not collected" },
  src_of_collected: { de: "{a} von {b} Quellen werden gesammelt", en: "{a} of {b} sources are collected" },
  src_municipalities: { de: "Die 17 Gemeinden", en: "The 17 municipalities" },
  src_municipalities_hint: {
    de: "Je Gemeinde: gesammelte Quellen, Einträge der letzten 30 Tage, Methoden.",
    en: "Per municipality: collected sources, items in the last 30 days, methods.",
  },
  src_n_sources: { de: "Quellen", en: "sources" },
  src_items_30: { de: "Einträge in 30 Tagen", en: "items in 30 days" },
  src_items_7: { de: "Einträge in 7 Tagen", en: "items in 7 days" },
  src_direct: { de: "direkte Quelle geprüft", en: "verified direct source" },
  src_query_only: { de: "nur Suchabfrage", en: "search query only" },
  src_none: { de: "keine gesammelte Quelle", en: "no collected source" },
  method: { de: "Methode", en: "Method" },
  authority: { de: "Autorität", en: "Authority" },
  status: { de: "Status", en: "Status" },
  items_7d: { de: "Einträge 7 T", en: "Items 7 d" },
  signals_7d: { de: "Signale 7 T", en: "Signals 7 d" },
  last_ok: { de: "Zuletzt OK", en: "Last OK" },
  reason: { de: "Grund", en: "Reason" },
  core: { de: "Kern", en: "core" },
  quarantined: { de: "in Quarantäne", en: "quarantined" },
  active: { de: "aktiv", en: "active" },
  models: { de: "Modelle", en: "Models" },
  cycles: { de: "Letzte Zyklen", en: "Recent cycles" },
  source: { de: "Quelle", en: "Source" },
  mode: { de: "Modus", en: "Mode" },
  result: { de: "Ergebnis", en: "Result" },

  // Vorschläge (self-updating sources, Task 9/10)
  src_suggestions: { de: "Vorschläge", en: "Suggestions" },
  src_suggestions_rule: {
    de: "Neue Quellen schlägt der Scanner wöchentlich vor. Wer nicht ablehnt, stimmt zu: nach sieben Tagen wird die Quelle nach erneuter Prüfung aufgenommen.",
    en: "The scanner proposes new sources once a week. Whoever does not decline agrees: after seven days the source is adopted, following a fresh check.",
  },
  src_suggestions_none: { de: "Derzeit keine offenen Vorschläge.", en: "No open suggestions at the moment." },
  src_suggestion_badge: { de: "Vorschlag", en: "Suggestion" },
  src_decline: { de: "Ablehnen", en: "Decline" },
  src_adopt_now: { de: "Jetzt aufnehmen", en: "Adopt now" },
  src_adopt_today: { de: "wird heute aufgenommen", en: "will be adopted today" },
  src_adopt_in_1: { de: "wird am {date} aufgenommen (1 Tag)", en: "will be adopted on {date} (1 day)" },
  src_adopt_in_n: { de: "wird am {date} aufgenommen ({n} Tage)", en: "will be adopted on {date} ({n} days)" },
  src_items_at_check: { de: "Einträge bei Prüfung", en: "items at check" },
  src_run_suggestions: { de: "Neue Vorschläge suchen", en: "Look for new suggestions" },
  src_run_running: { de: "läuft …", en: "running …" },
  src_run_busy: { de: "Es läuft bereits ein Lauf.", en: "A run is already in progress." },
  src_run_result: {
    de: "{proposed} geprüft, {pending_new} neu, {rejected} abgelehnt, {known} bekannt",
    en: "{proposed} checked, {pending_new} new, {rejected} rejected, {known} known",
  },
  src_conflict: {
    de: "Der Vorschlag wurde inzwischen bearbeitet. Bitte neu laden.",
    en: "This suggestion has already been resolved. Please reload.",
  },
  src_reverify_failed: { de: "Erneute Prüfung fehlgeschlagen", en: "Re-verification failed" },
  src_show_history: { de: "Verlauf anzeigen", en: "Show history" },
  src_hide_history: { de: "Verlauf ausblenden", en: "Hide history" },
  src_history: { de: "Verlauf", en: "History" },
  src_status_adopted: { de: "aufgenommen", en: "adopted" },
  src_status_declined: { de: "abgelehnt", en: "declined" },
  src_status_rejected: { de: "verworfen", en: "rejected" },
  src_status_failed: { de: "fehlgeschlagen", en: "failed" },
} as const;

export type Key = keyof typeof STRINGS;

export const LangContext = createContext<{ lang: Lang; setLang: (l: Lang) => void }>({ lang: "de", setLang: () => {} });

export function useLang() {
  return useContext(LangContext);
}

/** t("key") or t("key", {n: 3}) — `{n}` placeholders are filled from vars. */
export function useT() {
  const { lang } = useLang();
  return (key: Key, vars?: Record<string, string | number>) => {
    let s: string = STRINGS[key][lang];
    if (vars) for (const [k, v] of Object.entries(vars)) s = s.replace(`{${k}}`, String(v));
    return s;
  };
}

/** Pick `${base}_${lang}`, falling back to German, then English. */
export function pick(obj: object | null | undefined, base: string, lang: Lang): string {
  if (!obj) return "";
  const r = obj as Record<string, unknown>;
  const v = r[`${base}_${lang}`] || r[`${base}_de`] || r[`${base}_en`];
  return typeof v === "string" ? v : "";
}

const locale = (lang: Lang) => (lang === "de" ? "de-DE" : "en-GB");

/** Parse "2026-10-14" as a local calendar date (not UTC midnight). */
export function parseDay(iso: string): Date {
  if (/^\d{4}-\d{2}-\d{2}$/.test(iso)) {
    const [y, m, d] = iso.split("-").map(Number);
    return new Date(y, m - 1, d);
  }
  return new Date(iso);
}

export function fmtDate(iso: string | null | undefined, lang: Lang, opts: { time?: boolean; year?: boolean; weekday?: boolean } = {}): string {
  if (!iso) return "–";
  const d = parseDay(iso);
  if (Number.isNaN(d.getTime())) return iso;
  // The year is shown when asked for, or when it is not the current one.
  const year = opts.year ?? d.getFullYear() !== new Date().getFullYear();
  return d.toLocaleDateString(locale(lang), {
    ...(opts.weekday ? { weekday: "short" } : {}),
    day: "numeric",
    month: "short",
    ...(year ? { year: "numeric" } : {}),
    ...(opts.time ? { hour: "2-digit", minute: "2-digit" } : {}),
  });
}

/** Days from today's calendar date to `iso`'s (both local); negative when it is in the past. */
export function daysUntil(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const d = parseDay(iso);
  if (Number.isNaN(d.getTime())) return null;
  const target = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  return Math.round((target - today) / 86400000);
}

export function fmtNum(v: number, lang: Lang, digits = 2): string {
  return v.toLocaleString(locale(lang), { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function dayKey(d: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

export function mondayOf(d: Date): Date {
  const m = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  m.setDate(m.getDate() - ((m.getDay() + 6) % 7));
  return m;
}

/** ISO 8601 week number. */
export function isoWeek(d: Date): { year: number; week: number } {
  const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const day = t.getUTCDay() || 7;
  t.setUTCDate(t.getUTCDate() + 4 - day);
  const y0 = new Date(Date.UTC(t.getUTCFullYear(), 0, 1));
  return { year: t.getUTCFullYear(), week: Math.ceil(((t.getTime() - y0.getTime()) / 86400000 + 1) / 7) };
}

/** "KW 42 · 12.–18. Okt. 2026" for the week containing `d`. */
export function weekLabel(d: Date, lang: Lang): { kw: string; range: string } {
  const mon = mondayOf(d);
  const sun = new Date(mon);
  sun.setDate(mon.getDate() + 6);
  const { week } = isoWeek(mon);
  const sameMonth = mon.getMonth() === sun.getMonth();
  const loc = locale(lang);
  const end = sun.toLocaleDateString(loc, { day: "numeric", month: "long", year: "numeric" });
  const start = sameMonth
    ? mon.toLocaleDateString(loc, { day: "numeric" }) + (lang === "de" ? "." : "")
    : mon.toLocaleDateString(loc, { day: "numeric", month: "long" });
  return { kw: `${lang === "de" ? "KW" : "Week"} ${week}`, range: `${start}–${end}` };
}

/** Quotation marks per language. */
export function quoted(s: string, lang: Lang): string {
  return lang === "de" ? `„${s}“` : `“${s}”`;
}
