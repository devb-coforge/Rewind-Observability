import json
from pathlib import Path

from fastapi.testclient import TestClient

from obs.adapters.cursor import CursorAdapter
from obs.config import AppConfig, SourceConfig
from obs.main import create_app


def write_records(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(record) + "\n" for record in records))
    return path


def transcript(root, workspace="Users-test-my-project", session="session-1"):
    return root / "projects" / workspace / "agent-transcripts" / session / f"{session}.jsonl"


RECORDS = [
    {"role": "user", "message": {"content": [{"type": "text", "text": "Fix the cursor parser"}]}},
    {"role": "assistant", "message": {"content": [
        {"type": "text", "text": "Checking the file"},
        {"type": "tool_use", "name": "Read", "input": {"path": "/work/proj/app.py"}},
        {"type": "tool_use", "name": "Shell", "input": {"command": "cat /tmp/file"}},
    ]}},
    {"type": "turn_ended", "status": "success"},
]


def test_actual_cursor_shape_preserves_blocks_and_unknown_metadata(tmp_path):
    path = write_records(transcript(tmp_path / ".cursor"), RECORDS)
    result = CursorAdapter().parse(path, 0)
    assert result.native_id == "session-1"
    assert result.project_name == "Users-test-my-project"
    assert result.project_cwd is None
    assert result.models == []
    assert result.started_at is None and result.ended_at is None
    assert [e.kind for e in result.events] == ["message", "message", "tool_call", "tool_call", "system"]
    assert all(e.usage is None and e.ts is None for e in result.events)
    assert all(e.tool_call_id is None for e in result.events)
    raw = path.read_bytes()
    for event in result.events:
        assert json.loads(raw[event.raw_offset:event.raw_offset + event.raw_length]) in RECORDS


def test_discovery_layouts_and_subagent_identity(tmp_path):
    root = tmp_path / "cursor"
    nested = write_records(transcript(root), RECORDS)
    flat = write_records(nested.parent.parent / "flat.jsonl", RECORDS)
    sub = write_records(nested.parent / "subagents" / "agent-1.jsonl", RECORDS)
    other_sub = write_records(transcript(root, session="session-2").parent / "subagents" / "agent-1.jsonl", RECORDS)
    write_records(root / "projects" / "workspace" / "unrelated.jsonl", RECORDS)
    adapter = CursorAdapter()
    assert adapter.detect(root)
    assert set(adapter.discover(root)) == {flat, nested, sub, other_sub}
    assert adapter.discover(tmp_path / "missing") == []
    assert adapter.parse(sub, 0).parent_native_id == "session-1"
    assert adapter.native_id_from_path(sub) != adapter.native_id_from_path(other_sub)


def test_partial_lines_invalid_records_and_optional_metadata(tmp_path):
    path = write_records(tmp_path / "s.jsonl", [{
        "role": "assistant", "cwd": "/work/proj", "timestamp": "2026-10-12T12:00:00Z",
        "message": {"id": "m", "model": "test-model", "usage": {"input_tokens": 10}, "content": [
            {"type": "thinking", "thinking": "Plan"},
            {"type": "tool_use", "id": "call-1", "name": "Read", "input": {"path": "x"}},
            {"type": "tool_result", "tool_use_id": "call-1", "content": "ok"},
        ]},
    }, {"type": "turn_ended", "status": "error", "error": "failed"}])
    with path.open("ab") as handle:
        handle.write(b'not-json\n{"future":true}\n{"role":"user"')
    adapter = CursorAdapter()
    result = adapter.parse(path, 0)
    assert result.project_cwd == "/work/proj"
    assert result.models == ["test-model"]
    assert result.started_at.isoformat() == "2026-10-12T12:00:00+00:00"
    assert [e.kind for e in result.events] == ["thinking", "tool_call", "tool_result", "system", "unknown", "unknown"]
    assert sum(e.usage is not None for e in result.events) == 1
    assert result.events[3].is_error
    with path.open("ab") as handle:
        handle.write(b',"message":{"content":"More"}}\n')
    appended = adapter.parse(path, result.end_offset)
    assert [e.text for e in appended.events] == ["More"]
    assert adapter.parse(path, appended.end_offset).events == []


def test_cursor_end_to_end_incremental_search_raw_and_workspace_groups(tmp_path):
    root = tmp_path / "cursor"
    path = write_records(transcript(root), RECORDS)
    write_records(transcript(root, "other-workspace", "session-2"), RECORDS)
    sub = write_records(path.parent / "subagents" / "agent-1.jsonl", RECORDS)
    before = {p: p.read_bytes() for p in (path, sub)}
    config = AppConfig(sources=[SourceConfig(path=str(root))], data_dir=tmp_path / "data", ingest_on_startup=False)
    with TestClient(create_app(config)) as client:
        assert client.post("/api/reindex").status_code == 200
        sessions = client.get("/api/sessions?agent=cursor").json()["sessions"]
        first = next(s for s in sessions if s["id"] == "cursor:session-1")
        second = next(s for s in sessions if s["id"] == "cursor:session-2")
        assert first["project_id"] != second["project_id"]
        assert first["project_name"] == "Users-test-my-project"
        assert first["project_cwd"] is None
        assert first["tokens_in"] is None and first["est_cost_usd"] is None
        assert first["title"] == "Fix the cursor parser"
        assert first["n_tool_calls"] == 2 and first["boundary_count"] == 0
        detail = client.get("/api/sessions/cursor:session-1").json()
        assert detail["children"][0]["id"] == "cursor:session-1:agent-1"
        assert client.get("/api/sessions/cursor:session-1:agent-1").status_code == 200
        events = client.get("/api/sessions/cursor:session-1/events").json()["events"]
        call = next(e for e in events if e["kind"] == "tool_call")
        assert "tool_use" in client.get(f"/api/events/{call['id']}/raw").text
        assert client.get("/api/search?q=cursor&agent=cursor").json()["hits"]
        source = client.get("/api/sources").json()["sources"][0]
        assert source["agent"] == "cursor" and source["files"] == 3
        assert client.post("/api/reindex").json()["files_parsed"] == 0
        for p, data in before.items():
            assert p.read_bytes() == data
        with path.open("a") as handle:
            handle.write(json.dumps({"role": "assistant", "message": {"content": "Fixed"}}) + "\n")
        assert client.post("/api/reindex").json()["events"] == 1
        after = client.get("/api/sessions/cursor:session-1/events").json()["events"]
        assert [e["id"] for e in after[:-1]] == [e["id"] for e in events]
        assert after[-1]["text"] == "Fixed"
        assert client.post("/api/reindex?full=true").status_code == 200
        assert client.get("/api/sessions/cursor:session-1").json()["n_events"] == len(after)
