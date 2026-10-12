import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import type { Project, Session } from "../api/types";
import { SessionGroups } from "./SessionGroups";

const project: Project = {
  project_id: "p1",
  agent: "claude_code",
  name: "proj",
  cwd: "/work/proj",
  hidden: false,
  n_sessions: 1,
};

function session(): Session {
  return {
    id: "claude_code:s1",
    agent: "claude_code",
    native_id: "s1",
    source_path: "/tmp/s.jsonl",
    project_cwd: "/work/proj",
    project_name: "proj",
    project_id: "p1",
    project_hidden: false,
    git_branch: "main",
    models: ["claude-sonnet-4"],
    parent_session_id: null,
    started_at: "2026-01-02T15:04:05.000Z",
    ended_at: "2026-01-02T15:10:05.000Z",
    duration_sec: 360,
    title: "Fix the parser",
    n_events: 4,
    n_user_msgs: 1,
    n_tool_calls: 1,
    n_tool_errors: 0,
    tokens_in: 100,
    tokens_out: 20,
    tokens_cache_read: 0,
    tokens_cache_write: 0,
    est_cost_usd: 0.01,
    cost_partial: false,
    usage_coverage: "complete",
    boundary_count: 1,
  };
}

function Harness() {
  const [hidden, setHidden] = useState(false);
  const [includeHidden, setIncludeHidden] = useState(false);
  const current = { ...project, hidden };
  const visibleProjects = includeHidden || !hidden ? [current] : [];
  const visibleSessions = includeHidden || !hidden ? [session()] : [];
  return (
    <SessionGroups
      projects={visibleProjects}
      sessions={visibleSessions}
      includeHidden={includeHidden}
      onIncludeHidden={setIncludeHidden}
      onSetHidden={async (_id, next) => setHidden(next)}
    />
  );
}

describe("hide and restore", () => {
  it("hides a project, undoes it, and restores it from the hidden list", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <Harness />
      </MemoryRouter>,
    );
    expect(screen.getByText(/Transcript files are not modified/)).toBeInTheDocument();
    expect(screen.getByText("Fix the parser")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Hide project" }));
    expect(screen.queryByText("Fix the parser")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Source files were left untouched");

    await user.click(screen.getByRole("button", { name: "Undo" }));
    expect(screen.getByText("Fix the parser")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Hide project" }));
    await user.click(screen.getByRole("checkbox", { name: "Show hidden projects" }));
    expect(screen.getByText("Fix the parser")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Restore project" }));
    expect(screen.getByRole("button", { name: "Hide project" })).toBeInTheDocument();
  });
});
