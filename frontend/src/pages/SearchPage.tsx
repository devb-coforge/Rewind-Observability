import { ArrowUpRight, Search, SearchX } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { SearchHit } from "../api/types";
import { AgentBadge, AgentOptions, Badge, Button, EmptyState, ErrorText, Input, Page, PageHeader, Select } from "../components/ui";
import { formatTime } from "../lib/format";

export function SearchPage() {
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
    <Page className="max-w-4xl">
      <PageHeader title="Search" description="Full-text search across messages, tool calls, and outputs." />
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
    </Page>
  );
}
