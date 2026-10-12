import Markdown from "react-markdown";
import type { ObsEvent } from "../../api/types";
import { formatTime } from "../../lib/format";
import { ThinkingBlock } from "./ThinkingBlock";

export function EventRow({
  event,
  focused,
  onRaw,
}: {
  event: ObsEvent;
  focused?: boolean;
  onRaw: (id: string) => void;
}) {
  const outside = event.paths?.some((item) => item.outside && !item.allowed);
  const ring = focused ? "ring-1 ring-accent" : "";
  const edge = outside ? "border-l-2 border-l-danger" : "";

  if (event.kind === "thinking") {
    return (
      <div className={ring}>
        <ThinkingBlock text={event.text} />
      </div>
    );
  }

  const role =
    event.kind === "summary"
      ? "Summary"
      : event.kind === "unknown"
        ? "Unrecognized"
        : event.kind === "system"
          ? "System"
          : event.role === "assistant"
            ? "Assistant"
            : event.role === "user"
              ? "You"
              : event.role;

  return (
    <article className={`rounded-lg border border-line bg-surface px-3 py-2 ${edge} ${ring}`}>
      <header className="mb-1 flex items-center gap-2 text-xs text-muted">
        <span className="uppercase tracking-wide">{role}</span>
        <span>{formatTime(event.ts)}</span>
        {event.model ? <span className="truncate">{event.model}</span> : null}
        {outside ? <span className="text-danger">outside project</span> : null}
        <button type="button" className="ml-auto underline-offset-2 hover:underline" onClick={() => onRaw(event.id)}>
          View raw
        </button>
      </header>
      {event.role === "assistant" && event.kind === "message" ? (
        <div className="md text-sm">
          <Markdown>{event.text || ""}</Markdown>
        </div>
      ) : (
        <p className="whitespace-pre-wrap text-sm">{event.text || (event.kind === "unknown" ? "(unparsed line)" : "")}</p>
      )}
    </article>
  );
}
