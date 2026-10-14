import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, isNotFound } from "../api";
import { CitedSignalLine, CopyButton, Empty, ErrorBox, LayerDot, Loading, MovementText, Quote, Section } from "../components/ui";
import { layerLabel } from "../domain";
import { eventDate, eventKind, eventName } from "../events";
import { fmtDate, parseDay, pick, useLang, useT, weekLabel } from "../i18n";
import { type CitedSignal, type EventOut, type JudgementOut, type Lang, type Meta, type ReportFull, type ReportPayload } from "../types";
import { useAsync } from "../useAsync";
import { qNumber, useQuestionsMap } from "../useQuestions";

/** The model's output may arrive flat or nested under `payload`; read either. */
function payload(r: ReportFull): ReportPayload {
  const p = r.payload ?? {};
  return {
    lead_de: r.lead_de ?? p.lead_de ?? "",
    lead_en: r.lead_en ?? p.lead_en ?? "",
    questions: r.questions ?? p.questions ?? [],
    sections: r.sections ?? p.sections ?? [],
    chains: r.chains ?? p.chains ?? [],
    watch: r.watch ?? p.watch ?? [],
    friday_de: r.friday_de ?? p.friday_de ?? "",
    friday_en: r.friday_en ?? p.friday_en ?? "",
    friday_signal_ids: r.friday_signal_ids ?? p.friday_signal_ids ?? [],
  };
}

function reportWeek(r: { week: string | null; created_at: string }, lang: Lang) {
  return weekLabel(r.week ? parseDay(r.week) : new Date(r.created_at), lang);
}

export function Lagebericht({ meta }: { meta: Meta | null }) {
  const { id } = useParams();
  const { lang } = useLang();
  const t = useT();
  const nav = useNavigate();
  const rep = useAsync(() => api.report(id ?? "latest"), [id]);
  const archive = useAsync(() => api.reports(), []);
  const [running, setRunning] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  async function run() {
    setRunning(true);
    setNotice(null);
    try {
      const r = await api.runReport();
      if (r.ok && r.id) {
        archive.reload();
        if (id) nav(`/lagebericht/${r.id}`);
        else rep.reload();
      } else setNotice(r.reason || t("rep_no_signals"));
    } catch (e) {
      setNotice((e as Error).message);
    } finally {
      setRunning(false);
    }
  }

  const runner = (
    <div>
      <button className="btn btn-fir" onClick={() => void run()} disabled={running}>
        {t("rep_run")}
      </button>
      {running && <p className="text-xs text-ink-3 mt-2">{t("rep_running")}</p>}
      {notice && <p className="text-xs mt-2 max-w-[40ch]">{notice}</p>}
    </div>
  );

  const archiveList = (
    <div>
      <h2 className="label mb-2">{t("rep_archive")}</h2>
      {archive.data && archive.data.length > 0 ? (
        <ul>
          {archive.data.map((a) => {
            const wk = reportWeek(a, lang);
            const current = rep.data?.id === a.id;
            return (
              <li key={a.id} className="rule py-2">
                <Link to={`/lagebericht/${a.id}`} className={`block group ${current ? "" : "text-ink-2"}`} aria-current={current ? "page" : undefined}>
                  <span className={`text-sm ${current ? "font-semibold" : "group-hover:text-fir"}`}>{wk.kw}</span>
                  <span className="text-xs text-ink-3 ml-2">{fmtDate(a.created_at, lang)}</span>
                  <span className="block text-xs line-clamp-2 mt-0.5">{pick(a, "lead", lang)}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="text-xs text-ink-3">–</p>
      )}
    </div>
  );

  if (rep.error && !isNotFound(rep.error)) return <ErrorBox error={rep.error} retry={rep.reload} />;
  if (rep.error) {
    return (
      <div className="fade-in pt-8 max-w-[62ch]">
        <h2 className="display text-[1.6rem]">{t("rep_title")}</h2>
        <Empty k="rep_none" />
        {runner}
      </div>
    );
  }
  if (!rep.data) return <Loading />;
  const r = rep.data;
  const p = payload(r);
  const signals = r.signals ?? {};
  const events = r.events ?? {};
  const judgements = r.judgements ?? {};
  const wk = reportWeek(r, lang);
  const friday = lang === "en" ? p.friday_en || p.friday_de : p.friday_de || p.friday_en;

  return (
    <div className="fade-in grid gap-x-12 gap-y-10 lg:grid-cols-[minmax(0,1fr)_250px]">
      <article className="min-w-0">
        <header className="pt-7">
          <p className="label">
            {t("rep_title")}, {wk.range}
          </p>
          <h2 className="display text-[2rem] md:text-[2.5rem] leading-none mt-1">{wk.kw}</h2>
          <p className="serif text-[1.3rem] md:text-[1.55rem] leading-[1.38] mt-4 max-w-[60ch]">{pick(p, "lead", lang)}</p>
          <p className="text-xs text-ink-3 mt-3">
            {t("rep_written_by")} {r.model}, {fmtDate(r.created_at, lang, { time: true })}
          </p>
        </header>

        {friday && (
          <section className="mt-9 border-2 border-ink px-5 py-4 md:px-7 md:py-6 bg-paper" aria-labelledby="friday-h">
            <header className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 id="friday-h" className="display text-[1.35rem] leading-tight">
                  {t("friday")}
                </h2>
                <p className="text-sm text-ink-3">{t("friday_to")}</p>
              </div>
              <CopyButton text={friday} />
            </header>
            <div className="serif text-[1.08rem] leading-[1.6] mt-4 max-w-[64ch] space-y-3">
              {friday
                .split(/\n\s*\n/)
                .map((para) => para.trim())
                .filter(Boolean)
                .map((para, i) => (
                  <p key={i}>{para}</p>
                ))}
            </div>
            {p.friday_signal_ids.some((sid) => signals[sid]) && (
              <div className="mt-5 pt-3 border-t border-rule">
                <h3 className="label mb-2">{t("friday_basis")}</h3>
                <ul className="grid gap-x-8 gap-y-3 md:grid-cols-2">
                  {p.friday_signal_ids.filter((sid) => signals[sid]).map((sid) => (
                    <li key={sid}>
                      <CitedSignalLine s={signals[sid]} compact />
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </section>
        )}

        {p.questions.length > 0 && <QuestionsBlock items={p.questions} judgements={judgements} />}

        {p.sections.map((sec) => (
          <Section
            key={sec.layer}
            title={
              <span className="inline-flex items-center gap-2">
                <LayerDot layer={sec.layer} />
                {layerLabel(sec.layer, meta, lang)}
              </span>
            }
          >
            {(sec.items ?? []).map((it, i) => (
              <div key={it.signal_id + i} className="grid gap-x-8 gap-y-1 md:grid-cols-2 rule py-3">
                <CitedSignalLine s={signals[it.signal_id]} />
                <p className="text-[0.95rem] leading-relaxed md:border-l md:border-rule md:pl-5">{pick(it, "note", lang)}</p>
              </div>
            ))}
          </Section>
        ))}

        {p.chains.length > 0 && (
          <Section title={t("rep_chains")} hint={t("rep_chains_hint")}>
            <div className="grid gap-6 md:grid-cols-2">
              {p.chains.map((c, i) => (
                <div key={i} className="border border-rule p-4">
                  <h3 className="font-semibold mb-3">{pick(c, "title", lang)}</h3>
                  <ol className="border-l-2 border-ink pl-3 space-y-3">
                    {(c.signal_ids ?? []).map((sid) => (
                      <ChainStep key={sid} s={signals[sid]} />
                    ))}
                  </ol>
                </div>
              ))}
            </div>
          </Section>
        )}

        {p.watch.length > 0 && (
          <Section title={t("rep_watch")}>
            <table className="data text-sm">
              <tbody>
                {p.watch.map((w, i) => (
                  <WatchRow key={w.event_id + i} e={events[w.event_id]} why={pick(w, "why", lang)} />
                ))}
              </tbody>
            </table>
          </Section>
        )}
      </article>

      <aside className="lg:pt-7 space-y-8 text-sm lg:sticky lg:top-4 self-start">
        {runner}
        {archiveList}
      </aside>
    </div>
  );
}

function QuestionsBlock({ items, judgements }: { items: ReportPayload["questions"]; judgements: Record<string, JudgementOut> }) {
  const { lang } = useLang();
  const t = useT();
  const qs = useQuestionsMap();
  return (
    <Section title={t("rep_questions")}>
      <ul>
        {items.map((it) => {
          const q = qs[it.question_id];
          const cited = (it.judgement_ids ?? []).map((jid) => judgements[jid]).filter(Boolean);
          return (
            <li key={it.question_id} className="rule py-4 grid gap-x-8 gap-y-2 md:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
              <div>
                <Link to={`/fragen/${it.question_id}`} className="group">
                  <span className="label">
                    {t("q_no")} {qNumber(it.question_id)}
                  </span>
                  <span className="serif block leading-snug group-hover:text-fir">{q ? pick(q, "title", lang) : it.question_id}</span>
                </Link>
                {q && <MovementText q={q} movement={it.movement} className="block text-sm font-medium mt-1.5" />}
              </div>
              <div>
                <p className="leading-relaxed">{pick(it, "note", lang)}</p>
                {cited.length > 0 && (
                  <ul className="mt-2 space-y-2">
                    {cited.map((j) => (
                      <li key={j.id} className="border-l-2 border-rust pl-3">
                        <Quote text={j.quote} className="text-[0.95rem]" />
                        <div className="mt-1">
                          <CitedSignalLine s={j.signal} compact />
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </Section>
  );
}

function ChainStep({ s }: { s: CitedSignal | undefined }) {
  if (!s) return null;
  return (
    <li>
      <CitedSignalLine s={s} compact />
    </li>
  );
}

function WatchRow({ e, why }: { e: EventOut | undefined; why: string }) {
  const { lang } = useLang();
  const t = useT();
  if (!e) return null;
  const kind = eventKind(e);
  return (
    <tr>
      <td className="whitespace-nowrap w-36">
        {kind === "deadline" ? (
          <span className="text-rust font-semibold">
            {t("deadline")} {fmtDate(eventDate(e), lang)}
          </span>
        ) : kind === "window" ? (
          <span>
            {fmtDate(e.start_date, lang)} – {fmtDate(e.end_date, lang)}
          </span>
        ) : (
          <span className="font-medium">{fmtDate(eventDate(e), lang)}</span>
        )}
      </td>
      <td>
        <div>{eventName(e, lang)}</div>
        <div className="text-ink-2 text-xs mt-0.5">{why}</div>
      </td>
    </tr>
  );
}
