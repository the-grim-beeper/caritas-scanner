import { useState } from "react";
import { api, errorDetail, HttpError } from "../api";
import { layerLabel, METHOD_LABELS, safeUrl } from "../domain";
import { daysUntil, fmtDate, pick, useLang, useT, type Key } from "../i18n";
import type { Meta, Suggestion } from "../types";
import { useAsync } from "../useAsync";
import { Empty, Fail, LayerDot, Loading, Section } from "./ui";

const HISTORY_STATUS_KEY: Record<string, Key> = {
  adopted: "src_status_adopted",
  declined: "src_status_declined",
  rejected: "src_status_rejected",
  failed: "src_status_failed",
};

/**
 * The weekly source-discovery run proposes new sources; a pending one is adopted automatically
 * after seven days unless declined. This panel shows what is open, lets staff act on it, and
 * keeps a collapsed record of what was already decided (Task 9's /api/suggestions).
 */
export function SuggestionsPanel({ meta }: { meta: Meta | null }) {
  const t = useT();
  const res = useAsync(() => api.suggestions("all"), []);
  const [running, setRunning] = useState(false);
  const [runNotice, setRunNotice] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [busy, setBusy] = useState<Record<string, boolean>>({});
  const [rowError, setRowError] = useState<Record<string, string>>({});

  async function run() {
    setRunning(true);
    setRunNotice(null);
    try {
      const r = await api.runSuggestions();
      setRunNotice(t("src_run_result", { proposed: r.proposed, pending_new: r.pending_new, rejected: r.rejected, known: r.known }));
      res.reload();
    } catch (e) {
      setRunNotice(e instanceof HttpError && e.status === 409 ? t("src_run_busy") : errorDetail(e));
    } finally {
      setRunning(false);
    }
  }

  async function act(id: string, kind: "decline" | "adopt") {
    setBusy((b) => ({ ...b, [id]: true }));
    setRowError((r) => ({ ...r, [id]: "" }));
    try {
      if (kind === "decline") await api.declineSuggestion(id);
      else await api.adoptSuggestion(id);
      res.reload();
    } catch (e) {
      const msg = e instanceof HttpError && e.status === 409 && !e.detail ? t("src_conflict") : errorDetail(e);
      setRowError((r) => ({ ...r, [id]: msg }));
    } finally {
      setBusy((b) => ({ ...b, [id]: false }));
    }
  }

  const runner = (
    <div className="flex flex-wrap items-center justify-end gap-3 max-w-full">
      {runNotice && <p className="text-xs text-ink-3 max-w-[38ch]">{runNotice}</p>}
      <button className="btn btn-quiet" onClick={() => void run()} disabled={running}>
        {running ? t("src_run_running") : t("src_run_suggestions")}
      </button>
    </div>
  );

  if (res.error) {
    return (
      <Section title={t("src_suggestions")} hint={t("src_suggestions_rule")} right={runner}>
        <Fail error={res.error} retry={res.reload} emptyKey="src_suggestions_none" />
      </Section>
    );
  }
  if (!res.data) {
    return (
      <Section title={t("src_suggestions")} hint={t("src_suggestions_rule")}>
        <Loading />
      </Section>
    );
  }

  const pending = res.data
    .filter((s) => s.status === "pending")
    .sort((a, b) => (a.adopt_after ?? a.suggested_at).localeCompare(b.adopt_after ?? b.suggested_at));
  const history = res.data
    .filter((s) => s.status !== "pending")
    .sort((a, b) => (b.resolved_at ?? b.suggested_at).localeCompare(a.resolved_at ?? a.suggested_at));

  return (
    <Section title={t("src_suggestions")} hint={t("src_suggestions_rule")} right={runner}>
      {pending.length === 0 ? (
        <Empty k="src_suggestions_none" />
      ) : (
        <ul className="space-y-4">
          {pending.map((s) => (
            <SuggestionCard
              key={s.id}
              s={s}
              meta={meta}
              busy={!!busy[s.id]}
              error={rowError[s.id]}
              onDecline={() => void act(s.id, "decline")}
              onAdopt={() => void act(s.id, "adopt")}
            />
          ))}
        </ul>
      )}

      {history.length > 0 && (
        <div className="mt-5">
          <button className="btn btn-quiet" onClick={() => setShowHistory((v) => !v)} aria-expanded={showHistory}>
            {showHistory ? t("src_hide_history") : t("src_show_history")}
          </button>
          {showHistory && (
            <ul className="mt-3 text-sm max-w-[70ch]">
              {history.map((s) => (
                <HistoryRow key={s.id} s={s} />
              ))}
            </ul>
          )}
        </div>
      )}
    </Section>
  );
}

function SuggestionCard({
  s,
  meta,
  busy,
  error,
  onDecline,
  onAdopt,
}: {
  s: Suggestion;
  meta: Meta | null;
  busy: boolean;
  error: string | undefined;
  onDecline: () => void;
  onAdopt: () => void;
}) {
  const { lang } = useLang();
  const t = useT();
  const link = s.url ?? s.feed_url;
  const days = daysUntil(s.adopt_after);
  const adoptText =
    days === null ? null : days <= 0 ? t("src_adopt_today") : days === 1 ? t("src_adopt_in_1", { date: fmtDate(s.adopt_after, lang, { weekday: true }) }) : t("src_adopt_in_n", { date: fmtDate(s.adopt_after, lang, { weekday: true }), n: days });

  return (
    <li className="border border-rule p-4">
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1">
        <div className="min-w-0">
          <h3 className="font-semibold leading-snug">
            {link ? (
              <a href={safeUrl(link)} target="_blank" rel="noreferrer" className="link">
                {s.name}
              </a>
            ) : (
              s.name
            )}
          </h3>
          <p className="text-xs text-ink-3 mt-0.5 flex items-center gap-1.5 flex-wrap">
            <LayerDot layer={s.layer} />
            {layerLabel(s.layer, meta, lang)}
            {s.places && s.places.length > 0 && <span>· {s.places.join(", ")}</span>}
          </p>
        </div>
        {adoptText && <p className="text-xs text-ink-3 text-right whitespace-nowrap">{adoptText}</p>}
      </div>

      <p className="text-sm mt-2 max-w-[70ch] leading-relaxed">{pick(s, "rationale", lang)}</p>

      <p className="text-xs text-ink-3 mt-1.5 num">
        {METHOD_LABELS[s.method]?.[lang] ?? s.method}
        {typeof s.items_at_check === "number" && (
          <>
            {" "}
            · {s.items_at_check} {t("src_items_at_check")}
          </>
        )}
      </p>

      {error && <p className="text-xs mt-2 font-medium max-w-[50ch]">{error}</p>}

      <div className="mt-3 flex gap-2">
        <button className="btn btn-quiet" onClick={onDecline} disabled={busy}>
          {t("src_decline")}
        </button>
        <button className="btn btn-fir" onClick={onAdopt} disabled={busy}>
          {t("src_adopt_now")}
        </button>
      </div>
    </li>
  );
}

function HistoryRow({ s }: { s: Suggestion }) {
  const { lang } = useLang();
  const t = useT();
  return (
    <li className="rule py-2 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
      <span className="min-w-0">
        {s.status === "adopted" && s.source_slug ? (
          <a href={`#src-${s.source_slug}`} className="link">
            {s.name}
          </a>
        ) : (
          s.name
        )}
        <span className="text-xs text-ink-3 ml-2">
          {t(HISTORY_STATUS_KEY[s.status] ?? "src_status_rejected")}
          {s.reason && <> · {s.reason}</>}
        </span>
      </span>
      <span className="text-xs text-ink-3 num whitespace-nowrap">{fmtDate(s.resolved_at ?? s.suggested_at, lang)}</span>
    </li>
  );
}
