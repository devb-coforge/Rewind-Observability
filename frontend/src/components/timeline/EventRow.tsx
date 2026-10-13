import { Bot, ChevronRight, FileText, HelpCircle, Settings2, User } from "lucide-react";
import { useState, type ReactNode } from "react";
import Markdown from "react-markdown";
import type { ObsEvent } from "../../api/types";
import { cn } from "../../lib/cn";
import { formatTime } from "../../lib/format";
import { Badge } from "../ui";
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
  const ring = focused ? "ring-1 ring-accent/70 ring-offset-2 ring-offset-bg" : "";

  if (event.kind === "thinking") {
    return (
      <div className={cn("rounded-lg", ring)}>
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
    <div className="md break-words text-[13px] text-ink/90"><Markdown>{event.text || ""}</Markdown></div>
  ) : (
    <p className="whitespace-pre-wrap break-words text-[13px] leading-relaxed text-ink/90">
      {event.text || (event.kind === "unknown" ? "(unparsed line)" : "No message content.")}
    </p>
  );

  const flags = (
    <>
      {outside ? <Badge tone="warn">outside project</Badge> : null}
      {event.is_error ? <Badge tone="danger">error</Badge> : null}
    </>
  );
  const rawButton = (
    <button
      type="button"
      className="shrink-0 rounded px-1.5 py-0.5 text-2xs font-medium text-subtle transition-colors hover:bg-surface3 hover:text-ink"
      onClick={() => onRaw(event.id)}
    >
      View raw
    </button>
  );

  if (system) {
    return (
      <article className={cn("rounded-lg border border-dashed border-line-strong/70 bg-surface/40", outside && "border-warn/40", ring)}>
        <div className="flex items-center gap-2 px-3 py-1.5">
          <button
            type="button"
            className="flex min-w-0 flex-1 items-center gap-2 py-0.5 text-left text-xs text-muted hover:text-ink"
            aria-expanded={open}
            aria-label={`${open ? "Collapse" : "Expand"} ${role.toLowerCase()} message`}
            onClick={() => (onExpandedChange || setLocalExpanded)(!open)}
          >
            <ChevronRight aria-hidden="true" className={cn("size-3.5 shrink-0 text-subtle transition-transform", open && "rotate-90")} />
            <Settings2 aria-hidden="true" className="size-3.5 shrink-0 text-subtle" />
            <span className="shrink-0 font-medium">{role}</span>
            <span className="shrink-0 tabular-nums text-subtle">{formatTime(event.ts)}</span>
            {!open ? (
              <span className="truncate text-subtle">
                {event.text?.replace(/\s+/g, " ").trim().slice(0, 180) || "No message content."}
              </span>
            ) : null}
          </button>
          {flags}
          {rawButton}
        </div>
        {open ? <div className="border-t border-dashed border-line-strong/70 px-4 py-3">{body}</div> : null}
      </article>
    );
  }

  const user = event.role === "user";
  return (
    <article
      className={cn(
        "rounded-lg border px-4 py-3",
        user ? "border-accent/20 bg-accent/[0.05]" : "border-line bg-surface",
        outside && "border-l-2 border-l-warn",
        ring,
      )}
    >
      <header className="mb-1.5 flex items-center gap-2 text-xs">
        <RoleIcon role={role} />
        <span className={cn("font-medium", user ? "text-accent" : "text-ink")}>{role}</span>
        <span className="tabular-nums text-subtle">{formatTime(event.ts)}</span>
        {event.model ? <span className="truncate font-mono text-2xs text-subtle">{event.model}</span> : null}
        <span className="ml-auto flex items-center gap-1.5">
          {flags}
          {rawButton}
        </span>
      </header>
      {body}
    </article>
  );
}

function RoleIcon({ role }: { role: string }) {
  const icons: Record<string, ReactNode> = {
    You: <User className="size-3.5 text-accent" />,
    Assistant: <Bot className="size-3.5 text-muted" />,
    Summary: <FileText className="size-3.5 text-muted" />,
  };
  return <span aria-hidden="true">{icons[role] ?? <HelpCircle className="size-3.5 text-subtle" />}</span>;
}
