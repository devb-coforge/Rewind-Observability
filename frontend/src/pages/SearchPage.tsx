import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { SearchHit } from "../api/types";
import { agentLabel, formatTime } from "../lib/format";

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
    <div className="h-full overflow-auto px-4 py-4 md:px-6">
      <form className="mb-4 flex flex-wrap gap-2" onSubmit={(event) => void onSubmit(event)}>
        <input
          className="min-w-56 flex-1 rounded-md border border-line bg-surface px-3 py-2 text-sm"
          value={q}
          onChange={(event) => setQ(event.target.value)}
          placeholder="Search transcripts"
          aria-label="Search transcripts"
        />
        <select className="rounded-md border border-line bg-surface px-2 py-2 text-sm" aria-label="Agent" value={agent} onChange={(event) => setAgent(event.target.value)}>
          <option value="">All agents</option>
          <option value="claude_code">Claude Code</option>
          <option value="codex">Codex</option>
          <option value="cursor">Cursor</option>
        </select>
        <button type="submit" className="rounded-md bg-accent px-3 py-2 text-sm font-medium text-[#1a1608]" disabled={pending}>
          {pending ? "Searching…" : "Search"}
        </button>
      </form>
      {error ? <p className="text-sm text-danger">{error}</p> : null}
      {hits && hits.length === 0 ? <p className="text-sm text-muted">No matches.</p> : null}
      <ul className="space-y-2">
        {(hits ?? []).map((hit) => (
          <li key={hit.event_id} className="rounded-lg border border-line bg-surface px-4 py-3">
            <Link
              className="text-sm text-accent hover:underline"
              to={`/sessions/${encodeURIComponent(hit.session_id)}?event=${encodeURIComponent(hit.event_id)}`}
            >
              {hit.session_title || hit.session_id}
            </Link>
            <p className="mt-1 text-xs text-muted">
              {agentLabel(hit.agent)} · {hit.project_name || "(unknown)"} · {hit.kind} · {formatTime(hit.ts)}
            </p>
            <p className="mt-2 text-sm">{hit.snippet}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
