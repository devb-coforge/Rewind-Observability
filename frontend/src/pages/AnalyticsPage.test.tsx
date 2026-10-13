import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { api } from "../api/client";
import { AnalyticsPage } from "./AnalyticsPage";
import { EvalsPage } from "./EvalsPage";

vi.mock("recharts", async () => {
  const actual = await vi.importActual<typeof import("recharts")>("recharts");
  return { ...actual, ResponsiveContainer: () => null };
});
afterEach(() => vi.restoreAllMocks());

for (const Page of [AnalyticsPage, EvalsPage]) {
  it(`${Page.name} groups repository options and sends a path filter with an ID fallback`, async () => {
    vi.spyOn(api, "projects").mockResolvedValue({ projects: [
      { project_id: "p1", agent: "codex", name: "Project", cwd: "/work/proj", hidden: false, n_sessions: 1 },
      { project_id: "p2", agent: "claude_code", name: "Subdirectory", cwd: "/work/proj/frontend", group_cwd: "/work/proj", hidden: false, n_sessions: 1 },
      { project_id: "p3", agent: "cursor", name: "Project", cwd: null, group_cwd: "/work/proj", hidden: false, n_sessions: 1 },
      { project_id: "unknown", agent: "cursor", name: "Workspace", cwd: null, hidden: false, n_sessions: 1 },
      { project_id: "other", agent: "codex", name: "Project", cwd: "/other/proj", hidden: false, n_sessions: 1 },
    ] });
    const summary = vi.spyOn(api, "summary").mockResolvedValue({
      sessions: 0, tokens_in: null, tokens_out: null, tokens_cache_read: null, tokens_cache_write: null,
      est_cost_usd: null, usage_coverage: "none", cost_coverage: "none", tool_calls: 0, tool_errors: 0,
      median_duration_sec: null, sessions_missing_usage: 0, sessions_missing_start: 0,
    });
    const series = vi.spyOn(api, "timeseries").mockResolvedValue({ metric: "sessions", bucket: "day", group_by: null, points: [] });
    const tools = vi.spyOn(api, "tools").mockResolvedValue({ tools: [] });
    const evals = vi.spyOn(api, "evalsSummary").mockResolvedValue({ note: "", groups: [] });
    const cases = vi.spyOn(api, "cases").mockResolvedValue({ cases: [] });
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><Page /></QueryClientProvider>);
    const dropdown = screen.getByRole("combobox", { name: "Project" });
    await within(dropdown).findByRole("option", { name: "Workspace" });
    expect(within(dropdown).getAllByRole("option")).toHaveLength(4);
    const user = userEvent.setup();
    for (const [selection, filters] of [
      ["path:/work/proj", { project: "", project_cwd: "/work/proj" }],
      ["id:unknown", { project: "unknown", project_cwd: "" }],
      ["", { project: "", project_cwd: "" }],
    ] as const) {
      await user.selectOptions(dropdown, selection);
      await waitFor(() => {
        for (const spy of Page === AnalyticsPage ? [summary, tools, series] : [evals, cases]) {
          expect(spy).toHaveBeenLastCalledWith(expect.objectContaining(filters));
        }
      });
      if (Page === AnalyticsPage) {
        expect(series).toHaveBeenCalledWith(expect.objectContaining({ ...filters, group_by: "model" }));
      }
    }
  });
}
