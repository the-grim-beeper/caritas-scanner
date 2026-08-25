import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { SignalRow } from "../components/SignalRow";
import { Empty, ErrorBox, LayerDot, Loading, Section } from "../components/ui";
import { fmtDate, pick, useLang, useT } from "../i18n";
import { LAYER_COLOR, LAYERS, type Layer, type Meta, type Signal } from "../types";
import { useAsync } from "../useAsync";

const PER_LAYER = 7;

export function Radar({ meta }: { meta: Meta | null }) {
  const { lang } = useLang();
  const t = useT();
  const [notice, setNotice] = useState<string | null>(null);

  const ov = useAsync(() => api.overview(), []);
  const cols = useAsync(
    async () => {
      const out: Record<Layer, Signal[]> = { policy: [], editorial: [], innovation: [], corporate: [], infrastructure: [], funding: [] };
      await Promise.all(
        LAYERS.map(async (layer) => {
          const r = await api.signals({ layer, sort: "score", per_page: PER_LAYER, since: sinceDays(30) });
          out[layer] = r.items;
        }),
      );
      return out;
    },
    [],
  );

  async function runCycle() {
    const r = await api.runCycle();
    setNotice(r.started ? t("cycle_started") : t("cycle_running"));
  }

  if (ov.error) return <ErrorBox error={ov.error} retry={ov.reload} />;
  if (!ov.data) return <Loading />;
  const o = ov.data;
  const byLayer: Partial<Record<Layer, { count_7d: number; count_30d: number }>> = {};
  for (const l of o.layers) byLayer[l.layer] = l;

  return (
    <div className="fade-in">
      {/* lead strip: the cycle reading */}
      <div className="py-3 flex flex-wrap items-baseline gap-x-6 gap-y-1 text-xs text-ink-3 border-b border-rule">
        {o.last_cycle ? (
          <>
            <span className="eyebrow">{t("last_cycle")}</span>
            <span className="reading">{fmtDate(o.last_cycle.finished_at, lang, true)}</span>
            <span>
              <b className="reading text-ink">{o.last_cycle.items_fetched}</b> {t("items_fetched")} · <b className="reading text-ink">{o.last_cycle.items_new}</b> {t("new_items")} ·{" "}
              <b className="reading text-ink">{o.last_cycle.signals}</b> {t("signals_n")} · <b className="reading text-ink">{o.last_cycle.stories_new}</b> {t("stories_n")} ·{" "}
              <b className="reading text-ink">{o.last_cycle.corroborations}</b> {t("corroborations")}
            </span>
          </>
        ) : (
          <span>{t("no_cycle")}</span>
        )}
        <span className="ml-auto flex items-center gap-3">
          {notice && <span className="text-river">{notice}</span>}
          <button className="btn btn-quiet" onClick={() => void runCycle()}>
            {t("run_cycle")}
          </button>
        </span>
      </div>

      {/* digest lead */}
      {o.latest_digest && (
        <div className="mt-6 grid md:grid-cols-[1fr_auto] gap-4 items-end">
          <div>
            <div className="eyebrow">
              {t("digest_lead")} · {fmtDate(o.latest_digest.created_at, lang)}
            </div>
            <p className="display text-[1.35rem] md:text-[1.6rem] leading-snug mt-1 max-w-[62ch]">{pick(o.latest_digest, "lead", lang)}</p>
          </div>
          <Link to="/digest" className="btn">
            {t("read_digest")} →
          </Link>
        </div>
      )}

      {/* six layers */}
      <Section eyebrow={t("radar_lead")} title={undefined} right={<span className="eyebrow">{t("ranked_by_score")}</span>}>
        {cols.error && <ErrorBox error={cols.error} retry={cols.reload} />}
        <div className="grid gap-x-6 gap-y-8 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-6">
          {LAYERS.map((layer) => {
            const v = byLayer[layer];
            const items = cols.data?.[layer] ?? [];
            return (
              <div key={layer} className="min-w-0">
                <header className="flex items-baseline justify-between gap-2 pb-1 border-b-2" style={{ borderColor: LAYER_COLOR[layer] }}>
                  <h3 className="text-sm font-medium inline-flex items-center gap-1.5">
                    <LayerDot layer={layer} />
                    {meta?.layers[layer]?.[lang] ?? layer}
                  </h3>
                  <span className="reading text-[0.66rem] text-ink-3" title={`${t("week")} / ${t("month")}`}>
                    {v?.count_7d ?? 0} / {v?.count_30d ?? 0}
                  </span>
                </header>
                {items.length === 0 ? (
                  <Empty />
                ) : (
                  items.map((s) => <SignalRow key={s.id} s={s} meta={meta} showLayer={false} compact />)
                )}
                <Link to={`/signals?layer=${layer}`} className="block mt-2 text-xs text-ink-3 hover:text-ink">
                  {t("more_in_layer")} →
                </Link>
              </div>
            );
          })}
        </div>
      </Section>

      <div className="grid gap-8 lg:grid-cols-2">
        <Section eyebrow={t("movers")}>
          {o.movers.length === 0 ? (
            <Empty />
          ) : (
            <table className="data text-sm">
              <tbody>
                {o.movers.map((m) => (
                  <tr key={`${m.topic}-${m.layer}`}>
                    <td className="w-4">
                      <LayerDot layer={m.layer} />
                    </td>
                    <td>
                      <Link to={`/signals?topic=${encodeURIComponent(m.topic)}&layer=${m.layer}`} className="hover:underline">
                        {meta?.topics[m.topic]?.[lang] ?? m.topic}
                      </Link>
                      <span className="text-xs text-ink-3 ml-2">{meta?.layers[m.layer]?.[lang] ?? m.layer}</span>
                    </td>
                    <td className="reading text-right text-ink-3">
                      {m.previous} → {m.current}
                    </td>
                    <td className={`reading text-right ${m.delta > 0 ? "text-river" : m.delta < 0 ? "text-warn" : ""}`}>
                      {m.delta > 0 ? "+" : ""}
                      {m.delta}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Section>

        <Section eyebrow={t("next_deadlines")}>
          {o.next_events.length === 0 ? (
            <Empty k="no_events" />
          ) : (
            <table className="data text-sm">
              <tbody>
                {o.next_events.map((e) => (
                  <tr key={e.id}>
                    <td className="reading whitespace-nowrap">
                      {e.deadline ? (
                        <span className="text-warn">
                          {t("deadline")} {fmtDate(e.deadline, lang)}
                        </span>
                      ) : (
                        fmtDate(e.start_date, lang)
                      )}
                    </td>
                    <td>
                      {e.name}
                      {e.signal && pick(e.signal, "headline", lang) !== e.name && (
                        <div className="text-xs text-ink-3 inline-flex items-center gap-1.5 ml-2">
                          <LayerDot layer={e.signal.layer} />
                          {pick(e.signal, "headline", lang)}
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <Link to="/calendar" className="block mt-2 text-xs text-ink-3 hover:text-ink">
            {t("nav_calendar")} →
          </Link>
        </Section>
      </div>
    </div>
  );
}

function sinceDays(n: number): string {
  const d = new Date(Date.now() - n * 86400000);
  return d.toISOString().slice(0, 10);
}
