import { describe, expect, it } from "vitest";
import type { ObsEvent } from "../../api/types";
import { filterTimeline, itemKey, pairEvents } from "./pair";

function event(partial: Partial<ObsEvent> & Pick<ObsEvent, "id" | "kind">): ObsEvent {
  return {
    session_id: "s",
    parent_id: null,
    seq: 0,
    ts: null,
    role: "assistant",
    text: null,
    tool_name: null,
    tool_call_id: null,
    tool_input: null,
    tool_output_preview: null,
    is_error: false,
    model: null,
    usage: null,
    raw: { path: "", offset: 0, length: 0 },
    paths: [],
    ...partial,
  };
}

describe("pairEvents", () => {
  it("filters conversation, tools, and errors while retaining failed tool results", () => {
    const items = pairEvents([
      event({ id: "s", kind: "system" }),
      event({ id: "u", kind: "message", role: "user" }),
      event({ id: "a", kind: "message" }),
      event({ id: "c", kind: "tool_call", tool_call_id: "1" }),
      event({ id: "r", kind: "tool_result", tool_call_id: "1", is_error: true }),
      event({ id: "orphan", kind: "tool_result" }),
      event({ id: "t", kind: "thinking" }),
      event({ id: "summary", kind: "summary" }),
    ]);
    expect(filterTimeline(items, "conversation", false).map(itemKey)).toEqual(["u", "a", "summary"]);
    expect(filterTimeline(items, "tools", false).map(itemKey)).toEqual(["c", "orphan"]);
    expect(filterTimeline(items, "errors", false).map(itemKey)).toEqual(["c"]);
    expect(filterTimeline(items, "all", false).map(itemKey)).not.toContain("t");
    expect(filterTimeline(items, "all", true).map(itemKey)).toContain("t");
  });

  it("keeps linked context and tool results accessible through filters", () => {
    const items = pairEvents([
      event({ id: "s", kind: "system" }),
      event({ id: "t", kind: "thinking" }),
      event({ id: "c", kind: "tool_call", tool_call_id: "1" }),
      event({ id: "r", kind: "tool_result", tool_call_id: "1" }),
    ]);
    expect(filterTimeline(items, "conversation", false, "s").map(itemKey)).toEqual(["s"]);
    expect(filterTimeline(items, "all", false, "t").map(itemKey)).toContain("t");
    expect(filterTimeline(items, "conversation", false, "r").map(itemKey)).toEqual(["c"]);
  });

  it("pairs a tool call with its result and keeps other events", () => {
    const items = pairEvents([
      event({ id: "u", kind: "message", role: "user", text: "go", seq: 0 }),
      event({ id: "c", kind: "tool_call", tool_name: "Read", tool_call_id: "1", seq: 1 }),
      event({ id: "r", kind: "tool_result", role: "tool", tool_call_id: "1", seq: 2, tool_output_preview: "ok" }),
      event({ id: "t", kind: "thinking", text: "hmm", seq: 3 }),
    ]);
    expect(items.map((item) => item.type)).toEqual(["single", "tool", "single"]);
    const tool = items[1];
    expect(tool.type).toBe("tool");
    if (tool.type === "tool") {
      expect(tool.call.id).toBe("c");
      expect(tool.result?.id).toBe("r");
    }
  });
});
