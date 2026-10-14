import type { ReactNode } from "react";
import { api } from "../api";
import { Empty, ErrorBox, LayerDot, Loading, Section } from "../components/ui";
import { slugName, topicLabel, safeUrl } from "../domain";
import { eventKind, eventName, eventNote, eventRange, isFromReport, todayKey, upcoming } from "../events";
import { dayKey, fmtDate, mondayOf, parseDay, pick, useLang, useT, weekLabel } from "../i18n";
import type { EventOut, Meta } from "../types";
import { useAsync } from "../useAsync";

type Entry = { key: string; date: string; role: "deadline" | "event" | "start" | "end"; e: EventOut };

export function Kalender({ meta }: { meta: Meta | null }) {
  const { lang } = useLang();
  const t = useT();
  const res = useAsync(() => {
    const r = eventRange(400);
    return api.events(r.from, r.to);
  }, []);
  if (res.error) return <ErrorBox error={res.error} retry={res.reload} />;
  if (!res.data) return <Loading />;

  const items = upcoming(res.data.items);
  const today = todayKey();
  const windows = items.filter((e) => eventKind(e) === "window" && e.start_date && e.end_date);

  // Everything that happens on a day, filed under its week; windows contribute their start and end.
  const entries: Entry[] = [];
  for (const e of items) {
    const k = eventKind(e);
    if (k === "deadline") {
      const d = e.deadline ?? e.start_date;
      if (d) entries.push({ key: `${e.id}-d`, date: d.slice(0, 10), role: "deadline", e });
    } else if (k === "window") {
      if (e.start_date && e.start_date.slice(0, 10) >= today) entries.push({ key: `${e.id}-s`, date: e.start_date.slice(0, 10), role: "start", e });
      if (e.end_date) entries.push({ key: `${e.id}-e`, date: e.end_date.slice(0, 10), role: "end", e });
    } else {
      const d = e.start_date ?? e.deadline;
      if (d && d.slice(0, 10) >= today) entries.push({ key: `${e.id}-v`, date: d.slice(0, 10), role: "event", e });
      // An extracted event that also has a registration deadline: the deadline is its own line.
      if (e.deadline && e.start_date && e.deadline !== e.start_date && e.deadline.slice(0, 10) >= today)
        entries.push({ key: `${e.id}-dl`, date: e.deadline.slice(0, 10), role: "deadline", e });
    }
  }
  entries.sort((a, b) => a.date.localeCompare(b.date) || roleOrder(a.role) - roleOrder(b.role));
  const weeks = new Map<string, Entry[]>();
  for (const en of entries) {
    const wk = dayKey(mondayOf(parseDay(en.date)));
    weeks.set(wk, [...(weeks.get(wk) ?? []), en]);
  }

  return (
    <div className="fade-in">
      <p className="serif text-[1.1rem] leading-snug pt-6 max-w-[70ch]">{t("cal_lead")}</p>

      {(windows.length > 0 || entries.length > 0) && <Timeline windows={windows} entries={entries} />}

      <Section title={t("cal_by_week")}>
        {weeks.size === 0 && <Empty k="no_events" />}
        {[...weeks.entries()].map(([wk, list]) => {
          const w = weekLabel(parseDay(wk), lang);
          return (
            <section key={wk} className="grid gap-x-6 md:grid-cols-[150px_minmax(0,1fr)] border-t-2 border-ink pt-2 pb-4">
              <h3 className="leading-tight mb-2">
                <span className="display text-lg">{w.kw}</span>
                <span className="block text-xs text-ink-3">{w.range}</span>
              </h3>
              <ul>
                {list.map((en) => (
                  <Row key={en.key} en={en} meta={meta} />
                ))}
              </ul>
            </section>
          );
        })}
      </Section>
    </div>
  );
}

function roleOrder(r: Entry["role"]) {
  return { deadline: 0, end: 1, start: 2, event: 3 }[r];
}

function Row({ en, meta }: { en: Entry; meta: Meta | null }) {
  const { lang } = useLang();
  const t = useT();
  const e = en.e;
  const note = eventNote(e, lang);
  const where = [slugName(e.place), e.programme ? `${t("programme")}: ${slugName(e.programme)}` : null, e.location, e.organizer].filter(Boolean);
  const fromReport = isFromReport(e);
  return (
    <li className="grid grid-cols-[92px_minmax(0,1fr)] gap-x-4 py-2.5 border-t border-rule first:border-t-0">
      <div className="text-sm leading-tight">
        <span className={en.role === "deadline" ? "text-rust font-semibold" : "font-medium"}>{fmtDate(en.date, lang)}</span>
        <span className={`block text-xs mt-0.5 ${en.role === "deadline" ? "text-rust" : "text-ink-3"}`}>
          {en.role === "deadline" ? t("deadline") : en.role === "event" ? t("event") : `${t("window")} ${en.role === "start" ? t("window_starts") : t("window_ends")}`}
        </span>
      </div>
      <div className="min-w-0">
        <div className={en.role === "deadline" ? "font-semibold" : ""}>{eventName(e, lang)}</div>
        {note && <p className="text-sm text-ink-2 mt-0.5 leading-snug max-w-[75ch]">{note}</p>}
        <div className="text-xs text-ink-3 mt-1 flex flex-wrap gap-x-3 gap-y-0.5">
          {where.map((w, i) => (
            <span key={i}>{w}</span>
          ))}
          {e.topic && <span>{topicLabel(e.topic, meta, lang)}</span>}
          {en.role === "start" && e.end_date && (
            <span>
              {t("until")} {fmtDate(e.end_date, lang, { year: true })}
            </span>
          )}
          {fromReport ? (
            <span className="text-fir">
              {t("from_report")}
              {e.brief_ref && /^\d+$/.test(e.brief_ref) ? `, ${t("footnote")} ${e.brief_ref}` : ""}
            </span>
          ) : null}
        </div>
        {!fromReport && e.signal && (
          <div className="text-xs mt-1 inline-flex items-center gap-1.5">
            <LayerDot layer={e.signal.layer} />
            {e.signal.url ? (
              <a href={safeUrl(e.signal.url)} target="_blank" rel="noreferrer" className="link">
                {pick(e.signal, "headline", lang)} <span aria-hidden>↗</span>
              </a>
            ) : (
              pick(e.signal, "headline", lang)
            )}
          </div>
        )}
        {e.registration_url && (
          <a href={safeUrl(e.registration_url)} target="_blank" rel="noreferrer" className="link text-xs ml-3">
            {t("register")} ↗
          </a>
        )}
      </div>
    </li>
  );
}

/** Watch windows as bars on a month axis; deadlines and dates as marks on two rows above them. */
function Timeline({ windows, entries }: { windows: EventOut[]; entries: Entry[] }) {
  const { lang } = useLang();
  const t = useT();
  const now = new Date();
  const start = new Date(now.getFullYear(), now.getMonth(), 1);
  const lastEnd = Math.max(
    new Date(now.getFullYear(), now.getMonth() + 6, 1).getTime(),
    ...windows.map((w) => parseDay(w.end_date!).getTime()),
    ...entries.map((e) => parseDay(e.date).getTime()),
  );
  const endCap = new Date(now.getFullYear(), now.getMonth() + 15, 1).getTime();
  const lastDay = new Date(Math.min(lastEnd, endCap));
  const end = new Date(lastDay.getFullYear(), lastDay.getMonth() + 1, 1);
  const span = end.getTime() - start.getTime();
  const pct = (d: Date) => Math.max(0, Math.min(100, ((d.getTime() - start.getTime()) / span) * 100));
  const months: Date[] = [];
  for (let m = new Date(start); m < end; m = new Date(m.getFullYear(), m.getMonth() + 1, 1)) months.push(m);
  const loc = lang === "de" ? "de-DE" : "en-GB";
  const deadlines = entries.filter((e) => e.role === "deadline");
  const dates = entries.filter((e) => e.role === "event");
  const todayPct = pct(now);

  const track = (children: ReactNode) => <div className="relative h-6">{children}</div>;

  return (
    <Section title={t("cal_windows")}>
      <div className="overflow-x-auto">
        <div className="min-w-[720px] grid grid-cols-[220px_minmax(0,1fr)] gap-x-4 text-sm">
          {/* month axis */}
          <div />
          <div className="relative h-6 border-b border-ink">
            {months.map((m) => (
              <span key={m.toISOString()} className="absolute top-0 text-xs text-ink-3 pl-1 border-l border-rule h-full" style={{ left: `${pct(m)}%` }}>
                {m.toLocaleDateString(loc, { month: "short" })}
                {m.getMonth() === 0 || m.getTime() === start.getTime() ? ` ${m.getFullYear()}` : ""}
              </span>
            ))}
          </div>

          <div className="py-1 text-rust font-medium">{t("cal_deadlines_row")}</div>
          {track(
            <>
              <TodayLine pct={todayPct} />
              {deadlines.map((d) => (
                <span
                  key={d.key}
                  className="absolute top-1/2 w-2.5 h-2.5 bg-rust rotate-45 -translate-x-1/2 -translate-y-1/2"
                  style={{ left: `${pct(parseDay(d.date))}%` }}
                  title={`${fmtDate(d.date, lang)}: ${eventName(d.e, lang)}`}
                />
              ))}
            </>,
          )}

          <div className="py-1 text-ink-2">{t("events_row")}</div>
          {track(
            <>
              <TodayLine pct={todayPct} />
              {dates.map((d) => (
                <span
                  key={d.key}
                  className="absolute top-1/2 w-2 h-2 rounded-full bg-ink -translate-x-1/2 -translate-y-1/2"
                  style={{ left: `${pct(parseDay(d.date))}%` }}
                  title={`${fmtDate(d.date, lang)}: ${eventName(d.e, lang)}`}
                />
              ))}
            </>,
          )}

          {windows.map((w) => {
            const s = parseDay(w.start_date!);
            const e = parseDay(w.end_date!);
            const left = pct(s);
            const right = pct(e);
            const elapsed = Math.max(left, Math.min(right, todayPct));
            return (
              <div key={w.id} className="contents">
                <div className="py-1.5 leading-snug border-t border-rule">
                  {eventName(w, lang)}
                  <span className="block text-xs text-ink-3">
                    {fmtDate(w.start_date, lang)} – {fmtDate(w.end_date, lang, { year: true })}
                    {isFromReport(w) ? <span className="text-fir">, {t("from_report")}</span> : null}
                  </span>
                </div>
                <div className="relative border-t border-rule" title={`${eventName(w, lang)}: ${fmtDate(w.start_date, lang)} – ${fmtDate(w.end_date, lang, { year: true })}`}>
                  <TodayLine pct={todayPct} />
                  <div className="absolute top-1/2 -translate-y-1/2 h-3 bg-paper-3 border border-ink-3" style={{ left: `${left}%`, width: `${Math.max(0.6, right - left)}%` }} />
                  {elapsed > left && <div className="absolute top-1/2 -translate-y-1/2 h-3 bg-ink-3" style={{ left: `${left}%`, width: `${elapsed - left}%` }} />}
                  {e.getTime() > end.getTime() && <span className="absolute right-0 top-1/2 -translate-y-1/2 text-xs text-ink-3">→</span>}
                </div>
              </div>
            );
          })}
        </div>
      </div>
      <p className="text-xs text-ink-3 mt-2">
        <span className="inline-block h-3 border-l-2 border-fir align-middle mr-1.5" aria-hidden />
        {t("cal_today")}, {fmtDate(dayKey(now), lang, { year: true })}
      </p>
    </Section>
  );
}

function TodayLine({ pct }: { pct: number }) {
  return <span className="absolute inset-y-0 w-0 border-l-2 border-fir" style={{ left: `${pct}%` }} aria-hidden />;
}
