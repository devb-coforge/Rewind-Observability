import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { NoteEditor } from "../components/NoteEditor";
import { Timeline } from "../components/timeline/Timeline";
import { agentLabel, formatCost, formatDuration, formatTime, formatTokens } from "../lib/format";

export function SessionDetailPage() {
  const { sessionId = "" } = useParams();
  const [search] = useSearchParams();
  const focusId = search.get("event");
  const queryClient = useQueryClient();
  const [showThinking, setShowThinking] = useState(false);
  const [raw, setRaw] = useState<string | null>(null);
  const [fromSeq, setFromSeq] = useState("");
  const [toSeq, setToSeq] = useState("");
  const [freezeMessage, setFreezeMessage] = useState("");

  const session = useQuery({
    queryKey: ["session", sessionId],
    queryFn: () => api.session(sessionId),
  });
  const events = useQuery({
    queryKey: ["events", sessionId],
    queryFn: () => api.allEvents(sessionId),
  });
  const boundary = useQuery({
    queryKey: ["boundary", sessionId],
    queryFn: () => api.boundary(sessionId),
  });

  const freeze = useMutation({
    mutationFn: () =>
      api.freeze(
        sessionId,
        fromSeq === "" ? undefined : Number(fromSeq),
        toSeq === "" ? undefined : Number(toSeq),
      ),
    onSuccess: (created) => {
      setFreezeMessage(`Saved case ${created.id.slice(0, 8)}.`);
      void queryClient.invalidateQueries({ queryKey: ["benchmark"] });
    },
  });

  async function loadRaw(id: string) {
    try {
      setRaw(await api.eventRaw(id));
    } catch (err) {
      setRaw(err instanceof Error ? err.message : "Could not read the source line");
    }
  }

  async function setAllowed(path: string, allowed: boolean) {
    if (!session.data) return;
    if (allowed) await api.dismiss(session.data.project_id, path);
    else await api.undismiss(session.data.project_id, path);
    await queryClient.invalidateQueries({ queryKey: ["boundary", sessionId] });
    await queryClient.invalidateQueries({ queryKey: ["events", sessionId] });
    await queryClient.invalidateQueries({ queryKey: ["session", sessionId] });
  }

  if (session.isLoading) return <p className="p-6 text-sm text-muted">Loading session…</p>;
  if (session.isError || !session.data) {
    return <p className="p-6 text-sm text-danger">Session not found.</p>;
  }
  const detail = session.data;
  const paths = uniquePaths(boundary.data?.paths ?? []);

  return (
    <div className="grid h-full min-h-0 grid-cols-1 grid-rows-[minmax(0,1.4fr)_minmax(0,1fr)] lg:grid-cols-[minmax(0,1fr)_22rem] lg:grid-rows-1">
      <section className="flex min-h-0 flex-col border-b border-line lg:border-b-0 lg:border-r">
        <header className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-3">
          <div className="min-w-0 flex-1">
            <h1 className="truncate text-lg font-medium">{detail.title || detail.native_id}</h1>
            <p className="truncate text-xs text-muted">
              {agentLabel(detail.agent)} · {detail.project_name || "(unknown)"} · {formatTime(detail.started_at)}
              {detail.git_branch ? ` · ${detail.git_branch}` : ""}
            </p>
          </div>
        </header>
        {detail.project_hidden ? (
          <p className="border-b border-line bg-surface px-4 py-2 text-sm text-muted">
            Hidden project ·{" "}
            <button
              type="button"
              className="text-accent"
              onClick={() =>
                void api.setHidden(detail.project_id, false).then(() => queryClient.invalidateQueries())
              }
            >
              Restore project
            </button>
          </p>
        ) : null}
        <div className="min-h-0 flex-1">
          {events.isLoading ? <p className="p-4 text-sm text-muted">Loading events…</p> : null}
          {events.data ? (
            <Timeline key={sessionId} events={events.data} showThinking={showThinking} onShowThinkingChange={setShowThinking} focusId={focusId} onRaw={(id) => void loadRaw(id)} />
          ) : null}
        </div>
      </section>
      <aside className="min-h-0 space-y-6 overflow-auto px-4 py-4">
        <section className="space-y-1 text-sm">
          <h2 className="font-medium">Stats</h2>
          <p className="text-muted">
            Tokens in/out: {formatTokens(detail.tokens_in)} / {formatTokens(detail.tokens_out)}
          </p>
          <p className="text-muted">
            Cache read/write: {formatTokens(detail.tokens_cache_read)} / {formatTokens(detail.tokens_cache_write)}
          </p>
          <p className="text-muted">Estimated cost: {formatCost(detail.est_cost_usd, detail.cost_partial)}</p>
          <p className="text-muted">Duration: {formatDuration(detail.duration_sec)}</p>
          <p className="text-muted">
            Tool calls: {detail.n_tool_calls}, errors: {detail.n_tool_errors}
          </p>
          <p className="text-muted">Models: {detail.models.join(", ") || "—"}</p>
        </section>
        <section className="space-y-2 text-sm">
          <h2 className="font-medium">Subagents</h2>
          {detail.children.length === 0 ? <p className="text-muted">None linked.</p> : null}
          {detail.children.map((child) => (
            <Link key={child.id} className="block text-accent hover:underline" to={`/sessions/${encodeURIComponent(child.id)}`}>
              {child.title || child.id}
            </Link>
          ))}
        </section>
        <section className="space-y-2 text-sm">
          <h2 className="font-medium">Outside the recorded directory</h2>
          {paths.length === 0 ? <p className="text-muted">No outside paths.</p> : null}
          {paths.map((item) => (
            <div key={item.resolved || item.path} className="rounded-md border border-line p-2">
              <div className="break-all font-mono text-xs">{item.path}</div>
              <div className="mt-1 flex items-center justify-between gap-2">
                <span className="text-xs text-muted">{item.allowed ? "Allowed" : "Outside"}</span>
                {item.resolved ? (
                  <button
                    type="button"
                    className="text-xs text-accent"
                    onClick={() => void setAllowed(item.resolved || "", !item.allowed)}
                  >
                    {item.allowed ? "Remove allow" : "Allow path"}
                  </button>
                ) : null}
              </div>
            </div>
          ))}
        </section>
        <NoteEditor
          initial={{ text: detail.note?.text ?? "", updated_at: detail.note?.updated_at ?? null }}
          onSave={async (text) => {
            const saved = await api.putNote(sessionId, text);
            await queryClient.invalidateQueries({ queryKey: ["session", sessionId] });
            return { text: saved.text, updated_at: saved.updated_at };
          }}
        />
        <section className="space-y-2 text-sm">
          <h2 className="font-medium">Freeze a benchmark case</h2>
          <div className="flex gap-2">
            <input
              className="w-24 rounded-md border border-line bg-surface px-2 py-1"
              inputMode="numeric"
              placeholder="From seq"
              aria-label="From seq"
              value={fromSeq}
              onChange={(event) => setFromSeq(event.target.value)}
            />
            <input
              className="w-24 rounded-md border border-line bg-surface px-2 py-1"
              inputMode="numeric"
              placeholder="To seq"
              aria-label="To seq"
              value={toSeq}
              onChange={(event) => setToSeq(event.target.value)}
            />
          </div>
          <button
            type="button"
            className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-[#1a1608] disabled:opacity-50"
            disabled={freeze.isPending}
            onClick={() => freeze.mutate()}
          >
            {freeze.isPending ? "Freezing…" : "Freeze case"}
          </button>
          {freeze.isError ? <p className="text-xs text-danger">{(freeze.error as Error).message}</p> : null}
          {freezeMessage ? (
            <p className="text-xs text-muted">
              {freezeMessage} <Link className="text-accent" to="/benchmark">Open benchmark</Link>
            </p>
          ) : null}
        </section>
      </aside>
      {raw != null ? (
        <div className="fixed inset-0 z-20 flex items-center justify-center bg-black/60 p-4" onClick={() => setRaw(null)}>
          <div className="max-h-[80vh] w-full max-w-3xl overflow-auto rounded-xl border border-line bg-bg p-4" onClick={(event) => event.stopPropagation()}>
            <div className="mb-2 flex items-center justify-between">
              <h2 className="text-sm font-medium">Raw source</h2>
              <button type="button" className="text-sm text-accent" onClick={() => setRaw(null)}>
                Close
              </button>
            </div>
            <pre className="whitespace-pre-wrap font-mono text-xs">{raw}</pre>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function uniquePaths(paths: { path: string | null; resolved: string | null; allowed: boolean }[]) {
  const seen = new Map<string, { path: string | null; resolved: string | null; allowed: boolean }>();
  for (const item of paths) {
    const key = item.resolved || item.path || "";
    if (!key || seen.has(key)) continue;
    seen.set(key, item);
  }
  return [...seen.values()];
}
