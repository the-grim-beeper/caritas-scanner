import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { layerLabel, relationLabel, safeUrl } from "../domain";
import { fmtDate, fmtNum, pick, useLang, useT } from "../i18n";
import type { Meta, Signal } from "../types";
import { qNumber, useQuestionsMap } from "../useQuestions";
import { Corroboration, LayerName, Panorama, PanoramaBoard, Quote, StrengthMark, TopicTag } from "./ui";

/** Where an entity link goes: places filter the signal list, actors open in the network panel. */
export function entityHref(slug: string, kind: string): string {
  return kind === "place" ? `/signale?entity=${encodeURIComponent(slug)}` : `/netz?akteur=${encodeURIComponent(slug)}`;
}

/** One signal as a row; expands to its full reading: summary, panorama board, questions, story. */
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
  const d = detail ?? s;
  const original = s.original_title && s.original_title.trim() !== head.trim() ? s.original_title : null;

  return (
    <article className="rule py-2.5">
      <button onClick={() => void toggle()} className="w-full text-left flex gap-3 items-start cursor-pointer" aria-expanded={open}>
        <Panorama factors={s.factors} title={`${t("score")} ${fmtNum(s.score, lang, 3)}`} />
        <div className="min-w-0 flex-1">
          <h3 className={`serif leading-snug ${compact ? "text-[1rem]" : "text-[1.08rem]"}`}>{head}</h3>
          {original && (
            <p className={`text-xs text-ink-3 mt-0.5 ${compact ? "line-clamp-1" : ""}`} title={original}>
              {t("original")}: {original}
            </p>
          )}
          <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-ink-3">
            {showLayer && <LayerName layer={s.layer} meta={meta} />}
            {s.source_name && <span>{s.source_name}</span>}
            <span>{fmtDate(s.published_at, lang)}</span>
            {!compact && <span>{meta?.signal_types?.[s.signal_type]?.[lang] ?? s.signal_type}</span>}
            <Corroboration s={s} />
          </div>
        </div>
      </button>

      {open && (
        <div className={`fade-in mt-3 ml-[42px] grid gap-5 ${compact ? "" : "md:grid-cols-[1fr_300px]"}`}>
          <div className="text-sm min-w-0">
            <p className="leading-relaxed max-w-[68ch]">{pick(d, "summary", lang)}</p>
            {lang === "en" && s.headline_de && <p className="text-xs text-ink-3 italic mt-2">{s.headline_de}</p>}
            {d.topics.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {d.topics.map((c) => (
                  <TopicTag key={c} code={c} meta={meta} />
                ))}
              </div>
            )}
            {d.entities && d.entities.length > 0 && (
              <p className="mt-3 text-xs">
                <span className="label mr-2">{t("actors")}</span>
                {d.entities.map((e, i) => (
                  <span key={e.slug}>
                    {i > 0 && ", "}
                    <Link to={entityHref(e.slug, e.kind)} className="link">
                      {e.name}
                    </Link>
                  </span>
                ))}
              </p>
            )}
            {d.places.length > 0 && (!d.entities || d.entities.length === 0) && <p className="mt-2 text-xs text-ink-3">{d.places.join(", ")}</p>}
            {d.judgements && d.judgements.length > 0 && <Judgements s={d} />}
            {d.edges && d.edges.length > 0 && (
              <div className="mt-4">
                <div className="label mb-1">{t("relations_seen")}</div>
                <ul className="text-xs space-y-1">
                  {d.edges.map((e) => (
                    <li key={e.id}>
                      <Link to={`/netz?akteur=${encodeURIComponent(e.a)}`} className="link">
                        {e.a}
                      </Link>{" "}
                      <span className="text-ink-3">{relationLabel(e.relation, meta, lang)}</span>{" "}
                      <Link to={`/netz?akteur=${encodeURIComponent(e.b)}`} className="link">
                        {e.b}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {d.url && (
              <a href={safeUrl(d.url)} target="_blank" rel="noreferrer" className="btn btn-quiet inline-block mt-4">
                {t("open")} ↗
              </a>
            )}
          </div>
          <aside className="text-xs min-w-0">
            <div className="label mb-1">{t("factors")}</div>
            <PanoramaBoard factors={d.factors} score={d.score} />
            {d.story && d.story.members && d.story.members.length > 1 && (
              <div className="mt-4">
                <div className="label mb-1">
                  {t("story_members")}, {t("confidence")} {fmtNum(d.story.confidence, lang)}
                </div>
                <ul className="space-y-1">
                  {d.story.members.map((m) => (
                    <li key={m.id} className="flex gap-2">
                      <span className="text-ink-3 w-14 shrink-0">{fmtDate(m.published_at, lang)}</span>
                      <span className="min-w-0">
                        {m.url ? (
                          <a href={safeUrl(m.url)} target="_blank" rel="noreferrer" className="link">
                            {m.source_name}
                          </a>
                        ) : (
                          m.source_name
                        )}
                        {m.is_founder && <span className="text-fir ml-1">({t("founder")})</span>}
                        {m.layer && <span className="text-ink-3 ml-1">{layerLabel(m.layer, meta, lang)}</span>}
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

function Judgements({ s }: { s: Signal }) {
  const { lang } = useLang();
  const t = useT();
  const qs = useQuestionsMap();
  return (
    <div className="mt-4">
      <div className="label mb-1">{t("bears_on")}</div>
      <ul className="space-y-2">
        {s.judgements!.map((j) => {
          const q = qs[j.question_id];
          return (
            <li key={j.id} className="border-l-2 border-rust pl-3">
              <Link to={`/fragen/${j.question_id}`} className="link text-xs">
                {t("q_no")} {qNumber(j.question_id)}
                {q ? `: ${pick(q, j.direction === "for" ? "for_label" : "against_label", lang)}` : ""}
              </Link>
              <span className="ml-2 text-xs">
                <StrengthMark strength={j.strength} />
              </span>
              <Quote text={j.quote} className="text-sm mt-0.5" />
            </li>
          );
        })}
      </ul>
    </div>
  );
}
