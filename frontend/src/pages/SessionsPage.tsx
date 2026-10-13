import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { api } from "../api/client";
import { SessionGroups } from "../components/SessionGroups";
import { agentLabel } from "../lib/format";

export function SessionsPage() {
  const queryClient = useQueryClient();
  const [includeHidden, setIncludeHidden] = useState(false);
  const [agent, setAgent] = useState("");
  const [project, setProject] = useState("");
  const [model, setModel] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState("started_at");

  const filters = { agent, project, model, from, to, q, sort, include_hidden: includeHidden };
  const projects = useQuery({
    queryKey: ["projects", includeHidden],
    queryFn: () => api.projects(includeHidden),
  });
  const sessions = useInfiniteQuery({
    queryKey: ["sessions", filters],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) => api.sessions({ ...filters, cursor: pageParam, limit: 100 }),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });

  const rows = useMemo(() => sessions.data?.pages.flatMap((page) => page.sessions) ?? [], [sessions.data]);
  const models = useMemo(() => [...new Set(rows.flatMap((session) => session.models))].sort(), [rows]);

  return (
    <div className="h-full overflow-auto px-4 py-4 md:px-6">
      <div className="mb-4 flex flex-wrap gap-2">
        <select className="rounded-md border border-line bg-surface px-2 py-1.5 text-sm" value={agent} onChange={(event) => setAgent(event.target.value)} aria-label="Agent">
          <option value="">All agents</option>
          <option value="claude_code">Claude Code</option>
          <option value="codex">Codex</option>
          <option value="cursor">Cursor</option>
        </select>
        <select className="rounded-md border border-line bg-surface px-2 py-1.5 text-sm" value={project} onChange={(event) => setProject(event.target.value)} aria-label="Project">
          <option value="">All projects</option>
          {(projects.data?.projects ?? []).map((item) => (
            <option key={item.project_id} value={item.project_id}>
              {item.name} ({agentLabel(item.agent)})
            </option>
          ))}
        </select>
        <select className="rounded-md border border-line bg-surface px-2 py-1.5 text-sm" value={model} onChange={(event) => setModel(event.target.value)} aria-label="Model">
          <option value="">All models</option>
          {models.map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </select>
        <input className="rounded-md border border-line bg-surface px-2 py-1.5 text-sm" type="date" value={from} onChange={(event) => setFrom(event.target.value)} aria-label="From" />
        <input className="rounded-md border border-line bg-surface px-2 py-1.5 text-sm" type="date" value={to} onChange={(event) => setTo(event.target.value)} aria-label="To" />
        <select className="rounded-md border border-line bg-surface px-2 py-1.5 text-sm" value={sort} onChange={(event) => setSort(event.target.value)} aria-label="Sort">
          <option value="started_at">Newest</option>
          <option value="cost">Cost</option>
          <option value="tokens">Tokens</option>
          <option value="duration">Duration</option>
          <option value="errors">Errors</option>
        </select>
        <input
          className="min-w-40 flex-1 rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
          placeholder="Filter titles"
          value={q}
          onChange={(event) => setQ(event.target.value)}
          aria-label="Filter titles"
        />
      </div>
      {sessions.isError ? <p className="mb-3 text-sm text-danger">{(sessions.error as Error).message}</p> : null}
      {sessions.isLoading ? <p className="text-sm text-muted">Loading sessions…</p> : null}
      {sessions.isSuccess ? (
        <SessionGroups
          projects={projects.data?.projects ?? []}
          sessions={rows}
          includeHidden={includeHidden}
          onIncludeHidden={setIncludeHidden}
          onSetHidden={async (projectId, hidden) => {
            await api.setHidden(projectId, hidden);
            await queryClient.invalidateQueries({ queryKey: ["projects"] });
            await queryClient.invalidateQueries({ queryKey: ["sessions"] });
          }}
        />
      ) : null}
      {sessions.hasNextPage ? (
        <button
          type="button"
          className="mt-4 rounded-md border border-line px-3 py-1.5 text-sm"
          onClick={() => void sessions.fetchNextPage()}
        >
          Load more
        </button>
      ) : null}
    </div>
  );
}
