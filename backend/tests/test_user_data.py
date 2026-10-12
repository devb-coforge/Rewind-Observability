import json

CLAUDE = "claude_code:11111111-1111-1111-1111-111111111111"


def _project(client) -> str:
    return client.get(f"/api/sessions/{CLAUDE}").json()["project_id"]


def test_note_survives_full_reindex(client):
    saved = client.put(f"/api/sessions/{CLAUDE}/note", json={"text": "look here"}).json()
    assert saved["text"] == "look here"
    client.post("/api/reindex", params={"full": "true"})
    note = client.get(f"/api/sessions/{CLAUDE}/note").json()
    assert note["text"] == "look here"
    cleared = client.put(f"/api/sessions/{CLAUDE}/note", json={"text": ""}).json()
    assert cleared["text"] == ""
    assert client.get(f"/api/sessions/{CLAUDE}/note").json()["updated_at"] is None


def test_hide_filters_lists_search_and_analytics_and_survives_rebuild(client, source_dirs):
    project_id = _project(client)
    hidden = client.patch(f"/api/projects/{project_id}", json={"hidden": True}).json()
    assert hidden["hidden"] is True
    listed = client.get("/api/sessions").json()["sessions"]
    assert all(item["project_id"] != project_id for item in listed)
    assert client.get("/api/search", params={"q": "parser"}).json()["hits"] == []
    assert client.get("/api/analytics/summary", params={"agent": "claude_code"}).json()["sessions"] == 0
    assert client.get("/api/analytics/summary", params={"agent": "codex"}).json()["sessions"] == 1
    direct = client.get(f"/api/sessions/{CLAUDE}").json()
    assert direct["project_hidden"] is True
    visible = client.get("/api/sessions", params={"include_hidden": True}).json()["sessions"]
    assert any(item["id"] == CLAUDE for item in visible)
    client.post("/api/reindex", params={"full": "true"})
    still = client.get("/api/sessions").json()["sessions"]
    assert all(item["project_id"] != project_id for item in still)
    client.patch(f"/api/projects/{project_id}", json={"hidden": False})
    restored = client.get("/api/sessions").json()["sessions"]
    assert any(item["id"] == CLAUDE for item in restored)


def test_preferences_survive_source_disappearance(client, source_dirs):
    claude, _codex = source_dirs
    project_id = _project(client)
    client.put(f"/api/sessions/{CLAUDE}/note", json={"text": "keep me"})
    client.patch(f"/api/projects/{project_id}", json={"hidden": True})
    for path in claude.rglob("*.jsonl"):
        path.unlink()
    client.post("/api/reindex")
    assert client.get("/api/sessions", params={"include_hidden": True}).json()["sessions"] == [] or all(
        item["agent"] != "claude_code" or item["id"] != CLAUDE
        for item in client.get("/api/sessions", params={"include_hidden": True}).json()["sessions"]
    )
    # The Claude session file is gone, so that session leaves the index.
    assert client.get(f"/api/sessions/{CLAUDE}").status_code == 404
    assert client.get(f"/api/sessions/{CLAUDE}/note").json()["text"] == "keep me"
    # Put the transcript back and the same project stays hidden.
    fixture = (
        __import__("pathlib").Path(__file__).parent
        / "fixtures"
        / "claude"
        / "projects"
        / "-work-proj"
        / "11111111-1111-1111-1111-111111111111.jsonl"
    )
    target = claude / "projects" / "-work-proj" / fixture.name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(fixture.read_text())
    client.post("/api/reindex")
    body = client.get(f"/api/sessions/{CLAUDE}").json()
    assert body["project_hidden"] is True
    assert client.get(f"/api/sessions/{CLAUDE}/note").json()["text"] == "keep me"


def test_analytics_filters(client):
    summary = client.get("/api/analytics/summary", params={"agent": "codex"}).json()
    assert summary["sessions"] == 1
    assert summary["tokens_in"] == 30
    assert summary["usage_coverage"] == "complete"
    series = client.get(
        "/api/analytics/timeseries",
        params={"metric": "sessions", "bucket": "day", "group_by": "agent"},
    ).json()
    assert series["points"]
    tools = client.get("/api/analytics/tools", params={"agent": "claude_code"}).json()["tools"]
    names = {item["tool_name"]: item for item in tools}
    assert names["Bash"]["errors"] == 1
    assert names["Read"]["errors"] == 0
