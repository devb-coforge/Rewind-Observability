import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useMemo, useState } from "react";
import { api } from "../api/client";
import { SessionGroups } from "../components/SessionGroups";
import { AgentOptions, Button, ErrorText, Input, Loading, Page, PageHeader, Select, Toolbar } from "../components/ui";
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
    <Page>
      <PageHeader
        title="Sessions"
        description={
          sessions.isSuccess
            ? `${rows.length}${sessions.hasNextPage ? "+" : ""} sessions across ${new Set(rows.map((row) => row.project_id)).size} projects`
            : "Agent sessions grouped by project"
        }
      />
      <Toolbar>
        <Input
          className="min-w-56 flex-1"
          icon={<Search className="size-3.5" />}
          placeholder="Filter titles"
          value={q}
          onChange={(event) => setQ(event.target.value)}
          aria-label="Filter titles"
        />
        <Select className="w-36" value={agent} onChange={(event) => setAgent(event.target.value)} aria-label="Agent">
          <AgentOptions />
        </Select>
        <Select className="w-48" value={project} onChange={(event) => setProject(event.target.value)} aria-label="Project">
          <option value="">All projects</option>
          {(projects.data?.projects ?? []).map((item) => (
            <option key={item.project_id} value={item.project_id}>
              {item.name} ({agentLabel(item.agent)})
            </option>
          ))}
        </Select>
        <Select className="w-40" value={model} onChange={(event) => setModel(event.target.value)} aria-label="Model">
          <option value="">All models</option>
          {models.map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </Select>
        <div className="flex items-center gap-1.5">
          <Input className="w-36" type="date" value={from} onChange={(event) => setFrom(event.target.value)} aria-label="From" />
          <span className="text-subtle">–</span>
          <Input className="w-36" type="date" value={to} onChange={(event) => setTo(event.target.value)} aria-label="To" />
        </div>
        <Select className="w-32" value={sort} onChange={(event) => setSort(event.target.value)} aria-label="Sort">
          <option value="started_at">Newest</option>
          <option value="cost">Cost</option>
          <option value="tokens">Tokens</option>
          <option value="duration">Duration</option>
          <option value="errors">Errors</option>
        </Select>
      </Toolbar>
      {sessions.isError ? <ErrorText>{(sessions.error as Error).message}</ErrorText> : null}
      {sessions.isLoading ? <Loading label="Loading sessions…" /> : null}
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
        <div className="mt-6 flex justify-center">
          <Button disabled={sessions.isFetchingNextPage} onClick={() => void sessions.fetchNextPage()}>
            {sessions.isFetchingNextPage ? "Loading…" : "Load more"}
          </Button>
        </div>
      ) : null}
    </Page>
  );
}
