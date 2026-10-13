import { ChevronRight, FilePen, Terminal, Wrench } from "lucide-react";
import { useState, type ReactNode, type SyntheticEvent } from "react";
import { api } from "../../api/client";
import type { ObsEvent } from "../../api/types";
import { cn } from "../../lib/cn";
import { stringField } from "../../lib/diff";
import { formatTime } from "../../lib/format";
import { Badge } from "../ui";
import { codeBlock, DiffView, PatchView } from "./DiffView";

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
  const content = stringField(input, "content") || stringField(input, "contents");
  const edits = Array.isArray(input?.edits) ? input.edits : [];
  const declined = call.is_declined || result?.is_declined;
  const failed = call.is_error || Boolean(result?.is_error);
  const outside = [...(call.paths || []), ...(result?.paths || [])].some((item) => item.outside && !item.allowed);
  const [output, setOutput] = useState(result?.text || result?.tool_output_preview || call.tool_output_preview || "");
  const [loaded, setLoaded] = useState(false);
  const shell = SHELL.has(name.toLowerCase());
  const Icon = shell ? Terminal : path || patch ? FilePen : Wrench;

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
    <details
      open={expanded}
      className={cn("tool-card group rounded-lg border bg-surface", failed ? "border-danger/35" : "border-line")}
      onToggle={onToggle}
    >
      <summary className="flex cursor-pointer list-none items-center gap-2 rounded-lg px-3 py-2 transition-colors hover:bg-surface2/60">
        <ChevronRight aria-hidden="true" className="disclosure size-3.5 shrink-0 text-subtle transition-transform" />
        <span
          aria-hidden="true"
          className={cn(
            "grid size-5 shrink-0 place-items-center rounded border",
            failed ? "border-danger/30 bg-danger/10 text-danger" : "border-line-strong bg-surface2 text-muted",
          )}
        >
          <Icon className="size-3" />
        </span>
        <span className="shrink-0 font-mono text-xs font-medium text-ink">{name}</span>
        <span className="min-w-0 flex-1 truncate font-mono text-xs text-subtle">
          {command || path || patch?.split("\n")[0] || ""}
        </span>
        {outside ? <Badge tone="warn">outside project</Badge> : null}
        {declined ? (
          <Badge tone="warn">User declined</Badge>
        ) : failed ? (
          <Badge tone="danger">error</Badge>
        ) : result ? (
          <span className="flex shrink-0 items-center gap-1.5 text-2xs text-subtle">
            <span aria-hidden="true" className="size-1.5 rounded-full bg-ok" />
            completed
          </span>
        ) : (
          <span className="flex shrink-0 items-center gap-1.5 text-2xs text-subtle">
            <span aria-hidden="true" className="size-1.5 rounded-full bg-line-strong" />
            no result
          </span>
        )}
        <span className="hidden shrink-0 text-2xs tabular-nums text-subtle sm:inline">{formatTime(call.ts)}</span>
      </summary>
      <div className="space-y-3 border-t border-line px-4 py-3">
        {onRaw ? (
          <div className="flex items-center gap-1 text-2xs text-subtle">
            <span className="tabular-nums">Step {call.seq}</span>
            <span className="ml-auto" />
            <RawButton onClick={() => onRaw(call.id)}>View raw call</RawButton>
            {result ? <RawButton onClick={() => onRaw(result.id)}>View raw result</RawButton> : null}
          </div>
        ) : null}
        {shell && command ? (
          <Block label="Command">
            <pre className={cn(codeBlock, "text-ink")}>
              <span className="select-none text-subtle">$ </span>
              {command}
            </pre>
          </Block>
        ) : null}
        {path && !command ? <div className="truncate font-mono text-xs text-muted">{path}</div> : null}
        {oldString != null || newString != null ? <DiffView before={oldString || ""} after={newString || ""} /> : null}
        {edits.map((edit, index) => {
          if (!edit || typeof edit !== "object") return null;
          const record = edit as Record<string, unknown>;
          return (
            <div key={index} className="space-y-1.5">
              <div className="font-mono text-2xs text-subtle">{stringField(record, "file_path")}</div>
              <DiffView before={stringField(record, "old_string") || ""} after={stringField(record, "new_string") || ""} />
            </div>
          );
        })}
        {patch ? <PatchView patch={patch} /> : null}
        {content && !oldString && !patch ? <pre className={cn(codeBlock, "max-h-80 text-ink/90")}>{content}</pre> : null}
        {!command && !patch && !path && !content && oldString == null && newString == null && edits.length === 0 && input ? (
          <Block label="Input">
            <pre className={cn(codeBlock, "max-h-64 whitespace-pre-wrap break-words text-ink/90")}>{JSON.stringify(input, null, 2)}</pre>
          </Block>
        ) : null}
        <Block label="Output">
          {output ? (
            <pre className={cn(codeBlock, "max-h-80 whitespace-pre-wrap break-words", failed ? "text-danger/90" : "text-ink/90")}>{output}</pre>
          ) : (
            <p className="text-xs text-subtle">No output captured.</p>
          )}
        </Block>
      </div>
    </details>
  );
}

function Block({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <h3 className="mb-1.5 text-2xs font-medium uppercase tracking-[0.06em] text-subtle">{label}</h3>
      {children}
    </div>
  );
}

function RawButton({ onClick, children }: { onClick: () => void; children: ReactNode }) {
  return (
    <button type="button" className="rounded px-1.5 py-0.5 font-medium transition-colors hover:bg-surface3 hover:text-ink" onClick={onClick}>
      {children}
    </button>
  );
}
