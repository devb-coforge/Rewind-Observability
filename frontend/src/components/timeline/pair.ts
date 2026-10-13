import type { ObsEvent } from "../../api/types";

export type TimelineItem =
  | { type: "single"; event: ObsEvent }
  | { type: "tool"; call: ObsEvent; result?: ObsEvent };

export type TimelineView = "all" | "conversation" | "tools" | "errors";

export function matchesView(item: TimelineItem, view: TimelineView): boolean {
  if (view === "all") return true;
  if (view === "errors") {
    return item.type === "tool" ? item.call.is_error || Boolean(item.result?.is_error) : item.event.is_error;
  }
  if (view === "tools") {
    return item.type === "tool" || ["tool_call", "tool_result"].includes(item.event.kind);
  }
  return item.type === "single" && (item.event.kind === "summary" ||
    (item.event.kind === "message" && ["user", "assistant"].includes(item.event.role)));
}

export function filterTimeline(items: TimelineItem[], view: TimelineView, showThinking: boolean, focusId?: string | null): TimelineItem[] {
  return items.filter((item) => (focusId && itemMatches(item, focusId)) ||
    (matchesView(item, view) && (showThinking || item.type === "tool" || item.event.kind !== "thinking")));
}

export function pairEvents(events: ObsEvent[]): TimelineItem[] {
  const results = new Map<string, ObsEvent>();
  for (const event of events) {
    if (event.kind === "tool_result" && event.tool_call_id) {
      results.set(event.tool_call_id, event);
    }
  }
  const consumed = new Set<string>();
  const items: TimelineItem[] = [];
  for (const event of events) {
    if (event.kind === "tool_result" && event.tool_call_id && results.has(event.tool_call_id)) {
      const callExists = events.some(
        (candidate) => candidate.kind === "tool_call" && candidate.tool_call_id === event.tool_call_id,
      );
      if (callExists) continue;
    }
    if (event.kind === "tool_call") {
      if (event.tool_call_id && consumed.has(event.tool_call_id)) continue;
      if (event.tool_call_id) consumed.add(event.tool_call_id);
      items.push({ type: "tool", call: event, result: event.tool_call_id ? results.get(event.tool_call_id) : undefined });
      continue;
    }
    items.push({ type: "single", event });
  }
  return items;
}

export function timelineItems(events: ObsEvent[], showThinking: boolean): TimelineItem[] {
  return pairEvents(events).filter((item) => {
    if (showThinking || item.type === "tool") return true;
    return item.event.kind !== "thinking";
  });
}

export function itemKey(item: TimelineItem): string {
  return item.type === "tool" ? item.call.id : item.event.id;
}

export function itemMatches(item: TimelineItem, eventId: string): boolean {
  if (item.type === "tool") return item.call.id === eventId || item.result?.id === eventId;
  return item.event.id === eventId;
}
