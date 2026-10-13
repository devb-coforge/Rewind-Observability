import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Calendar, FolderOpen, GitBranch, X } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { NoteEditor } from "../components/NoteEditor";
import { Timeline } from "../components/timeline/Timeline";
import { AgentBadge, Badge, Button, Input, Loading, SectionTitle } from "../components/ui";
import { cn } from "../lib/cn";
import { formatCompact, formatCost, formatDuration, formatTime, formatTokens } from "../lib/format";

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
      void queryClient.invalidateQueries({ queryKey: ["evals"] });
    },
  });

  useEffect(() => {
    if (raw == null) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setRaw(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [raw]);

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

  if (session.isLoading) {
    return (
      <div className="px-8">
        <Loading label="Loading session…" />
      </div>
    );
  }
  if (session.isError || !session.data) {
    return (
      <div className="space-y-3 px-8 py-8">
        <p className="text-[13px] text-danger">Session not found.</p>
        <BackLink />
      </div>
    );
  }
  const detail = session.data;
  const paths = uniquePaths(boundary.data?.paths ?? []);

  return (
    <div className="grid h-full min-h-0 grid-cols-1 grid-rows-[minmax(0,1.4fr)_minmax(0,1fr)] lg:grid-cols-[minmax(0,1fr)_21rem] lg:grid-rows-1">
      <section className="flex min-h-0 flex-col border-b border-line lg:border-b-0 lg:border-r">
        <header className="border-b border-line px-5 pb-4 pt-4">
          <BackLink />
          <h1 className="mt-2 truncate text-base font-semibold tracking-tight">{detail.title || detail.native_id}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-muted">
            <AgentBadge agent={detail.agent} />
            <Meta icon={<FolderOpen className="size-3.5" />}>{detail.project_name || "(unknown)"}</Meta>
            <Meta icon={<Calendar className="size-3.5" />}>{formatTime(detail.started_at)}</Meta>
            {detail.git_branch ? <Meta icon={<GitBranch className="size-3.5" />} mono>{detail.git_branch}</Meta> : null}
          </div>
        </header>
        {detail.hidden ? (
          <div className="flex items-center justify-between gap-3 border-b border-line bg-warn/[0.06] px-5 py-2 text-xs text-muted">
            <span>This session is hidden from session lists.</span>
            <Button
              size="sm"
              variant="ghost"
              onClick={() =>
                void api
                  .setSessionHidden(detail.id, false)
                  .then(() => queryClient.invalidateQueries({ queryKey: ["session", sessionId] }))
                  .then(() => queryClient.invalidateQueries({ queryKey: ["sessions"] }))
              }
            >
              Restore session
            </Button>
          </div>
        ) : null}
        {detail.project_hidden ? (
          <div className="flex items-center justify-between gap-3 border-b border-line bg-warn/[0.06] px-5 py-2 text-xs text-muted">
            <span>This project is hidden from session lists.</span>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => void api.setHidden(detail.project_id, false).then(() => queryClient.invalidateQueries())}
            >
              Restore project
            </Button>
          </div>
        ) : null}
        <div className="min-h-0 flex-1">
          {events.isLoading ? (
            <div className="px-5">
              <Loading label="Loading events…" />
            </div>
          ) : null}
          {events.data ? (
            <Timeline key={sessionId} events={events.data} showThinking={showThinking} onShowThinkingChange={setShowThinking} focusId={focusId} onRaw={(id) => void loadRaw(id)} />
          ) : null}
        </div>
      </section>
      <aside className="min-h-0 space-y-7 overflow-auto bg-surface/40 px-5 py-5">
        <section>
          <SectionTitle>Overview</SectionTitle>
          <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line bg-line">
            <Stat label="Cost" value={formatCost(detail.est_cost_usd, detail.cost_partial)} />
            <Stat label="Duration" value={formatDuration(detail.duration_sec)} />
            <Stat label="Tokens in" value={formatCompact(detail.tokens_in)} title={formatTokens(detail.tokens_in)} />
            <Stat label="Tokens out" value={formatCompact(detail.tokens_out)} title={formatTokens(detail.tokens_out)} />
            <Stat label="Cache read" value={formatCompact(detail.tokens_cache_read)} title={formatTokens(detail.tokens_cache_read)} />
            <Stat label="Cache write" value={formatCompact(detail.tokens_cache_write)} title={formatTokens(detail.tokens_cache_write)} />
            <Stat label="Tool calls" value={String(detail.n_tool_calls)} />
            <Stat label="Tool errors" value={String(detail.n_tool_errors)} tone={detail.n_tool_errors > 0 ? "danger" : undefined} />
          </div>
          <dl className="mt-3 text-xs">
            <dt className="text-subtle">Models</dt>
            <dd className="mt-1 flex flex-wrap gap-1">
              {detail.models.length ? detail.models.map((model) => <Badge key={model} className="font-mono">{model}</Badge>) : <span className="text-muted">—</span>}
            </dd>
            {detail.selected_model ? <>
              <dt className="mt-3 text-subtle">Current model selection</dt>
              <dd className="mt-1"><Badge className="font-mono">{detail.selected_model}</Badge></dd>
            </> : null}
          </dl>
        </section>
        <section>
          <SectionTitle>Subagents</SectionTitle>
          {detail.children.length === 0 ? <p className="text-xs text-subtle">None linked.</p> : null}
          <div className="space-y-1">
            {detail.children.map((child) => (
              <Link
                key={child.id}
                className="block truncate rounded-md border border-line bg-surface px-3 py-2 text-[13px] text-ink transition-colors hover:border-line-strong hover:bg-surface2"
                to={`/sessions/${encodeURIComponent(child.id)}`}
              >
                {child.title || child.id}
              </Link>
            ))}
          </div>
        </section>
        <section>
          <SectionTitle aside={paths.length ? <Badge tone="warn">{paths.length}</Badge> : undefined}>Outside the recorded directory</SectionTitle>
          {paths.length === 0 ? <p className="text-xs text-subtle">No outside paths.</p> : null}
          <div className="space-y-1.5">
            {paths.map((item) => (
              <div key={item.resolved || item.path} className="rounded-md border border-line bg-surface px-3 py-2">
                <div className="break-all font-mono text-2xs leading-relaxed text-ink/90">{item.path}</div>
                <div className="mt-1.5 flex items-center justify-between gap-2">
                  <Badge tone={item.allowed ? "ok" : "warn"}>{item.allowed ? "Allowed" : "Outside"}</Badge>
                  {item.resolved ? (
                    <Button size="sm" variant="ghost" className="h-6" onClick={() => void setAllowed(item.resolved || "", !item.allowed)}>
                      {item.allowed ? "Remove allow" : "Allow path"}
                    </Button>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        </section>
        <section>
          <NoteEditor
            initial={{ text: detail.note?.text ?? "", updated_at: detail.note?.updated_at ?? null }}
            onSave={async (text) => {
              const saved = await api.putNote(sessionId, text);
              await queryClient.invalidateQueries({ queryKey: ["session", sessionId] });
              return { text: saved.text, updated_at: saved.updated_at };
            }}
          />
        </section>
        <section>
          <SectionTitle>Freeze an eval case</SectionTitle>
          <p className="mb-2.5 text-xs text-subtle">Capture a step range as a reusable case. Leave blank for the whole session.</p>
          <div className="flex gap-2">
            <Input className="w-full" inputMode="numeric" placeholder="From step" aria-label="From seq" value={fromSeq} onChange={(event) => setFromSeq(event.target.value)} />
            <Input className="w-full" inputMode="numeric" placeholder="To step" aria-label="To seq" value={toSeq} onChange={(event) => setToSeq(event.target.value)} />
            <Button variant="primary" disabled={freeze.isPending} onClick={() => freeze.mutate()}>
              {freeze.isPending ? "Freezing…" : "Freeze case"}
            </Button>
          </div>
          {freeze.isError ? <p className="mt-2 text-xs text-danger">{(freeze.error as Error).message}</p> : null}
          {freezeMessage ? (
            <p className="mt-2 text-xs text-muted">
              {freezeMessage}{" "}
              <Link className="font-medium text-accent hover:underline" to="/evals">Open evals</Link>
            </p>
          ) : null}
        </section>
      </aside>
      {raw != null ? (
        <div className="fixed inset-0 z-20 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm" onClick={() => setRaw(null)}>
          <div
            role="dialog"
            aria-label="Raw source"
            className="flex max-h-[80vh] w-full max-w-3xl flex-col overflow-hidden rounded-xl border border-line-strong bg-surface shadow-pop"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
              <h2 className="text-[13px] font-semibold">Raw source</h2>
              <Button size="sm" variant="ghost" aria-label="Close" onClick={() => setRaw(null)}>
                <X aria-hidden="true" className="size-4" />
              </Button>
            </div>
            <pre className="overflow-auto whitespace-pre-wrap break-all bg-code p-4 font-mono text-xs leading-5 text-ink/90">{raw}</pre>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function BackLink() {
  return (
    <Link to="/" className="inline-flex items-center gap-1 text-xs text-subtle transition-colors hover:text-ink">
      <ArrowLeft aria-hidden="true" className="size-3.5" />
      Sessions
    </Link>
  );
}

function Meta({ icon, children, mono }: { icon: ReactNode; children: ReactNode; mono?: boolean }) {
  return (
    <span className="inline-flex min-w-0 items-center gap-1.5">
      <span aria-hidden="true" className="text-subtle">{icon}</span>
      <span className={cn("truncate", mono && "font-mono text-2xs")}>{children}</span>
    </span>
  );
}

function Stat({ label, value, title, tone }: { label: string; value: string; title?: string; tone?: "danger" }) {
  return (
    <div className="bg-surface px-3 py-2.5" title={title}>
      <div className="text-2xs text-subtle">{label}</div>
      <div className={cn("mt-0.5 text-[13px] font-medium tabular-nums", tone === "danger" ? "text-danger" : "text-ink")}>{value}</div>
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
