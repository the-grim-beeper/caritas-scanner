import { api } from "../api";
import { ErrorBox, LayerDot, Loading, Section } from "../components/ui";
import { fmtDate, useLang, useT } from "../i18n";
import { LAYERS, type Meta, type SourceOut } from "../types";
import { useAsync } from "../useAsync";

export function Coverage({ meta }: { meta: Meta | null }) {
  const { lang } = useLang();
  const t = useT();
  const res = useAsync(() => api.sources(), []);
  const cycles = useAsync(() => api.cycles(), []);
  if (res.error) return <ErrorBox error={res.error} retry={res.reload} />;
  if (!res.data) return <Loading />;
  const items = res.data.items;
  const collected = items.filter((s) => s.collect).length;

  return (
    <div className="fade-in">
      <p className="eyebrow pt-4">{t("cov_lead")}</p>
      <p className="reading text-sm mt-1">
        {collected} / {items.length} {t("collected")}
        {meta && (
          <span className="text-ink-3">
            {" "}
            · {t("models")}: {meta.extraction_model} · {meta.digest_model} · {meta.embedding_model.split("/").pop()}
          </span>
        )}
      </p>

      {LAYERS.map((layer) => {
        const rows = items.filter((s) => s.layer === layer);
        return (
          <Section
            key={layer}
            title={
              <span className="inline-flex items-center gap-2">
                <LayerDot layer={layer} />
                {meta?.layers[layer]?.[lang] ?? layer}
              </span>
            }
            right={
              <span className="reading text-xs text-ink-3">
                {rows.filter((r) => r.collect).length} / {rows.length} {t("collected")}
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

      <Section eyebrow={t("cycles")}>
        <div className="overflow-x-auto">
          <table className="data text-sm min-w-[760px]">
            <thead>
              <tr>
                <th>{t("last_cycle")}</th>
                <th>mode</th>
                <th className="text-right">{t("items_fetched")}</th>
                <th className="text-right">{t("new_items")}</th>
                <th className="text-right">{t("signals_n")}</th>
                <th className="text-right">{t("stories_n")}</th>
                <th className="text-right">{t("corroborations")}</th>
                <th>digest</th>
              </tr>
            </thead>
            <tbody>
              {cycles.data?.items.map((c) => (
                <tr key={c.id}>
                  <td className="reading">{fmtDate(c.started_at, lang, true)}</td>
                  <td className="reading">{c.mode}</td>
                  <td className="reading text-right">{c.items_fetched}</td>
                  <td className="reading text-right">{c.items_new}</td>
                  <td className="reading text-right">{c.signals}</td>
                  <td className="reading text-right">{c.stories_new}</td>
                  <td className="reading text-right">{c.corroborations}</td>
                  <td className="reading">{c.error ? <span className="text-warn">{c.error}</span> : c.digest_ok === null ? "—" : c.digest_ok ? "ok" : "failed"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>
    </div>
  );
}

function Row({ s }: { s: SourceOut }) {
  const { lang } = useLang();
  const t = useT();
  const link = s.url ?? s.homepage;
  return (
    <tr className={s.collect ? "" : "text-ink-3"}>
      <td>
        {link ? (
          <a href={link} target="_blank" rel="noreferrer" className="hover:underline">
            {s.name}
          </a>
        ) : (
          s.name
        )}
        {s.priority === "core" && <span className="eyebrow ml-2">core</span>}
      </td>
      <td className="reading">{s.method}</td>
      <td className="reading">{s.authority}</td>
      <td className="reading">
        {s.collect ? (s.status === "quarantined" ? <span className="text-warn">{t("quarantined")}</span> : t("active")) : t("not_collected")}
      </td>
      <td className="reading text-right">{s.collect ? s.items_7d : "—"}</td>
      <td className="reading text-right">{s.collect ? s.signals_7d : "—"}</td>
      <td className="reading whitespace-nowrap">{s.collect ? fmtDate(s.last_ok_at, lang, true) : "—"}</td>
      <td className="text-xs max-w-[280px]">{s.collect ? s.last_error && <span className="text-warn">{s.last_error}</span> : s.not_collected_reason}</td>
    </tr>
  );
}
