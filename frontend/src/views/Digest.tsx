import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { SignalRow } from "../components/SignalRow";
import { Empty, ErrorBox, LayerDot, LayerName, Loading, Section } from "../components/ui";
import { fmtDate, pick, useLang, useT } from "../i18n";
import { LAYER_COLOR, type Meta } from "../types";
import { useAsync } from "../useAsync";

export function Digest({ meta }: { meta: Meta | null }) {
  const { id } = useParams();
  const { lang } = useLang();
  const t = useT();
  const [notice, setNotice] = useState<string | null>(null);
  const d = useAsync(() => api.digest(id ?? "latest"), [id]);
  const archive = useAsync(() => api.digests(), []);

  async function regenerate() {
    const r = await api.runDigest();
    setNotice(r.started ? t("cycle_started") : t("cycle_running"));
  }

  if (d.error) {
    if (d.error.message.startsWith("404")) return <Empty k="no_digest" />;
    return <ErrorBox error={d.error} retry={d.reload} />;
  }
  if (!d.data) return <Loading />;
  const g = d.data;

  return (
    <div className="fade-in grid gap-10 lg:grid-cols-[1fr_240px]">
      <article>
        <header className="pt-6">
          <div className="eyebrow flex flex-wrap gap-x-3">
            <span>
              {t("digest_title")} · {fmtDate(g.created_at, lang, true)}
            </span>
            <span>
              {t("written_by")} {g.model}
            </span>
          </div>
          <p className="display text-[1.5rem] md:text-[1.9rem] leading-snug mt-3 max-w-[60ch]">{pick(g, "lead", lang)}</p>
        </header>

        {g.chains.length > 0 && (
          <Section eyebrow={t("chains")} title={undefined}>
            <p className="text-xs text-ink-3 -mt-2 mb-3">{t("chains_hint")}</p>
            <div className="grid gap-6 md:grid-cols-2">
              {g.chains.map((c, i) => (
                <div key={i} className="border border-rule p-3">
                  <h3 className="font-medium text-sm mb-2">{pick(c, "title", lang)}</h3>
                  <ol className="relative ml-2 border-l border-ink pl-4 space-y-3">
                    {c.signals.map((s) => (
                      <li key={s.id} className="relative text-sm">
                        <span
                          className="absolute -left-[21px] top-1.5 w-2.5 h-2.5 rounded-full border-2 border-paper"
                          style={{ background: s.layer ? LAYER_COLOR[s.layer] : "#c9cdc6" }}
                        />
                        <div className="text-xs text-ink-3">
                          <LayerName layer={s.layer} meta={meta} /> · {s.source_name} · {fmtDate(s.published_at, lang)}
                        </div>
                        {pick(s, "headline", lang)}
                      </li>
                    ))}
                  </ol>
                </div>
              ))}
            </div>
          </Section>
        )}

        {g.sections.map((sec) => (
          <Section
            key={sec.layer}
            eyebrow={undefined}
            title={
              <span className="inline-flex items-center gap-2">
                <LayerDot layer={sec.layer} />
                {meta?.layers[sec.layer]?.[lang] ?? sec.layer}
              </span>
            }
          >
            {sec.items.map((it, i) =>
              it.signal ? (
                <div key={it.signal.id + i} className="grid gap-x-6 md:grid-cols-[1fr_1fr]">
                  <SignalRow s={it.signal} meta={meta} showLayer={false} />
                  <p className="text-sm leading-relaxed py-2.5 md:border-t md:border-rule md:pl-4 md:border-l">{pick(it, "note", lang)}</p>
                </div>
              ) : null,
            )}
          </Section>
        ))}

        {g.watch.length > 0 && (
          <Section eyebrow={t("watch")}>
            <table className="data text-sm">
              <tbody>
                {g.watch.map((w, i) =>
                  w.event ? (
                    <tr key={w.event.id + i}>
                      <td className="reading whitespace-nowrap">
                        {w.event.deadline ? (
                          <span className="text-warn">
                            {t("deadline")} {fmtDate(w.event.deadline, lang)}
                          </span>
                        ) : (
                          fmtDate(w.event.start_date, lang)
                        )}
                      </td>
                      <td>
                        <div>{w.event.name}</div>
                        <div className="text-ink-2 text-xs mt-0.5">{pick(w, "why", lang)}</div>
                      </td>
                    </tr>
                  ) : null,
                )}
              </tbody>
            </table>
          </Section>
        )}
      </article>

      <aside className="pt-6 text-sm">
        <div className="eyebrow mb-2">{t("digest_archive")}</div>
        <ul className="space-y-2">
          {archive.data?.items.map((a) => (
            <li key={a.id}>
              <Link to={`/digest/${a.id}`} className={`block hover:underline ${a.id === g.id ? "font-medium" : "text-ink-2"}`}>
                <span className="reading text-xs text-ink-3 block">{fmtDate(a.created_at, lang, true)}</span>
                <span className="line-clamp-2 text-xs">{pick(a, "lead", lang)}</span>
              </Link>
            </li>
          ))}
        </ul>
        <button className="btn btn-quiet mt-6" onClick={() => void regenerate()}>
          {t("regenerate")}
        </button>
        {notice && <p className="text-river text-xs mt-2">{notice}</p>}
      </aside>
    </div>
  );
}
