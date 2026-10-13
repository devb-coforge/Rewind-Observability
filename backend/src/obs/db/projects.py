"""Projects operations."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
import re

from obs.gitroot import git_worktree_root

if TYPE_CHECKING:
    from obs.db.repo import Store


def project_name_key(cwd: str | None, project_id: str) -> str:
    return f"path:{cwd}" if cwd else f"id:{project_id}"


def project_group_paths(store: Store) -> dict[str, str | None]:
    rows = list(store.index.execute(
        "SELECT project_id, project_cwd, agent, source_path FROM sessions GROUP BY project_id"
    ))
    candidates: dict[str, set[str]] = {}
    for row in rows:
        if row["project_cwd"]:
            # Cursor encodes the directory as a workspace folder name.
            slug = re.sub(r"[^a-zA-Z0-9-]", "-", row["project_cwd"]).strip("-")
            candidates.setdefault(slug, set()).add(row["project_cwd"])
    paths = {}
    roots: dict[str, str] = {}
    for row in rows:
        cwd = row["project_cwd"]
        if not cwd and row["agent"] == "cursor":
            parts = Path(row["source_path"]).parts
            if "agent-transcripts" in parts:
                position = parts.index("agent-transcripts")
                matches = candidates.get(parts[position - 1], set()) if position else set()
                if len(matches) == 1:
                    cwd = next(iter(matches))
        if cwd:
            if cwd not in roots:
                # A checkout opened at a subdirectory shares the worktree root.
                roots[cwd] = git_worktree_root(cwd) or cwd
            cwd = roots[cwd]
        paths[row["project_id"]] = cwd
    return paths


def refresh_project_names(store: Store) -> None:
    overrides = {row["project_key"]: row["project_name"] for row in store.user.execute("SELECT * FROM project_names")}
    for project_id, cwd in store.project_group_paths().items():
        name = overrides.get(store.project_name_key(cwd, project_id))
        if name is not None:
            store.index.execute("UPDATE sessions SET project_name = ? WHERE project_id = ?", (name, project_id))


def rename_project(store: Store, project_id: str, name: str, now: str) -> bool:
    project = store.index.execute(
        "SELECT project_cwd FROM sessions WHERE project_id = ? LIMIT 1", (project_id,)
    ).fetchone()
    if project is None:
        return False
    group_paths = store.project_group_paths()
    cwd = group_paths[project_id]
    key = store.project_name_key(cwd, project_id)
    store.user.execute(
        """INSERT INTO project_names(project_key, project_name, updated_at) VALUES(?, ?, ?)
           ON CONFLICT(project_key) DO UPDATE SET project_name = excluded.project_name,
             updated_at = excluded.updated_at""",
        (key, name, now),
    )
    for target_id, target_cwd in group_paths.items():
        if target_id == project_id or (cwd and target_cwd == cwd):
            store.index.execute("UPDATE sessions SET project_name = ? WHERE project_id = ?", (name, target_id))
    return True


def list_projects(store: Store, include_hidden: bool) -> list[dict]:
    hidden = set(store.hidden_ids())
    group_paths = store.project_group_paths()
    rows = list(
        store.index.execute(
            """
            SELECT project_id, agent, project_name, project_cwd, COUNT(*) AS n_sessions
            FROM sessions
            GROUP BY project_id
            ORDER BY project_name IS NULL, project_name, agent
            """
        )
    )
    projects = []
    path_names = {row["project_cwd"]: row["project_name"] for row in rows if row["project_cwd"]}
    for row in rows:
        is_hidden = row["project_id"] in hidden
        if is_hidden and not include_hidden:
            continue
        group = group_paths[row["project_id"]]
        recorded = path_names.get(group) if group else None
        if recorded:
            name = recorded
        elif group and row["project_cwd"] and group != row["project_cwd"]:
            name = group.rstrip("/").split("/")[-1] or row["project_name"] or "(unknown)"
        else:
            name = row["project_name"] or "(unknown)"
        projects.append(
            {
                "project_id": row["project_id"],
                "agent": row["agent"],
                "name": name,
                "cwd": row["project_cwd"],
                "group_cwd": group_paths[row["project_id"]],
                "hidden": is_hidden,
                "n_sessions": row["n_sessions"],
            }
        )
    return projects
