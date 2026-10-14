import { api } from "../api";
import { SuggestionsPanel } from "../components/SuggestionsPanel";
import { ErrorBox, Fail, LayerDot, Loading, Section } from "../components/ui";
import { layerLabel, METHOD_LABELS, MUNICIPALITIES, placeMatches, safeUrl } from "../domain";
import { fmtDate, useLang, useT } from "../i18n";
import { LAYERS, type Meta, type SourceOut } from "../types";
import { useAsync } from "../useAsync";

export function Quellen({ meta }: { meta: Meta | null }) {
  const { lang } = useLang();
  const t = useT();
  const res = useAsync(() => api.sources(), []);
  const cycles = useAsync(() => api.cycles(), []);
  if (res.error) return <ErrorBox error={res.error} retry={res.reload} />;
  if (!res.data) return <Loading />;
  const items = res.data.items;
  const collected = items.filter((s) => s.collect).length;
  const models = meta ? [meta.extraction_model, meta.judge_model, meta.digest_model].filter(Boolean) : [];

  return (
    <div className="fade-in">
      <p className="serif text-[1.1rem] leading-snug pt-6 max-w-[70ch]">{t("src_lead")}</p>
      <p className="text-sm mt-1 num">
        {t("src_of_collected", { a: collected, b: items.length })}
        {models.length > 0 && (
          <span className="text-ink-3">
            . {t("models")}: {[...new Set(models)].join(", ")}
          </span>
        )}
      </p>

      <SuggestionsPanel meta={meta} />

      <MunicipalityGrid items={items} />

      {LAYERS.map((layer) => {
        const rows = items.filter((s) => s.layer === layer);
        if (rows.length === 0) return null;
        return (
          <Section
            key={layer}
            title={
              <span className="inline-flex items-center gap-2">
                <LayerDot layer={layer} />
                {layerLabel(layer, meta, lang)}
              </span>
            }
            right={
              <span className="text-xs text-ink-3 num">
                {rows.filter((r) => r.collect).length} / {rows.length} {t("src_collected")}
              </span>
            }
          >
            <div className="overflow-x-auto">
              <table className="data text-sm min-w-[880px]">
                <thead>
                  <tr>
                    <th>{t("source")}</th>
                    <th>{t("method")}</th>
                    <th>{t("authority")}</th>
                    <th>{t("status")}</th>
                    <th className="text-right">{t("items_7d")}</th>
                    <th className="text-right">{t("signals_7d")}</th>
                    <th>{t("last_ok")}</th>
                    <th>{t("reason")}</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((s) => (
                    <Row key={s.slug} s={s} />
                  ))}
                </tbody>
              </table>
            </div>
          </Section>
        );
      })}

      <Section title={t("cycles")}>
        {cycles.error ? (
          <Fail error={cycles.error} retry={cycles.reload} emptyKey="no_cycle" />
        ) : (
          <div className="overflow-x-auto">
            <table className="data text-sm min-w-[760px]">
              <thead>
                <tr>
                  <th>{t("last_cycle")}</th>
                  <th>{t("mode")}</th>
                  <th className="text-right">{t("items_fetched")}</th>
                  <th className="text-right">{t("new_items")}</th>
                  <th className="text-right">{t("signals_n")}</th>
                  <th className="text-right">{t("judgements_n")}</th>
                  <th>{t("result")}</th>
                </tr>
              </thead>
              <tbody>
                {cycles.data?.items.map((c) => (
                  <tr key={c.id}>
                    <td className="whitespace-nowrap">{fmtDate(c.started_at, lang, { time: true })}</td>
                    <td>{c.mode}</td>
                    <td className="text-right num">{c.items_fetched}</td>
                    <td className="text-right num">{c.items_new}</td>
                    <td className="text-right num">{c.signals}</td>
                    <td className="text-right num">{c.judgements ?? "–"}</td>
                    <td>{c.error ? <span className="font-medium">{c.error}</span> : c.finished_at ? "ok" : "…"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>
    </div>
  );
}

/** The 17 municipalities: is each one covered by a verified source of its own, or only by search? */
function MunicipalityGrid({ items }: { items: SourceOut[] }) {
  const { lang } = useLang();
  const t = useT();
  const has30 = items.some((s) => typeof s.items_30d === "number");
  return (
    <Section title={t("src_municipalities")} hint={t("src_municipalities_hint")}>
      <ul className="grid gap-x-5 gap-y-5 grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
        {MUNICIPALITIES.map((m) => {
          const mine = items.filter((s) => (s.places ?? []).some((p) => placeMatches(p, m)));
          const coll = mine.filter((s) => s.collect);
          const direct = coll.some((s) => s.method !== "query");
          const status = direct ? "direct" : coll.length > 0 ? "query" : "none";
          const n = coll.reduce((acc, s) => acc + (has30 ? (s.items_30d ?? 0) : s.items_7d), 0);
          const methods = [...new Set(coll.map((s) => s.method))];
          return (
            <li key={m.slug} className={`pt-2 ${status === "direct" ? "border-t-2 border-ink" : status === "query" ? "border-t-2 border-ink-3" : "border-t-2 border-dashed border-ink-3"}`}>
              <h3 className={`display text-[1.05rem] leading-tight ${status === "none" ? "text-ink-3" : ""}`}>{m.name}</h3>
              <p className={`text-xs mt-0.5 ${status === "direct" ? "text-fir" : "text-ink-3"}`}>
                {status === "direct" ? t("src_direct") : status === "query" ? t("src_query_only") : t("src_none")}
              </p>
              <dl className="mt-2 text-sm grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5 items-baseline">
                <dt className="num font-semibold text-right">{coll.length}</dt>
                <dd className="text-xs text-ink-3">{t("src_n_sources")}</dd>
                <dt className="num font-semibold text-right">{n}</dt>
                <dd className="text-xs text-ink-3">{has30 ? t("src_items_30") : t("src_items_7")}</dd>
              </dl>
              {methods.length > 0 && (
                <p className="mt-1.5 flex flex-wrap gap-1">
                  {methods.map((me) => (
                    <span key={me} className="text-[0.7rem] border border-rule px-1 text-ink-2">
                      {METHOD_LABELS[me]?.[lang] ?? me}
                    </span>
                  ))}
                </p>
              )}
              {coll.length > 0 && (
                <ul className="mt-1.5 text-xs text-ink-3 space-y-0.5">
                  {coll.slice(0, 3).map((s) => (
                    <li key={s.slug} className="line-clamp-1" title={s.name}>
                      {s.url || s.homepage ? (
                        <a href={safeUrl(s.url || s.homepage)} target="_blank" rel="noreferrer" className="link">
                          {s.name}
                        </a>
                      ) : (
                        s.name
                      )}
                    </li>
                  ))}
                  {coll.length > 3 && <li>+{coll.length - 3}</li>}
                </ul>
              )}
            </li>
          );
        })}
      </ul>
    </Section>
  );
}

function Row({ s }: { s: SourceOut }) {
  const { lang } = useLang();
  const t = useT();
  const link = s.url ?? s.homepage;
  return (
    <tr id={`src-${s.slug}`} className={s.collect ? "" : "text-ink-3"}>
      <td>
        {link ? (
          <a href={safeUrl(link)} target="_blank" rel="noreferrer" className="link">
            {s.name}
          </a>
        ) : (
          s.name
        )}
        {s.priority === "core" && <span className="label ml-2">{t("core")}</span>}
        {s.origin === "suggestion" && <span className="label ml-2">{t("src_suggestion_badge")}</span>}
      </td>
      <td>{METHOD_LABELS[s.method]?.[lang] ?? s.method}</td>
      <td>{s.authority}</td>
      <td>
        {s.collect ? (s.status === "quarantined" ? <span className="font-medium">{t("quarantined")}</span> : t("active")) : t("src_not_collected")}
      </td>
      <td className="text-right num">{s.collect ? s.items_7d : "–"}</td>
      <td className="text-right num">{s.collect ? s.signals_7d : "–"}</td>
      <td className="whitespace-nowrap">{s.collect ? fmtDate(s.last_ok_at, lang, { time: true }) : "–"}</td>
      <td className="text-xs max-w-[280px]">{s.collect ? s.last_error && <span className="text-ink">{s.last_error}</span> : s.not_collected_reason}</td>
    </tr>
  );
}
