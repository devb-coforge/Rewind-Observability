import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { expect, it, vi } from "vitest";
import { api } from "../api/client";
import { SessionsPage } from "./SessionsPage";

it("shows one option per path and filters across agents, with an ID fallback for unknown paths", async () => {
  const user = userEvent.setup();
  vi.spyOn(api, "projects").mockResolvedValue({ projects: [
    { project_id: "p1", agent: "claude_code", name: "Project", cwd: "/work/proj", hidden: false, n_sessions: 1 },
    { project_id: "p2", agent: "codex", name: "Project", cwd: "/work/proj", hidden: false, n_sessions: 1 },
    { project_id: "p4", agent: "cursor", name: "work-proj", cwd: null, group_cwd: "/work/proj", hidden: false, n_sessions: 1 },
    { project_id: "p3", agent: "cursor", name: "Workspace", cwd: null, hidden: false, n_sessions: 1 },
  ] });
  const sessions = vi.spyOn(api, "sessions").mockResolvedValue({ sessions: [], next_cursor: null });
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter><SessionsPage /></MemoryRouter>
  </QueryClientProvider>);
  const dropdown = screen.getByRole("combobox", { name: "Project" });
  await within(dropdown).findByRole("option", { name: "Project" });
  expect(within(dropdown).getAllByRole("option")).toHaveLength(3);
  await user.selectOptions(dropdown, "path:/work/proj");
  await waitFor(() => expect(sessions).toHaveBeenLastCalledWith(expect.objectContaining({ project_cwd: "/work/proj", project: "" })));
  await user.selectOptions(dropdown, "id:p3");
  await waitFor(() => expect(sessions).toHaveBeenLastCalledWith(expect.objectContaining({ project_cwd: "", project: "p3" })));
  await user.selectOptions(dropdown, "");
  await waitFor(() => expect(dropdown).toHaveValue(""));
  vi.restoreAllMocks();
});
