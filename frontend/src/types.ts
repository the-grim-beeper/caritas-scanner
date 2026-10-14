export type Lang = "de" | "en";

// --- vocabulary (binding: backend mhs/vocab.py) ---------------------------------------------
export type Layer = "gemeinden" | "landkreis" | "wohlfahrt" | "kirche" | "bezirk" | "freistaat" | "bund" | "medien" | "vergleich";

export const LAYERS: Layer[] = ["gemeinden", "landkreis", "wohlfahrt", "kirche", "bezirk", "freistaat", "bund", "medien", "vergleich"];

/** Nine muted hues, validated as a set on the paper colour (see index.css). */
export const LAYER_COLOR: Record<Layer, string> = {
  gemeinden: "#a97416",
  landkreis: "#26652b",
  wohlfahrt: "#c26576",
  kirche: "#644395",
  bezirk: "#068fa7",
  freistaat: "#29559f",
  bund: "#7e8832",
  medien: "#8e3776",
  vergleich: "#ba673f",
};

export type Family = "struktur" | "personal" | "bedarf" | "geld" | "regeln" | "stimmung";
export const FAMILIES: Family[] = ["struktur", "personal", "bedarf", "geld", "regeln", "stimmung"];

export type EntityKind = "place" | "organisation" | "forum" | "programme" | "office";
export type ActorKind = "authority" | "provider" | "forum" | "church" | "funder" | "programme" | "media" | "peer" | "other";
export const ACTOR_KINDS: ActorKind[] = ["authority", "provider", "forum", "church", "funder", "programme", "media", "peer", "other"];

export type Relation = "funding" | "commissioning" | "membership" | "coordination" | "supervision" | "cooperation" | "consultation" | "transfer";
export type Direction = "for" | "against";
export type Movement = "for" | "against" | "mixed" | "quiet";
export type Strength = "weak" | "moderate" | "strong";
export type EventKind = "event" | "deadline" | "window";
export type Origin = "report" | "signal";

export interface Label {
  en: string;
  de: string;
}

// --- signals -----------------------------------------------------------------------------------
export interface Factors {
  authority: number;
  regional_relevance: number;
  novelty: number;
  consequence: number;
  forward_lag: number;
}

export interface StoryBrief {
  id: string;
  corroboration_count: number;
  distinct_sources: number;
  confidence: number;
  score: number;
  first_seen: string | null;
  last_seen: string | null;
  members?: StoryMember[];
}

export interface StoryMember {
  id: string;
  headline_de: string;
  headline_en: string;
  source_name: string | null;
  source_slug: string | null;
  layer: Layer | null;
  url: string | null;
  published_at: string | null;
  is_founder: boolean;
  nearest_distance: number | null;
}

export interface Signal {
  id: string;
  headline_en: string;
  headline_de: string;
  summary_en: string | null;
  summary_de: string | null;
  signal_type: string;
  layer: Layer | null;
  source_name: string | null;
  source_slug: string | null;
  authority_tier: string | null;
  url: string | null;
  original_title: string | null;
  published_at: string | null;
  score: number;
  is_founder: boolean;
  factors: Factors;
  topics: string[];
  places: string[];
  story: StoryBrief | null;
  entities?: EntityBrief[];
  events?: EventOut[];
  /** /api/signals/{id} only (Task 4/5 additions). */
  judgements?: JudgementOut[];
  edges?: NetEdge[];
}

/** The short signal shape the questions, network and report endpoints embed. */
export interface CitedSignal {
  id?: string;
  headline_de: string;
  headline_en: string;
  layer?: Layer | null;
  source_name?: string | null;
  url: string | null;
  published_at: string | null;
}

export interface EntityBrief {
  id: string;
  slug: string;
  kind: EntityKind | string;
  name: string;
  seeded: boolean;
  actor_kind?: ActorKind | null;
  count_30d?: number;
  count_90d?: number;
}

export interface EntityDetail extends EntityBrief {
  aliases: string[];
  timeline: Signal[];
  weekly: [string, number][];
}

// --- events / calendar ---------------------------------------------------------------------------
export interface EventOut {
  id: string;
  slug?: string | null;
  name: string;
  name_en?: string | null;
  kind?: EventKind;
  origin?: Origin;
  note_de?: string | null;
  note_en?: string | null;
  organizer: string | null;
  location: string | null;
  place?: string | null;
  programme?: string | null;
  start_date: string | null;
  end_date: string | null;
  deadline: string | null;
  topic: string | null;
  registration_url: string | null;
  funding_program: string | null;
  target_audience: string | null;
  brief_ref?: string | null;
  signal_id: string | null;
  signal?: { id: string; headline_en: string; headline_de: string; layer: Layer | null; url: string | null };
}

// --- questions (Task 4) --------------------------------------------------------------------------
export interface JudgementOut {
  id: string;
  question_id: string;
  direction: Direction;
  strength: Strength;
  weight: number;
  quote: string;
  rationale_de: string;
  rationale_en: string;
  model: string;
  created_at: string;
  signal: CitedSignal & { id: string };
}

export interface WeekPoint {
  week: string;
  net: number;
  balance: number;
  n: number;
}

export interface QuestionLabels {
  id: string;
  title_de: string;
  title_en: string;
  for_label_de: string;
  for_label_en: string;
  against_label_de: string;
  against_label_en: string;
}

export interface QuestionOut extends QuestionLabels {
  sort: number;
  driver_de: string;
  driver_en: string;
  balance: number;
  movement: Movement;
  series: WeekPoint[];
  counts: { for: number; against: number };
  latest: JudgementOut[];
}

export interface QuestionDetail extends QuestionOut {
  for_de: string;
  for_en: string;
  against_de: string;
  against_en: string;
  sources_de: string;
  evidence: JudgementOut[];
}

export interface QuestionMoving extends QuestionLabels {
  movement: Movement;
  balance: number;
}

// --- network (Task 5) ----------------------------------------------------------------------------
export interface NetNode {
  id: string;
  slug: string;
  name: string;
  kind: EntityKind | string;
  actor_kind: ActorKind | string | null;
  seeded: boolean;
  degree: number;
  signals_30d: number;
}

export interface NetEdge {
  id: string;
  a: string;
  b: string;
  relation: Relation | string;
  origin: Origin;
  confidence: string | null;
  evidence_de: string | null;
  evidence_en: string | null;
  quote: string | null;
  brief_ref: string | null;
  signal: (CitedSignal & { id: string }) | null;
}

export interface ForumProfile {
  slug: string;
  name: string;
  convener_de: string;
  attendance_visible: boolean;
  public_minutes: boolean;
  treatment_de: string;
  treatment_en: string;
  brief_ref: string | null;
}

export interface NetworkGap {
  id: string;
  kind: string;
  title_de: string;
  title_en: string;
  detail_de: string;
  detail_en: string;
  actor_slugs: string[];
}

export interface Network {
  nodes: NetNode[];
  edges: NetEdge[];
  forums: ForumProfile[];
  gaps: NetworkGap[];
}

// --- reports (Task 6) ----------------------------------------------------------------------------
export interface ReportBrief {
  id: string;
  week: string | null;
  created_at: string;
  model: string;
  lead_de: string;
  lead_en: string;
}

export interface ReportPayload {
  lead_de: string;
  lead_en: string;
  questions: { question_id: string; movement: Movement; note_de: string; note_en: string; judgement_ids: string[] }[];
  sections: { layer: Layer; items: { signal_id: string; note_de: string; note_en: string }[] }[];
  chains: { title_de: string; title_en: string; signal_ids: string[] }[];
  watch: { event_id: string; why_de: string; why_en: string }[];
  friday_de: string;
  friday_en: string;
  friday_signal_ids: string[];
}

export interface ReportFull extends ReportBrief, Partial<Omit<ReportPayload, "lead_de" | "lead_en">> {
  /** Some serialisations nest the model's output under `payload`. */
  payload?: Partial<ReportPayload>;
  signals?: Record<string, CitedSignal>;
  events?: Record<string, EventOut>;
  judgements?: Record<string, JudgementOut>;
}

// --- overview / meta / sources -------------------------------------------------------------------
export interface Mover {
  topic: string;
  layer: Layer;
  current: number;
  previous: number;
  delta: number;
}

export interface CycleOut {
  id: string;
  mode: "live" | "mock";
  started_at: string | null;
  finished_at: string | null;
  items_fetched: number;
  items_new: number;
  extracted: number;
  signals: number;
  stories_new: number;
  corroborations: number;
  failed_sources: number;
  judged?: number;
  judgements?: number;
  edges_new?: number;
  digest_ok: boolean | null;
  error: string | null;
}

export interface TopicLabel extends Label {
  family?: Family | string;
}

export interface Meta {
  mode: "live" | "mock";
  extraction_model: string;
  digest_model: string;
  judge_model?: string;
  embedding_model: string;
  languages: Lang[];
  layers: Partial<Record<Layer, Label>>;
  topics: Record<string, TopicLabel>;
  families?: Record<string, Label>;
  topic_family?: Record<string, string>;
  relations?: Record<string, Label>;
  signal_types: Record<string, Label>;
  last_cycle: CycleOut | null;
  cycle_hour_utc: number;
}

export interface Overview {
  last_cycle: CycleOut | null;
  top_stories: Signal[];
  layers: { layer: Layer; count_7d: number; count_30d: number }[];
  next_events: EventOut[];
  latest_digest?: { id: string; lead_en: string; lead_de: string; created_at: string; model: string } | null;
  report_lead?: { lead_de: string; lead_en: string; week: string | null; id?: string } | null;
  questions_moving?: QuestionMoving[];
  movers: Mover[];
  totals: { signals: number; stories: number; items: number; sources_collected: number };
}

export interface SourceOut {
  id: string;
  slug: string;
  name: string;
  layer: Layer;
  authority: string;
  scope: string;
  places?: string[];
  language: string;
  method: string;
  url: string | null;
  homepage: string | null;
  priority: string;
  cadence: string | null;
  notes: string | null;
  brief_ref: string | null;
  collect: boolean;
  not_collected_reason: string | null;
  items_at_check: number | null;
  status: string;
  consecutive_failures: number;
  last_fetched_at: string | null;
  last_ok_at: string | null;
  last_error: string | null;
  items_7d: number;
  items_30d?: number;
  signals_7d: number;
  /** "catalogue" (the original 168) or "suggestion" (adopted from the weekly proposal run). Older backends omit it. */
  origin?: "catalogue" | "suggestion";
}

// --- source suggestions (Task 9/10: self-updating sources) -------------------------------------
export type SuggestionStatus = "pending" | "adopted" | "declined" | "rejected" | "failed";

export interface Suggestion {
  id: string;
  name: string;
  url: string | null;
  layer: Layer;
  scope: string;
  places?: string[];
  rationale_de: string;
  rationale_en: string;
  method: string | null;
  feed_url: string | null;
  items_at_check: number | null;
  status: SuggestionStatus;
  reason: string | null;
  suggested_at: string;
  adopt_after: string | null;
  resolved_at: string | null;
  source_slug: string | null;
}

export interface SuggestionRunResult {
  proposed: number;
  pending_new: number;
  rejected: number;
  known: number;
}

export interface TrendCell {
  week: string;
  topic: string;
  layer: Layer;
  count: number;
}
