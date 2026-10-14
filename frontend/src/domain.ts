// Domain labels the UI needs even when /api/meta is older than the vocabulary.
// Source of truth: spec §2 and backend mhs/vocab.py; data/entities.yaml for names.
import type { ActorKind, Label, Lang, Layer, Meta } from "./types";

export const LAYER_LABELS: Record<Layer, Label> = {
  gemeinden: { de: "Gemeinden", en: "Municipalities" },
  landkreis: { de: "Landkreis & Dienste", en: "County & local services" },
  wohlfahrt: { de: "Wohlfahrt & Zivilgesellschaft", en: "Welfare & civil society" },
  kirche: { de: "Kirche", en: "Church" },
  bezirk: { de: "Bezirk Oberbayern", en: "District of Upper Bavaria" },
  freistaat: { de: "Freistaat Bayern", en: "State of Bavaria" },
  bund: { de: "Bund", en: "Federal" },
  medien: { de: "Medien & Forschung", en: "Media & research" },
  vergleich: { de: "Vergleichsfälle", en: "Peer cases" },
};

export function layerLabel(layer: string | null | undefined, meta: Meta | null, lang: Lang): string {
  if (!layer) return "";
  return meta?.layers?.[layer as Layer]?.[lang] ?? LAYER_LABELS[layer as Layer]?.[lang] ?? layer;
}

export const FAMILY_LABELS: Record<string, Label> = {
  struktur: { de: "Struktur", en: "Structure" },
  personal: { de: "Personal", en: "People" },
  bedarf: { de: "Bedarf & Angebot", en: "Demand & supply" },
  geld: { de: "Geld", en: "Money" },
  regeln: { de: "Regeln", en: "Rules" },
  stimmung: { de: "Stimmung", en: "Sentiment" },
};

export function topicLabel(code: string, meta: Meta | null, lang: Lang): string {
  return meta?.topics?.[code]?.[lang] ?? code;
}

/** Topic codes grouped by family, if the backend tells us the family; otherwise one group. */
export function topicGroups(meta: Meta | null, lang: Lang): { family: string | null; label: string; codes: string[] }[] {
  const topics = meta?.topics ?? {};
  const fam = (code: string): string | null => topics[code]?.family ?? meta?.topic_family?.[code] ?? null;
  const groups = new Map<string | null, string[]>();
  for (const code of Object.keys(topics)) {
    const f = fam(code);
    groups.set(f, [...(groups.get(f) ?? []), code]);
  }
  const order = ["struktur", "personal", "bedarf", "geld", "regeln", "stimmung"];
  return [...groups.entries()]
    .sort(([a], [b]) => (a === null ? 99 : order.indexOf(a)) - (b === null ? 99 : order.indexOf(b)))
    .map(([family, codes]) => ({
      family,
      label: family ? (meta?.families?.[family]?.[lang] ?? FAMILY_LABELS[family]?.[lang] ?? family) : "",
      codes,
    }));
}

export const RELATION_LABELS: Record<string, Label> = {
  funding: { de: "Förderung", en: "Funding" },
  commissioning: { de: "Beauftragung", en: "Commissioning" },
  membership: { de: "Mitgliedschaft", en: "Membership" },
  coordination: { de: "Koordination", en: "Coordination" },
  supervision: { de: "Aufsicht", en: "Supervision" },
  cooperation: { de: "Kooperation", en: "Cooperation" },
  consultation: { de: "Beratung", en: "Consultation" },
  transfer: { de: "Übergabe", en: "Transfer" },
};

export function relationLabel(rel: string, meta: Meta | null, lang: Lang): string {
  return meta?.relations?.[rel]?.[lang] ?? RELATION_LABELS[rel]?.[lang] ?? rel;
}

export const ACTOR_LABELS: Record<ActorKind, Label> = {
  authority: { de: "Behörde", en: "Authority" },
  provider: { de: "Träger & Dienste", en: "Provider" },
  forum: { de: "Gremium", en: "Forum" },
  church: { de: "Kirche", en: "Church" },
  funder: { de: "Fördergeber", en: "Funder" },
  programme: { de: "Programm", en: "Programme" },
  media: { de: "Medien", en: "Media" },
  peer: { de: "Vergleichsfall", en: "Peer case" },
  other: { de: "Sonstige", en: "Other" },
};

/** Same validated hue set as the layers, re-assigned; "other" is the neutral. */
export const ACTOR_COLOR: Record<ActorKind, string> = {
  authority: "#29559f",
  provider: "#c26576",
  forum: "#26652b",
  church: "#644395",
  funder: "#a97416",
  programme: "#068fa7",
  media: "#7e8832",
  peer: "#ba673f",
  other: "#8a877c",
};

export function actorColor(k: string | null | undefined): string {
  return ACTOR_COLOR[(k ?? "other") as ActorKind] ?? ACTOR_COLOR.other;
}

export function actorLabel(k: string | null | undefined, lang: Lang): string {
  if (!k) return ACTOR_LABELS.other[lang];
  return ACTOR_LABELS[k as ActorKind]?.[lang] ?? k;
}

export const ENTITY_KIND_LABELS: Record<string, Label> = {
  place: { de: "Ort", en: "Place" },
  organisation: { de: "Organisation", en: "Organisation" },
  forum: { de: "Gremium", en: "Forum" },
  programme: { de: "Programm", en: "Programme" },
  office: { de: "Amt", en: "Office" },
};

export const METHOD_LABELS: Record<string, Label> = {
  rss: { de: "RSS", en: "RSS" },
  page: { de: "Seite", en: "Page" },
  query: { de: "Suche", en: "Search" },
  diff: { de: "Änderung", en: "Diff" },
  pdf: { de: "PDF", en: "PDF" },
  newsletter: { de: "Newsletter", en: "Newsletter" },
  api: { de: "API", en: "API" },
  social: { de: "Social Media", en: "Social" },
};

export const COLLECTED_METHODS = ["rss", "page", "query", "diff", "pdf"];

/** The 17 municipalities (closed set), with the spellings sources use for them. */
export const MUNICIPALITIES: { slug: string; name: string; aliases: string[] }[] = [
  { slug: "bad-wiessee", name: "Bad Wiessee", aliases: [] },
  { slug: "bayrischzell", name: "Bayrischzell", aliases: [] },
  { slug: "fischbachau", name: "Fischbachau", aliases: [] },
  { slug: "gmund", name: "Gmund a. Tegernsee", aliases: ["Gmund", "Gmund am Tegernsee"] },
  { slug: "hausham", name: "Hausham", aliases: [] },
  { slug: "holzkirchen", name: "Holzkirchen", aliases: ["Markt Holzkirchen"] },
  { slug: "irschenberg", name: "Irschenberg", aliases: [] },
  { slug: "kreuth", name: "Kreuth", aliases: [] },
  { slug: "miesbach", name: "Miesbach", aliases: ["Stadt Miesbach"] },
  { slug: "otterfing", name: "Otterfing", aliases: [] },
  { slug: "rottach-egern", name: "Rottach-Egern", aliases: [] },
  { slug: "schliersee", name: "Schliersee", aliases: ["Markt Schliersee"] },
  { slug: "tegernsee", name: "Tegernsee", aliases: ["Stadt Tegernsee"] },
  { slug: "valley", name: "Valley", aliases: [] },
  { slug: "waakirchen", name: "Waakirchen", aliases: [] },
  { slug: "warngau", name: "Warngau", aliases: [] },
  { slug: "weyarn", name: "Weyarn", aliases: [] },
];

const norm = (s: string) => s.normalize("NFC").toLocaleLowerCase("de").replace(/\s+/g, " ").trim();

/** Does a source's `places` entry name this municipality (by slug, name or alias)? */
export function placeMatches(place: string, m: (typeof MUNICIPALITIES)[number]): boolean {
  const p = norm(place);
  return p === m.slug || p === norm(m.name) || m.aliases.some((a) => norm(a) === p);
}

/** Display names for place and programme slugs that the calendar carries. */
const SLUG_NAMES: Record<string, string> = {
  ...Object.fromEntries(MUNICIPALITIES.map((m) => [m.slug, m.name])),
  "landkreis-miesbach": "Landkreis Miesbach",
  "tegernseer-tal": "Tegernseer Tal",
  leitzachtal: "Leitzachtal",
  oberland: "Oberland",
  "region-17": "Region 17",
  oberbayern: "Oberbayern",
  bayern: "Bayern",
  "rheinland-pfalz": "Rheinland-Pfalz",
  oesterreich: "Österreich",
  sozialraumlotsen: "Interkommunale Sozialraumlotsen",
  sela: "SeLA",
  pflegesonah: "PflegesoNah",
  leader: "LEADER",
  "esf-plus": "ESF Plus",
  "mobilitaetskonzept-miesbach": "Mobilitätskonzept",
  bergbus: "BergBus",
  grundsicherungsgeld: "Grundsicherungsgeld (SGB II)",
};

export function slugName(slug: string | null | undefined): string {
  if (!slug) return "";
  return SLUG_NAMES[slug] ?? slug;
}

/** Short labels for long seeded actor names in the graph (full name stays in the panel). */
const SHORT: Record<string, string> = {
  "caritas-zentrum-miesbach": "Caritas-Zentrum Miesbach",
  "caritasverband-muenchen-freising": "Caritas München-Freising",
  "fachstelle-soziales-senioren": "Fachstelle Soziales & Senioren",
  "jugendamt-miesbach": "Jugendamt",
  "jobcenter-miesbach": "Jobcenter",
  "pflegestuetzpunkt-miesbach": "Pflegestützpunkt",
  "freistaat-bayern": "Freistaat Bayern",
  stmas: "StMAS",
  stmgp: "StMGP",
  stmfh: "StMFH",
  bmas: "BMAS",
  bmbfsfj: "BMBFSFJ",
  bmg: "BMG",
  "diakonie-rosenheim": "Diakonie Rosenheim",
  "diakonie-jugendhilfe-miesbach": "Diakonie Jugendhilfe",
  "awo-seniorenzentrum-miesbach": "AWO-Seniorenzentrum",
  "hospizkreis-miesbach": "Hospizkreis",
  "erzbistum-muenchen-freising": "Erzbistum München und Freising",
  "pfarrverbaende-dekanat-miesbach": "Pfarrverbände",
  "dekanat-bad-toelz": "Evang. Dekanat Bad Tölz",
  "evang-gemeinden-miesbach": "Evang. Kirchengemeinden",
  "regionalentwicklung-oberland": "Regionalentwicklung Oberland",
  "lokale-projekttraeger": "LEADER-Projektträger",
  mvv: "MVV",
  "statistik-bayern": "Landesamt für Statistik",
  sozialbeirat: "Sozialbeirat",
  "verbund-psychische-gesundheit": "Verbund Psychische Gesundheit",
  jugendhilfeausschuss: "Jugendhilfeausschuss",
  gesundheitsregionplus: "GesundheitsregionPlus",
  "gsv-gremium": "GSV-Gremium (Bezirk)",
  "kreistag-miesbach": "Kreistag",
  "bezirkstag-oberbayern": "Bezirkstag",
  sozialraumlotsen: "Sozialraumlotsen",
  sela: "SeLA",
  pflegesonah: "PflegesoNah",
  "mobilitaetskonzept-miesbach": "Mobilitätskonzept",
  bergbus: "BergBus",
  "gemeindeschwester-plus": "Gemeindeschwester plus",
  "community-nursing": "Community Nursing",
  praeventionsketten: "Präventionsketten",
};

export function shortName(slug: string, name: string): string {
  if (SHORT[slug]) return SHORT[slug];
  const plain = name.replace(/\s*\([^)]*\)\s*/g, " ").trim();
  return plain.length > 30 ? plain.slice(0, 28).trimEnd() + "…" : plain;
}
