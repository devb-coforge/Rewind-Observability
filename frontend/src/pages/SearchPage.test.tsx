import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import { api } from "../api/client";
import { SearchPage } from "./SearchPage";

afterEach(() => vi.restoreAllMocks());

it("lists user declines separately, links to commands, and loads remaining results", async () => {
  const user = userEvent.setup();
  const hit = { event_id: "r1", session_id: "cursor:session", seq: 2, ts: null,
    tool_name: "Shell", tool_input: JSON.stringify({ command: "echo declined" }),
    error_preview: "User declined this command.", session_title: "A session",
    project_name: "Project", agent: "cursor", project_id: "p" };
  const declined = vi.spyOn(api, "searchDeclined")
    .mockResolvedValueOnce({ total: 2, by_tool: [{ tool_name: "Shell", count: 2 }], hits: [hit], next_offset: 1 })
    .mockResolvedValueOnce({ total: 2, by_tool: [{ tool_name: "Shell", count: 2 }],
      hits: [{ ...hit, event_id: "r2", tool_input: JSON.stringify({ command: "echo second" }) }], next_offset: null });
  const failures = vi.spyOn(api, "searchFailures").mockResolvedValue({ total: 0, by_tool: [], hits: [] });
  render(<MemoryRouter><SearchPage /></MemoryRouter>);
  await user.click(screen.getByRole("tab", { name: "User declined" }));
  expect(await screen.findByText("echo declined")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /A session/ })).toHaveAttribute("href", "/sessions/cursor%3Asession?event=r1");
  expect(failures).not.toHaveBeenCalled();
  await user.type(screen.getByRole("textbox", { name: "Filter user-declined commands" }), "unapplied text");
  await user.click(screen.getByRole("button", { name: "Load more" }));
  expect(await screen.findByText("echo second")).toBeInTheDocument();
  expect(declined).toHaveBeenLastCalledWith({ agent: "", tool: "", q: "", offset: 1 });
  await user.click(screen.getByRole("tab", { name: "Failed tool calls" }));
  await waitFor(() => expect(failures).toHaveBeenCalled());
  expect(await screen.findByText("No failed tool calls.")).toBeInTheDocument();
  expect(screen.queryByText("echo declined")).not.toBeInTheDocument();
});
