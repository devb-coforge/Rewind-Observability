import { useState, type SyntheticEvent } from "react";
import { api } from "../../api/client";
import type { ObsEvent } from "../../api/types";
import { stringField } from "../../lib/diff";
import { formatTime } from "../../lib/format";
import { DiffView, PatchView } from "./DiffView";

const SHELL = new Set(["bash", "shell", "exec", "exec_command", "powershell", "cmd"]);

function filePath(input: Record<string, unknown> | null): string | null {
  return stringField(input, "file_path") || stringField(input, "path") || stringField(input, "notebook_path");
}

export function ToolCallCard({ call, result, expanded, onExpandedChange, onRaw }: {
  call: ObsEvent;
  result?: ObsEvent;
  expanded?: boolean;
  onExpandedChange?: (open: boolean) => void;
  onRaw?: (id: string) => void;
}) {
  const input = call.tool_input;
  const name = call.tool_name || "tool";
  const command = stringField(input, "command") || stringField(input, "cmd");
  const path = filePath(input);
  const patch = stringField(input, "patch");
  const oldString = stringField(input, "old_string");
  const newString = stringField(input, "new_string");
  const content = stringField(input, "content");
  const edits = Array.isArray(input?.edits) ? input.edits : [];
  const failed = call.is_error || Boolean(result?.is_error);
  const outside = [...(call.paths || []), ...(result?.paths || [])].some((item) => item.outside && !item.allowed);
  const [output, setOutput] = useState(result?.text || result?.tool_output_preview || call.tool_output_preview || "");
  const [loaded, setLoaded] = useState(false);

  async function onToggle(event: SyntheticEvent<HTMLDetailsElement>) {
    const open = event.currentTarget.open;
    onExpandedChange?.(open);
    if (!open || loaded || !result) return;
    setLoaded(true);
    try {
      const body = await api.eventOutput(result.id);
      if (body.output != null) setOutput(body.output);
    } catch {
      /* preview stays */
    }
  }

  return (
    <details open={expanded} className={`tool-card rounded-lg border bg-surface ${failed ? "border-danger/60" : "border-line"}`} onToggle={onToggle}>
      <summary className="cursor-pointer list-none px-3 py-2">
        <div className="flex flex-wrap items-center gap-2">
          <span aria-hidden="true" className="disclosure-arrow text-muted">›</span>
          <span className="font-mono text-sm text-accent">{name}</span>
          {failed ? <span className="rounded bg-danger/20 px-1.5 py-0.5 text-xs text-danger">error</span> : null}
          {!failed ? <span className={`rounded px-1.5 py-0.5 text-xs ${result ? "bg-ok/10 text-ok" : "bg-surface2 text-muted"}`}>{result ? "completed" : "no result"}</span> : null}
          {outside ? (
            <span className="rounded bg-danger/20 px-1.5 py-0.5 text-xs text-danger">outside project</span>
          ) : null}
          <span className="min-w-0 flex-1 truncate font-mono text-xs text-muted">
            {command || path || patch?.split("\n")[0] || ""}
          </span>
          <span className="text-xs text-muted">{formatTime(call.ts)}</span>
        </div>
      </summary>
      <div className="space-y-3 border-t border-line px-3 py-3">
        {onRaw ? <div className="flex items-center gap-3 text-xs text-muted">
          <span>Step {call.seq}</span>
          <button type="button" className="ml-auto hover:text-ink" onClick={() => onRaw(call.id)}>View raw call</button>
          {result ? <button type="button" className="hover:text-ink" onClick={() => onRaw(result.id)}>View raw result</button> : null}
        </div> : null}
        {SHELL.has(name) && command ? (
          <pre className="overflow-auto rounded-md bg-[#10120c] p-3 font-mono text-xs text-ink">{command}</pre>
        ) : null}
        {oldString != null || newString != null ? <DiffView before={oldString || ""} after={newString || ""} /> : null}
        {edits.map((edit, index) => {
          if (!edit || typeof edit !== "object") return null;
          const record = edit as Record<string, unknown>;
          return (
            <div key={index} className="space-y-1">
              <div className="font-mono text-xs text-muted">{stringField(record, "file_path")}</div>
              <DiffView before={stringField(record, "old_string") || ""} after={stringField(record, "new_string") || ""} />
            </div>
          );
        })}
        {patch ? <PatchView patch={patch} /> : null}
        {content && !oldString && !patch ? (
          <pre className="overflow-auto rounded-md bg-[#10120c] p-3 font-mono text-xs">{content}</pre>
        ) : null}
        {path && !command ? <div className="font-mono text-xs text-muted">{path}</div> : null}
        {!command && !patch && !path && !content && oldString == null && newString == null && edits.length === 0 && input ? (
          <div><h3 className="mb-1 text-xs text-muted">Input</h3><pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-md bg-[#10120c] p-3 font-mono text-xs">{JSON.stringify(input, null, 2)}</pre></div>
        ) : null}
        <h3 className="text-xs text-muted">Output</h3>
        {output ? (
          <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded-md bg-[#10120c] p-3 font-mono text-xs text-ink">
            {output}
          </pre>
        ) : (
          <p className="text-xs text-muted">No output captured.</p>
        )}
      </div>
    </details>
  );
}
