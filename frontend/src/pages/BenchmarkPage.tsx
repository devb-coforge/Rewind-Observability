import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { BenchmarkCase } from "../api/types";
import { agentLabel, formatCost, formatPercent, formatTokens } from "../lib/format";

export function BenchmarkPage() {
  const queryClient = useQueryClient();
  const [project, setProject] = useState("");
  const [verdict, setVerdict] = useState("");
  const projects = useQuery({ queryKey: ["projects", true], queryFn: () => api.projects(true) });
  const summary = useQuery({
    queryKey: ["benchmark", "summary", project],
    queryFn: () => api.benchmarkSummary(project || undefined),
  });
  const cases = useQuery({
    queryKey: ["benchmark", "cases", project, verdict],
    queryFn: () => api.cases({ project: project || undefined, verdict: verdict || undefined }),
  });

  function refresh() {
    return queryClient.invalidateQueries({ queryKey: ["benchmark"] });
  }

  return (
    <div className="h-full overflow-auto px-4 py-4 md:px-6">
      <p className="mb-4 max-w-3xl text-sm text-muted">{summary.data?.note}</p>
      <div className="mb-4 flex flex-wrap gap-2">
        <select className="rounded-md border border-line bg-surface px-2 py-1.5 text-sm" aria-label="Project" value={project} onChange={(event) => setProject(event.target.value)}>
          <option value="">All projects</option>
          {(projects.data?.projects ?? []).map((item) => (
            <option key={item.project_id} value={item.project_id}>
              {item.name}
            </option>
          ))}
        </select>
        <select className="rounded-md border border-line bg-surface px-2 py-1.5 text-sm" aria-label="Verdict" value={verdict} onChange={(event) => setVerdict(event.target.value)}>
          <option value="">All verdicts</option>
          <option value="unset">Unset</option>
          <option value="pass">Pass</option>
          <option value="fail">Fail</option>
        </select>
      </div>
      <div className="mb-6 overflow-x-auto rounded-xl border border-line">
        <table className="w-full min-w-[640px] text-left text-sm">
          <thead className="text-xs uppercase tracking-wide text-muted">
            <tr>
              <th className="px-4 py-2 font-medium">Model</th>
              <th className="px-3 py-2 font-medium">Cases</th>
              <th className="px-3 py-2 font-medium">Pass rate</th>
              <th className="px-3 py-2 font-medium">Median cost</th>
              <th className="px-3 py-2 font-medium">Median tokens</th>
            </tr>
          </thead>
          <tbody>
            {(summary.data?.groups ?? []).map((group) => (
              <tr key={group.model} className="border-t border-line">
                <td className="px-4 py-2">{group.model}</td>
                <td className="px-3 py-2">{group.n}</td>
                <td className="px-3 py-2">
                  {formatPercent(group.pass_rate)}
                  <span className="text-xs text-muted"> ({group.n_verdict} labeled)</span>
                </td>
                <td className="px-3 py-2">{formatCost(group.median_cost)}</td>
                <td className="px-3 py-2">{formatTokens(group.median_tokens)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {summary.data && summary.data.groups.length === 0 ? <p className="px-4 py-3 text-sm text-muted">No cases yet. Freeze one from a session.</p> : null}
      </div>
      <div className="space-y-3">
        {(cases.data?.cases ?? []).map((item) => (
          <CaseCard key={item.id} item={item} onChange={refresh} />
        ))}
      </div>
    </div>
  );
}

function CaseCard({ item, onChange }: { item: BenchmarkCase; onChange: () => Promise<void> }) {
  const [note, setNote] = useState(item.note ?? "");
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");
  const detail = useQuery({
    queryKey: ["benchmark", "case", item.id],
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
    <article className="rounded-xl border border-line bg-surface p-4">
      <div className="flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1">
          <Link className="text-sm text-accent hover:underline" to={`/sessions/${encodeURIComponent(item.session_id)}`}>
            {item.prompt || item.session_id}
          </Link>
          <p className="mt-1 text-xs text-muted">
            {agentLabel(item.agent)} · {item.model || "unknown model"} · {item.project_name || "(unknown)"} ·{" "}
            {formatCost(item.est_cost_usd)} · {formatTokens(item.tokens_in)} / {formatTokens(item.tokens_out)} tokens
          </p>
        </div>
        <div className="flex gap-1">
          {(["pass", "fail", "unset"] as const).map((verdict) => (
            <button
              key={verdict}
              type="button"
              className={`rounded-md border px-2 py-1 text-xs ${item.verdict === verdict ? "border-accent text-accent" : "border-line text-muted"}`}
              onClick={() => void setVerdict(verdict)}
            >
              {verdict}
            </button>
          ))}
        </div>
      </div>
      <ul className="mt-3 space-y-1 text-xs text-muted">
        {item.tool_summary.map((tool, index) => (
          <li key={`${tool.tool_name}-${index}`}>
            {tool.tool_name || "tool"}
            {tool.is_error ? " · error" : ""}
            {tool.paths.length ? ` · ${tool.paths.join(", ")}` : ""}
          </li>
        ))}
      </ul>
      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" className="text-xs text-accent" onClick={() => setOpen((value) => !value)}>
          {open ? "Hide detail" : "Show detail"}
        </button>
        <button
          type="button"
          className="text-xs text-danger"
          onClick={() => {
            if (window.confirm("Delete this case?")) {
              void api.deleteCase(item.id).then(onChange);
            }
          }}
        >
          Delete
        </button>
      </div>
      {open && detail.data ? (
        <div className="mt-3 space-y-2 text-sm">
          <p className="whitespace-pre-wrap">{detail.data.prompt}</p>
          <p className="whitespace-pre-wrap text-muted">{detail.data.final_message}</p>
        </div>
      ) : null}
      <div className="mt-3 flex gap-2">
        <input
          className="min-w-0 flex-1 rounded-md border border-line bg-[#10120c] px-2 py-1 text-sm"
          aria-label="Case note"
          value={note}
          onChange={(event) => setNote(event.target.value)}
        />
        <button
          type="button"
          className="rounded-md border border-line px-2 py-1 text-sm"
          onClick={() => void api.patchCase(item.id, { note }).then(onChange).catch((err: unknown) => setError(err instanceof Error ? err.message : "Could not save the note"))}
        >
          Save note
        </button>
      </div>
      {error ? <p className="mt-2 text-xs text-danger">{error}</p> : null}
    </article>
  );
}
