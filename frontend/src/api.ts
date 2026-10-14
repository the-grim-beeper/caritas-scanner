import type {
  CycleOut,
  EntityBrief,
  EntityDetail,
  EventOut,
  Meta,
  Mover,
  Network,
  Overview,
  QuestionDetail,
  QuestionOut,
  ReportBrief,
  ReportFull,
  Signal,
  SourceOut,
  Suggestion,
  SuggestionRunResult,
  TrendCell,
} from "./types";

export class AuthError extends Error {}

export class HttpError extends Error {
  status: number;
  /** FastAPI's `{"detail": "..."}` body, when the error response is JSON and carries one. */
  detail?: string;
  constructor(status: number, message: string, detail?: string) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { credentials: "include", ...init });
  if (res.status === 401) throw new AuthError("not signed in");
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    let detail: string | undefined;
    try {
      const j: unknown = JSON.parse(text);
      if (j && typeof j === "object" && typeof (j as Record<string, unknown>).detail === "string") {
        detail = (j as Record<string, string>).detail;
      }
    } catch {
      /* body is not JSON */
    }
    throw new HttpError(res.status, detail ?? `${res.status} ${res.statusText}: ${text.slice(0, 200)}`, detail);
  }
  return (await res.json()) as T;
}

type Params = Record<string, string | number | undefined | null>;

export function get<T>(path: string, params?: Params): Promise<T> {
  const qs = new URLSearchParams();
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== "") qs.set(k, String(v));
    }
  }
  const q = qs.toString();
  return request<T>(q ? `${path}?${q}` : path);
}

export function post<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export const isNotFound = (e: unknown) => e instanceof HttpError && e.status === 404;

/** The backend's stated reason, when there is one; otherwise the plain error message. */
export const errorDetail = (e: unknown): string => {
  if (e instanceof HttpError && e.detail) return e.detail;
  return e instanceof Error ? e.message : String(e);
};

export const api = {
  login: (password: string) => post<{ ok: boolean }>("/api/login", { password }),
  meta: () => get<Meta>("/api/meta"),
  overview: () => get<Overview>("/api/overview"),
  signals: (params: Params) => get<{ total: number; page: number; per_page: number; items: Signal[] }>("/api/signals", params),
  signal: (id: string) => get<Signal>(`/api/signals/${id}`),
  entities: (kind?: string) => get<{ items: EntityBrief[] }>("/api/entities", { kind }),
  entity: (slug: string) => get<EntityDetail>(`/api/entities/${encodeURIComponent(slug)}`),
  events: (from?: string, to?: string) => get<{ from: string; to: string; items: EventOut[] }>("/api/events", { from, to }),
  questions: () => get<QuestionOut[] | { items: QuestionOut[] }>("/api/questions").then(unwrapList),
  question: (id: string) => get<QuestionDetail>(`/api/questions/${encodeURIComponent(id)}`),
  network: () => get<Network>("/api/network"),
  reports: () => get<ReportBrief[] | { items: ReportBrief[] }>("/api/reports").then(unwrapList),
  report: (id: string | "latest") => get<ReportFull>(id === "latest" ? "/api/reports/latest" : `/api/reports/${encodeURIComponent(id)}`),
  runReport: () => post<{ ok: boolean; id?: string | null; reason?: string }>("/api/report/run"),
  trends: (weeks = 12) => get<{ weeks: number; cells: TrendCell[]; movers: Mover[] }>("/api/trends", { weeks }),
  sources: () => get<{ items: SourceOut[] }>("/api/sources"),
  cycles: () => get<{ items: CycleOut[] }>("/api/cycles"),
  runCycle: () => post<{ started: boolean; reason?: string }>("/api/cycle/run"),
  suggestions: (status: string = "all") => get<Suggestion[] | { items: Suggestion[] }>("/api/suggestions", { status }).then(unwrapList),
  declineSuggestion: (id: string) => post<unknown>(`/api/suggestions/${encodeURIComponent(id)}/decline`),
  adoptSuggestion: (id: string) => post<unknown>(`/api/suggestions/${encodeURIComponent(id)}/adopt`),
  runSuggestions: () => post<SuggestionRunResult>("/api/suggestions/run"),
};

/** The list endpoints are specified as bare arrays; accept the template's `{items}` wrapper too. */
function unwrapList<T>(r: T[] | { items: T[] }): T[] {
  return Array.isArray(r) ? r : (r?.items ?? []);
}

// The fifteen questions are needed by several views (labels for judgements, report blocks).
// One request per page load; a failure is not cached.
let questionsPromise: Promise<QuestionOut[]> | null = null;
export function questionsCached(): Promise<QuestionOut[]> {
  if (!questionsPromise) {
    questionsPromise = api.questions().catch((e: unknown) => {
      questionsPromise = null;
      throw e;
    });
  }
  return questionsPromise;
}
