export class AuthError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { credentials: "include", ...init });
  if (res.status === 401) throw new AuthError("not signed in");
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${text.slice(0, 200)}`);
  }
  return (await res.json()) as T;
}

export function get<T>(path: string, params?: Record<string, string | number | undefined | null>): Promise<T> {
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

export const api = {
  login: (password: string) => post<{ ok: boolean }>("/api/login", { password }),
  session: () => get<{ ok: boolean }>("/api/session"),
  meta: () => get<import("./types").Meta>("/api/meta"),
  overview: () => get<import("./types").Overview>("/api/overview"),
  signals: (params: Record<string, string | number | undefined | null>) =>
    get<{ total: number; page: number; per_page: number; items: import("./types").Signal[] }>("/api/signals", params),
  signal: (id: string) => get<import("./types").Signal>(`/api/signals/${id}`),
  entities: (kind?: string) => get<{ items: import("./types").EntityBrief[] }>("/api/entities", { kind }),
  entity: (slug: string) =>
    get<import("./types").EntityBrief & { aliases: string[]; timeline: import("./types").Signal[]; weekly: [string, number][] }>(
      `/api/entities/${slug}`,
    ),
  events: (from?: string, to?: string) => get<{ from: string; to: string; items: import("./types").EventOut[] }>("/api/events", { from, to }),
  digests: () => get<{ items: { id: string; created_at: string; lead_en: string; lead_de: string; model: string }[] }>("/api/digests"),
  digest: (id: string | "latest") => get<import("./types").DigestFull>(`/api/digests/${id}`),
  trends: (weeks = 12) => get<{ weeks: number; cells: import("./types").TrendCell[]; movers: import("./types").Mover[] }>("/api/trends", { weeks }),
  sources: () => get<{ items: import("./types").SourceOut[] }>("/api/sources"),
  cycles: () => get<{ items: import("./types").CycleOut[] }>("/api/cycles"),
  runCycle: () => post<{ started: boolean; reason?: string }>("/api/cycle/run"),
  runDigest: () => post<{ started: boolean; reason?: string }>("/api/cycle/digest"),
};
