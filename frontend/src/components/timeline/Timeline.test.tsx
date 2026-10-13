import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ObsEvent } from "../../api/types";
import { Timeline } from "./Timeline";

// jsdom has no viewport measurements. Simulate a window of virtual rows.
const viewport = vi.hoisted(() => ({ start: 0 }));
vi.mock("@tanstack/react-virtual", () => ({
  useVirtualizer: (options: { count: number; getItemKey: (index: number) => string }) => ({
    getTotalSize: () => options.count * 96,
    getVirtualItems: () => Array.from({ length: options.count }, (_, index) => ({
      index, key: options.getItemKey(index), start: index * 96,
    })).slice(viewport.start, viewport.start + 5),
    measureElement: () => undefined,
    scrollToIndex: () => undefined,
  }),
}));

function event(id: string, kind: string, text: string): ObsEvent {
  return {
    id, kind, text, session_id: "s", parent_id: null, seq: 1, ts: null,
    role: kind === "system" ? "system" : "assistant", tool_name: null,
    tool_call_id: null, tool_input: null, tool_output_preview: null,
    is_error: false, model: null, usage: null, paths: [],
    raw: { path: "", offset: 0, length: 0 },
  };
}

const events = [event("sys", "system", "System instructions"), event("m", "message", "Hello")];
const props = { events, showThinking: false, onShowThinkingChange: vi.fn(), onRaw: vi.fn() };

beforeEach(() => {
  viewport.start = 0;
  Element.prototype.scrollTo = vi.fn();
});

describe("timeline navigation", () => {
  it("retains disclosure state after a virtualized row remounts and collapses it on demand", async () => {
    const user = userEvent.setup();
    const { rerender } = render(<Timeline {...props} />);
    await user.click(screen.getByRole("button", { name: "Expand system message" }));
    viewport.start = 1;
    rerender(<Timeline {...props} />);
    expect(screen.queryByRole("button", { name: "Collapse system message" })).toBeNull();
    viewport.start = 0;
    rerender(<Timeline {...props} />);
    expect(screen.getByRole("button", { name: "Collapse system message" })).toHaveAttribute("aria-expanded", "true");
    await user.click(screen.getByRole("button", { name: "Collapse details" }));
    expect(screen.getByRole("button", { name: "Expand system message" })).toHaveAttribute("aria-expanded", "false");
  });

  it("switches views and provides an empty-state way back", async () => {
    const user = userEvent.setup();
    render(<Timeline {...props} />);
    await user.click(screen.getByRole("button", { name: /Conversation/ }));
    expect(screen.getByText("Hello")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Expand system message" })).toBeNull();
    await user.click(screen.getByRole("button", { name: /Errors/ }));
    expect(screen.getByText("No errors recorded in this session.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Show all events" }));
    expect(screen.getByRole("button", { name: "Expand system message" })).toBeInTheDocument();
  });

  it("reveals a linked event through filters and allows it to be collapsed", async () => {
    const user = userEvent.setup();
    render(<Timeline {...props} focusId="sys" />);
    await user.click(screen.getByRole("button", { name: /Conversation/ }));
    expect(screen.getByRole("button", { name: "Collapse system message" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(/includes linked event/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Collapse system message" }));
    expect(screen.getByRole("button", { name: "Expand system message" })).toHaveAttribute("aria-expanded", "false");
  });
});
