import { useState } from "react";
import Markdown from "react-markdown";
import type { ObsEvent } from "../../api/types";
import { formatTime } from "../../lib/format";
import { ThinkingBlock } from "./ThinkingBlock";

export function EventRow({
  event,
  focused,
  onRaw,
  expanded,
  onExpandedChange,
}: {
  event: ObsEvent;
  focused?: boolean;
  onRaw: (id: string) => void;
  expanded?: boolean;
  onExpandedChange?: (open: boolean) => void;
}) {
  const [localExpanded, setLocalExpanded] = useState<boolean>();
  const open = expanded ?? localExpanded ?? Boolean(focused);
  const system = event.kind === "system" || event.role === "system" || event.role === "developer";
  const outside = event.paths?.some((item) => item.outside && !item.allowed);
  const ring = focused ? "ring-1 ring-accent" : "";
  const edge = outside ? "border-l-2 border-l-danger" : "";

  if (event.kind === "thinking") {
    return (
      <div className={ring}>
        <ThinkingBlock text={event.text} expanded={open} onExpandedChange={onExpandedChange || setLocalExpanded} />
      </div>
    );
  }

  const role =
    event.kind === "summary"
      ? "Summary"
      : event.kind === "unknown"
        ? "Unrecognized"
        : system
          ? event.role === "developer" ? "Developer" : "System"
          : event.role === "assistant"
            ? "Assistant"
            : event.role === "user"
              ? "You"
              : event.role;

  const body = event.role === "assistant" && event.kind === "message" ? (
    <div className="md break-words text-sm"><Markdown>{event.text || ""}</Markdown></div>
  ) : (
    <p className="whitespace-pre-wrap break-words text-sm">{event.text || (event.kind === "unknown" ? "(unparsed line)" : "No message content.")}</p>
  );

  if (system) {
    return (
      <article className={`rounded-lg border border-line bg-surface/60 ${edge} ${ring}`}>
        <div className="flex items-center gap-2 px-3 py-2">
          <button
            type="button"
            className="flex min-w-0 flex-1 items-center gap-2 text-left text-xs text-muted"
            aria-expanded={open}
            aria-label={`${open ? "Collapse" : "Expand"} ${role.toLowerCase()} message`}
            onClick={() => (onExpandedChange || setLocalExpanded)(!open)}
          >
            <span aria-hidden="true" className={`disclosure-arrow ${open ? "rotate-90" : ""}`}>›</span>
            <span className="shrink-0 uppercase tracking-wide">{role}</span>
            <span className="shrink-0">{formatTime(event.ts)}</span>
            {!open ? <span className="truncate">{event.text?.replace(/\s+/g, " ").trim().slice(0, 180) || "No message content."}</span> : null}
          </button>
          {outside ? <span className="text-xs text-danger">outside project</span> : null}
          {event.is_error ? <span className="text-xs text-danger">error</span> : null}
          <button type="button" className="shrink-0 text-xs text-muted hover:text-ink" onClick={() => onRaw(event.id)}>View raw</button>
        </div>
        {open ? <div className="border-t border-line px-3 py-3">{body}</div> : null}
      </article>
    );
  }

  return (
    <article className={`rounded-lg border border-line bg-surface px-3 py-2 ${event.role === "user" ? "border-l-2 border-l-accent" : ""} ${edge} ${ring}`}>
      <header className="mb-1 flex items-center gap-2 text-xs text-muted">
        <span className="uppercase tracking-wide">{role}</span>
        <span>{formatTime(event.ts)}</span>
        {event.model ? <span className="truncate">{event.model}</span> : null}
        {outside ? <span className="text-danger">outside project</span> : null}
        {event.is_error ? <span className="text-danger">error</span> : null}
        <button type="button" className="ml-auto underline-offset-2 hover:underline" onClick={() => onRaw(event.id)}>
          View raw
        </button>
      </header>
      {body}
    </article>
  );
}
