import { useQuery } from "@tanstack/react-query";
import { useMemo, useState, type ReactNode } from "react";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import { agentLabel, formatCost, formatDuration, formatTokens } from "../lib/format";

type Filters = { agent: string; project: string; model: string; from: string; to: string };

export function AnalyticsPage() {
  const [filters, setFilters] = useState<Filters>({ agent: "", project: "", model: "", from: "", to: "" });
  const [includeHidden, setIncludeHidden] = useState(false);
  const queryFilters = { ...filters, include_hidden: includeHidden };
  const projects = useQuery({ queryKey: ["projects", true], queryFn: () => api.projects(true) });
  const summary = useQuery({ queryKey: ["summary", queryFilters], queryFn: () => api.summary(queryFilters) });
  const sessions = useQuery({
    queryKey: ["series", "sessions", queryFilters],
    queryFn: () => api.timeseries({ ...queryFilters, metric: "sessions", bucket: "day", group_by: "agent" }),
  });
  const cost = useQuery({
    queryKey: ["series", "cost", queryFilters],
    queryFn: () => api.timeseries({ ...queryFilters, metric: "cost", bucket: "day" }),
  });
  const modelOptions = useQuery({
    queryKey: ["series", "model-options", filters.agent, filters.project, filters.from, filters.to, includeHidden],
    queryFn: () =>
      api.timeseries({
        agent: filters.agent,
        project: filters.project,
        from: filters.from,
        to: filters.to,
        include_hidden: includeHidden,
        metric: "sessions",
        bucket: "day",
        group_by: "model",
      }),
  });
  const tools = useQuery({ queryKey: ["tools", queryFilters], queryFn: () => api.tools(queryFilters) });
  const models = useQuery({
    queryKey: ["series", "models", queryFilters],
    queryFn: () => api.timeseries({ ...queryFilters, metric: "tokens", bucket: "day", group_by: "model" }),
  });

  const sessionChart = useMemo(() => pivot(sessions.data?.points ?? []), [sessions.data]);
  const modelChart = useMemo(() => pivot(models.data?.points ?? []), [models.data]);
  const modelChoices = useMemo(() => keysOf(modelOptions.data?.points ?? []), [modelOptions.data]);
  const modelKeys = useMemo(() => keysOf(models.data?.points ?? []), [models.data]);
  const agentKeys = useMemo(() => keysOf(sessions.data?.points ?? []), [sessions.data]);

  return (
    <div className="h-full overflow-auto px-4 py-4 md:px-6">
      <div className="mb-4 flex flex-wrap gap-2">
        <FilterSelect label="Agent" value={filters.agent} onChange={(agent) => setFilters({ ...filters, agent })}>
          <option value="">All agents</option>
          <option value="claude_code">Claude Code</option>
          <option value="codex">Codex</option>
          <option value="cursor">Cursor</option>
        </FilterSelect>
        <FilterSelect label="Project" value={filters.project} onChange={(project) => setFilters({ ...filters, project })}>
          <option value="">All projects</option>
          {(projects.data?.projects ?? []).map((project) => (
            <option key={project.project_id} value={project.project_id}>
              {project.name}
            </option>
          ))}
        </FilterSelect>
        <FilterSelect label="Model" value={filters.model} onChange={(model) => setFilters({ ...filters, model })}>
          <option value="">All models</option>
          {modelChoices.map((model) => (
            <option key={model} value={model}>
              {model}
            </option>
          ))}
        </FilterSelect>
        <input className="rounded-md border border-line bg-surface px-2 py-1.5 text-sm" type="date" aria-label="From" value={filters.from} onChange={(event) => setFilters({ ...filters, from: event.target.value })} />
        <input className="rounded-md border border-line bg-surface px-2 py-1.5 text-sm" type="date" aria-label="To" value={filters.to} onChange={(event) => setFilters({ ...filters, to: event.target.value })} />
        <label className="flex items-center gap-2 text-sm text-muted">
          <input type="checkbox" checked={includeHidden} onChange={(event) => setIncludeHidden(event.target.checked)} />
          Include hidden
        </label>
      </div>
      <div className="mb-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Kpi label="Sessions" value={summary.data ? String(summary.data.sessions) : "—"} />
        <Kpi
          label="Tokens in / out"
          value={
            summary.data
              ? `${formatTokens(summary.data.tokens_in)} / ${formatTokens(summary.data.tokens_out)}`
              : "—"
          }
        />
        <Kpi
          label="Estimated cost"
          value={formatCost(summary.data?.est_cost_usd, summary.data?.cost_coverage === "partial")}
        />
        <Kpi
          label="Median duration"
          value={formatDuration(summary.data?.median_duration_sec)}
          hint={summary.data ? `${summary.data.tool_errors} tool errors / ${summary.data.tool_calls} calls` : ""}
        />
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        <ChartCard title="Sessions by day">
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={sessionChart}>
              <CartesianGrid stroke="#34392c" />
              <XAxis dataKey="bucket" stroke="#a8a292" fontSize={12} />
              <YAxis stroke="#a8a292" fontSize={12} allowDecimals={false} />
              <Tooltip contentStyle={{ background: "#1b1e16", border: "1px solid #34392c" }} />
              <Legend />
              {agentKeys.map((key) => (
                <Line key={key} type="monotone" dataKey={key} name={agentLabel(key)} stroke={colorFor(key)} dot={false} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
        <ChartCard title="Estimated cost by day">
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={(cost.data?.points ?? []).map((point) => ({ bucket: point.bucket, cost: point.value }))}>
              <CartesianGrid stroke="#34392c" />
              <XAxis dataKey="bucket" stroke="#a8a292" fontSize={12} />
              <YAxis stroke="#a8a292" fontSize={12} />
              <Tooltip contentStyle={{ background: "#1b1e16", border: "1px solid #34392c" }} />
              <Line type="monotone" dataKey="cost" stroke="#e2b340" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
        <ChartCard title="Tokens by model">
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={modelChart}>
              <CartesianGrid stroke="#34392c" />
              <XAxis dataKey="bucket" stroke="#a8a292" fontSize={12} />
              <YAxis stroke="#a8a292" fontSize={12} />
              <Tooltip contentStyle={{ background: "#1b1e16", border: "1px solid #34392c" }} />
              <Legend />
              {modelKeys.map((key, index) => (
                <Line key={key} type="monotone" dataKey={key} stroke={palette[index % palette.length]} dot={false} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
        <ChartCard title="Tool use">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={tools.data?.tools ?? []}>
              <CartesianGrid stroke="#34392c" />
              <XAxis dataKey="tool_name" stroke="#a8a292" fontSize={12} />
              <YAxis stroke="#a8a292" fontSize={12} allowDecimals={false} />
              <Tooltip contentStyle={{ background: "#1b1e16", border: "1px solid #34392c" }} />
              <Bar dataKey="calls" fill="#e2b340" />
              <Bar dataKey="errors" fill="#e36a58" />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>
    </div>
  );
}

const palette = ["#e2b340", "#8fbf6a", "#7eb6d6", "#e36a58", "#c58be0"];

function colorFor(key: string): string {
  if (key === "claude_code") return "#e2b340";
  if (key === "codex") return "#8fbf6a";
  if (key === "cursor") return "#79b8df";
  return "#7eb6d6";
}

function keysOf(points: { group: string }[]): string[] {
  return [...new Set(points.map((point) => point.group).filter((group) => group && group !== "all"))];
}

function pivot(points: { bucket: string; group: string; value: number | null }[]) {
  const rows = new Map<string, Record<string, string | number | null>>();
  for (const point of points) {
    const row = rows.get(point.bucket) ?? { bucket: point.bucket };
    row[point.group] = point.value;
    rows.set(point.bucket, row);
  }
  return [...rows.values()];
}

function Kpi({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-xl border border-line bg-surface px-4 py-3">
      <div className="text-xs uppercase tracking-wide text-muted">{label}</div>
      <div className="mt-1 text-xl">{value}</div>
      {hint ? <div className="text-xs text-muted">{hint}</div> : null}
    </div>
  );
}

function ChartCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-xl border border-line bg-surface p-3">
      <h2 className="mb-2 text-sm font-medium">{title}</h2>
      {children}
    </section>
  );
}

function FilterSelect({
  label,
  value,
  onChange,
  children,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  children: ReactNode;
}) {
  return (
    <select className="rounded-md border border-line bg-surface px-2 py-1.5 text-sm" aria-label={label} value={value} onChange={(event) => onChange(event.target.value)}>
      {children}
    </select>
  );
}
