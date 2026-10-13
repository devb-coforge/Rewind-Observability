import re
from pathlib import Path

from obs.db.repo import Store
from obs.gitroot import git_worktree_root


def test_rename_applies_to_shared_path_and_survives_rebuild(client):
    projects = client.get("/api/projects").json()["projects"]
    project = next(item for item in projects if item["agent"] == "claude_code")
    response = client.put(f"/api/projects/{project['project_id']}/name", json={"name": "  My project  "})
    assert response.status_code == 200
    assert response.json()["name"] == "My project"
    for full in (False, True):
        client.post("/api/reindex", params={"full": full})
        renamed = client.get("/api/projects").json()["projects"]
        assert all(item["name"] == "My project" for item in renamed if item["cwd"] == project["cwd"])
        sessions = client.get("/api/sessions").json()["sessions"]
        assert all(item["project_name"] == "My project" for item in sessions if item["project_cwd"] == project["cwd"])


def test_new_sessions_use_saved_name_and_unknown_paths_remain_separate(tmp_path):
    store = Store(tmp_path)
    try:
        def insert(sid, project_id, cwd, agent="codex"):
            store.ensure_session({"id": sid, "project_id": project_id, "project_cwd": cwd,
                                  "project_name": "source name", "agent": agent,
                                  "native_id": sid, "source_path": f"/tmp/{sid}"})
        with store.transaction():
            insert("one", "p1", "/work/proj")
            insert("two", "p2", "/work/proj", "cursor")
            insert("three", "p3", "/other/proj")
            assert store.rename_project("p1", "Custom", "now")
            insert("four", "p4", "/work/proj", "claude_code")
            insert("one", "p1", "/work/proj")
            assert [store.get_session(sid)["project_name"] for sid in ("one", "two", "four")] == ["Custom"] * 3
            assert store.get_session("three")["project_name"] == "source name"
            insert("unknown1", "u1", None)
            insert("unknown2", "u2", None)
            assert store.rename_project("u1", "Unknown custom", "now")
            insert("unknown1", "u1", None)
            assert store.get_session("unknown1")["project_name"] == "Unknown custom"
            assert store.get_session("unknown2")["project_name"] == "source name"
    finally:
        store.close()


def test_rename_validation(client):
    project_id = client.get("/api/projects").json()["projects"][0]["project_id"]
    for name in ("", "   ", "x" * 201):
        assert client.put(f"/api/projects/{project_id}/name", json={"name": name}).status_code == 422
    assert client.put("/api/projects/missing/name", json={"name": "Name"}).status_code == 404


def test_session_path_filter_includes_all_agents_and_respects_agent_and_hidden_filters(client):
    sessions = client.get("/api/sessions", params={"project_cwd": "/work/proj"}).json()["sessions"]
    assert {item["agent"] for item in sessions} == {"claude_code", "codex"}
    assert all(item["project_cwd"] == "/work/proj" for item in sessions)
    assert client.get("/api/sessions", params={"project_cwd": "/work/other"}).json()["sessions"] == []
    codex = client.get("/api/sessions", params={"project_cwd": "/work/proj", "agent": "codex"}).json()["sessions"]
    assert len(codex) == 1
    client.patch(f"/api/projects/{codex[0]['project_id']}", json={"hidden": True})
    visible = client.get("/api/sessions", params={"project_cwd": "/work/proj"}).json()["sessions"]
    assert all(item["agent"] == "claude_code" for item in visible)


def test_cursor_workspace_alias_groups_filters_and_renames_without_inventing_cwd(client):
    store = client.app.state.obs.store
    fields = {"id": "cursor:alias", "native_id": "alias", "agent": "cursor", "project_id": "cursor-alias",
              "project_name": "work-proj", "project_cwd": None,
              "source_path": "/tmp/cursor/projects/work-proj/agent-transcripts/alias.jsonl"}
    with store.transaction():
        store.ensure_session(fields)
    projects = client.get("/api/projects").json()["projects"]
    cursor = next(item for item in projects if item["project_id"] == "cursor-alias")
    assert cursor["cwd"] is None
    assert cursor["group_cwd"] == "/work/proj"
    assert cursor["name"] == "proj"
    sessions = client.get("/api/sessions", params={"project_cwd": "/work/proj"}).json()["sessions"]
    assert {item["agent"] for item in sessions} == {"claude_code", "codex", "cursor"}
    assert next(item for item in sessions if item["agent"] == "cursor")["project_cwd"] is None
    assert client.put("/api/projects/cursor-alias/name", json={"name": "Unified"}).status_code == 200
    assert {item["name"] for item in client.get("/api/projects").json()["projects"]} == {"Unified"}
    with store.transaction():
        store.ensure_session(fields)
        store.refresh_project_names()
    assert store.get_session("cursor:alias")["project_name"] == "Unified"


def test_cursor_workspace_alias_does_not_merge_ambiguous_paths(tmp_path):
    store = Store(tmp_path)
    try:
        with store.transaction():
            for sid, cwd in (("one", "/work/a-b"), ("two", "/work/a/b"), ("three", None)):
                store.ensure_session({"id": sid, "native_id": sid, "agent": "cursor" if cwd is None else "codex",
                                      "project_id": sid, "project_cwd": cwd, "project_name": "work-a-b",
                                      "source_path": "/tmp/cursor/projects/work-a-b/agent-transcripts/three.jsonl"})
        assert store.project_group_paths()["three"] is None
    finally:
        store.close()


def test_git_worktree_root_uses_the_nearest_marker(tmp_path):
    repo = tmp_path / "repo"
    nested = repo / "vendor" / "lib"
    (nested / "src").mkdir(parents=True)
    (repo / "frontend").mkdir()
    (repo / ".git").mkdir()
    (nested / ".git").write_text("gitdir: /elsewhere\n")
    assert git_worktree_root(str(repo / "frontend")) == str(repo)
    assert git_worktree_root(str(nested / "src")) == str(nested)
    assert git_worktree_root(str(tmp_path / "loose")) is None
    assert git_worktree_root(None) is None


def test_subdirectory_sessions_group_at_the_git_root(tmp_path):
    repo = tmp_path / "Observability-System"
    frontend = repo / "frontend"
    frontend.mkdir(parents=True)
    (repo / ".git").mkdir()
    other = tmp_path / "other"
    other.mkdir()
    store = Store(tmp_path / "data")
    try:
        def insert(sid, project_id, cwd, agent="claude_code", name=None, source_path=None):
            store.ensure_session({
                "id": sid,
                "project_id": project_id,
                "project_cwd": cwd,
                "project_name": name or (Path(cwd).name if cwd else sid),
                "agent": agent,
                "native_id": sid,
                "source_path": source_path or f"/tmp/{sid}",
            })

        slug = re.sub(r"[^a-zA-Z0-9-]", "-", str(frontend)).strip("-")
        with store.transaction():
            insert("root", "root", str(repo), "codex", "Observability-System")
            insert("front", "front", str(frontend), "claude_code", "rewind-icon")
            insert(
                "cursor", "cursor-id", None, "cursor", "frontend-workspace",
                f"/tmp/cursor/projects/{slug}/agent-transcripts/cursor.jsonl",
            )
            insert("out", "out", str(other), "codex", "other")
        paths = store.project_group_paths()
        assert paths["root"] == str(repo)
        assert paths["front"] == str(repo)
        assert paths["cursor-id"] == str(repo)
        assert paths["out"] == str(other)
        projects = {item["project_id"]: item for item in store.list_projects(True)}
        assert projects["front"]["cwd"] == str(frontend)
        assert projects["front"]["group_cwd"] == str(repo)
        assert projects["front"]["name"] == "Observability-System"
        assert projects["cursor-id"]["name"] == "Observability-System"
        assert {item["id"] for item in store.list_sessions(project_cwd=str(repo))["sessions"]} == {
            "root", "front", "cursor",
        }
        assert store.rename_project("front", "Unified", "now")
        assert store.get_session("root")["project_name"] == "Unified"
        with store.transaction():
            insert("front2", "front2", str(frontend), "claude_code", "frontend")
        assert store.get_session("front2")["project_name"] == "Unified"
    finally:
        store.close()


def test_analytics_repository_filter_includes_agents_and_cursor_alias(client):
    store = client.app.state.obs.store
    with store.transaction():
        for sid, cwd, agent, source in (
            ("cursor:alias", None, "cursor", "/tmp/cursor/projects/work-proj/agent-transcripts/alias.jsonl"),
            ("other", "/other/proj", "codex", "/tmp/other.jsonl"),
        ):
            store.ensure_session({
                "id": sid, "native_id": sid, "agent": agent, "project_id": sid,
                "project_cwd": cwd, "project_name": "proj", "source_path": source,
                "started_at": "2026-10-12T12:00:00.000Z", "tokens_in": 7,
            })
            store.index.execute("INSERT INTO session_models VALUES (?, ?)", (sid, sid))
    params = {"project_cwd": "/work/proj"}
    summary = client.get("/api/analytics/summary", params=params).json()
    assert summary["sessions"] == 4
    points = client.get("/api/analytics/timeseries", params={**params, "group_by": "model"}).json()["points"]
    assert "cursor:alias" in {point["group"] for point in points}
    assert "other" not in {point["group"] for point in points}
    assert client.get("/api/analytics/summary", params={**params, "agent": "codex"}).json()["sessions"] == 1
    codex = next(item for item in store.list_projects(True) if item["agent"] == "codex" and item["cwd"] == "/work/proj")
    client.patch(f"/api/projects/{codex['project_id']}", json={"hidden": True})
    assert client.get("/api/analytics/summary", params=params).json()["sessions"] == 3
    assert client.get("/api/analytics/summary", params={**params, "include_hidden": True}).json()["sessions"] == 4
    missing = {"project_cwd": "/missing"}
    assert client.get("/api/analytics/summary", params=missing).json()["sessions"] == 0
    assert client.get("/api/analytics/timeseries", params=missing).json()["points"] == []
    assert client.get("/api/analytics/tools", params=missing).json()["tools"] == []


def test_eval_repository_filter_includes_cursor_alias_and_excludes_same_name_elsewhere(client):
    store = client.app.state.obs.store
    sessions = client.get("/api/sessions").json()["sessions"]
    for session in sessions:
        assert client.post("/api/evals/cases", json={"session_id": session["id"]}).status_code == 200
    with store.transaction():
        store.ensure_session({
            "id": "cursor:alias", "native_id": "alias", "agent": "cursor", "project_id": "cursor-id",
            "project_name": "proj", "project_cwd": None,
            "source_path": "/tmp/cursor/projects/work-proj/agent-transcripts/alias.jsonl",
        })
        snapshot = dict(store.user.execute("SELECT * FROM eval_cases LIMIT 1").fetchone())
        for case_id, project_id, cwd in (("alias-case", "cursor-id", None), ("other-case", "other-id", "/other/proj")):
            snapshot.update(id=case_id, project_id=project_id, project_cwd=cwd)
            store.user.execute(
                f"INSERT INTO eval_cases ({','.join(snapshot)}) VALUES ({','.join('?' for _ in snapshot)})",
                list(snapshot.values()),
            )
    params = {"project_cwd": "/work/proj"}
    cases = client.get("/api/evals/cases", params=params).json()["cases"]
    assert len(cases) == len(sessions) + 1
    assert "alias-case" in {item["id"] for item in cases}
    assert "other-case" not in {item["id"] for item in cases}
    assert sum(group["n"] for group in client.get("/api/evals/summary", params=params).json()["groups"]) == len(sessions) + 1
    assert client.get("/api/evals/cases", params={"project_cwd": "/missing"}).json()["cases"] == []
