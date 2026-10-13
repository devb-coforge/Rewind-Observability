import { useQuery } from "@tanstack/react-query";
import { useMemo, useState, type ReactElement } from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import { AgentOptions, Card, Checkbox, Input, Page, PageHeader, Select, Toolbar } from "../components/ui";
import { agentColor, agentLabel, formatCompact, formatCost, formatDuration } from "../lib/format";

type Filters = { agent: string; project: string; model: string; from: string; to: string };

const axis = { stroke: "rgb(104 104 114)", fontSize: 11, tickLine: false, axisLine: false } as const;
const grid = { stroke: "rgb(38 38 44)", strokeDasharray: "3 3", vertical: false } as const;
const palette = ["#8b97ff", "#4fc8a8", "#e08a6a", "#e5b94e", "#c48cf0", "#5fb4e8"];

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
  const costChart = useMemo(
    () => (cost.data?.points ?? []).map((point) => ({ bucket: point.bucket, cost: point.value })),
    [cost.data],
  );
  const toolChart = useMemo(
    () => [...(tools.data?.tools ?? [])].sort((a, b) => b.calls - a.calls).slice(0, 12),
    [tools.data],
  );
  const modelChoices = useMemo(() => keysOf(modelOptions.data?.points ?? []), [modelOptions.data]);
  const modelKeys = useMemo(() => keysOf(models.data?.points ?? []), [models.data]);
  const agentKeys = useMemo(() => keysOf(sessions.data?.points ?? []), [sessions.data]);
  const data = summary.data;
  const errorRate = data && data.tool_calls > 0 ? data.tool_errors / data.tool_calls : null;

  return (
    <Page>
      <PageHeader title="Analytics" description="Usage, cost, and tool activity across indexed sessions. Costs are estimates." />
      <Toolbar>
        <Select className="w-36" aria-label="Agent" value={filters.agent} onChange={(event) => setFilters({ ...filters, agent: event.target.value })}>
          <AgentOptions />
        </Select>
        <Select className="w-48" aria-label="Project" value={filters.project} onChange={(event) => setFilters({ ...filters, project: event.target.value })}>
          <option value="">All projects</option>
          {(projects.data?.projects ?? []).map((project) => (
            <option key={project.project_id} value={project.project_id}>
              {project.name}
            </option>
          ))}
        </Select>
        <Select className="w-44" aria-label="Model" value={filters.model} onChange={(event) => setFilters({ ...filters, model: event.target.value })}>
          <option value="">All models</option>
          {modelChoices.map((model) => (
            <option key={model} value={model}>
              {model}
            </option>
          ))}
        </Select>
        <div className="flex items-center gap-1.5">
          <Input className="w-36" type="date" aria-label="From" value={filters.from} onChange={(event) => setFilters({ ...filters, from: event.target.value })} />
          <span className="text-subtle">–</span>
          <Input className="w-36" type="date" aria-label="To" value={filters.to} onChange={(event) => setFilters({ ...filters, to: event.target.value })} />
        </div>
        <Checkbox className="ml-auto" label="Include hidden" checked={includeHidden} onChange={(event) => setIncludeHidden(event.target.checked)} />
      </Toolbar>
      <div className="mb-5 grid gap-px overflow-hidden rounded-lg border border-line bg-line shadow-card sm:grid-cols-2 xl:grid-cols-4">
        <Kpi label="Sessions" value={data ? data.sessions.toLocaleString() : "—"} />
        <Kpi
          label="Tokens in / out"
          value={data ? `${formatCompact(data.tokens_in)} / ${formatCompact(data.tokens_out)}` : "—"}
        />
        <Kpi
          label="Estimated cost"
          value={formatCost(data?.est_cost_usd)}
          hint={data?.cost_coverage === "partial" ? "Partial — some models have no pricing" : undefined}
        />
        <Kpi
          label="Median duration"
          value={formatDuration(data?.median_duration_sec)}
          hint={
            data
              ? `${data.tool_errors.toLocaleString()} errors in ${data.tool_calls.toLocaleString()} tool calls${errorRate != null ? ` · ${(errorRate * 100).toFixed(1)}%` : ""}`
              : undefined
          }
        />
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        <ChartCard title="Sessions by day" legend={agentKeys.map((key) => ({ label: agentLabel(key), color: agentColor(key) }))}>
          <LineChart data={sessionChart} margin={chartMargin}>
            <CartesianGrid {...grid} />
            <XAxis dataKey="bucket" {...axis} tickFormatter={shortDate} minTickGap={24} />
            <YAxis {...axis} allowDecimals={false} width={32} />
            <Tooltip content={<ChartTooltip labelFormat={shortDate} />} cursor={{ stroke: "rgb(54 54 62)" }} />
            {agentKeys.map((key) => (
              <Line key={key} type="monotone" dataKey={key} name={agentLabel(key)} stroke={agentColor(key)} strokeWidth={1.75} dot={false} activeDot={{ r: 3 }} />
            ))}
          </LineChart>
        </ChartCard>
        <ChartCard
          title="Estimated cost by day"
          empty={cost.isSuccess && !costChart.some((point) => point.cost) && "No priced usage in this range"}
        >
          <AreaChart data={costChart} margin={chartMargin}>
            <defs>
              <linearGradient id="costFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#8b97ff" stopOpacity={0.28} />
                <stop offset="100%" stopColor="#8b97ff" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid {...grid} />
            <XAxis dataKey="bucket" {...axis} tickFormatter={shortDate} minTickGap={24} />
            <YAxis {...axis} width={44} tickFormatter={(value: number) => `$${value}`} />
            <Tooltip content={<ChartTooltip labelFormat={shortDate} valueFormat={(value) => formatCost(value)} />} cursor={{ stroke: "rgb(54 54 62)" }} />
            <Area type="monotone" dataKey="cost" name="Cost" stroke="#8b97ff" strokeWidth={1.75} fill="url(#costFill)" />
          </AreaChart>
        </ChartCard>
        <ChartCard
          title="Tokens by model"
          empty={models.isSuccess && modelKeys.length === 0 && "No token usage recorded in this range"}
          legend={modelKeys.map((key, index) => ({ label: key, color: palette[index % palette.length] }))}>
          <LineChart data={modelChart} margin={chartMargin}>
            <CartesianGrid {...grid} />
            <XAxis dataKey="bucket" {...axis} tickFormatter={shortDate} minTickGap={24} />
            <YAxis {...axis} width={44} tickFormatter={(value: number) => formatCompact(value)} />
            <Tooltip content={<ChartTooltip labelFormat={shortDate} valueFormat={(value) => formatCompact(value)} />} cursor={{ stroke: "rgb(54 54 62)" }} />
            {modelKeys.map((key, index) => (
              <Line key={key} type="monotone" dataKey={key} stroke={palette[index % palette.length]} strokeWidth={1.75} dot={false} activeDot={{ r: 3 }} />
            ))}
          </LineChart>
        </ChartCard>
        <ChartCard
          title="Tool use"
          empty={tools.isSuccess && toolChart.length === 0 && "No tool calls in this range"}
          legend={[
            { label: "Calls", color: "#8b97ff" },
            { label: "Errors", color: "#f47272" },
          ]}
        >
          <BarChart data={toolChart} margin={chartMargin} barGap={2}>
            <CartesianGrid {...grid} />
            <XAxis dataKey="tool_name" {...axis} interval={0} tickFormatter={(value: string) => (value.length > 10 ? `${value.slice(0, 9)}…` : value)} />
            <YAxis {...axis} allowDecimals={false} width={36} />
            <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgb(255 255 255 / 0.03)" }} />
            <Bar dataKey="calls" name="Calls" fill="#8b97ff" radius={[3, 3, 0, 0]} maxBarSize={22} />
            <Bar dataKey="errors" name="Errors" fill="#f47272" radius={[3, 3, 0, 0]} maxBarSize={22} />
          </BarChart>
        </ChartCard>
      </div>
    </Page>
  );
}

const chartMargin = { top: 8, right: 8, bottom: 0, left: -4 };

function shortDate(value: string): string {
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function keysOf(points: { group: string }[]): string[] {
  return [...new Set(points.map((point) => point.group).filter((group) => group && group !== "all"))];
}

/** Counts are additive, so a group absent from a bucket had zero that day. */
function pivot(points: { bucket: string; group: string; value: number | null }[]) {
  const groups = keysOf(points);
  const rows = new Map<string, Record<string, string | number | null>>();
  for (const point of points) {
    const row = rows.get(point.bucket) ?? Object.fromEntries([["bucket", point.bucket], ...groups.map((group) => [group, 0])]);
    row[point.group] = point.value;
    rows.set(point.bucket, row);
  }
  return [...rows.values()];
}

type TooltipEntry = { name?: string; value?: number; color?: string; dataKey?: string };

function ChartTooltip({
  active,
  payload,
  label,
  labelFormat,
  valueFormat,
}: {
  active?: boolean;
  payload?: TooltipEntry[];
  label?: string;
  labelFormat?: (value: string) => string;
  valueFormat?: (value: number) => string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="min-w-36 rounded-md border border-line-strong bg-surface2/95 px-3 py-2 text-xs shadow-pop backdrop-blur">
      <div className="mb-1.5 font-medium text-ink">{label && labelFormat ? labelFormat(label) : label}</div>
      <div className="space-y-1">
        {payload.map((entry) => (
          <div key={entry.dataKey ?? entry.name} className="flex items-center gap-2">
            <span aria-hidden="true" className="size-2 rounded-sm" style={{ background: entry.color }} />
            <span className="max-w-40 truncate text-muted">{entry.name}</span>
            <span className="ml-auto pl-3 tabular-nums text-ink">
              {entry.value == null ? "—" : valueFormat ? valueFormat(entry.value) : entry.value.toLocaleString()}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function Kpi({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="bg-surface px-5 py-4">
      <div className="text-xs text-muted">{label}</div>
      <div className="mt-1.5 text-2xl font-semibold tabular-nums tracking-tight">{value}</div>
      {hint ? <div className="mt-1 text-2xs text-subtle">{hint}</div> : <div className="mt-1 h-4" />}
    </div>
  );
}

function ChartCard({
  title,
  legend,
  empty,
  children,
}: {
  title: string;
  legend?: { label: string; color: string }[];
  empty?: string | false;
  children: ReactElement;
}) {
  return (
    <Card className="p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
        <h2 className="text-[13px] font-medium">{title}</h2>
        {legend?.length ? (
          <div className="flex flex-wrap gap-x-3 gap-y-1">
            {legend.map((item) => (
              <span key={item.label} className="flex items-center gap-1.5 text-2xs text-muted">
                <span aria-hidden="true" className="size-2 rounded-sm" style={{ background: item.color }} />
                {item.label}
              </span>
            ))}
          </div>
        ) : null}
      </div>
      {empty ? (
        <div className="grid h-[232px] place-items-center rounded-md border border-dashed border-line text-xs text-subtle">{empty}</div>
      ) : (
        <ResponsiveContainer width="100%" height={232}>
          {children}
        </ResponsiveContainer>
      )}
    </Card>
  );
}
