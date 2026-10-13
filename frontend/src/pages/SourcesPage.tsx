import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, RefreshCw } from "lucide-react";
import { api } from "../api/client";
import { AgentBadge, Badge, Button, Card, ErrorText, Page, PageHeader, SectionTitle, td, th } from "../components/ui";
import { cn } from "../lib/cn";
import { formatTime } from "../lib/format";

export function SourcesPage() {
  const queryClient = useQueryClient();
  const sources = useQuery({ queryKey: ["sources"], queryFn: api.sources });
  const scan = useMutation({
    mutationFn: (full: boolean) => api.reindex(full),
    onSuccess: () => queryClient.invalidateQueries(),
  });
  const otel = sources.data?.otel;

  return (
    <Page>
      <PageHeader
        title="Sources"
        description={
          sources.data?.last_indexed_at
            ? `Transcript folders being indexed. Last indexed ${formatTime(sources.data.last_indexed_at)}.`
            : "Transcript folders being indexed."
        }
        actions={
          <>
            <Button
              disabled={scan.isPending}
              onClick={() => {
                if (window.confirm("Rebuild the index?")) {
                  scan.mutate(true);
                }
              }}
            >
              Full rebuild
            </Button>
            <Button variant="primary" onClick={() => scan.mutate(false)} disabled={scan.isPending}>
              <RefreshCw aria-hidden="true" className={cn("size-3.5", scan.isPending && "animate-spin")} />
              {scan.isPending ? "Scanning…" : "Rescan"}
            </Button>
          </>
        }
      />
      {scan.isError ? <ErrorText>{(scan.error as Error).message}</ErrorText> : null}
      <Card className="mb-8 overflow-x-auto">
        <table className="w-full min-w-[640px] text-[13px]">
          <thead className="bg-surface2/50">
            <tr>
              <th className={th}>Path</th>
              <th className={th}>Agent</th>
              <th className={th}>Status</th>
              <th className={cn(th, "text-right")}>Files</th>
              <th className={cn(th, "text-right")}>Sessions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {(sources.data?.sources ?? []).map((source) => (
              <tr key={source.path} className="hover:bg-surface2/60">
                <td className={cn(td, "font-mono text-xs")}>{source.path}</td>
                <td className={td}>
                  {source.agent ? <AgentBadge agent={source.agent} /> : <span className="text-subtle">Not detected</span>}
                </td>
                <td className={td}>
                  {!source.exists ? (
                    <Badge tone="danger">missing</Badge>
                  ) : !source.detected ? (
                    <Badge tone="warn">unrecognized</Badge>
                  ) : (
                    <Badge tone="ok">active</Badge>
                  )}
                </td>
                <td className={cn(td, "text-right tabular-nums text-muted")}>{source.files.toLocaleString()}</td>
                <td className={cn(td, "text-right tabular-nums")}>{source.sessions.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      <SectionTitle>Export</SectionTitle>
      <Card className="max-w-2xl p-4">
        <div className="flex items-start gap-3">
          <span aria-hidden="true" className="grid size-8 shrink-0 place-items-center rounded-md border border-line-strong bg-surface2 text-muted">
            <Activity className="size-4" />
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <h2 className="text-[13px] font-medium">OpenTelemetry</h2>
              {otel?.enabled ? <Badge tone="ok">Enabled</Badge> : <Badge>Disabled</Badge>}
            </div>
            {otel?.enabled ? (
              <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-xs">
                <dt className="text-subtle">Protocol</dt>
                <dd className="font-mono">{otel.protocol}</dd>
                <dt className="text-subtle">Endpoint</dt>
                <dd className="truncate font-mono">{otel.endpoint}</dd>
                <dt className="text-subtle">Content</dt>
                <dd>{otel.include_content ? "Content on" : "Content off"}</dd>
              </dl>
            ) : (
              <p className="mt-1 text-xs text-muted">Spans are not being exported.</p>
            )}
            {otel?.last_error ? <p className="mt-2 text-xs text-danger">Last export error: {otel.last_error}</p> : null}
          </div>
        </div>
      </Card>
    </Page>
  );
}
