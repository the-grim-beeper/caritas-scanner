import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { fmtDate, pick, useLang, useT } from "../i18n";
import type { Meta, Signal } from "../types";
import { Corroboration, Gauge, GaugeLegend, LayerName, Score, TopicTag } from "./ui";

/** One signal as a row; expands to its full decomposition and story members. */
export function SignalRow({ s, meta, showLayer = true, compact = false }: { s: Signal; meta: Meta | null; showLayer?: boolean; compact?: boolean }) {
  const { lang } = useLang();
  const t = useT();
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState<Signal | null>(null);

  async function toggle() {
    const next = !open;
    setOpen(next);
    if (next && !detail) {
      try {
        setDetail(await api.signal(s.id));
      } catch {
        setDetail(s);
      }
    }
  }

  const head = pick(s, "headline", lang);
  const other = lang === "de" ? s.headline_en : s.headline_de;
  const d = detail ?? s;

  return (
    <article className="rule py-2.5">
      <button onClick={toggle} className="w-full text-left flex gap-3 items-start" aria-expanded={open}>
        <Gauge factors={s.factors} title={`${t("score")} ${s.score.toFixed(3)}`} />
        <div className="min-w-0 flex-1">
          <h3 className={compact ? "text-[0.92rem] leading-snug" : "text-[1rem] leading-snug"}>{head}</h3>
          <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-ink-3">
            {showLayer && <LayerName layer={s.layer} meta={meta} />}
            <span>{s.source_name}</span>
            <span className="reading">{fmtDate(s.published_at, lang)}</span>
            <span className="reading">{meta?.signal_types[s.signal_type]?.[lang] ?? s.signal_type}</span>
            <Corroboration s={s} />
            <Score value={s.score} />
          </div>
        </div>
      </button>

      {open && (
        <div className="fade-in mt-3 ml-7 grid gap-4 md:grid-cols-[1fr_260px]">
          <div className="text-sm">
            {other && other !== head && <p className="text-ink-3 italic mb-2">{other}</p>}
            <p className="leading-relaxed">{pick(d, "summary", lang)}</p>
            {d.original_title && d.original_title !== head && (
              <p className="mt-2 text-xs text-ink-3">
                <span className="eyebrow">{t("original")}</span> {d.original_title}
              </p>
            )}
            <div className="mt-2 flex flex-wrap gap-1.5">
              {d.topics.map((c) => (
                <TopicTag key={c} code={c} meta={meta} />
              ))}
            </div>
            {d.entities && d.entities.length > 0 && (
              <p className="mt-2 text-xs">
                <span className="eyebrow mr-2">{t("entities")}</span>
                {d.entities.map((e, i) => (
                  <span key={e.slug}>
                    {i > 0 && " · "}
                    <Link to={`/watchlist/${e.slug}`} className="underline decoration-rule hover:decoration-ink">
                      {e.name}
                    </Link>
                  </span>
                ))}
              </p>
            )}
            {d.places.length > 0 && d.entities?.length === 0 && <p className="mt-2 text-xs text-ink-3">{d.places.join(" · ")}</p>}
            {d.url && (
              <a href={d.url} target="_blank" rel="noreferrer" className="btn btn-quiet inline-block mt-3">
                {t("open")} ↗
              </a>
            )}
          </div>
          <aside className="text-xs">
            <div className="eyebrow mb-1.5">{t("factors")}</div>
            <GaugeLegend factors={d.factors} />
            <div className="mt-2 reading">
              {t("score")} = {d.score.toFixed(3)}
            </div>
            {d.story && d.story.members && d.story.members.length > 1 && (
              <div className="mt-4">
                <div className="eyebrow mb-1">
                  {t("story_members")} · {t("confidence")} {d.story.confidence.toFixed(2)}
                </div>
                <ul className="space-y-1">
                  {d.story.members.map((m) => (
                    <li key={m.id} className="flex gap-2">
                      <span className="reading text-ink-3 w-16 shrink-0">{fmtDate(m.published_at, lang)}</span>
                      <span className="min-w-0">
                        {m.url ? (
                          <a href={m.url} target="_blank" rel="noreferrer" className="underline decoration-rule">
                            {m.source_name}
                          </a>
                        ) : (
                          m.source_name
                        )}
                        {m.is_founder && <span className="text-river ml-1">({t("founder")})</span>}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </aside>
        </div>
      )}
    </article>
  );
}
