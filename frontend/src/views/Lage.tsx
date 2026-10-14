import { useState } from "react";
import { Link } from "react-router-dom";
import { api, questionsCached } from "../api";
import { SignalRow } from "../components/SignalRow";
import { Empty, ErrorBox, LayerDot, Loading, MovementText, Section } from "../components/ui";
import { layerLabel, slugName } from "../domain";
import { eventKind, eventName, eventRange, isFromReport, upcoming, windowProgress } from "../events";
import { dayKey, fmtDate, parseDay, pick, useLang, useT, weekLabel } from "../i18n";
import { LAYER_COLOR, LAYERS, type EventOut, type Layer, type Meta, type QuestionMoving, type Signal } from "../types";
import { useAsync } from "../useAsync";
import { qNumber } from "../useQuestions";

const PER_LAYER = 4;

function sinceDays(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return dayKey(d);
}

type Band = { items: Signal[]; fallback: boolean };

export function Lage({ meta }: { meta: Meta | null }) {
  const { lang } = useLang();
  const t = useT();
  const [notice, setNotice] = useState<string | null>(null);

  const ov = useAsync(() => api.overview(), []);
  const bands = useAsync(async () => {
    const out = {} as Record<Layer, Band>;
    await Promise.all(
      LAYERS.map(async (layer) => {
        const week = await api.signals({ layer, sort: "score", per_page: PER_LAYER, since: sinceDays(7) });
        if (week.items.length > 0) {
          out[layer] = { items: week.items, fallback: false };
          return;
        }
        const month = await api.signals({ layer, sort: "score", per_page: PER_LAYER, since: sinceDays(30) });
        out[layer] = { items: month.items, fallback: month.items.length > 0 };
      }),
    );
    return out;
  }, []);
  // Older backends have no questions_moving on the overview: derive it from /api/questions.
  const qs = useAsync(() => questionsCached(), []);
  const ev = useAsync(() => {
    const r = eventRange(120);
    return api.events(r.from, r.to);
  }, []);

  async function runCycle() {
    try {
      const r = await api.runCycle();
      setNotice(r.started ? t("cycle_started") : t("cycle_running"));
    } catch (e) {
      setNotice((e as Error).message);
    }
  }

  if (ov.error) return <ErrorBox error={ov.error} retry={ov.reload} />;
  if (!ov.data) return <Loading />;
  const o = ov.data;
  const counts: Partial<Record<Layer, { count_7d: number; count_30d: number }>> = {};
  for (const l of o.layers) counts[l.layer] = l;

  const lead = o.report_lead ?? (o.latest_digest ? { lead_de: o.latest_digest.lead_de, lead_en: o.latest_digest.lead_en, week: null } : null);
  const fromOverview = Array.isArray(o.questions_moving);
  const movingSrc: QuestionMoving[] = fromOverview ? o.questions_moving! : (qs.data ?? []).filter((q) => q.movement !== "quiet");
  const movingQs = [...movingSrc].sort((a, b) => Math.abs(b.balance) - Math.abs(a.balance));
  const movingLoading = !fromOverview && qs.loading && !qs.data;
  const movingFailed = !fromOverview && !!qs.error;

  return (
    <div className="fade-in">
      <CycleStrip o={o} notice={notice} onRun={() => void runCycle()} />

      <div className="grid gap-x-10 lg:grid-cols-[minmax(0,1fr)_300px]">
        <div className="min-w-0">
          {lead && (
            <div className="mt-8">
              <p className="label">
                {t("report_lead")}
                {lead.week ? `, ${weekLabel(parseDay(lead.week), lang).kw}` : ""}
              </p>
              <p className="serif text-[1.35rem] md:text-[1.65rem] leading-[1.35] mt-1 max-w-[58ch]">{pick(lead, "lead", lang)}</p>
              <Link to="/lagebericht" className="link text-sm inline-block mt-3">
                {t("read_report")}
              </Link>
            </div>
          )}

          <Section
            title={t("moving")}
            right={
              <Link to="/fragen" className="link text-sm">
                {t("all_questions")}
              </Link>
            }
          >
            {movingLoading ? (
              <Loading />
            ) : movingQs.length === 0 ? (
              <Empty k={movingFailed ? "q_none" : "moving_none"} />
            ) : (
              <ul className="grid gap-x-8 sm:grid-cols-2 xl:grid-cols-3">
                {movingQs.map((q) => (
                  <li key={q.id} className="rule">
                    <Link to={`/fragen/${q.id}`} className="block py-3 group">
                      <span className="label">
                        {t("q_no")} {qNumber(q.id)}
                      </span>
                      <span className="serif block leading-snug mt-0.5 group-hover:text-fir">{pick(q, "title", lang)}</span>
                      <MovementText q={q} movement={q.movement} className="block text-sm font-medium mt-1.5" />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Section>

          <Section title={t("lage_layers")} hint={t("lage_layers_hint")}>
            {bands.error && <ErrorBox error={bands.error} retry={bands.reload} />}
            <div>
              {LAYERS.map((layer) => {
                const c = counts[layer];
                const band = bands.data?.[layer];
                return (
                  <div key={layer} className="grid gap-x-6 md:grid-cols-[200px_minmax(0,1fr)] pt-3 pb-5 border-t-2" style={{ borderColor: LAYER_COLOR[layer] }}>
                    <header className="mb-2 md:mb-0">
                      <h3 className="display text-[1.05rem] leading-tight inline-flex items-center gap-2">
                        <LayerDot layer={layer} />
                        {layerLabel(layer, meta, lang)}
                      </h3>
                      <p className="text-xs text-ink-3 mt-1 num">{t("layer_counts", { a: c?.count_7d ?? 0, b: c?.count_30d ?? 0 })}</p>
                      <Link to={`/signale?layer=${layer}`} className="link text-xs text-ink-3 hidden md:inline-block mt-2">
                        {t("more_in_layer")}
                      </Link>
                    </header>
                    <div className="min-w-0">
                      {!band ? (
                        bands.loading ? <p className="label py-2">{t("loading")}</p> : null
                      ) : band.items.length === 0 ? (
                        <p className="text-sm text-ink-3 py-2">{t("none_week")}</p>
                      ) : (
                        <>
                          {band.fallback && <p className="text-xs text-ink-3 pb-1">{t("lage_fallback_30")}</p>}
                          {band.items.map((s) => (
                            <SignalRow key={s.id} s={s} meta={meta} showLayer={false} compact />
                          ))}
                        </>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </Section>
        </div>

        <aside className="lg:sticky lg:top-4 self-start">
          <Section title={t("next_dates")}>
            {ev.error ? (
              <DatesRail items={o.next_events} />
            ) : !ev.data ? (
              <Loading />
            ) : (
              <DatesRail items={upcoming(ev.data.items)} />
            )}
            <Link to="/kalender" className="link text-sm inline-block mt-3">
              {t("nav_kalender")}
            </Link>
          </Section>
        </aside>
      </div>
    </div>
  );
}

function CycleStrip({ o, notice, onRun }: { o: import("../types").Overview; notice: string | null; onRun: () => void }) {
  const { lang } = useLang();
  const t = useT();
  const c = o.last_cycle;
  return (
    <div className="py-2.5 flex flex-wrap items-baseline gap-x-5 gap-y-1 text-xs text-ink-3 border-b border-rule">
      {c ? (
        <>
          <span>
            {t("last_cycle")} {fmtDate(c.finished_at ?? c.started_at, lang, { time: true })}
          </span>
          <span className="num">
            <b className="text-ink font-medium">{c.items_fetched}</b> {t("items_fetched")}, <b className="text-ink font-medium">{c.items_new}</b> {t("new_items")},{" "}
            <b className="text-ink font-medium">{c.signals}</b> {t("signals_n")}
            {typeof c.judgements === "number" && (
              <>
                , <b className="text-ink font-medium">{c.judgements}</b> {t("judgements_n")}
              </>
            )}
          </span>
        </>
      ) : (
        <span>{t("no_cycle")}</span>
      )}
      <span className="ml-auto flex items-center gap-3">
        {notice && <span className="text-fir">{notice}</span>}
        <button className="btn btn-quiet" onClick={onRun}>
          {t("run_cycle")}
        </button>
      </span>
    </div>
  );
}

/** Deadlines, dates and running windows, each in its own register. */
function DatesRail({ items }: { items: EventOut[] }) {
  const { lang } = useLang();
  const t = useT();
  const deadlines = items.filter((e) => eventKind(e) === "deadline").sort(by((e) => e.deadline ?? e.start_date)).slice(0, 5);
  const events = items.filter((e) => eventKind(e) === "event").sort(by((e) => e.start_date ?? e.deadline)).slice(0, 6);
  const windows = items.filter((e) => eventKind(e) === "window").sort(by((e) => e.end_date ?? e.start_date)).slice(0, 5);
  if (items.length === 0) return <Empty k="no_events" />;

  /** "Bayern, PflegesoNah, aus dem Bericht" */
  const sub = (e: EventOut, ...extra: (string | null | undefined)[]) =>
    [...extra, isFromReport(e) ? t("from_report") : null].filter(Boolean).join(", ");
  const where = (e: EventOut) => [slugName(e.place), slugName(e.programme)].filter(Boolean).join(", ");

  return (
    <div className="space-y-6 text-sm">
      {deadlines.length > 0 && (
        <div>
          <h3 className="label mb-1">{t("cal_deadlines_row")}</h3>
          <ul>
            {deadlines.map((e) => (
              <li key={e.id} className="rule py-2 grid grid-cols-[62px_1fr] gap-2">
                <span className="text-rust font-semibold num">{fmtDate(e.deadline ?? e.start_date, lang)}</span>
                <span>
                  {eventName(e, lang)}
                  <span className="block text-xs text-ink-3">{sub(e, where(e))}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {windows.length > 0 && (
        <div>
          <h3 className="label mb-1">{t("cal_windows")}</h3>
          <ul>
            {windows.map((e) => {
              const p = windowProgress(e);
              return (
                <li key={e.id} className="rule py-2">
                  <div>{eventName(e, lang)}</div>
                  <div className="relative h-[6px] bg-paper-3 mt-1.5" aria-hidden>
                    <div className="absolute inset-y-0 left-0 bg-ink-3" style={{ width: `${p * 100}%` }} />
                  </div>
                  <div className="text-xs text-ink-3 mt-1 num">
                    {sub(e, `${fmtDate(e.start_date, lang)} – ${fmtDate(e.end_date, lang, { year: true })}`, p > 0 && p < 1 ? t("running") : null)}
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      )}
      {events.length > 0 && (
        <div>
          <h3 className="label mb-1">{t("events_row")}</h3>
          <ul>
            {events.map((e) => (
              <li key={e.id} className="rule py-2 grid grid-cols-[62px_1fr] gap-2">
                <span className="font-medium num">{fmtDate(e.start_date, lang)}</span>
                <span>
                  {eventName(e, lang)}
                  <span className="block text-xs text-ink-3">{sub(e, where(e) || e.location || e.organizer)}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function by<T>(f: (x: T) => string | null | undefined) {
  return (a: T, b: T) => (f(a) ?? "9999").localeCompare(f(b) ?? "9999");
}
