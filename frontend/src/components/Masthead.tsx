import { NavLink } from "react-router-dom";
import { fmtDate, useLang, useT, weekLabel } from "../i18n";
import type { Meta } from "../types";

const NAV = [
  ["/", "nav_lage"],
  ["/fragen", "nav_fragen"],
  ["/netz", "nav_netz"],
  ["/lagebericht", "nav_bericht"],
  ["/signale", "nav_signale"],
  ["/kalender", "nav_kalender"],
  ["/quellen", "nav_quellen"],
] as const;

export function Masthead({ meta }: { meta: Meta | null }) {
  const { lang, setLang } = useLang();
  const t = useT();
  const mock = meta?.mode === "mock";
  const wk = weekLabel(new Date(), lang);
  return (
    <header className="border-b-2 border-ink">
      <div className="max-w-[1400px] mx-auto px-4 md:px-6 pt-5 pb-3 grid gap-x-8 gap-y-3 md:grid-cols-[1fr_auto] items-end">
        <div className="min-w-0">
          <h1 className="display text-[1.7rem] md:text-[2.2rem] leading-[1.05]">
            <span className="hidden sm:inline">{t("app_title")}</span>
            <span className="sm:hidden">{t("app_short")}</span>
          </h1>
          <p className="text-sm text-ink-2 mt-1.5 max-w-[70ch]">{t("app_sub")}</p>
        </div>
        <div className="flex flex-wrap items-end gap-x-5 gap-y-2 md:justify-end">
          <div className="md:text-right leading-tight">
            <div className="serif text-lg font-semibold">{wk.kw}</div>
            <div className="text-xs text-ink-3">{wk.range}</div>
          </div>
          <div className="flex items-center gap-3 text-xs">
            {meta?.last_cycle?.finished_at && (
              <span className="text-ink-3 hidden lg:inline">
                {t("last_cycle")} {fmtDate(meta.last_cycle.finished_at, lang, { time: true })}
              </span>
            )}
            {meta && (
              <span
                className={`px-1.5 py-[1px] border ${mock ? "border-ink-3 text-ink-3" : "border-fir text-fir"}`}
                title={mock ? t("mode_mock_hint") : [meta.extraction_model, meta.judge_model, meta.digest_model].filter(Boolean).join(", ")}
              >
                {mock ? t("mode_mock") : t("mode_live")}
              </span>
            )}
            <div className="flex" role="group" aria-label={lang === "de" ? "Sprache" : "Language"}>
              {(["de", "en"] as const).map((l) => (
                <button key={l} className="btn !px-2 !py-0.5" aria-pressed={lang === l} onClick={() => setLang(l)} lang={l}>
                  {l.toUpperCase()}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
      <nav className="max-w-[1400px] mx-auto px-4 md:px-6 flex gap-6 overflow-x-auto text-[0.95rem]">
        {NAV.map(([to, key]) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              `py-2 border-b-[3px] -mb-[2px] whitespace-nowrap ${isActive ? "border-fir text-ink font-semibold" : "border-transparent text-ink-2 hover:text-fir"}`
            }
          >
            {t(key)}
          </NavLink>
        ))}
      </nav>
    </header>
  );
}
