export type Lang = "en" | "de";
export type Layer = "gemeinden" | "landkreis" | "wohlfahrt" | "kirche" | "bezirk" | "freistaat" | "bund" | "medien" | "vergleich";

export const LAYERS: Layer[] = ["gemeinden", "landkreis", "wohlfahrt", "kirche", "bezirk", "freistaat", "bund", "medien", "vergleich"];

export const LAYER_COLOR: Record<Layer, string> = {
  gemeinden: "#4a5e8a",
  landkreis: "#2f5d50",
  wohlfahrt: "#5e7f3f",
  kirche: "#6e4a8a",
  bezirk: "#8a6a2a",
  freistaat: "#3d6b8a",
  bund: "#5a5f66",
  medien: "#9a4b3b",
  vergleich: "#7a7468",
};

export interface Label {
  en: string;
  de: string;
}

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
}

export interface EntityBrief {
  id: string;
  slug: string;
  kind: string;
  name: string;
  seeded: boolean;
  count_30d?: number;
  count_90d?: number;
}

export interface EventOut {
  id: string;
  name: string;
  organizer: string | null;
  location: string | null;
  start_date: string | null;
  end_date: string | null;
  deadline: string | null;
  topic: string | null;
  registration_url: string | null;
  funding_program: string | null;
  target_audience: string | null;
  signal_id: string;
  signal?: { id: string; headline_en: string; headline_de: string; layer: Layer | null; url: string | null };
}

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
  digest_ok: boolean | null;
  error: string | null;
}

export interface Meta {
  mode: "live" | "mock";
  extraction_model: string;
  digest_model: string;
  embedding_model: string;
  languages: Lang[];
  layers: Record<Layer, Label>;
  topics: Record<string, Label>;
  signal_types: Record<string, Label>;
  last_cycle: CycleOut | null;
  cycle_hour_utc: number;
}

export interface Overview {
  last_cycle: CycleOut | null;
  top_stories: Signal[];
  layers: { layer: Layer; count_7d: number; count_30d: number }[];
  next_events: EventOut[];
  latest_digest: { id: string; lead_en: string; lead_de: string; created_at: string; model: string } | null;
  movers: Mover[];
  totals: { signals: number; stories: number; items: number; sources_collected: number };
}

export interface DigestFull {
  id: string;
  created_at: string;
  model: string;
  lead_en: string;
  lead_de: string;
  sections: { layer: Layer; items: { signal: Signal | null; note_en: string; note_de: string }[] }[];
  chains: { title_en: string; title_de: string; signals: Signal[] }[];
  watch: { event: EventOut | null; why_en: string; why_de: string }[];
}

export interface SourceOut {
  id: string;
  slug: string;
  name: string;
  layer: Layer;
  authority: string;
  scope: string;
  places: string[];
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
  signals_7d: number;
}

export interface TrendCell {
  week: string;
  topic: string;
  layer: Layer;
  count: number;
}
