import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
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

async function expandProjectAndAgents(
  user: ReturnType<typeof userEvent.setup>,
  projectName = "proj",
  agents = ["Claude Code"],
) {
  const projectToggle = screen.getByRole("button", { name: new RegExp(`^(Expand|Collapse) ${projectName}$`) });
  if (projectToggle.getAttribute("aria-expanded") === "false") {
    await user.click(projectToggle);
  }
  for (const agent of agents) {
    await user.click(screen.getByRole("button", { name: `Expand ${agent} sessions` }));
  }
}

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
    hidden: false,
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
      onSetSessionHidden={async () => {}}
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
    await expandProjectAndAgents(user);
    expect(screen.getByText("Fix the parser")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Hide proj" }));
    expect(screen.queryByText("Fix the parser")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Hid proj.");

    await user.click(screen.getByRole("button", { name: "Undo" }));
    expect(screen.getByText("Fix the parser")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Hide proj" }));
    await user.click(screen.getByRole("checkbox", { name: "Show hidden projects and sessions" }));
    expect(screen.getByText("Fix the parser")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Restore proj" }));
    expect(screen.getByRole("button", { name: "Hide proj" })).toBeInTheDocument();
  });

  it("hides a single session and can undo it", async () => {
    const user = userEvent.setup();
    const onSetSessionHidden = vi.fn().mockResolvedValue(undefined);
    render(
      <MemoryRouter>
        <SessionGroups
          projects={[project]}
          sessions={[session()]}
          includeHidden={false}
          onIncludeHidden={() => {}}
          onSetHidden={async () => {}}
          onSetSessionHidden={onSetSessionHidden}
        />
      </MemoryRouter>,
    );
    await expandProjectAndAgents(user);
    await user.click(screen.getByRole("button", { name: "Hide Fix the parser" }));
    expect(onSetSessionHidden).toHaveBeenCalledWith("claude_code:s1", true);
    expect(screen.getByRole("status")).toHaveTextContent("Hid Fix the parser.");
    await user.click(screen.getByRole("button", { name: "Undo" }));
    expect(onSetSessionHidden).toHaveBeenCalledWith("claude_code:s1", false);
  });
});

describe("project path grouping", () => {
  function renderGroups(projects: Project[], includeHidden = false) {
    const onSetHidden = vi.fn().mockResolvedValue(undefined);
    render(
      <MemoryRouter>
        <SessionGroups
          projects={projects}
          sessions={projects.map((item) => ({
            ...session(), id: `${item.agent}:${item.project_id}`, agent: item.agent,
            project_id: item.project_id, project_cwd: item.cwd, project_hidden: item.hidden, hidden: false,
            title: `${item.agent} task`,
          }))}
          includeHidden={includeHidden}
          onIncludeHidden={() => {}}
          onSetHidden={onSetHidden}
          onSetSessionHidden={async () => {}}
        />
      </MemoryRouter>,
    );
    return onSetHidden;
  }

  it("groups three agents under one path and retains their session tables and hide controls", async () => {
    const user = userEvent.setup();
    const onSetHidden = renderGroups([
      project,
      { ...project, project_id: "p2", agent: "codex" },
      { ...project, project_id: "p3", agent: "cursor" },
    ]);
    expect(screen.getByRole("button", { name: "Hide proj" })).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 2 })).toHaveLength(1);
    expect(screen.getAllByText("/work/proj")).toHaveLength(1);
    expect(screen.getByText("3 sessions")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    const toggle = screen.getByRole("button", { name: "Expand proj" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await user.click(screen.getByRole("button", { name: "Hide proj" }));
    expect(onSetHidden).toHaveBeenCalledWith("p1", true);
    expect(onSetHidden).toHaveBeenCalledWith("p3", true);
    await user.click(screen.getByRole("button", { name: "Undo" }));
    for (const projectId of ["p1", "p2", "p3"]) {
      expect(onSetHidden).toHaveBeenCalledWith(projectId, false);
    }
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    await expandProjectAndAgents(user, "proj", ["Claude Code", "Codex", "Cursor"]);
    expect(screen.getAllByRole("table")).toHaveLength(3);
    for (const agent of ["claude_code", "codex", "cursor"]) {
      expect(screen.getByText(`${agent} task`)).toBeInTheDocument();
    }
    expect(screen.queryByRole("button", { name: "Hide project" })).not.toBeInTheDocument();
    await user.click(toggle);
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(toggle).toHaveAttribute("aria-expanded", "false");
  });

  it("keeps identical names at different paths and unknown paths separate", () => {
    renderGroups([
      project,
      { ...project, project_id: "p2", cwd: "/other/proj" },
      { ...project, project_id: "p3", cwd: null },
      { ...project, project_id: "p4", cwd: null, agent: "cursor" },
    ]);
    expect(screen.getAllByRole("heading", { level: 2 })).toHaveLength(4);
  });

  it("excludes hidden agents and can show mixed visibility within a path", async () => {
    const user = userEvent.setup();
    const projects = [project, { ...project, project_id: "p2", agent: "codex", hidden: true }];
    renderGroups(projects);
    await user.click(screen.getByRole("button", { name: "Expand proj" }));
    expect(screen.getAllByRole("heading", { level: 2 })).toHaveLength(1);
    expect(screen.queryByText("codex task")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Expand Claude Code sessions" }));
    expect(screen.getAllByRole("table")).toHaveLength(1);
  });

  it("restores a hidden project across all agents sharing a path", async () => {
    const user = userEvent.setup();
    const onSetHidden = renderGroups([{ ...project, hidden: true }, { ...project, project_id: "p2", agent: "codex", hidden: true }], true);
    await expandProjectAndAgents(user, "proj", ["Claude Code", "Codex"]);
    expect(screen.getAllByRole("heading", { level: 2 })).toHaveLength(1);
    expect(screen.getAllByRole("table")).toHaveLength(2);
    await user.click(screen.getByRole("button", { name: "Restore proj" }));
    expect(onSetHidden).toHaveBeenCalledWith("p2", false);
  });
});

describe("project rename", () => {
  it("renames a collapsed project and allows cancellation", async () => {
    const user = userEvent.setup();
    const onRename = vi.fn().mockResolvedValue(undefined);
    render(<MemoryRouter><SessionGroups projects={[project]} sessions={[session()]} includeHidden={false}
      onIncludeHidden={() => {}} onSetHidden={async () => {}} onSetSessionHidden={async () => {}} onRename={onRename} /></MemoryRouter>);
    expect(screen.getByRole("button", { name: "Rename proj" })).toHaveTextContent("");
    await user.click(screen.getByRole("button", { name: "Rename proj" }));
    const input = screen.getByRole("textbox", { name: "Project name" });
    expect(input).toHaveFocus();
    await user.clear(input);
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    await user.type(input, "  Custom project  ");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(onRename).toHaveBeenCalledWith("p1", "Custom project");
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Expand proj" })).toHaveAttribute("aria-expanded", "false");
    await user.click(screen.getByRole("button", { name: "Rename proj" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onRename).toHaveBeenCalledTimes(1);
  });

  it("keeps the editor open when saving fails", async () => {
    const user = userEvent.setup();
    render(<MemoryRouter><SessionGroups projects={[project]} sessions={[session()]} includeHidden={false}
      onIncludeHidden={() => {}} onSetHidden={async () => {}} onSetSessionHidden={async () => {}}
      onRename={async () => { throw new Error("Rename failed"); }} /></MemoryRouter>);
    await user.click(screen.getByRole("button", { name: "Rename proj" }));
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(screen.getByText("Rename failed")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Project name" })).toBeInTheDocument();
  });
});
