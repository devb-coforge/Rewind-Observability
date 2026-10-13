import { EyeOff, FolderOpen, Inbox, RotateCcw } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import type { Project, Session } from "../api/types";
import { cn } from "../lib/cn";
import { formatCompact, formatCost, formatDuration, formatTime } from "../lib/format";
import { AgentBadge, Badge, Button, Checkbox, EmptyState, ErrorText, td, th } from "./ui";

export function SessionGroups({
  projects,
  sessions,
  includeHidden,
  onIncludeHidden,
  onSetHidden,
}: {
  projects: Project[];
  sessions: Session[];
  includeHidden: boolean;
  onIncludeHidden: (value: boolean) => void;
  onSetHidden: (projectId: string, hidden: boolean) => Promise<void>;
}) {
  const [toast, setToast] = useState<{ id: string; name: string } | null>(null);
  const [error, setError] = useState("");

  const known = new Map(projects.map((project) => [project.project_id, project]));
  for (const session of sessions) {
    if (!known.has(session.project_id)) {
      known.set(session.project_id, {
        project_id: session.project_id,
        agent: session.agent,
        name: session.project_name || "(unknown)",
        cwd: session.project_cwd,
        hidden: session.project_hidden,
        n_sessions: 0,
      });
    }
  }

  async function change(project: Project, hidden: boolean) {
    setError("");
    try {
      await onSetHidden(project.project_id, hidden);
      setToast(hidden ? { id: project.project_id, name: project.name } : null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update the project");
    }
  }

  const groups = [...known.values()].filter((project) => includeHidden || !project.hidden);
  const visible = groups.filter(
    (project) => project.hidden || sessions.some((session) => session.project_id === project.project_id),
  );

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-end gap-3">
        <Checkbox
          label="Show hidden projects"
          checked={includeHidden}
          onChange={(event) => onIncludeHidden(event.target.checked)}
        />
      </div>
      {error ? <ErrorText>{error}</ErrorText> : null}
      {toast ? (
        <div
          role="status"
          className="flex items-center justify-between gap-3 rounded-lg border border-line-strong bg-surface2 px-4 py-2.5 text-[13px] shadow-card"
        >
          <span className="flex items-center gap-2 text-muted">
            <EyeOff aria-hidden="true" className="size-4 text-subtle" />
            <span>Hid {toast.name}.</span>
          </span>
          <Button
            size="sm"
            onClick={() =>
              void change(
                {
                  project_id: toast.id,
                  name: toast.name,
                  agent: "",
                  cwd: null,
                  hidden: true,
                  n_sessions: 0,
                },
                false,
              )
            }
          >
            Undo
          </Button>
        </div>
      ) : null}
      {visible.length === 0 ? (
        <EmptyState
          icon={<Inbox className="size-6" />}
          title="No sessions match these filters"
          description="Try widening the date range or clearing filters."
        />
      ) : null}
      {visible.map((project) => {
        const rows = sessions.filter((session) => session.project_id === project.project_id);
        return (
          <section
            key={project.project_id}
            className={cn("overflow-hidden rounded-lg border border-line bg-surface shadow-card", project.hidden && "opacity-70")}
          >
            <header className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-3">
              <FolderOpen aria-hidden="true" className="size-4 shrink-0 text-subtle" />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="truncate text-[13px] font-semibold">{project.name}</h2>
                  <AgentBadge agent={project.agent} />
                  {project.hidden ? <Badge>Hidden</Badge> : null}
                  <span className="text-2xs tabular-nums text-subtle">
                    {rows.length} {rows.length === 1 ? "session" : "sessions"}
                  </span>
                </div>
                {project.cwd ? <p className="mt-0.5 truncate font-mono text-2xs text-subtle">{project.cwd}</p> : null}
              </div>
              {project.hidden ? (
                <Button size="sm" variant="ghost" onClick={() => void change(project, false)}>
                  <RotateCcw aria-hidden="true" className="size-3.5" />
                  Restore project
                </Button>
              ) : (
                <Button size="sm" variant="ghost" onClick={() => void change(project, true)}>
                  <EyeOff aria-hidden="true" className="size-3.5" />
                  Hide project
                </Button>
              )}
            </header>
            {rows.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[760px] text-[13px]">
                  <thead className="bg-surface2/50">
                    <tr>
                      <th className={th}>Session</th>
                      <th className={th}>Started</th>
                      <th className={cn(th, "text-right")}>Duration</th>
                      <th className={cn(th, "text-right")}>Tokens in / out</th>
                      <th className={cn(th, "text-right")}>Cost</th>
                      <th className={cn(th, "text-right")}>Errors</th>
                      <th className={cn(th, "text-right")}>Paths</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {rows.map((session) => (
                      <tr key={session.id} className="transition-colors hover:bg-surface2/60">
                        <td className={cn(td, "max-w-[28rem] py-2")}>
                          <Link
                            className="block truncate font-medium text-ink hover:text-accent"
                            to={`/sessions/${encodeURIComponent(session.id)}`}
                          >
                            {session.title || session.native_id}
                          </Link>
                          <div className="mt-0.5 truncate font-mono text-2xs text-subtle">
                            {session.models.join(", ") || "model unknown"}
                          </div>
                        </td>
                        <td className={cn(td, "whitespace-nowrap text-muted")}>{formatTime(session.started_at)}</td>
                        <td className={cn(td, "text-right tabular-nums text-muted")}>{formatDuration(session.duration_sec)}</td>
                        <td className={cn(td, "whitespace-nowrap text-right tabular-nums text-muted")}>
                          {session.usage_coverage === "none" ? (
                            "—"
                          ) : (
                            <>
                              <span className="text-ink">{formatCompact(session.tokens_in)}</span>
                              <span className="px-1 text-subtle">/</span>
                              {formatCompact(session.tokens_out)}
                            </>
                          )}
                        </td>
                        <td className={cn(td, "whitespace-nowrap text-right tabular-nums")}>
                          {formatCost(session.est_cost_usd, session.cost_partial)}
                        </td>
                        <td className={cn(td, "text-right tabular-nums")}>
                          {session.n_tool_errors > 0 ? (
                            <Badge tone="danger">{session.n_tool_errors}</Badge>
                          ) : (
                            <span className="text-subtle">0</span>
                          )}
                        </td>
                        <td className={cn(td, "text-right tabular-nums")}>
                          {session.boundary_count > 0 ? (
                            <Badge tone="warn">{session.boundary_count}</Badge>
                          ) : (
                            <span className="text-subtle">—</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="px-4 py-4 text-[13px] text-muted">No sessions in this view.</p>
            )}
          </section>
        );
      })}
    </div>
  );
}
