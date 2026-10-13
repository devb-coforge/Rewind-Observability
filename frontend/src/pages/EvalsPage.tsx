import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronDown, FlaskConical, Minus, Trash2, X } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { EvalCase } from "../api/types";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Button, Card, EmptyState, Input, Page, PageHeader, SectionTitle, Select, td, th, Toolbar } from "../components/ui";
import { cn } from "../lib/cn";
import { agentLabel, formatCompact, formatCost, formatPercent } from "../lib/format";
import { groupProjectsByPath, projectFilters } from "../lib/projects";

export function EvalsPage() {
  const queryClient = useQueryClient();
  const [project, setProject] = useState("");
  const [verdict, setVerdict] = useState("");
  const projects = useQuery({ queryKey: ["projects", true], queryFn: () => api.projects(true) });
  const summary = useQuery({
    queryKey: ["evals", "summary", project],
    queryFn: () => api.evalsSummary(projectFilters(project)),
  });
  const cases = useQuery({
    queryKey: ["evals", "cases", project, verdict],
    queryFn: () => api.cases({ ...projectFilters(project), verdict: verdict || undefined }),
  });

  function refresh() {
    return queryClient.invalidateQueries({ queryKey: ["evals"] });
  }

  const groups = summary.data?.groups ?? [];
  const caseList = cases.data?.cases ?? [];

  return (
    <Page>
      <PageHeader title="Evals" />
      <Toolbar>
        <Select className="w-52" aria-label="Project" value={project} onChange={(event) => setProject(event.target.value)}>
          <option value="">All projects</option>
          {groupProjectsByPath(projects.data?.projects ?? []).map((group) => (
            <option key={group.key} value={group.key} title={group.cwd || undefined}>
              {group.name}
            </option>
          ))}
        </Select>
        <Select className="w-36" aria-label="Verdict" value={verdict} onChange={(event) => setVerdict(event.target.value)}>
          <option value="">All verdicts</option>
          <option value="unset">Unset</option>
          <option value="pass">Pass</option>
          <option value="fail">Fail</option>
        </Select>
      </Toolbar>
      <Card className="mb-8 overflow-x-auto">
        <table className="w-full min-w-[640px] text-[13px]">
          <thead className="bg-surface2/50">
            <tr>
              <th className={th}>Model</th>
              <th className={th}>Agent</th>
              <th className={cn(th, "text-right")}>Cases</th>
              <th className={th}>Pass rate</th>
              <th className={cn(th, "text-right")}>Median cost</th>
              <th className={cn(th, "text-right")}>Median tokens</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {groups.map((group) => (
              <tr key={`${group.model}::${group.agent}`} className="hover:bg-surface2/60">
                <td className={cn(td, "font-mono text-xs")}>{group.model}</td>
                <td className={cn(td, "text-muted")}>{agentLabel(group.agent)}</td>
                <td className={cn(td, "text-right tabular-nums")}>{group.n}</td>
                <td className={td}>
                  <div className="flex items-center gap-3">
                    <div className="h-1.5 w-24 overflow-hidden rounded-full bg-surface3">
                      <div className="h-full rounded-full bg-ok" style={{ width: `${Math.round((group.pass_rate ?? 0) * 100)}%` }} />
                    </div>
                    <span className="tabular-nums">{formatPercent(group.pass_rate)}</span>
                  </div>
                </td>
                <td className={cn(td, "text-right tabular-nums")}>{formatCost(group.median_cost)}</td>
                <td className={cn(td, "text-right tabular-nums text-muted")}>{formatCompact(group.median_tokens)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {summary.data && groups.length === 0 ? (
          <p className="px-4 py-4 text-[13px] text-muted">No cases yet. Freeze one from a session.</p>
        ) : null}
      </Card>
      <SectionTitle aside={caseList.length ? <span className="text-2xs tabular-nums text-subtle">{caseList.length}</span> : undefined}>
        Cases
      </SectionTitle>
      {cases.data && caseList.length === 0 ? (
        <EmptyState
          icon={<FlaskConical className="size-6" />}
          title="No cases match"
          description="Open a session and use “Freeze an eval case” to capture one."
        />
      ) : null}
      <div className="space-y-3">
        {caseList.map((item) => (
          <CaseCard key={item.id} item={item} onChange={refresh} />
        ))}
      </div>
    </Page>
  );
}

const verdictStyle = {
  pass: { icon: Check, active: "border-ok/40 bg-ok/10 text-ok" },
  fail: { icon: X, active: "border-danger/40 bg-danger/10 text-danger" },
  unset: { icon: Minus, active: "border-line-strong bg-surface3 text-ink" },
} as const;

function CaseCard({ item, onChange }: { item: EvalCase; onChange: () => Promise<void> }) {
  const [note, setNote] = useState(item.note ?? "");
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const detail = useQuery({
    queryKey: ["evals", "case", item.id],
    queryFn: () => api.case(item.id),
    enabled: open,
  });

  async function setVerdict(verdict: string) {
    setError("");
    try {
      await api.patchCase(item.id, { verdict });
      await onChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update the verdict");
    }
  }

  return (
    <Card className="p-4">
      <div className="flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1">
          <Link className="line-clamp-2 text-[13px] font-medium text-ink hover:text-accent" to={`/sessions/${encodeURIComponent(item.session_id)}`}>
            {item.session_title || "Untitled session"}
          </Link>
        </div>
        <div role="group" aria-label="Verdict" className="inline-flex rounded-md border border-line bg-bg p-0.5">
          {(["pass", "fail", "unset"] as const).map((verdict) => {
            const { icon: Icon, active } = verdictStyle[verdict];
            const selected = item.verdict === verdict;
            return (
              <button
                key={verdict}
                type="button"
                aria-pressed={selected}
                className={cn(
                  "flex h-6 items-center gap-1 rounded border px-2 text-2xs font-medium capitalize transition-colors",
                  selected ? active : "border-transparent text-subtle hover:text-ink",
                )}
                onClick={() => void setVerdict(verdict)}
              >
                <Icon aria-hidden="true" className="size-3" />
                {verdict}
              </button>
            );
          })}
        </div>
      </div>
      {open && detail.data ? (
        <div className="mt-3 space-y-3 rounded-md border border-line bg-bg/60 p-3 text-[13px]">
          <div>
            <div className="mb-1 text-2xs font-medium uppercase tracking-[0.06em] text-subtle">Prompt</div>
            <p className="whitespace-pre-wrap leading-relaxed">{detail.data.prompt}</p>
          </div>
          <div>
            <div className="mb-1 text-2xs font-medium uppercase tracking-[0.06em] text-subtle">Final message</div>
            <p className="whitespace-pre-wrap leading-relaxed text-muted">{detail.data.final_message}</p>
          </div>
        </div>
      ) : null}
      <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-line pt-3">
        <Input className="min-w-48 flex-1" placeholder="Add a note" aria-label="Case note" value={note} onChange={(event) => setNote(event.target.value)} />
        <Button
          size="sm"
          className="h-8"
          onClick={() => void api.patchCase(item.id, { note }).then(onChange).catch((err: unknown) => setError(err instanceof Error ? err.message : "Could not save the note"))}
        >
          Save note
        </Button>
        <Button size="sm" variant="ghost" className="h-8" onClick={() => setOpen((value) => !value)}>
          <ChevronDown aria-hidden="true" className={cn("size-3.5 transition-transform", open && "rotate-180")} />
          {open ? "Hide detail" : "Show detail"}
        </Button>
        <Button size="sm" variant="danger" className="h-8" onClick={() => setConfirmDelete(true)}>
          <Trash2 aria-hidden="true" className="size-3.5" />
          Delete
        </Button>
      </div>
      {error ? <p className="mt-2 text-xs text-danger">{error}</p> : null}
      <ConfirmDialog
        open={confirmDelete}
        title="Delete this case?"
        description="This removes the frozen eval case. This can't be undone."
        confirmLabel="Delete case"
        tone="danger"
        onConfirm={() => {
          setConfirmDelete(false);
          void api.deleteCase(item.id).then(onChange);
        }}
        onCancel={() => setConfirmDelete(false)}
      />
    </Card>
  );
}
