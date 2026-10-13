import type {
  EvalCase,
  EvalGroup,
  BoundaryPath,
  Filters,
  Note,
  ObsEvent,
  Project,
  SearchHit,
  Session,
  SessionDetail,
  SourcesResponse,
  Summary,
  SeriesPoint,
  ToolStat,
} from "./types";

function query(params: Record<string, string | number | boolean | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(path, { ...init, headers });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* response had no JSON body */
    }
    throw new Error(detail || "Request failed");
  }
  const type = response.headers.get("content-type") || "";
  if (type.includes("text/plain")) return (await response.text()) as T;
  return (await response.json()) as T;
}

export const api = {
  health: () => request<{ status: string }>("/api/health"),
  sources: () => request<SourcesResponse>("/api/sources"),
  reindex: (full = false) => request<Record<string, unknown>>(`/api/reindex${query({ full })}`, { method: "POST" }),
  projects: (includeHidden = false) =>
    request<{ projects: Project[] }>(`/api/projects${query({ include_hidden: includeHidden })}`),
  setHidden: (projectId: string, hidden: boolean) =>
    request<{ project_id: string; hidden: boolean }>(`/api/projects/${encodeURIComponent(projectId)}`, {
      method: "PATCH",
      body: JSON.stringify({ hidden }),
    }),
  sessions: (filters: Filters & { q?: string; sort?: string; cursor?: string; limit?: number }) =>
    request<{ sessions: Session[]; next_cursor: string | null }>(`/api/sessions${query(filters)}`),
  session: (id: string) => request<SessionDetail>(`/api/sessions/${encodeURIComponent(id)}`),
  note: (id: string) => request<Note & { session_id: string }>(`/api/sessions/${encodeURIComponent(id)}/note`),
  putNote: (id: string, text: string) =>
    request<Note & { session_id: string }>(`/api/sessions/${encodeURIComponent(id)}/note`, {
      method: "PUT",
      body: JSON.stringify({ text }),
    }),
  events: (id: string, cursor?: number) =>
    request<{ events: ObsEvent[]; next_cursor: number | null }>(
      `/api/sessions/${encodeURIComponent(id)}/events${query({ cursor, limit: 400 })}`,
    ),
  async allEvents(id: string): Promise<ObsEvent[]> {
    const events: ObsEvent[] = [];
    let cursor: number | undefined;
    for (let page = 0; page < 40; page += 1) {
      const body = await this.events(id, cursor);
      events.push(...body.events);
      if (body.next_cursor == null) break;
      cursor = body.next_cursor;
    }
    return events;
  },
  eventOutput: (id: string) =>
    request<{ event_id: string; output: string | null }>(`/api/events/${encodeURIComponent(id)}/output`),
  eventRaw: (id: string) => request<string>(`/api/events/${encodeURIComponent(id)}/raw`),
  search: (filters: Filters & { q: string }) => request<{ hits: SearchHit[] }>(`/api/search${query(filters)}`),
  summary: (filters: Filters) => request<Summary>(`/api/analytics/summary${query(filters)}`),
  timeseries: (filters: Filters & { metric: string; bucket?: string; group_by?: string }) =>
    request<{ metric: string; bucket: string; group_by: string | null; points: SeriesPoint[] }>(
      `/api/analytics/timeseries${query(filters)}`,
    ),
  tools: (filters: Filters) => request<{ tools: ToolStat[] }>(`/api/analytics/tools${query(filters)}`),
  boundary: (sessionId: string) =>
    request<{ paths: BoundaryPath[]; count: number }>(`/api/sessions/${encodeURIComponent(sessionId)}/boundary`),
  dismiss: (projectId: string, pathPrefix: string) =>
    request(`/api/boundary/dismissals`, {
      method: "PUT",
      body: JSON.stringify({ project_id: projectId, path_prefix: pathPrefix }),
    }),
  undismiss: (projectId: string, pathPrefix: string) =>
    request(`/api/boundary/dismissals${query({ project_id: projectId, path_prefix: pathPrefix })}`, {
      method: "DELETE",
    }),
  freeze: (sessionId: string, fromSeq?: number, toSeq?: number) =>
    request<EvalCase>("/api/evals/cases", {
      method: "POST",
      body: JSON.stringify({
        session_id: sessionId,
        from_seq: fromSeq ?? null,
        to_seq: toSeq ?? null,
      }),
    }),
  cases: (filters: { project?: string; model?: string; verdict?: string }) =>
    request<{ cases: EvalCase[] }>(`/api/evals/cases${query(filters)}`),
  case: (id: string) => request<EvalCase>(`/api/evals/cases/${encodeURIComponent(id)}`),
  patchCase: (id: string, body: { verdict?: string; note?: string }) =>
    request<EvalCase>(`/api/evals/cases/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  deleteCase: (id: string) =>
    request<{ deleted: string }>(`/api/evals/cases/${encodeURIComponent(id)}`, { method: "DELETE" }),
  evalsSummary: (project?: string) =>
    request<{ note: string; groups: EvalGroup[] }>(`/api/evals/summary${query({ project, group_by: "model" })}`),
};
