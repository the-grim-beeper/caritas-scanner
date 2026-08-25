import { api } from "../api";
import { Empty, ErrorBox, LayerDot, Loading } from "../components/ui";
import { fmtDate, pick, useLang, useT } from "../i18n";
import type { EventOut, Meta } from "../types";
import { useAsync } from "../useAsync";

function weekKey(iso: string): string {
  const d = new Date(iso);
  const day = (d.getDay() + 6) % 7;
  d.setDate(d.getDate() - day);
  return d.toISOString().slice(0, 10);
}

export function Calendar({ meta }: { meta: Meta | null }) {
  const { lang } = useLang();
  const t = useT();
  const res = useAsync(() => api.events(), []);
  if (res.error) return <ErrorBox error={res.error} retry={res.reload} />;
  if (!res.data) return <Loading />;

  const groups = new Map<string, EventOut[]>();
  for (const e of res.data.items) {
    const k = weekKey((e.deadline ?? e.start_date)!);
    groups.set(k, [...(groups.get(k) ?? []), e]);
  }

  return (
    <div className="fade-in">
      <p className="eyebrow pt-4">{t("cal_lead")}</p>
      {groups.size === 0 && <Empty k="no_events" />}
      {[...groups.entries()].map(([wk, evs]) => (
        <section key={wk} className="mt-6">
          <h2 className="rule-strong pt-1 reading text-xs text-ink-3">
            {lang === "de" ? "Woche ab" : "Week of"} {fmtDate(wk, lang)}
          </h2>
          <table className="data text-sm">
            <tbody>
              {evs.map((e) => (
                <tr key={e.id}>
                  <td className="reading whitespace-nowrap w-40">
                    {e.deadline ? (
                      <span className="text-warn">
                        {t("deadline")} {fmtDate(e.deadline, lang)}
                      </span>
                    ) : (
                      <span>
                        {fmtDate(e.start_date, lang)}
                        {e.end_date && e.end_date !== e.start_date ? ` – ${fmtDate(e.end_date, lang)}` : ""}
                      </span>
                    )}
                    {e.deadline && e.start_date && <div className="text-ink-3">{fmtDate(e.start_date, lang)}</div>}
                  </td>
                  <td>
                    <div className="font-medium">{e.name}</div>
                    <div className="text-xs text-ink-3 flex flex-wrap gap-x-3 mt-0.5">
                      {e.organizer && <span>{e.organizer}</span>}
                      {e.location && <span>{e.location}</span>}
                      {e.funding_program && (
                        <span>
                          {t("programme")}: {e.funding_program}
                        </span>
                      )}
                      {e.topic && <span>{meta?.topics[e.topic]?.[lang] ?? e.topic}</span>}
                    </div>
                    {e.signal && pick(e.signal, "headline", lang) !== e.name && (
                      <div className="text-xs mt-1 inline-flex items-center gap-1.5">
                        <LayerDot layer={e.signal.layer} />
                        {e.signal.url ? (
                          <a href={e.signal.url} target="_blank" rel="noreferrer" className="underline decoration-rule hover:decoration-ink">
                            {pick(e.signal, "headline", lang)}
                          </a>
                        ) : (
                          pick(e.signal, "headline", lang)
                        )}
                      </div>
                    )}
                  </td>
                  <td className="text-right whitespace-nowrap">
                    {e.registration_url && (
                      <a href={e.registration_url} target="_blank" rel="noreferrer" className="btn btn-quiet">
                        {t("register")} ↗
                      </a>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ))}
    </div>
  );
}
