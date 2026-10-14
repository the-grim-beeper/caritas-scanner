import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useLang, useT, type Key } from "../i18n";
import { LAYER_COLOR, type Factors, type Layer, type Meta, type Signal } from "../types";

// ---------------------------------------------------------------------------
// The signature: a Pegellatte — the striped river-gauge post on the Rhine and
// Neckar banks — reading the five factors of the brief's score.
// ---------------------------------------------------------------------------
export const FACTOR_ORDER: (keyof Factors)[] = [
  "forward_lag",
  "consequence",
  "novelty",
  "regional_relevance",
  "authority",
];

export function Gauge({ factors, size = "s", title }: { factors: Factors; size?: "s" | "l"; title?: string }) {
  const w = size === "l" ? 48 : 26;
  const h = size === "l" ? 12 : 3;
  const gap = size === "l" ? 3 : 2;
  const H = FACTOR_ORDER.length * (h + gap) - gap;
  return (
    <svg width={w} height={H} viewBox={`0 0 ${w} ${H}`} role="img" aria-label={title ?? "score"} className="shrink-0">
      <title>{title}</title>
      {FACTOR_ORDER.map((k, i) => {
        const v = Math.max(0, Math.min(1, factors[k] ?? 0));
        const y = i * (h + gap);
        return (
          <g key={k}>
            <rect x={0} y={y} width={w} height={h} fill="#dfe2dc" />
            <rect x={0} y={y} width={w * v} height={h} fill={i % 2 === 0 ? "#161b22" : "#3a414b"} />
          </g>
        );
      })}
    </svg>
  );
}

export function GaugeLegend({ factors }: { factors: Factors }) {
  const t = useT();
  return (
    <div className="flex items-start gap-3">
      <Gauge factors={factors} size="l" />
      <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-[3px] text-xs">
        {FACTOR_ORDER.map((k) => (
          <div key={k} className="contents">
            <dt className="text-ink-2">{t(`f_${k}` as Key)}</dt>
            <dd className="reading text-right">{factors[k].toFixed(2)}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

export function LayerDot({ layer }: { layer: Layer | null | undefined }) {
  return <span className="layer-bar" style={{ background: layer ? LAYER_COLOR[layer] : "#c9cdc6" }} aria-hidden />;
}

export function LayerName({ layer, meta }: { layer: Layer | null | undefined; meta: Meta | null }) {
  const { lang } = useLang();
  if (!layer) return null;
  return (
    <span className="inline-flex items-center gap-1.5">
      <LayerDot layer={layer} />
      <span>{meta?.layers[layer]?.[lang] ?? layer}</span>
    </span>
  );
}

export function TopicTag({ code, meta }: { code: string; meta: Meta | null }) {
  const { lang } = useLang();
  return (
    <Link
      to={`/signals?topic=${encodeURIComponent(code)}`}
      className="reading text-[0.66rem] border border-rule px-1.5 py-[1px] text-ink-2 hover:border-ink"
    >
      {meta?.topics[code]?.[lang] ?? code}
    </Link>
  );
}

export function Score({ value }: { value: number }) {
  return <span className="reading text-xs">{value.toFixed(3)}</span>;
}

export function Corroboration({ s }: { s: Signal }) {
  const t = useT();
  if (!s.story || s.story.distinct_sources <= 1) return null;
  return (
    <span className="reading text-[0.66rem] text-river" title={`${t("confidence")} ${s.story.confidence.toFixed(2)}`}>
      ×{s.story.distinct_sources} {t("sources_n")}
    </span>
  );
}

export function Sparkline({ values, width = 80, height = 18, color = "#0f6e6b" }: { values: number[]; width?: number; height?: number; color?: string }) {
  if (values.length === 0) return <svg width={width} height={height} />;
  const max = Math.max(1, ...values);
  const step = width / Math.max(1, values.length - 1);
  const pts = values.map((v, i) => `${i * step},${height - (v / max) * (height - 2) - 1}`).join(" ");
  return (
    <svg width={width} height={height} aria-hidden>
      <polyline points={pts} fill="none" stroke={color} strokeWidth={1.25} />
    </svg>
  );
}

export function Empty({ k = "none_yet" }: { k?: Key }) {
  const t = useT();
  return <p className="text-ink-3 text-sm py-8">{t(k)}</p>;
}

export function Loading() {
  const t = useT();
  return <p className="eyebrow py-8">{t("loading")}</p>;
}

export function ErrorBox({ error, retry }: { error: Error; retry?: () => void }) {
  const t = useT();
  return (
    <div className="border border-warn text-warn text-sm p-3 my-4">
      <p>
        {t("error")} <span className="reading text-xs">{error.message}</span>
      </p>
      {retry && (
        <button className="btn mt-2" onClick={retry}>
          {t("retry")}
        </button>
      )}
    </div>
  );
}

export function Section({ eyebrow, title, right, children }: { eyebrow?: string; title?: ReactNode; right?: ReactNode; children: ReactNode }) {
  return (
    <section className="mt-8">
      {(eyebrow || title || right) && (
        <header className="rule-strong pt-2 mb-3 flex items-baseline justify-between gap-4">
          <div>
            {eyebrow && <div className="eyebrow">{eyebrow}</div>}
            {title && <h2 className="display text-xl">{title}</h2>}
          </div>
          {right}
        </header>
      )}
      {children}
    </section>
  );
}
