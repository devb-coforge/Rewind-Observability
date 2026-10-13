import { useState } from "react";
import { Link } from "react-router-dom";
import type { Project, Session } from "../api/types";
import { agentLabel, formatCost, formatDuration, formatTime, formatTokens } from "../lib/format";

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

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-end gap-3 text-sm text-muted">
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={includeHidden}
            onChange={(event) => onIncludeHidden(event.target.checked)}
          />
          Show hidden projects
        </label>
      </div>
      {error ? <p className="text-sm text-danger">{error}</p> : null}
      {toast ? (
        <div role="status" className="flex items-center justify-between gap-3 rounded-md border border-line bg-surface px-3 py-2 text-sm">
          <span>Hid {toast.name}.</span>
          <button
            type="button"
            className="text-accent"
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
          </button>
        </div>
      ) : null}
      {groups.length === 0 ? <p className="text-sm text-muted">No sessions match these filters.</p> : null}
      {groups.map((project) => {
        const rows = sessions.filter((session) => session.project_id === project.project_id);
        if (rows.length === 0 && !project.hidden) return null;
        return (
          <section key={project.project_id} className="overflow-hidden rounded-xl border border-line">
            <header className="flex flex-wrap items-center gap-3 border-b border-line bg-surface px-4 py-3">
              <div className="min-w-0">
                <h2 className="truncate font-medium">{project.name}</h2>
                <p className="truncate text-xs text-muted">
                  {agentLabel(project.agent)}
                  {project.cwd ? ` · ${project.cwd}` : ""}
                  {project.hidden ? " · hidden" : ""}
                </p>
              </div>
              {project.hidden ? (
                <button
                  type="button"
                  className="ml-auto rounded-md border border-line px-3 py-1.5 text-sm"
                  onClick={() => void change(project, false)}
                >
                  Restore project
                </button>
              ) : (
                <button
                  type="button"
                  className="ml-auto rounded-md border border-line px-3 py-1.5 text-sm"
                  onClick={() => void change(project, true)}
                >
                  Hide project
                </button>
              )}
            </header>
            {rows.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[720px] text-left text-sm">
                  <thead className="text-xs uppercase tracking-wide text-muted">
                    <tr>
                      <th className="px-4 py-2 font-medium">Session</th>
                      <th className="px-3 py-2 font-medium">Start</th>
                      <th className="px-3 py-2 font-medium">Duration</th>
                      <th className="px-3 py-2 font-medium">Tokens</th>
                      <th className="px-3 py-2 font-medium">Cost</th>
                      <th className="px-3 py-2 font-medium">Errors</th>
                      <th className="px-3 py-2 font-medium">Paths</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((session) => (
                      <tr key={session.id} className="border-t border-line">
                        <td className="px-4 py-2">
                          <Link className="text-accent hover:underline" to={`/sessions/${encodeURIComponent(session.id)}`}>
                            {session.title || session.native_id}
                          </Link>
                          <div className="text-xs text-muted">{session.models.join(", ") || agentLabel(session.agent)}</div>
                        </td>
                        <td className="px-3 py-2 whitespace-nowrap">{formatTime(session.started_at)}</td>
                        <td className="px-3 py-2">{formatDuration(session.duration_sec)}</td>
                        <td className="px-3 py-2">
                          {session.usage_coverage === "none"
                            ? "—"
                            : `${formatTokens(session.tokens_in)} / ${formatTokens(session.tokens_out)}`}
                        </td>
                        <td className="px-3 py-2">{formatCost(session.est_cost_usd, session.cost_partial)}</td>
                        <td className="px-3 py-2">{session.n_tool_errors}</td>
                        <td className="px-3 py-2">{session.boundary_count > 0 ? session.boundary_count : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="px-4 py-3 text-sm text-muted">No sessions in this view.</p>
            )}
          </section>
        );
      })}
    </div>
  );
}
