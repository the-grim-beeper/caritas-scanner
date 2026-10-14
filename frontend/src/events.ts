import { dayKey, parseDay } from "./i18n";
import type { EventKind, EventOut, Lang } from "./types";

/** Kind, inferred for rows from an older backend that does not send it. */
export function eventKind(e: EventOut): EventKind {
  if (e.kind) return e.kind;
  return e.deadline && !e.start_date ? "deadline" : "event";
}

export function eventName(e: EventOut, lang: Lang): string {
  return (lang === "en" && e.name_en) || e.name;
}

export function eventNote(e: EventOut, lang: Lang): string {
  return (lang === "en" ? e.note_en || e.note_de : e.note_de || e.note_en) ?? "";
}

/** The date a row is filed under: the deadline, else its start. */
export function eventDate(e: EventOut): string | null {
  return eventKind(e) === "deadline" ? (e.deadline ?? e.start_date) : (e.start_date ?? e.deadline);
}

/** The last day the row is still relevant. */
export function eventEnd(e: EventOut): string | null {
  return e.end_date ?? e.deadline ?? e.start_date;
}

export function isFromReport(e: EventOut): boolean {
  return e.origin === "report" || (!e.signal_id && !!e.slug);
}

export const todayKey = () => dayKey(new Date());

/** Rows that are not over yet, i.e. whose end is today or later. */
export function upcoming(items: EventOut[]): EventOut[] {
  const today = todayKey();
  return items.filter((e) => {
    const end = eventEnd(e);
    return !!end && end.slice(0, 10) >= today;
  });
}

/** Share of a window already elapsed, 0..1. */
export function windowProgress(e: EventOut): number {
  if (!e.start_date || !e.end_date) return 0;
  const s = parseDay(e.start_date).getTime();
  const en = parseDay(e.end_date).getTime();
  const now = Date.now();
  if (en <= s) return 1;
  return Math.max(0, Math.min(1, (now - s) / (en - s)));
}

/** A from/to pair wide enough to catch windows that opened up to a year ago. */
export function eventRange(daysAhead: number): { from: string; to: string } {
  const now = new Date();
  const from = new Date(now);
  from.setDate(now.getDate() - 365);
  const to = new Date(now);
  to.setDate(now.getDate() + daysAhead);
  return { from: dayKey(from), to: dayKey(to) };
}
