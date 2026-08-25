import { NavLink } from "react-router-dom";
import { fmtDate, useLang, useT } from "../i18n";
import type { Meta } from "../types";

const NAV = [
  ["/", "nav_radar"],
  ["/digest", "nav_digest"],
  ["/signals", "nav_signals"],
  ["/watchlist", "nav_watchlist"],
  ["/calendar", "nav_calendar"],
  ["/coverage", "nav_coverage"],
] as const;

export function Masthead({ meta }: { meta: Meta | null }) {
  const { lang, setLang } = useLang();
  const t = useT();
  const mock = meta?.mode === "mock";
  return (
    <header className="border-b-2 border-ink">
      <div className="max-w-[1400px] mx-auto px-4 md:px-6 pt-4 pb-2 flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
        <div>
          <h1 className="display text-2xl md:text-[1.75rem] leading-none">{t("app_title")}</h1>
          <p className="text-xs text-ink-3 mt-1">{t("app_sub")}</p>
        </div>
        <div className="flex items-center gap-3 text-xs">
          {meta?.last_cycle?.finished_at && (
            <span className="reading text-ink-3">
              {t("last_cycle")} {fmtDate(meta.last_cycle.finished_at, lang, true)}
            </span>
          )}
          <span
            className={`reading px-1.5 py-[1px] border ${mock ? "border-warn text-warn" : "border-river text-river"}`}
            title={mock ? t("mode_mock_hint") : `${meta?.extraction_model} · ${meta?.digest_model}`}
          >
            {mock ? t("mode_mock") : t("mode_live")}
          </span>
          <div className="flex" role="group" aria-label="language">
            {(["en", "de"] as const).map((l) => (
              <button key={l} className="btn" aria-pressed={lang === l} onClick={() => setLang(l)}>
                {l.toUpperCase()}
              </button>
            ))}
          </div>
        </div>
      </div>
      <nav className="max-w-[1400px] mx-auto px-4 md:px-6 flex gap-5 overflow-x-auto text-sm">
        {NAV.map(([to, key]) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              `py-2 border-b-2 -mb-[2px] whitespace-nowrap ${isActive ? "border-ink font-medium" : "border-transparent text-ink-2 hover:text-ink"}`
            }
          >
            {t(key)}
          </NavLink>
        ))}
      </nav>
    </header>
  );
}
