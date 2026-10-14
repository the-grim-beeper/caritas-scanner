import { useMemo } from "react";
import { questionsCached } from "./api";
import type { QuestionOut } from "./types";
import { useAsync } from "./useAsync";

/** The fifteen questions keyed by id (fetched once per page load). Empty while loading or if unavailable. */
export function useQuestionsMap(): Record<string, QuestionOut> {
  const res = useAsync(() => questionsCached(), []);
  return useMemo(() => Object.fromEntries((res.data ?? []).map((q) => [q.id, q])), [res.data]);
}

/** "3" for "q03". */
export function qNumber(id: string): string {
  const m = /(\d+)$/.exec(id);
  return m ? String(Number(m[1])) : id;
}
