import type { ObsEvent } from "../../api/types";

export type TimelineItem =
  | { type: "single"; event: ObsEvent }
  | { type: "tool"; call: ObsEvent; result?: ObsEvent };

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
    if (event.kind === "tool_call" && event.tool_call_id) {
      if (consumed.has(event.tool_call_id)) continue;
      consumed.add(event.tool_call_id);
      items.push({ type: "tool", call: event, result: results.get(event.tool_call_id) });
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
