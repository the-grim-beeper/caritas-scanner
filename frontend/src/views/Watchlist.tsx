import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { SignalRow } from "../components/SignalRow";
import { Empty, ErrorBox, Loading, Section, Sparkline } from "../components/ui";
import { useT, type Key } from "../i18n";
import type { Meta } from "../types";
import { useAsync } from "../useAsync";

const KINDS = ["place", "project", "organisation", "fund"] as const;

export function Watchlist({ meta }: { meta: Meta | null }) {
  const { slug } = useParams();
  if (slug) return <EntityPage slug={slug} meta={meta} />;
  return <EntityList />;
}

function EntityList() {
  const t = useT();
  const res = useAsync(() => api.entities(), []);
  if (res.error) return <ErrorBox error={res.error} retry={res.reload} />;
  if (!res.data) return <Loading />;
  const items = res.data.items;
  return (
    <div className="fade-in">
      <p className="eyebrow pt-4">{t("watch_lead")}</p>
      <div className="grid gap-x-8 md:grid-cols-2 xl:grid-cols-4">
        {KINDS.map((kind) => {
          const rows = items.filter((e) => e.kind === kind && ((e.count_90d ?? 0) > 0 || e.seeded)).slice(0, 40);
          return (
            <Section key={kind} eyebrow={t(`kind_${kind}` as Key)}>
              {rows.length === 0 ? (
                <Empty />
              ) : (
                <table className="data text-sm">
                  <tbody>
                    {rows.map((e) => (
                      <tr key={e.slug}>
                        <td>
                          <Link to={`/watchlist/${e.slug}`} className="hover:underline">
                            {e.name}
                          </Link>
                          {!e.seeded && <span className="eyebrow ml-2">{t("discovered")}</span>}
                        </td>
                        <td className="reading text-right text-ink-3 whitespace-nowrap" title="30 d / 90 d">
                          {e.count_30d} / {e.count_90d}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Section>
          );
        })}
      </div>
    </div>
  );
}

function EntityPage({ slug, meta }: { slug: string; meta: Meta | null }) {
  const t = useT();
  const res = useAsync(() => api.entity(slug), [slug]);
  if (res.error) return <ErrorBox error={res.error} retry={res.reload} />;
  if (!res.data) return <Loading />;
  const e = res.data;
  const weekly = e.weekly.map(([, n]) => n);
  return (
    <div className="fade-in">
      <Link to="/watchlist" className="eyebrow inline-block pt-4 hover:text-ink">
        ← {t("back")}
      </Link>
      <header className="mt-2 flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="eyebrow">
            {t(`kind_${e.kind}` as Key)} · {e.seeded ? t("seeded") : t("discovered")}
          </div>
          <h2 className="display text-2xl">{e.name}</h2>
          {e.aliases.length > 0 && (
            <p className="text-xs text-ink-3 mt-1">
              {t("aliases")}: {e.aliases.join(", ")}
            </p>
          )}
        </div>
        <div className="text-right">
          <Sparkline values={weekly} width={140} height={28} />
          <div className="reading text-xs text-ink-3">{e.timeline.length} {t("stories_n")}</div>
        </div>
      </header>
      <Section eyebrow={t("timeline")}>
        {e.timeline.length === 0 ? <Empty /> : e.timeline.map((s) => <SignalRow key={s.id} s={s} meta={meta} />)}
      </Section>
    </div>
  );
}
