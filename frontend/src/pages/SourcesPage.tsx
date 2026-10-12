import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { agentLabel, formatTime } from "../lib/format";

export function SourcesPage() {
  const queryClient = useQueryClient();
  const sources = useQuery({ queryKey: ["sources"], queryFn: api.sources });
  const scan = useMutation({
    mutationFn: (full: boolean) => api.reindex(full),
    onSuccess: () => queryClient.invalidateQueries(),
  });

  return (
    <div className="h-full overflow-auto px-4 py-4 md:px-6">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <button type="button" className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-[#1a1608]" onClick={() => scan.mutate(false)} disabled={scan.isPending}>
          {scan.isPending ? "Scanning…" : "Rescan"}
        </button>
        <button
          type="button"
          className="rounded-md border border-line px-3 py-1.5 text-sm"
          disabled={scan.isPending}
          onClick={() => {
            if (window.confirm("Rebuild the index? Notes, hidden projects, path allows, and benchmark cases stay.")) {
              scan.mutate(true);
            }
          }}
        >
          Full rebuild
        </button>
        <span className="text-sm text-muted">
          Last index: {formatTime(sources.data?.last_indexed_at)}
        </span>
      </div>
      {scan.isError ? <p className="mb-3 text-sm text-danger">{(scan.error as Error).message}</p> : null}
      <div className="mb-6 overflow-hidden rounded-xl border border-line">
        <table className="w-full text-left text-sm">
          <thead className="text-xs uppercase tracking-wide text-muted">
            <tr>
              <th className="px-4 py-2 font-medium">Path</th>
              <th className="px-3 py-2 font-medium">Agent</th>
              <th className="px-3 py-2 font-medium">Files</th>
              <th className="px-3 py-2 font-medium">Sessions</th>
            </tr>
          </thead>
          <tbody>
            {(sources.data?.sources ?? []).map((source) => (
              <tr key={source.path} className="border-t border-line">
                <td className="px-4 py-2 font-mono text-xs">{source.path}</td>
                <td className="px-3 py-2">
                  {source.agent ? agentLabel(source.agent) : "Not detected"}
                  {!source.exists ? " · missing" : ""}
                  {source.exists && !source.detected ? " · unrecognized" : ""}
                </td>
                <td className="px-3 py-2">{source.files}</td>
                <td className="px-3 py-2">{source.sessions}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <section className="max-w-2xl space-y-2 rounded-xl border border-line bg-surface p-4 text-sm">
        <h2 className="font-medium">OpenTelemetry</h2>
        {sources.data?.otel.enabled ? (
          <p className="text-muted">
            Exporting {sources.data.otel.protocol} to {sources.data.otel.endpoint}.
            {sources.data.otel.include_content
              ? " Content export is on, so prompt and tool text can leave this machine."
              : " Content stays local. Spans carry structure and usage only."}
          </p>
        ) : (
          <p className="text-muted">Export is off because no collector endpoint is set.</p>
        )}
        {sources.data?.otel.last_error ? <p className="text-danger">Last export error: {sources.data.otel.last_error}</p> : null}
      </section>
    </div>
  );
}
