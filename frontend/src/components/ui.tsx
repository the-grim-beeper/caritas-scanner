import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { isNotFound } from "../api";
import { layerLabel, topicLabel, safeUrl } from "../domain";
import { fmtDate, fmtNum, pick, quoted, useLang, useT, type Key } from "../i18n";
import { LAYER_COLOR, type CitedSignal, type Factors, type Layer, type Meta, type Movement, type QuestionLabels, type Signal, type WeekPoint } from "../types";

// ---------------------------------------------------------------------------------------------
// The signature: a Bergpanorama. Five summits, one per score factor, read left to right like
// the panorama boards on the Wallberg or the Wendelstein. A tall ridge is a strong signal.
// ---------------------------------------------------------------------------------------------
export const FACTOR_ORDER: (keyof Factors)[] = ["authority", "regional_relevance", "novelty", "consequence", "forward_lag"];

function factorValue(f: Factors | null | undefined, k: keyof Factors): number {
  if (!f) return 0;
  const r = f as unknown as Record<string, number | undefined>;
  const v = r[k] ?? (k === "consequence" ? r.economic_materiality : undefined) ?? 0;
  return Math.max(0, Math.min(1, v));
}

function ridgePath(vals: number[], x0: number, w: number, top: number, h: number): string {
  const step = w / vals.length;
  const y = (v: number) => (top + h - v * h).toFixed(2);
  let d = `M${x0},${top + h} L${x0},${y(vals[0] * 0.22)}`;
  vals.forEach((v, i) => {
    if (i > 0) d += ` L${(x0 + step * i).toFixed(2)},${y(Math.min(v, vals[i - 1]) * 0.42)}`;
    d += ` L${(x0 + step * (i + 0.5)).toFixed(2)},${y(v)}`;
  });
  d += ` L${x0 + w},${y(vals[vals.length - 1] * 0.22)} L${x0 + w},${top + h} Z`;
  return d;
}

export function Panorama({ factors, title }: { factors: Factors; title?: string }) {
  const vals = FACTOR_ORDER.map((k) => factorValue(factors, k));
  const w = 30;
  const h = 13;
  return (
    <svg width={w} height={h + 1} viewBox={`0 0 ${w} ${h + 1}`} role="img" aria-label={title ?? "Score"} className="shrink-0 mt-[3px]">
      <title>{title}</title>
      <path d={ridgePath(vals, 0, w, 0, h)} fill="var(--color-fir)" />
      <line x1={0} x2={w} y1={h + 0.5} y2={h + 0.5} stroke="var(--color-ink)" strokeWidth={1} />
    </svg>
  );
}

/** The panorama board: each summit named, with its value, on a leader line. */
export function PanoramaBoard({ factors, score }: { factors: Factors; score: number }) {
  const { lang } = useLang();
  const t = useT();
  const vals = FACTOR_ORDER.map((k) => factorValue(factors, k));
  const W = 196;
  const H = 44;
  const top = 74;
  const step = W / vals.length;
  const labels = FACTOR_ORDER.map((k, i) => `${t(`f_${k}` as Key)} ${fmtNum(vals[i], lang)}`);
  return (
    <figure className="m-0">
      <svg width={W + 92} height={top + H + 4} viewBox={`0 0 ${W + 92} ${top + H + 4}`} role="img" aria-label={t("factors")} className="block max-w-full">
        <title>{labels.join(", ")}</title>
        <path d={ridgePath(vals, 0, W, top, H)} fill="var(--color-fir)" />
        <line x1={0} x2={W} y1={top + H + 0.5} y2={top + H + 0.5} stroke="var(--color-ink)" />
        {vals.map((v, i) => {
          const x = step * (i + 0.5);
          const py = top + H - v * H;
          return (
            <g key={i}>
              <line x1={x} x2={x} y1={py - 2} y2={top - 8} stroke="var(--color-ink-3)" strokeWidth={0.75} />
              <text x={x + 1} y={top - 11} transform={`rotate(-38 ${x + 1} ${top - 11})`} fontSize={10.5} fill="var(--color-ink-2)">
                {labels[i]}
              </text>
            </g>
          );
        })}
      </svg>
      <figcaption className="text-xs text-ink-2 mt-1 num">
        {t("score")} {fmtNum(score, lang, 3)}
      </figcaption>
    </figure>
  );
}

// ---------------------------------------------------------------------------------------------
// Layers, topics, small marks
// ---------------------------------------------------------------------------------------------
export function LayerDot({ layer }: { layer: Layer | string | null | undefined }) {
  return <span className="layer-bar" style={{ background: layer ? (LAYER_COLOR[layer as Layer] ?? "#c9c4b6") : "#c9c4b6" }} aria-hidden />;
}

export function LayerName({ layer, meta }: { layer: Layer | string | null | undefined; meta: Meta | null }) {
  const { lang } = useLang();
  if (!layer) return null;
  return (
    <span className="inline-flex items-center gap-1.5">
      <LayerDot layer={layer} />
      <span>{layerLabel(layer, meta, lang)}</span>
    </span>
  );
}

export function TopicTag({ code, meta }: { code: string; meta: Meta | null }) {
  const { lang } = useLang();
  return (
    <Link to={`/signale?topic=${encodeURIComponent(code)}`} className="text-[0.72rem] border border-rule px-1.5 py-[1px] text-ink-2 hover:border-fir hover:text-fir">
      {topicLabel(code, meta, lang)}
    </Link>
  );
}

export function Corroboration({ s }: { s: Signal }) {
  const t = useT();
  const { lang } = useLang();
  if (!s.story || s.story.distinct_sources <= 1) return null;
  return (
    <span className="text-fir" title={`${t("confidence")} ${fmtNum(s.story.confidence, lang)}`}>
      {s.story.distinct_sources} {t("sources_n")}
    </span>
  );
}

// ---------------------------------------------------------------------------------------------
// The questions: tilt between the two sides, balance over twelve weeks, movement
// ---------------------------------------------------------------------------------------------
/** Squash the running balance into (-1, 1): a balance of 3 already leans most of the way. */
const lean = (b: number) => Math.tanh(b / 3);

export function TiltBar({ q, balance, movement, size = "s" }: { q: QuestionLabels; balance: number; movement: Movement; size?: "s" | "l" }) {
  const { lang } = useLang();
  const w = size === "l" ? 360 : 168;
  const h = 14;
  const cx = w / 2;
  const mx = cx + lean(balance) * (cx - 5);
  const quiet = movement === "quiet" && Math.abs(balance) < 0.05;
  const forL = pick(q, "for_label", lang);
  const againstL = pick(q, "against_label", lang);
  const toward = balance > 0.05 ? "for" : balance < -0.05 ? "against" : null;
  return (
    <div style={{ width: w }} className="max-w-full">
      <div className={`flex justify-between gap-3 leading-tight ${size === "l" ? "text-sm" : "text-[0.7rem]"}`}>
        <span className={toward === "against" ? "text-ink font-medium" : "text-ink-3"}>{againstL}</span>
        <span className={`text-right ${toward === "for" ? "text-ink font-medium" : "text-ink-3"}`}>{forL}</span>
      </div>
      <svg viewBox={`0 0 ${w} ${h}`} style={{ width: "100%", height: "auto" }} role="img" aria-label={`${againstL} ← → ${forL}: ${fmtNum(balance, lang, 1)}`} className="block mt-0.5">
        <line x1={0} x2={w} y1={h / 2} y2={h / 2} stroke="var(--color-rule)" strokeWidth={2} />
        <line x1={cx} x2={cx} y1={1} y2={h - 1} stroke="var(--color-ink-3)" strokeWidth={1} />
        {!quiet && <rect x={Math.min(cx, mx)} y={h / 2 - 2} width={Math.abs(mx - cx)} height={4} fill="var(--color-rust)" />}
        <circle cx={mx} cy={h / 2} r={4} fill={quiet ? "var(--color-paper)" : "var(--color-rust)"} stroke={quiet ? "var(--color-ink-3)" : "var(--color-rust)"} strokeWidth={1.25} />
      </svg>
    </div>
  );
}

export function MovementText({ q, movement, className = "" }: { q: QuestionLabels; movement: Movement; className?: string }) {
  const { lang } = useLang();
  const t = useT();
  if (movement === "for")
    return (
      <span className={className}>
        <span className="text-rust" aria-hidden>
          →{" "}
        </span>
        {pick(q, "for_label", lang)}
      </span>
    );
  if (movement === "against")
    return (
      <span className={className}>
        <span className="text-rust" aria-hidden>
          ←{" "}
        </span>
        {pick(q, "against_label", lang)}
      </span>
    );
  if (movement === "mixed")
    return (
      <span className={className}>
        <span className="text-rust" aria-hidden>
          ↔{" "}
        </span>
        {t("mv_mixed")}
      </span>
    );
  return <span className={`text-ink-3 ${className}`}>{t("mv_quiet")}</span>;
}

/** Twelve weeks of running balance; up is "for", down is "against". */
export function BalanceSpark({ series, q, size = "s" }: { series: WeekPoint[]; q?: QuestionLabels; size?: "s" | "l" }) {
  const { lang } = useLang();
  const t = useT();
  const L = size === "l";
  const W = L ? 560 : 120;
  const H = L ? 150 : 30;
  const padL = L ? 6 : 1;
  // Large: a band at the top and bottom of the plot holds the two side labels; week numbers below.
  const top = L ? 18 : 1;
  const bottom = L ? H - 18 - 16 : H - 1;
  if (series.length === 0) return <svg width={W} height={H} aria-hidden />;
  const m = Math.max(1.5, ...series.map((p) => Math.abs(p.balance)));
  const step = (W - padL * 2) / Math.max(1, series.length - 1);
  const x = (i: number) => padL + i * step;
  const mid = (top + bottom) / 2;
  const y = (v: number) => mid - (v / m) * ((bottom - top) / 2 - 2);
  const pts = series.map((p, i) => `${x(i).toFixed(1)},${y(p.balance).toFixed(1)}`).join(" ");
  const last = series[series.length - 1];
  const tip = (p: WeekPoint) => {
    const kw = `${t("week_short")} ${weekNo(p.week)}`;
    return `${kw}: ${p.balance >= 0 ? "+" : ""}${fmtNum(p.balance, lang, 1)} (${p.n} ${t("q_evidence")})`;
  };
  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      {...(L ? { style: { width: "100%", height: "auto" } } : { width: W, height: H })}
      className="block max-w-full"
      role="img"
      aria-label={`${t("q_weeks")}: ${tip(last)}`}
    >
      <line x1={0} x2={W} y1={y(0)} y2={y(0)} stroke="var(--color-rule)" strokeDasharray="2 2" />
      {size === "l" && q && (
        <>
          <text x={0} y={11} fontSize={11} fill="var(--color-ink-3)">
            ↑ {pick(q, "for_label", lang)}
          </text>
          <text x={0} y={bottom + 14} fontSize={11} fill="var(--color-ink-3)">
            ↓ {pick(q, "against_label", lang)}
          </text>
          <line x1={0} x2={W} y1={H - 16} y2={H - 16} stroke="var(--color-ink)" />
          {series.map((p, i) =>
            i % 2 === series.length % 2 ? null : (
              <text key={p.week} x={x(i)} y={H - 3} textAnchor="middle" fontSize={10} fill="var(--color-ink-3)">
                {weekNo(p.week)}
              </text>
            ),
          )}
        </>
      )}
      <polyline points={pts} fill="none" stroke="var(--color-ink-2)" strokeWidth={size === "l" ? 2 : 1.5} strokeLinejoin="round" />
      {size === "l" &&
        series.map((p, i) => (p.n > 0 ? <circle key={p.week} cx={x(i)} cy={y(p.balance)} r={Math.min(6, 2.5 + p.n)} fill="var(--color-paper)" stroke="var(--color-ink-2)" strokeWidth={1.25} /> : null))}
      <circle cx={x(series.length - 1)} cy={y(last.balance)} r={size === "l" ? 4 : 2.5} fill="var(--color-rust)" />
      {series.map((p, i) => (
        <rect key={`h${p.week}`} x={x(i) - step / 2} y={0} width={step} height={H} fill="transparent">
          <title>{tip(p)}</title>
        </rect>
      ))}
    </svg>
  );
}

function weekNo(iso: string): number | string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const t = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()));
  const day = t.getUTCDay() || 7;
  t.setUTCDate(t.getUTCDate() + 4 - day);
  const y0 = new Date(Date.UTC(t.getUTCFullYear(), 0, 1));
  return Math.ceil(((t.getTime() - y0.getTime()) / 86400000 + 1) / 7);
}

export function StrengthMark({ strength }: { strength: string }) {
  const t = useT();
  const n = strength === "strong" ? 3 : strength === "moderate" ? 2 : 1;
  const key = (strength === "strong" ? "st_strong" : strength === "moderate" ? "st_moderate" : "st_weak") as Key;
  return (
    <span className="inline-flex items-center gap-1 text-ink-3" title={t(key)}>
      <span aria-hidden className="inline-flex gap-[2px]">
        {[1, 2, 3].map((i) => (
          <span key={i} className={`inline-block w-[5px] h-[5px] rounded-full ${i <= n ? "bg-rust" : "border border-rule"}`} />
        ))}
      </span>
      {t(key)}
    </span>
  );
}

// ---------------------------------------------------------------------------------------------
// Cited signals (the short shape embedded in questions, network and report payloads)
// ---------------------------------------------------------------------------------------------
export function CitedSignalLine({ s, compact = false }: { s: CitedSignal | null | undefined; compact?: boolean }) {
  const { lang } = useLang();
  if (!s) return null;
  const head = pick(s, "headline", lang);
  const german = lang === "en" && s.headline_de && s.headline_de !== head ? s.headline_de : null;
  return (
    <div className={compact ? "text-[0.85rem]" : "text-sm"}>
      <div className="flex items-start gap-2">
        <span className="mt-[0.4em]">
          <LayerDot layer={s.layer} />
        </span>
        <div className="min-w-0">
          {s.url ? (
            <a href={safeUrl(s.url)} target="_blank" rel="noreferrer" className="link leading-snug">
              {head}&nbsp;<span aria-hidden>↗</span>
            </a>
          ) : (
            <span className="leading-snug">{head}</span>
          )}
          {german && <div className="text-xs text-ink-3 italic mt-0.5">{german}</div>}
          <div className="text-xs text-ink-3 mt-0.5 flex flex-wrap gap-x-3">
            {s.source_name && <span>{s.source_name}</span>}
            <span>{fmtDate(s.published_at, lang)}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

export function Quote({ text, className = "" }: { text: string; className?: string }) {
  const { lang } = useLang();
  return <blockquote className={`serif m-0 ${className}`}>{quoted(text, lang)}</blockquote>;
}

// ---------------------------------------------------------------------------------------------
// States and layout
// ---------------------------------------------------------------------------------------------
export function Empty({ k = "none_yet", children }: { k?: Key; children?: ReactNode }) {
  const t = useT();
  return <p className="text-ink-3 text-sm py-6 max-w-[62ch]">{children ?? t(k)}</p>;
}

export function Loading() {
  const t = useT();
  return <p className="label py-8">{t("loading")}</p>;
}

export function ErrorBox({ error, retry }: { error: Error; retry?: () => void }) {
  const t = useT();
  return (
    <div className="border border-ink text-sm p-3 my-4 max-w-[70ch]">
      <p>
        {t("error")} <span className="text-xs text-ink-3">{error.message}</span>
      </p>
      {retry && (
        <button className="btn mt-2" onClick={retry}>
          {t("retry")}
        </button>
      )}
    </div>
  );
}

/** A view whose endpoint does not exist yet (older backend) shows its empty state, not an error. */
export function Fail({ error, retry, emptyKey }: { error: Error; retry?: () => void; emptyKey?: Key }) {
  if (isNotFound(error) && emptyKey) return <Empty k={emptyKey} />;
  return <ErrorBox error={error} retry={retry} />;
}

export function Section({ title, hint, right, children, id }: { title?: ReactNode; hint?: ReactNode; right?: ReactNode; children: ReactNode; id?: string }) {
  return (
    <section className="mt-10" id={id}>
      {(title || right) && (
        <header className="rule-strong pt-2 mb-3 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <div>
            {title && <h2 className="display text-[1.35rem] leading-tight">{title}</h2>}
            {hint && <p className="text-sm text-ink-3 mt-0.5 max-w-[70ch]">{hint}</p>}
          </div>
          {right}
        </header>
      )}
      {children}
    </section>
  );
}

export function CopyButton({ text }: { text: string }) {
  const t = useT();
  const [state, setState] = useState<"idle" | "ok" | "fail">("idle");
  async function copy() {
    try {
      if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(text);
      else {
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        const ok = document.execCommand("copy");
        document.body.removeChild(ta);
        if (!ok) throw new Error("copy");
      }
      setState("ok");
      window.setTimeout(() => setState("idle"), 2200);
    } catch {
      setState("fail");
    }
  }
  return (
    <span className="inline-flex items-center gap-3">
      {state === "fail" && <span className="text-xs text-ink-3">{t("copy_failed")}</span>}
      <button className={state === "ok" ? "btn btn-fir" : "btn"} onClick={() => void copy()} aria-live="polite">
        {state === "ok" ? `${t("copied")} ✓` : t("copy")}
      </button>
    </span>
  );
}
