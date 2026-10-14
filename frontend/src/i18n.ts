import { createContext, useContext } from "react";
import type { Lang } from "./types";

const STRINGS = {
  // masthead / nav
  app_title: { en: "Horizon Scanner Landkreis Miesbach", de: "Horizont-Scanner Landkreis Miesbach" },
  app_sub: { en: "Horizon scanner for social provision in Landkreis Miesbach", de: "Horizont-Scanner für die soziale Versorgung im Landkreis Miesbach" },
  nav_radar: { en: "Radar", de: "Radar" },
  nav_digest: { en: "Digest", de: "Lagebild" },
  nav_signals: { en: "Signals", de: "Signale" },
  nav_watchlist: { en: "Watchlist", de: "Beobachtungsliste" },
  nav_calendar: { en: "Calendar", de: "Kalender" },
  nav_coverage: { en: "Coverage", de: "Abdeckung" },
  mode_mock: { en: "Mock", de: "Mock" },
  mode_live: { en: "Live", de: "Live" },
  mode_mock_hint: {
    en: "No API key set: extraction and digest are rule-based placeholders, not analysis.",
    de: "Kein API-Schlüssel gesetzt: Extraktion und Lagebild sind regelbasierte Platzhalter, keine Analyse.",
  },
  sign_in: { en: "Sign in", de: "Anmelden" },
  password: { en: "Password", de: "Passwort" },
  wrong_password: { en: "That password is not right.", de: "Das Passwort stimmt nicht." },
  loading: { en: "Loading…", de: "Lädt…" },
  error: { en: "Could not load this view.", de: "Diese Ansicht konnte nicht geladen werden." },
  retry: { en: "Try again", de: "Erneut versuchen" },
  none_yet: { en: "Nothing here yet. Run a cycle to collect and extract.", de: "Noch nichts vorhanden. Zyklus starten, um zu sammeln und auszuwerten." },

  // common
  score: { en: "Score", de: "Score" },
  factors: { en: "Score factors", de: "Score-Faktoren" },
  f_authority: { en: "Authority", de: "Autorität" },
  f_regional_relevance: { en: "Regional relevance", de: "Regionalbezug" },
  f_novelty: { en: "Novelty", de: "Neuheit" },
  f_consequence: { en: "Consequence", de: "Tragweite" },
  f_forward_lag: { en: "Forward lag", de: "Vorlauf" },
  corroborations: { en: "corroborations", de: "Bestätigungen" },
  sources_n: { en: "sources", de: "Quellen" },
  confidence: { en: "Confidence", de: "Konfidenz" },
  source: { en: "Source", de: "Quelle" },
  original: { en: "Original", de: "Original" },
  published: { en: "Published", de: "Veröffentlicht" },
  topics: { en: "Topics", de: "Themen" },
  entities: { en: "Entities", de: "Entitäten" },
  type: { en: "Type", de: "Typ" },
  layer: { en: "Layer", de: "Ebene" },
  all: { en: "All", de: "Alle" },
  open: { en: "Open source", de: "Quelle öffnen" },
  story_members: { en: "Reported by", de: "Berichtet von" },
  founder: { en: "first", de: "zuerst" },
  distance: { en: "distance", de: "Distanz" },

  // radar
  radar_lead: { en: "This week across the nine layers", de: "Diese Woche über die neun Ebenen" },
  last_cycle: { en: "Last cycle", de: "Letzter Zyklus" },
  no_cycle: { en: "No cycle has run yet.", de: "Noch kein Zyklus gelaufen." },
  items_fetched: { en: "items fetched", de: "Einträge geholt" },
  new_items: { en: "new", de: "neu" },
  signals_n: { en: "signals", de: "Signale" },
  stories_n: { en: "stories", de: "Meldungen" },
  week: { en: "7 d", de: "7 T" },
  month: { en: "30 d", de: "30 T" },
  movers: { en: "Movers, 4 weeks vs previous 4", de: "Bewegung, 4 Wochen ggü. den 4 davor" },
  next_deadlines: { en: "Next deadlines and dates", de: "Nächste Fristen und Termine" },
  digest_lead: { en: "Latest digest", de: "Aktuelles Lagebild" },
  read_digest: { en: "Read the digest", de: "Lagebild lesen" },
  run_cycle: { en: "Run a cycle now", de: "Zyklus jetzt starten" },
  cycle_started: { en: "Cycle started — this takes a few minutes. Refresh later.", de: "Zyklus gestartet — dauert einige Minuten. Später neu laden." },
  cycle_running: { en: "A cycle is already running.", de: "Ein Zyklus läuft bereits." },
  ranked_by_score: { en: "ranked by score", de: "nach Score" },
  more_in_layer: { en: "all in this layer", de: "alle dieser Ebene" },

  // digest
  digest_title: { en: "Digest", de: "Lagebild" },
  digest_archive: { en: "Earlier digests", de: "Frühere Lagebilder" },
  chains: { en: "Chains across layers", de: "Ketten über Ebenen" },
  chains_hint: { en: "Where one development feeds the next — the scanner's reason to exist.", de: "Wo eine Entwicklung die nächste speist — der Zweck des Scanners." },
  watch: { en: "Watch", de: "Beobachten" },
  no_digest: { en: "No digest yet. Run a cycle first.", de: "Noch kein Lagebild. Zuerst einen Zyklus starten." },
  written_by: { en: "written by", de: "verfasst von" },
  regenerate: { en: "Regenerate digest", de: "Lagebild neu erzeugen" },

  // signals
  search: { en: "Search headlines", de: "Überschriften durchsuchen" },
  min_score: { en: "Min score", de: "Min. Score" },
  results: { en: "results", de: "Treffer" },
  page: { en: "Page", de: "Seite" },
  prev: { en: "Previous", de: "Zurück" },
  next: { en: "Next", de: "Weiter" },
  sort_published: { en: "newest", de: "neueste" },
  sort_score: { en: "highest score", de: "höchster Score" },

  // watchlist
  watch_lead: { en: "Places, projects, organisations and funds by story count", de: "Orte, Projekte, Organisationen und Fonds nach Meldungen" },
  kind_place: { en: "Places", de: "Orte" },
  kind_project: { en: "Projects", de: "Projekte" },
  kind_organisation: { en: "Organisations", de: "Organisationen" },
  kind_fund: { en: "Funds & programmes", de: "Fonds & Programme" },
  seeded: { en: "from the brief", de: "aus dem Briefing" },
  discovered: { en: "discovered", de: "entdeckt" },
  timeline: { en: "Timeline", de: "Verlauf" },
  aliases: { en: "Also written as", de: "Auch geschrieben als" },
  back: { en: "Back", de: "Zurück" },

  // calendar
  cal_lead: { en: "Events and deadlines, next 90 days", de: "Termine und Fristen, nächste 90 Tage" },
  deadline: { en: "Deadline", de: "Frist" },
  event: { en: "Event", de: "Termin" },
  organizer: { en: "Organiser", de: "Veranstalter" },
  register: { en: "Registration", de: "Anmeldung" },
  programme: { en: "Programme", de: "Programm" },
  no_events: { en: "No dated events or deadlines in this window.", de: "Keine datierten Termine oder Fristen in diesem Zeitraum." },

  // coverage
  cov_lead: { en: "Every catalogued source, whether it is collected, and what it produced in 7 days", de: "Jede katalogisierte Quelle, ob sie erfasst wird, und was sie in 7 Tagen lieferte" },
  collected: { en: "collected", de: "erfasst" },
  not_collected: { en: "not collected", de: "nicht erfasst" },
  method: { en: "Method", de: "Methode" },
  authority: { en: "Authority", de: "Autorität" },
  status: { en: "Status", de: "Status" },
  items_7d: { en: "Items 7 d", de: "Einträge 7 T" },
  signals_7d: { en: "Signals 7 d", de: "Signale 7 T" },
  last_ok: { en: "Last OK", de: "Zuletzt OK" },
  reason: { en: "Reason", de: "Grund" },
  quarantined: { en: "quarantined", de: "in Quarantäne" },
  active: { en: "active", de: "aktiv" },
  models: { en: "Models", de: "Modelle" },
  cycles: { en: "Recent cycles", de: "Letzte Zyklen" },
} as const;

export type Key = keyof typeof STRINGS;

export const LangContext = createContext<{ lang: Lang; setLang: (l: Lang) => void }>({ lang: "en", setLang: () => {} });

export function useLang() {
  return useContext(LangContext);
}

export function useT() {
  const { lang } = useLang();
  return (key: Key) => STRINGS[key][lang];
}

/** Pick `${base}_${lang}` from a bilingual record. */
export function pick(obj: object | null | undefined, base: string, lang: Lang): string {
  if (!obj) return "";
  const r = obj as Record<string, unknown>;
  const v = r[`${base}_${lang}`] ?? r[`${base}_de`] ?? r[`${base}_en`];
  return typeof v === "string" ? v : "";
}

export function fmtDate(iso: string | null | undefined, lang: Lang, withTime = false): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(lang === "de" ? "de-DE" : "en-GB", {
    day: "2-digit",
    month: "short",
    ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}),
  });
}
