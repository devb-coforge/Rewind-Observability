import { ChevronRight, EyeOff, FolderOpen, Inbox, Pencil, RotateCcw, Trash2 } from "lucide-react";
import { useId, useState } from "react";
import { Link } from "react-router-dom";
import type { Project, Session } from "../api/types";
import { cn } from "../lib/cn";
import { formatCompact, formatCost, formatDuration, formatTime } from "../lib/format";
import { groupProjectsByPath } from "../lib/projects";
import { AgentBadge, Badge, Button, Checkbox, EmptyState, ErrorText, Input, td, th } from "./ui";

export function SessionGroups({
  projects,
  sessions,
  includeHidden,
  onIncludeHidden,
  onSetHidden,
  onRename,
}: {
  projects: Project[];
  sessions: Session[];
  includeHidden: boolean;
  onIncludeHidden: (value: boolean) => void;
  onSetHidden: (projectId: string, hidden: boolean) => Promise<void>;
  onRename?: (projectId: string, name: string) => Promise<void>;
}) {
  const [toast, setToast] = useState<{ projects: Project[]; name: string } | null>(null);
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const id = useId();
  const [editing, setEditing] = useState<{ key: string; name: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [changing, setChanging] = useState(false);

  async function saveName(projectId: string) {
    if (!editing || !onRename || saving) return;
    const name = editing.name.trim();
    if (!name) {
      setError("Project name cannot be blank");
      return;
    }
    setError("");
    setSaving(true);
    try {
      await onRename(projectId, name);
      setEditing(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not rename the project");
    } finally {
      setSaving(false);
    }
  }

  const known = new Map(projects.map((project) => [project.project_id, project]));
  for (const session of sessions) {
    if (!known.has(session.project_id)) {
      known.set(session.project_id, {
        project_id: session.project_id,
        agent: session.agent,
        name: session.project_name || "(unknown)",
        cwd: session.project_cwd,
        group_cwd: session.project_group_cwd,
        hidden: session.project_hidden,
        n_sessions: 0,
      });
    }
  }

  async function changeMany(projects: Project[], hidden: boolean, name: string) {
    if (changing) return;
    setError("");
    setChanging(true);
    const changed: Project[] = [];
    try {
      for (const project of projects) {
        await onSetHidden(project.project_id, hidden);
        changed.push(project);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update the project");
    } finally {
      setToast(hidden && changed.length ? { projects: changed, name } : null);
      setChanging(false);
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
            disabled={changing}
            onClick={() => void changeMany(toast.projects, false, toast.name)}
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
      {groupProjectsByPath(visible).map((group) => {
        const projectIds = new Set(group.projects.map((project) => project.project_id));
        const count = sessions.filter((session) => projectIds.has(session.project_id)).length;
        const isExpanded = expanded.has(group.key);
        const contentId = `${id}-${encodeURIComponent(group.key)}`;
        const allHidden = group.projects.every((project) => project.hidden);
        const hideTargets = [...known.values()].filter((project) =>
          !project.hidden && (group.cwd ? (project.group_cwd || project.cwd) === group.cwd : project.project_id === group.projects[0].project_id),
        );
        return (
          <section key={group.key} className="overflow-hidden rounded-lg border border-line bg-surface shadow-card">
            <header className={cn("flex items-center", isExpanded && "border-b border-line")}>
              <h2 className="min-w-0 flex-1">
                <button
                  type="button"
                  aria-expanded={isExpanded}
                  aria-controls={contentId}
                  aria-label={`${isExpanded ? "Collapse" : "Expand"} ${group.name}`}
                  className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-surface2/60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent focus-visible:-outline-offset-2"
                  onClick={() => setExpanded((current) => {
                    const next = new Set(current);
                    if (next.has(group.key)) next.delete(group.key);
                    else next.add(group.key);
                    return next;
                  })}
                >
                  <ChevronRight aria-hidden="true" className={cn("size-4 shrink-0 text-subtle transition-transform", isExpanded && "rotate-90")} />
                  <FolderOpen aria-hidden="true" className="size-4 shrink-0 text-subtle" />
                  <span className="min-w-0 flex-1">
                    <span className="flex flex-wrap items-center gap-2">
                      <span className="truncate text-[13px] font-semibold">{group.name}</span>
                      <span className="text-2xs tabular-nums text-subtle">
                        {count} {count === 1 ? "session" : "sessions"}
                      </span>
                    </span>
                    {group.cwd ? <span className="mt-0.5 block truncate font-mono text-2xs text-subtle">{group.cwd}</span> : null}
                  </span>
                </button>
              </h2>
              <div className="mr-4 flex shrink-0 items-center gap-1">
                {onRename ? (
                  <Button
                    size="sm" variant="ghost" className="size-8 p-0"
                    aria-label={`Rename ${group.name}`}
                    title="Rename project"
                    disabled={saving || changing}
                    onClick={() => { setError(""); setEditing({ key: group.key, name: group.name }); }}
                  >
                    <Pencil aria-hidden="true" className="size-3.5" />
                  </Button>
                ) : null}
                <Button
                  size="sm" variant="ghost" className="size-8 p-0"
                  aria-label={`${allHidden ? "Restore" : "Hide"} ${group.name}`}
                  title={allHidden ? "Restore project" : "Hide project"}
                  disabled={changing || saving}
                  onClick={() => void changeMany(allHidden ? group.projects : hideTargets, !allHidden, group.name)}
                >
                  {allHidden ? <RotateCcw aria-hidden="true" className="size-3.5" /> : <Trash2 aria-hidden="true" className="size-3.5" />}
                </Button>
              </div>
            </header>
            {editing?.key === group.key ? (
              <form
                className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-3"
                onSubmit={(event) => { event.preventDefault(); void saveName(group.projects[0].project_id); }}
              >
                <Input
                  autoFocus aria-label="Project name" maxLength={200}
                  className="min-w-48 flex-1" value={editing.name} disabled={saving}
                  onChange={(event) => setEditing({ key: group.key, name: event.target.value })}
                  onKeyDown={(event) => { if (event.key === "Escape" && !saving) setEditing(null); }}
                />
                <Button type="submit" size="sm" disabled={saving || !editing.name.trim()}>{saving ? "Saving…" : "Save"}</Button>
                <Button type="button" size="sm" variant="ghost" disabled={saving} onClick={() => setEditing(null)}>Cancel</Button>
              </form>
            ) : null}
            <div id={contentId} hidden={!isExpanded}>
              {group.projects.map((project) => {
                const rows = sessions.filter((session) => session.project_id === project.project_id);
                return (
                  <section
                    key={project.project_id}
                    aria-label={`${group.name} ${project.agent} sessions`}
                    className={cn("border-b border-line last:border-b-0", project.hidden && "opacity-70")}
                  >
                    <header className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <AgentBadge agent={project.agent} />
                          {project.hidden ? <Badge>Hidden</Badge> : null}
                          <span className="text-2xs tabular-nums text-subtle">
                            {rows.length} {rows.length === 1 ? "session" : "sessions"}
                          </span>
                      </div>
                    </div>
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
          </section>
        );
      })}
    </div>
  );
}
