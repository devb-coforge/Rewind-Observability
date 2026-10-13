import { ArrowUpRight, CircleAlert, Search, SearchX } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { FailureSearch, SearchHit } from "../api/types";
import { AgentBadge, AgentOptions, Badge, Button, EmptyState, ErrorText, Input, Page, PageHeader, Select } from "../components/ui";
import { formatTime } from "../lib/format";

function TextSearch() {
  const [q, setQ] = useState("");
  const [agent, setAgent] = useState("");
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setError("");
    try {
      const body = await api.search({ q, agent });
      setHits(body.hits);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setPending(false);
    }
  }

  return (
    <>
      <form className="mb-6 flex flex-wrap gap-2" onSubmit={(event) => void onSubmit(event)}>
        <Input
          className="min-w-64 flex-1 [&_input]:h-9"
          icon={<Search className="size-4" />}
          value={q}
          onChange={(event) => setQ(event.target.value)}
          placeholder="Search transcripts"
          aria-label="Search transcripts"
          autoFocus
        />
        <Select className="w-36 [&_select]:h-9" aria-label="Agent" value={agent} onChange={(event) => setAgent(event.target.value)}>
          <AgentOptions />
        </Select>
        <Button type="submit" variant="primary" className="h-9 px-4" disabled={pending}>
          {pending ? "Searching…" : "Search"}
        </Button>
      </form>
      {error ? <ErrorText>{error}</ErrorText> : null}
      {hits && hits.length === 0 ? (
        <EmptyState icon={<SearchX className="size-6" />} title="No matches." description="Try fewer or different terms." />
      ) : null}
      {hits && hits.length > 0 ? (
        <p className="mb-3 text-2xs text-subtle">
          {hits.length} {hits.length === 1 ? "result" : "results"}
        </p>
      ) : null}
      <ul className="divide-y divide-line overflow-hidden rounded-lg border border-line bg-surface shadow-card empty:hidden">
        {(hits ?? []).map((hit) => (
          <li key={hit.event_id}>
            <Link
              className="group block px-4 py-3.5 transition-colors hover:bg-surface2/60"
              to={`/sessions/${encodeURIComponent(hit.session_id)}?event=${encodeURIComponent(hit.event_id)}`}
            >
              <div className="flex items-center gap-2">
                <span className="min-w-0 flex-1 truncate text-[13px] font-medium text-ink group-hover:text-accent">
                  {hit.session_title || hit.session_id}
                </span>
                <ArrowUpRight aria-hidden="true" className="size-3.5 shrink-0 text-subtle opacity-0 transition-opacity group-hover:opacity-100" />
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-2xs text-subtle">
                <AgentBadge agent={hit.agent} />
                <Badge>{hit.kind.replace(/_/g, " ")}</Badge>
                <span>{hit.project_name || "(unknown)"}</span>
                <span aria-hidden="true">·</span>
                <span className="tabular-nums">{formatTime(hit.ts)}</span>
              </div>
              <p className="mt-2 line-clamp-3 text-[13px] leading-relaxed text-muted">{hit.snippet}</p>
            </Link>
          </li>
        ))}
      </ul>
    </>
  );
}

function inputPreview(raw: string | null): string {
  if (!raw) return "";
  try {
    const input = JSON.parse(raw) as Record<string, unknown>;
    for (const key of ["command", "cmd", "file_path", "path", "pattern", "url", "query"]) {
      if (typeof input[key] === "string") return input[key] as string;
    }
    const first = Object.values(input).find((value) => typeof value === "string");
    return typeof first === "string" ? first : raw;
  } catch {
    return raw;
  }
}

function FailureSearchView({ declined = false }: { declined?: boolean }) {
  const [applied, setApplied] = useState({ agent: "", tool: "", q: "" });
  const [agent, setAgent] = useState("");
  const [tool, setTool] = useState("");
  const [q, setQ] = useState("");
  const [data, setData] = useState<FailureSearch | null>(null);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  async function load(next: { agent: string; tool: string; q: string }, offset = 0) {
    setPending(true);
    setError("");
    try {
      if (!offset) setApplied(next);
      const body = declined ? await api.searchDeclined({ ...next, offset }) : await api.searchFailures(next);
      setData((previous) => offset && previous ? { ...body, hits: [...previous.hits, ...body.hits] } : body);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setPending(false);
    }
  }

  useEffect(() => {
    void load({ agent, tool, q: "" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    void load({ agent, tool, q });
  }

  function pickTool(next: string) {
    setTool(next);
    void load({ agent, tool: next, q });
  }

  return (
    <>
      {declined ? <p className="mb-4 text-[13px] text-muted">Commands and tool requests explicitly declined by the user.</p> : null}
      <form className="mb-4 flex flex-wrap gap-2" onSubmit={onSubmit}>
        <Input
          className="min-w-64 flex-1 [&_input]:h-9"
          icon={<Search className="size-4" />}
          value={q}
          onChange={(event) => setQ(event.target.value)}
          placeholder={declined ? "Filter by command or decline reason" : "Filter by command or error text"}
          aria-label={declined ? "Filter user-declined commands" : "Filter failed tool calls"}
        />
        <Select
          className="w-36 [&_select]:h-9"
          aria-label="Agent"
          value={agent}
          onChange={(event) => {
            setAgent(event.target.value);
            void load({ agent: event.target.value, tool, q });
          }}
        >
          <AgentOptions />
        </Select>
        <Button type="submit" variant="primary" className="h-9 px-4" disabled={pending}>
          {pending ? "Loading…" : "Apply"}
        </Button>
      </form>
      {error ? <ErrorText>{error}</ErrorText> : null}
      {data && data.by_tool.length > 0 ? (
        <div className="mb-4 flex flex-wrap items-center gap-1.5" aria-label={declined ? "User declines by tool" : "Failures by tool"}>
          <button
            type="button"
            onClick={() => pickTool("")}
            className={`rounded-full border px-2.5 py-1 text-2xs ${tool === "" ? "border-accent text-accent" : "border-line text-muted hover:text-ink"}`}
          >
            All tools · {data.total}
          </button>
          {data.by_tool.map((item) => (
            <button
              key={item.tool_name}
              type="button"
              onClick={() => pickTool(item.tool_name)}
              className={`rounded-full border px-2.5 py-1 text-2xs ${tool === item.tool_name ? "border-accent text-accent" : "border-line text-muted hover:text-ink"}`}
            >
              {item.tool_name} · {item.count}
            </button>
          ))}
        </div>
      ) : null}
      {data && data.hits.length === 0 ? (
        <EmptyState icon={<SearchX className="size-6" />} title={declined ? "No user-declined commands." : "No failed tool calls."} description="Nothing matches these filters." />
      ) : null}
      <ul className="divide-y divide-line overflow-hidden rounded-lg border border-line bg-surface shadow-card empty:hidden">
        {(data?.hits ?? []).map((hit) => (
          <li key={hit.event_id}>
            <Link
              className="group block px-4 py-3.5 transition-colors hover:bg-surface2/60"
              to={`/sessions/${encodeURIComponent(hit.session_id)}?event=${encodeURIComponent(hit.event_id)}`}
            >
              <div className="flex items-center gap-2">
                <CircleAlert aria-hidden="true" className="size-3.5 shrink-0 text-red-400" />
                <span className="min-w-0 flex-1 truncate text-[13px] font-medium text-ink group-hover:text-accent">
                  {hit.session_title || hit.session_id}
                </span>
                <ArrowUpRight aria-hidden="true" className="size-3.5 shrink-0 text-subtle opacity-0 transition-opacity group-hover:opacity-100" />
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-2xs text-subtle">
                <AgentBadge agent={hit.agent} />
                <Badge>{hit.tool_name}</Badge>
                {declined ? <Badge tone="warn">User declined</Badge> : null}
                <span>{hit.project_name || "(unknown)"}</span>
                <span aria-hidden="true">·</span>
                <span className="tabular-nums">{formatTime(hit.ts)}</span>
              </div>
              {inputPreview(hit.tool_input) ? (
                <p className="mt-2 truncate font-mono text-2xs text-muted">{inputPreview(hit.tool_input)}</p>
              ) : null}
              {hit.error_preview ? (
                <p className="mt-1 line-clamp-3 text-[13px] leading-relaxed text-muted">{hit.error_preview}</p>
              ) : null}
            </Link>
          </li>
        ))}
      </ul>
      {declined && data?.next_offset != null ? (
        <Button className="mt-4" disabled={pending} onClick={() => void load(applied, data.next_offset!)}>
          {pending ? "Loading…" : "Load more"}
        </Button>
      ) : null}
    </>
  );
}

export function SearchPage() {
  const [mode, setMode] = useState<"text" | "failures" | "declined">("text");
  return (
    <Page className="max-w-4xl">
      <PageHeader title="Search" />
      <div className="mb-4 inline-flex rounded-md border border-line p-0.5 text-[13px]" role="tablist" aria-label="Search mode">
        {(
          [
            ["text", "Text"],
            ["failures", "Failed tool calls"],
            ["declined", "User declined"],
          ] as const
        ).map(([value, label]) => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={mode === value}
            onClick={() => setMode(value)}
            className={`rounded px-3 py-1 ${mode === value ? "bg-surface2 text-ink" : "text-muted hover:text-ink"}`}
          >
            {label}
          </button>
        ))}
      </div>
      {mode === "text" ? <TextSearch /> : <FailureSearchView key={mode} declined={mode === "declined"} />}
    </Page>
  );
}
