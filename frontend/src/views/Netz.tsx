import { forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY, type SimulationLinkDatum, type SimulationNodeDatum } from "d3-force";
import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, isNotFound } from "../api";
import { CitedSignalLine, Empty, Fail, Loading, Quote, Section } from "../components/ui";
import { actorColor, actorLabel, ENTITY_KIND_LABELS, relationLabel, shortName } from "../domain";
import { pick, useLang, useT, type Key } from "../i18n";
import { ACTOR_KINDS, type ActorKind, type Meta, type NetEdge, type NetNode, type Network, type NetworkGap } from "../types";
import { useAsync } from "../useAsync";

type SimNode = SimulationNodeDatum & { slug: string; node: NetNode; r: number; label: string };
type LinkKind = "report" | "signal" | "missing";
type DrawLink = { key: string; kind: LinkKind; a: string; b: string; edge?: NetEdge; gap?: NetworkGap };
type SimLink = DrawLink & SimulationLinkDatum<SimNode>;

const CHAR_W = 6.2; // approx. width of an 11px Plex Sans character, for label bounds

/** Consecutive pairs of a "missing_edge" gap's actors become dashed links: there is no Edge row for them. */
function missingPairs(gaps: NetworkGap[], have: Set<string>): { a: string; b: string; gap: NetworkGap }[] {
  const out: { a: string; b: string; gap: NetworkGap }[] = [];
  for (const g of gaps) {
    if (g.kind !== "missing_edge") continue;
    const slugs = (g.actor_slugs ?? []).filter((s) => have.has(s));
    for (let i = 0; i + 1 < slugs.length; i++) out.push({ a: slugs[i], b: slugs[i + 1], gap: g });
  }
  return out;
}

type Box = { x0: number; y0: number; x1: number; y1: number };

/** Node circle plus its label to the right: what must not overlap another node's. */
function nodeBox(n: SimNode, pad = 3): Box {
  const x = n.x ?? 0, y = n.y ?? 0;
  const h = Math.max(n.r, 7);
  return { x0: x - n.r - pad, y0: y - h - pad, x1: x + n.r + 4 + n.label.length * CHAR_W + pad, y1: y + h + pad };
}

function bounds(nodes: SimNode[]): Box {
  const b = { x0: Infinity, y0: Infinity, x1: -Infinity, y1: -Infinity };
  for (const n of nodes) {
    const r = nodeBox(n, 0);
    b.x0 = Math.min(b.x0, r.x0);
    b.y0 = Math.min(b.y0, r.y0);
    b.x1 = Math.max(b.x1, r.x1);
    b.y1 = Math.max(b.y1, r.y1);
  }
  return b;
}

/** Push apart nodes whose circle+label boxes overlap, along the axis of least overlap. */
function separate(nodes: SimNode[], passes = 60) {
  for (let p = 0; p < passes; p++) {
    let moved = false;
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodeBox(nodes[i]), b = nodeBox(nodes[j]);
        const ox = Math.min(a.x1, b.x1) - Math.max(a.x0, b.x0);
        const oy = Math.min(a.y1, b.y1) - Math.max(a.y0, b.y0);
        if (ox <= 0 || oy <= 0) continue;
        moved = true;
        const ni = nodes[i], nj = nodes[j];
        if (oy <= ox) {
          const d = (oy / 2 + 0.5) * ((ni.y ?? 0) <= (nj.y ?? 0) ? 1 : -1);
          ni.y = (ni.y ?? 0) - d;
          nj.y = (nj.y ?? 0) + d;
        } else {
          const d = (ox / 2 + 0.5) * ((ni.x ?? 0) <= (nj.x ?? 0) ? 1 : -1);
          ni.x = (ni.x ?? 0) - d;
          nj.x = (nj.x ?? 0) + d;
        }
      }
    }
    if (!moved) break;
  }
}

/**
 * Lay out each connected cluster on its own (the county hub, the church line, the Bezirk, LEADER …),
 * remove label overlaps, then shelf-pack the clusters, largest first, into rows.
 */
function layout(net: Network) {
  const nodes: SimNode[] = net.nodes.map((n) => ({
    slug: n.slug,
    node: n,
    r: 5 + Math.sqrt(Math.max(0, n.degree)) * 2.4 + Math.min(4, Math.sqrt(Math.max(0, n.signals_30d ?? 0))),
    label: shortName(n.slug, n.name),
  }));
  const bySlug = new Map(nodes.map((n) => [n.slug, n]));
  const links: DrawLink[] = [];
  for (const e of net.edges) {
    if (!bySlug.has(e.a) || !bySlug.has(e.b) || e.a === e.b) continue;
    links.push({ key: e.id, kind: e.origin === "signal" ? "signal" : "report", a: e.a, b: e.b, edge: e });
  }
  for (const m of missingPairs(net.gaps, new Set(bySlug.keys()))) {
    links.push({ key: `gap-${m.gap.id}-${m.a}-${m.b}`, kind: "missing", a: m.a, b: m.b, gap: m.gap });
  }
  const degree = new Map<string, number>();
  const adj = new Map<string, string[]>();
  for (const l of links) {
    for (const k of [l.a, l.b]) degree.set(k, (degree.get(k) ?? 0) + 1);
    adj.set(l.a, [...(adj.get(l.a) ?? []), l.b]);
    adj.set(l.b, [...(adj.get(l.b) ?? []), l.a]);
  }
  const deg = (k: string) => degree.get(k) ?? 0;

  // connected components
  const seen = new Set<string>();
  const comps: SimNode[][] = [];
  for (const n of nodes) {
    if (seen.has(n.slug)) continue;
    const members: SimNode[] = [];
    const stack = [n.slug];
    seen.add(n.slug);
    while (stack.length) {
      const cur = stack.pop()!;
      members.push(bySlug.get(cur)!);
      for (const nb of adj.get(cur) ?? []) {
        if (!seen.has(nb)) {
          seen.add(nb);
          stack.push(nb);
        }
      }
    }
    comps.push(members);
  }

  const placed: { members: SimNode[]; b: Box }[] = [];
  for (const members of comps) {
    if (members.length > 1) {
      const inComp = new Set(members.map((m) => m.slug));
      // d3 replaces source/target with node objects; give it copies so the drawn links stay plain.
      const simLinks: SimLink[] = links.filter((l) => inComp.has(l.a)).map((l) => ({ ...l, source: l.a, target: l.b }));
      forceSimulation<SimNode>(members)
        .force(
          "link",
          forceLink<SimNode, SimLink>(simLinks)
            .id((d) => d.slug)
            // Hubs get longer spokes, so their leaves (and leaf labels) do not pile up.
            .distance((l) => (l.kind === "missing" ? 110 : Math.min(130, 50 + 9 * Math.max(deg(l.a), deg(l.b)))))
            .strength(0.7),
        )
        .force("charge", forceManyBody<SimNode>().strength(-260))
        .force("collide", forceCollide<SimNode>().radius((d) => d.r + 14))
        .force("x", forceX<SimNode>(0).strength(0.04))
        .force("y", forceY<SimNode>(0).strength(0.06))
        .stop()
        .tick(360);
      separate(members);
    } else {
      members[0].x = 0;
      members[0].y = 0;
    }
    placed.push({ members, b: bounds(members) });
  }

  // Shelf packing: biggest cluster first, rows no wider than the widest cluster (or 900).
  placed.sort((a, b) => b.members.length - a.members.length || b.b.x1 - b.b.x0 - (a.b.x1 - a.b.x0));
  const GAP = 34;
  const rowW = Math.max(900, ...placed.map((p) => p.b.x1 - p.b.x0));
  let cx = 0, cy = 0, rowH = 0;
  for (const p of placed) {
    const w = p.b.x1 - p.b.x0, h = p.b.y1 - p.b.y0;
    if (cx > 0 && cx + w > rowW) {
      cx = 0;
      cy += rowH + GAP;
      rowH = 0;
    }
    const dx = cx - p.b.x0, dy = cy - p.b.y0;
    for (const n of p.members) {
      n.x = (n.x ?? 0) + dx;
      n.y = (n.y ?? 0) + dy;
    }
    cx += w + GAP;
    rowH = Math.max(rowH, h);
  }

  const b = nodes.length ? bounds(nodes) : { x0: 0, y0: 0, x1: 100, y1: 100 };
  return { nodes, links, box: { x: b.x0 - 12, y: b.y0 - 12, w: b.x1 - b.x0 + 24, h: b.y1 - b.y0 + 24 } };
}

export function Netz({ meta }: { meta: Meta | null }) {
  const { lang } = useLang();
  const t = useT();
  const [sp, setSp] = useSearchParams();
  const selected = sp.get("akteur");
  const res = useAsync(() => api.network(), []);
  const graph = useMemo(() => (res.data ? layout(res.data) : null), [res.data]);
  const [hover, setHover] = useState<string | null>(null);

  function select(slug: string | null) {
    const next = new URLSearchParams(sp);
    if (slug && slug !== selected) next.set("akteur", slug);
    else next.delete("akteur");
    setSp(next, { replace: true });
  }

  if (res.error) return <Fail error={res.error} retry={res.reload} emptyKey="net_empty" />;
  if (!res.data || !graph) return <Loading />;
  const net = res.data;
  if (net.nodes.length === 0) return <Empty k="net_empty" />;

  const bySlug = new Map(graph.nodes.map((n) => [n.slug, n]));
  const neighbours = new Set<string>();
  if (selected) for (const l of graph.links) if (l.a === selected || l.b === selected) neighbours.add(l.a === selected ? l.b : l.a);
  const kindsPresent = ACTOR_KINDS.filter((k) => net.nodes.some((n) => (n.actor_kind ?? "other") === k));
  const unknownKinds = [...new Set(net.nodes.map((n) => n.actor_kind ?? "other").filter((k) => !ACTOR_KINDS.includes(k as ActorKind)))];
  const gapsSorted = [...net.gaps].sort((a, b) => Number(b.kind === "missing_edge") - Number(a.kind === "missing_edge"));

  return (
    <div className="fade-in">
      <p className="serif text-[1.1rem] leading-snug pt-6 max-w-[70ch]">{t("net_lead")}</p>

      <div className="mt-5 grid gap-x-8 gap-y-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="min-w-0">
          <div className="border-t-2 border-ink overflow-x-auto">
            <svg
              viewBox={`${graph.box.x} ${graph.box.y} ${graph.box.w} ${graph.box.h}`}
              className="block w-full h-auto max-h-[80vh] mx-auto"
              // Never scale above 1:1, so labels stay at their set size on wide screens.
              style={{ maxWidth: graph.box.w, minWidth: Math.min(graph.box.w, 820) }}
              role="group"
              aria-label={t("nav_netz")}
              onClick={(e) => {
                if (e.target === e.currentTarget) select(null);
              }}
            >
              {graph.links.map((l) => {
                const s = bySlug.get(l.a)!;
                const tg = bySlug.get(l.b)!;
                const x1 = s.x ?? 0, y1 = s.y ?? 0, x2 = tg.x ?? 0, y2 = tg.y ?? 0;
                const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
                const incident = selected && (l.a === selected || l.b === selected);
                const dim = selected && !incident;
                const showLabel = hover === l.key || incident;
                const rel = l.kind === "missing" ? t("net_missing") : relationLabel(l.edge!.relation, meta, lang);
                const stroke = l.kind === "missing" ? "var(--color-ink-3)" : "var(--color-ink-2)";
                const dash = l.kind === "signal" ? "7 3 1.5 3" : l.kind === "missing" ? "5 5" : undefined;
                return (
                  <g key={l.key} opacity={dim ? 0.18 : 1} onMouseEnter={() => setHover(l.key)} onMouseLeave={() => setHover(null)}>
                    <title>{`${s.node.name} – ${rel} – ${tg.node.name}`}</title>
                    <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="transparent" strokeWidth={10} />
                    <line x1={x1} y1={y1} x2={x2} y2={y2} stroke={stroke} strokeWidth={incident ? 1.8 : 1.15} strokeDasharray={dash} />
                    {l.kind === "signal" && <circle cx={mx} cy={my} r={2.6} fill="var(--color-ink-2)" />}
                    {l.kind === "missing" && (
                      <g>
                        <circle cx={mx} cy={my} r={7.5} fill="var(--color-paper)" stroke="var(--color-ink-3)" strokeDasharray="2 2" />
                        <text x={mx} y={my + 3.6} textAnchor="middle" fontSize={10} fontWeight={600} fill="var(--color-ink-3)">
                          ?
                        </text>
                      </g>
                    )}
                    {showLabel && (
                      <text x={mx} y={my - (l.kind === "missing" ? 11 : 6)} textAnchor="middle" fontSize={10.5} fill="var(--color-ink)" className="halo" style={{ pointerEvents: "none" }}>
                        {rel}
                      </text>
                    )}
                  </g>
                );
              })}
              {graph.nodes.map((n) => {
                const isSel = n.slug === selected;
                const dim = selected && !isSel && !neighbours.has(n.slug);
                const col = actorColor(n.node.actor_kind);
                return (
                  <g
                    key={n.slug}
                    transform={`translate(${n.x ?? 0},${n.y ?? 0})`}
                    opacity={dim ? 0.3 : 1}
                    className="cursor-pointer focus:outline-none"
                    role="button"
                    tabIndex={0}
                    aria-pressed={isSel}
                    aria-label={`${n.node.name}, ${actorLabel(n.node.actor_kind, lang)}`}
                    onClick={() => select(n.slug)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        select(n.slug);
                      }
                    }}
                  >
                    <title>{n.node.name}</title>
                    {isSel && <circle r={n.r + 4} fill="none" stroke="var(--color-ink)" strokeWidth={1.5} />}
                    <circle r={n.r} fill={n.node.seeded ? col : "var(--color-paper)"} stroke={col} strokeWidth={n.node.seeded ? 0 : 2} />
                    <text x={n.r + 4} y={3.8} fontSize={11} fontWeight={isSel ? 600 : 400} fill="var(--color-ink)" className="halo">
                      {n.label}
                    </text>
                  </g>
                );
              })}
            </svg>
          </div>
          <Legend kinds={[...kindsPresent, ...unknownKinds]} />
        </div>

        <aside className="lg:sticky lg:top-4 self-start min-w-0">
          {selected ? (
            <ActorPanel slug={selected} net={net} meta={meta} onSelect={select} />
          ) : (
            <p className="text-sm text-ink-3 border-t-2 border-ink pt-3">{t("net_pick")}</p>
          )}
        </aside>
      </div>

      <Section title={t("net_forums")}>
        <div className="overflow-x-auto">
          <table className="data text-sm min-w-[760px]">
            <thead>
              <tr>
                <th>{t("net_forum")}</th>
                <th>{t("net_convener")}</th>
                <th>{t("net_attendance")}</th>
                <th>{t("net_minutes")}</th>
                <th>{t("net_treatment")}</th>
              </tr>
            </thead>
            <tbody>
              {net.forums.map((f) => (
                <tr key={f.slug}>
                  <td className="font-medium">
                    <button className="link text-left" onClick={() => select(f.slug)}>
                      {f.name}
                    </button>
                  </td>
                  <td>{f.convener_de}</td>
                  <td>
                    <YesNo v={f.attendance_visible} />
                  </td>
                  <td>
                    <YesNo v={f.public_minutes} />
                  </td>
                  <td className="text-ink-2 max-w-[44ch]">
                    {pick(f, "treatment", lang)}
                    {f.brief_ref && (
                      <span className="text-ink-3 text-xs ml-1">
                        ({t("footnote")} {f.brief_ref})
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section title={t("net_gaps")} hint={t("net_gaps_lead")}>
        <ol className="grid gap-x-10 md:grid-cols-2">
          {gapsSorted.map((g) => (
            <li key={g.id} className={`py-3 ${g.kind === "missing_edge" ? "md:col-span-2 border-t-2 border-dashed border-ink-3" : "rule"}`}>
              <p className="label">{t(gapKindKey(g.kind))}</p>
              <h3 className={g.kind === "missing_edge" ? "display text-[1.25rem] mt-0.5" : "font-semibold mt-0.5"}>{pick(g, "title", lang)}</h3>
              <p className={`text-ink-2 mt-1 leading-relaxed ${g.kind === "missing_edge" ? "serif text-[1.02rem] max-w-[75ch]" : "text-sm"}`}>{pick(g, "detail", lang)}</p>
              {g.actor_slugs?.length > 0 && (
                <p className="text-xs mt-1.5 flex flex-wrap gap-x-3">
                  {g.actor_slugs.map((s) => (
                    <button key={s} className="link" onClick={() => select(s)}>
                      {net.nodes.find((n) => n.slug === s)?.name ?? s}
                    </button>
                  ))}
                </p>
              )}
            </li>
          ))}
        </ol>
      </Section>
    </div>
  );
}

function gapKindKey(kind: string): Key {
  if (kind === "missing_edge") return "gap_missing_edge";
  if (kind === "not_found") return "gap_not_found";
  return "gap_interview";
}

function YesNo({ v }: { v: boolean }) {
  const t = useT();
  return v ? <span className="font-medium">{t("yes")}</span> : <span className="text-ink-3">{t("no")}</span>;
}

function Legend({ kinds }: { kinds: string[] }) {
  const { lang } = useLang();
  const t = useT();
  const sample = (dash: string | undefined, kind: LinkKind) => (
    <svg width={44} height={14} aria-hidden className="shrink-0">
      <line x1={2} x2={42} y1={7} y2={7} stroke={kind === "missing" ? "var(--color-ink-3)" : "var(--color-ink-2)"} strokeWidth={1.3} strokeDasharray={dash} />
      {kind === "signal" && <circle cx={22} cy={7} r={2.6} fill="var(--color-ink-2)" />}
      {kind === "missing" && <circle cx={22} cy={7} r={5} fill="var(--color-paper)" stroke="var(--color-ink-3)" strokeDasharray="2 2" />}
    </svg>
  );
  return (
    <div className="mt-3 grid gap-3 text-xs text-ink-2 md:grid-cols-[1fr_auto]">
      <ul className="flex flex-wrap gap-x-4 gap-y-1">
        {kinds.map((k) => (
          <li key={k} className="inline-flex items-center gap-1.5">
            <span className="inline-block w-2.5 h-2.5 rounded-full" style={{ background: actorColor(k) }} aria-hidden />
            {actorLabel(k, lang)}
          </li>
        ))}
        <li className="inline-flex items-center gap-1.5 text-ink-3">
          <span className="inline-block w-2.5 h-2.5 rounded-full border-2 border-ink-3" aria-hidden />
          {t("net_discovered")}
        </li>
      </ul>
      <ul className="flex flex-wrap gap-x-4 gap-y-1">
        <li className="inline-flex items-center gap-1.5">
          {sample(undefined, "report")}
          {t("net_edge_report")}
        </li>
        <li className="inline-flex items-center gap-1.5">
          {sample("7 3 1.5 3", "signal")}
          {t("net_edge_signal")}
        </li>
        <li className="inline-flex items-center gap-1.5">
          {sample("5 5", "missing")}
          {t("net_edge_missing")}
        </li>
      </ul>
    </div>
  );
}

function ActorPanel({ slug, net, meta, onSelect }: { slug: string; net: Network; meta: Meta | null; onSelect: (s: string | null) => void }) {
  const { lang } = useLang();
  const t = useT();
  const node = net.nodes.find((n) => n.slug === slug) ?? null;
  const ent = useAsync(() => api.entity(slug), [slug]);
  const name = node?.name ?? ent.data?.name ?? slug;
  const kind = node?.kind ?? ent.data?.kind;
  const nameOf = (s: string) => net.nodes.find((n) => n.slug === s)?.name ?? s;
  const edges = net.edges.filter((e) => e.a === slug || e.b === slug);
  const gaps = net.gaps.filter((g) => g.actor_slugs?.includes(slug));
  const timeline = ent.data?.timeline ?? [];

  return (
    <div className="border-t-2 border-ink pt-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="label inline-flex items-center gap-1.5">
            {node && <span className="inline-block w-2.5 h-2.5 rounded-full" style={{ background: actorColor(node.actor_kind) }} aria-hidden />}
            {[node ? actorLabel(node.actor_kind, lang) : kind ? (ENTITY_KIND_LABELS[kind]?.[lang] ?? kind) : "", node ? (node.seeded ? t("net_seeded") : t("net_discovered")) : ""]
              .filter(Boolean)
              .join(", ")}
          </p>
          <h2 className="display text-[1.4rem] leading-tight mt-0.5">{name}</h2>
          {node && node.signals_30d > 0 && <p className="text-xs text-ink-3 mt-1">{t("net_n_items", { n: node.signals_30d })}</p>}
        </div>
        <button className="btn btn-quiet !px-2 !py-0.5" onClick={() => onSelect(null)} aria-label={t("net_close")} title={t("net_close")}>
          ×
        </button>
      </div>

      <h3 className="label mt-5 mb-1">{t("net_links")}</h3>
      {edges.length === 0 ? (
        <p className="text-sm text-ink-3">{t("net_no_links")}</p>
      ) : (
        <ul className="text-sm">
          {edges.map((e) => {
            const out = e.a === slug;
            const other = out ? e.b : e.a;
            return (
              <li key={e.id} className="rule py-2.5">
                <div>
                  <span className="font-medium">{relationLabel(e.relation, meta, lang)}</span> <span className="text-ink-3">{out ? "→" : "←"}</span>{" "}
                  <button className="link text-left" onClick={() => onSelect(other)}>
                    {nameOf(other)}
                  </button>
                </div>
                {pick(e, "evidence", lang) && <p className="text-ink-2 mt-1 leading-snug">{pick(e, "evidence", lang)}</p>}
                {e.quote && <Quote text={e.quote} className="mt-1.5 text-[0.95rem]" />}
                {e.signal && (
                  <div className="mt-1.5">
                    <CitedSignalLine s={e.signal} compact />
                  </div>
                )}
                <p className="text-xs text-ink-3 mt-1">
                  {e.origin === "signal" ? t("from_signal") : t("from_report")}
                  {e.brief_ref ? `, ${t("footnote")} ${e.brief_ref}` : ""}
                </p>
              </li>
            );
          })}
        </ul>
      )}

      {gaps.length > 0 && (
        <>
          <h3 className="label mt-5 mb-1">{t("net_gaps_of")}</h3>
          <ul className="text-sm">
            {gaps.map((g) => (
              <li key={g.id} className={`py-2 ${g.kind === "missing_edge" ? "border-t border-dashed border-ink-3" : "rule"}`}>
                <span className="font-medium">{pick(g, "title", lang)}</span>
                <p className="text-ink-2 text-xs mt-0.5 leading-snug">{pick(g, "detail", lang)}</p>
              </li>
            ))}
          </ul>
        </>
      )}

      <h3 className="label mt-5 mb-1">{t("net_timeline")}</h3>
      {ent.loading && !ent.data ? (
        <p className="label">{t("loading")}</p>
      ) : ent.error && !isNotFound(ent.error) ? (
        <p className="text-xs text-ink-3">{ent.error.message}</p>
      ) : timeline.length === 0 ? (
        <p className="text-sm text-ink-3">{t("net_no_timeline")}</p>
      ) : (
        <ul>
          {timeline.slice(0, 15).map((s) => (
            <li key={s.id} className="rule py-2">
              <CitedSignalLine s={s} compact />
            </li>
          ))}
          {timeline.length > 15 && (
            <li className="rule pt-2 text-xs">
              <Link to={`/signale?entity=${encodeURIComponent(slug)}`} className="link">
                {t("nav_signale")} ({timeline.length})
              </Link>
            </li>
          )}
        </ul>
      )}
    </div>
  );
}
