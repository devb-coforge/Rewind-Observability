import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { ObsEvent } from "../../api/types";
import { DiffView } from "./DiffView";
import { EventRow } from "./EventRow";
import { ToolCallCard } from "./ToolCallCard";

function event(partial: Partial<ObsEvent> & Pick<ObsEvent, "id" | "kind">): ObsEvent {
  return {
    session_id: "s",
    parent_id: null,
    seq: 1,
    ts: "2026-01-02T15:04:05.000Z",
    role: "assistant",
    text: null,
    tool_name: null,
    tool_call_id: null,
    tool_input: null,
    tool_output_preview: null,
    is_error: false,
    model: null,
    usage: null,
    raw: { path: "a", offset: 0, length: 1 },
    paths: [],
    ...partial,
  };
}

describe("event renderers", () => {
  it("shows a shell command in the summary and keeps output collapsed", () => {
    render(
      <ToolCallCard
        call={event({
          id: "c",
          kind: "tool_call",
          tool_name: "Bash",
          tool_call_id: "t",
          tool_input: { command: "cat /tmp/secret.txt" },
        })}
        result={event({
          id: "r",
          kind: "tool_result",
          role: "tool",
          tool_call_id: "t",
          is_error: true,
          text: "permission denied",
          tool_output_preview: "permission denied",
        })}
      />,
    );
    expect(screen.getAllByText("cat /tmp/secret.txt").length).toBeGreaterThan(0);
    expect(screen.getByText("error")).toBeInTheDocument();
    expect(document.querySelector("details")).not.toHaveAttribute("open");
  });

  it("renders an edit as a line diff", () => {
    render(<DiffView before={"alpha\nkeep"} after={"beta\nkeep"} />);
    expect(screen.getByText("- alpha")).toBeInTheDocument();
    expect(screen.getByText("+ beta")).toBeInTheDocument();
    expect(screen.getAllByText("keep", { exact: false }).length).toBeGreaterThan(0);
  });

  it("renders assistant markdown as text, not raw html", () => {
    render(
      <EventRow
        event={event({ id: "m", kind: "message", text: "Hello <script>alert(1)</script>" })}
        onRaw={() => undefined}
      />,
    );
    expect(screen.getByText(/Hello/)).toBeInTheDocument();
    expect(document.querySelector("script")).toBeNull();
  });
});

describe("diff interaction", () => {
  it("opens a tool card", async () => {
    const user = userEvent.setup();
    render(
      <ToolCallCard
        call={event({
          id: "c",
          kind: "tool_call",
          tool_name: "Edit",
          tool_call_id: "t",
          tool_input: { file_path: "src/app.py", old_string: "old", new_string: "new" },
        })}
      />,
    );
    await user.click(screen.getByText("Edit"));
    expect(document.querySelector("details")).toHaveAttribute("open");
    expect(screen.getByText("- old")).toBeInTheDocument();
    expect(screen.getByText("+ new")).toBeInTheDocument();
  });
});
