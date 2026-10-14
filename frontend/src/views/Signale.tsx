import { useSearchParams } from "react-router-dom";
import { api } from "../api";
import { SignalRow } from "../components/SignalRow";
import { Empty, ErrorBox, Loading } from "../components/ui";
import { layerLabel, slugName, topicGroups, topicLabel } from "../domain";
import { useLang, useT } from "../i18n";
import { LAYERS, type Meta } from "../types";
import { useAsync } from "../useAsync";

export function Signale({ meta }: { meta: Meta | null }) {
  const { lang } = useLang();
  const t = useT();
  const [sp, setSp] = useSearchParams();
  const layer = sp.get("layer") ?? "";
  const topic = sp.get("topic") ?? "";
  const type = sp.get("type") ?? "";
  const q = sp.get("q") ?? "";
  const minScore = sp.get("min_score") ?? "";
  const sort = sp.get("sort") ?? "published";
  const page = Number(sp.get("page") ?? "1");
  const entity = sp.get("entity") ?? "";

  const res = useAsync(
    () => api.signals({ layer, topic, type, q, min_score: minScore, sort, page, per_page: 50, entity }),
    [layer, topic, type, q, minScore, sort, page, entity],
  );

  function set(k: string, v: string) {
    const next = new URLSearchParams(sp);
    if (v) next.set(k, v);
    else next.delete(k);
    if (k !== "page") next.delete("page");
    setSp(next);
  }

  const pages = res.data ? Math.max(1, Math.ceil(res.data.total / res.data.per_page)) : 1;
  const groups = topicGroups(meta, lang);
  // A topic in the URL that meta does not list (older or newer vocabulary) still shows as selected.
  const topicKnown = !topic || groups.some((g) => g.codes.includes(topic));

  return (
    <div className="fade-in">
      <div className="py-4 flex flex-wrap items-end gap-3 text-sm border-b border-rule">
        <label className="grid gap-1">
          <span className="label">{t("layer")}</span>
          <select value={layer} onChange={(e) => set("layer", e.target.value)}>
            <option value="">{t("all")}</option>
            {LAYERS.map((l) => (
              <option key={l} value={l}>
                {layerLabel(l, meta, lang)}
              </option>
            ))}
          </select>
        </label>
        <label className="grid gap-1">
          <span className="label">{t("topics")}</span>
          <select value={topic} onChange={(e) => set("topic", e.target.value)} className="max-w-[260px]">
            <option value="">{t("all")}</option>
            {!topicKnown && <option value={topic}>{topic}</option>}
            {groups.map((g) =>
              g.family ? (
                <optgroup key={g.family} label={g.label}>
                  {g.codes.map((code) => (
                    <option key={code} value={code}>
                      {topicLabel(code, meta, lang)}
                    </option>
                  ))}
                </optgroup>
              ) : (
                g.codes.map((code) => (
                  <option key={code} value={code}>
                    {topicLabel(code, meta, lang)}
                  </option>
                ))
              ),
            )}
          </select>
        </label>
        <label className="grid gap-1">
          <span className="label">{t("type")}</span>
          <select value={type} onChange={(e) => set("type", e.target.value)}>
            <option value="">{t("all")}</option>
            {Object.entries(meta?.signal_types ?? {}).map(([code, lbl]) => (
              <option key={code} value={code}>
                {lbl[lang]}
              </option>
            ))}
          </select>
        </label>
        <label className="grid gap-1">
          <span className="label">{t("min_score")}</span>
          <select value={minScore} onChange={(e) => set("min_score", e.target.value)}>
            <option value="">{t("all")}</option>
            {["0.05", "0.1", "0.2", "0.3", "0.5"].map((v) => (
              <option key={v} value={v}>
                ≥ {lang === "de" ? v.replace(".", ",") : v}
              </option>
            ))}
          </select>
        </label>
        <label className="grid gap-1 flex-1 min-w-[180px]">
          <span className="label">{t("search")}</span>
          <input
            key={q}
            type="search"
            defaultValue={q}
            onKeyDown={(e) => e.key === "Enter" && set("q", (e.target as HTMLInputElement).value)}
            onBlur={(e) => e.target.value !== q && set("q", e.target.value)}
          />
        </label>
        <div className="flex" role="group">
          <button className="btn" aria-pressed={sort === "published"} onClick={() => set("sort", "published")}>
            {t("sort_published")}
          </button>
          <button className="btn" aria-pressed={sort === "score"} onClick={() => set("sort", "score")}>
            {t("sort_score")}
          </button>
        </div>
        {entity && (
          <button className="btn btn-quiet" onClick={() => set("entity", "")} title={t("entity_filter")}>
            {slugName(entity)} ×
          </button>
        )}
      </div>

      {res.error && <ErrorBox error={res.error} retry={res.reload} />}
      {res.loading && !res.data && <Loading />}
      {res.data && (
        <>
          <p className="label py-2 num">
            {res.data.total} {t("results")}
          </p>
          {res.data.items.length === 0 ? <Empty /> : res.data.items.map((s) => <SignalRow key={s.id} s={s} meta={meta} />)}
          {pages > 1 && (
            <div className="flex items-center gap-3 py-4 text-xs">
              <button className="btn btn-quiet" disabled={page <= 1} onClick={() => set("page", String(page - 1))}>
                {t("prev")}
              </button>
              <span className="num">
                {t("page")} {page} / {pages}
              </span>
              <button className="btn btn-quiet" disabled={page >= pages} onClick={() => set("page", String(page + 1))}>
                {t("next")}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
