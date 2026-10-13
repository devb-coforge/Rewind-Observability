import json
import sqlite3

from fastapi.testclient import TestClient

from obs.config import AppConfig, SourceConfig
from obs.main import create_app
from obs.adapters.cursor import CursorAdapter


def test_sqlite_results_pair_refresh_and_keep_raw_provenance(tmp_path, monkeypatch):
    root = tmp_path / "cursor"
    path = root / "projects/workspace/agent-transcripts/session/session.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"role": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Shell", "input": {"command": "npm test"}},
        {"type": "tool_use", "name": "Read", "input": {"path": "missing.py"}},
    ]}}) + "\n")
    base = tmp_path / "cursor-user"
    dbpath = base / "globalStorage/state.vscdb"
    dbpath.parent.mkdir(parents=True)
    db = sqlite3.connect(dbpath)
    db.execute("CREATE TABLE cursorDiskKV(key TEXT PRIMARY KEY, value TEXT)")

    def bubble(key, name, args, result, status="completed", error=None, order=1):
        obj = {"startedAtMs": order, "toolFormerData": {
            "toolCallId": key, "name": name, "rawArgs": json.dumps(args),
            "status": status, "result": json.dumps(result), "error": error,
        }}
        db.execute("INSERT OR REPLACE INTO cursorDiskKV VALUES (?, ?)",
                   (f"bubbleId:session:{key}", json.dumps(obj)))
        db.commit()

    bubble("shell", "run_terminal_command_v2", {"command": "npm test"}, {"exitCode": 1, "output": "failure"})
    bubble("read", "read_file_v2", {"path": "missing.py"}, {}, "error", "File not found", 2)
    # A result whose call cannot be identified must still count, without adding a duplicate call.
    bubble("other", "read_file_v2", {"path": "other.py"}, {}, "error", "Denied", 3)
    before = path.read_bytes()
    config = AppConfig(sources=[SourceConfig(path=str(root))], cursor_user_data_dir=base,
                       data_dir=tmp_path / "data", pricing_file=tmp_path / "missing-pricing.yaml",
                       ingest_on_startup=False)
    with TestClient(create_app(config)) as client:
        assert client.post("/api/reindex").status_code == 200
        detail = client.get("/api/sessions/cursor:session").json()
        assert detail["n_tool_calls"] == 2
        assert detail["n_tool_errors"] == 3
        events = client.get("/api/sessions/cursor:session/events").json()["events"]
        call = next(e for e in events if e["tool_name"] == "Shell" and e["kind"] == "tool_call")
        result = next(e for e in events if e["tool_call_id"] == call["tool_call_id"] and e["kind"] == "tool_result")
        assert result["is_error"]
        raw = client.get(f"/api/events/{result['id']}/raw").json()
        assert raw["key"] == "bubbleId:session:shell"
        assert raw["database"] == str(dbpath)
        assert client.get("/api/search?q=failure&agent=cursor").json()["hits"]
        tools = client.get("/api/analytics/tools?agent=cursor").json()["tools"]
        assert sum(t["calls"] for t in tools) == 2
        assert sum(t["errors"] for t in tools) == 3
        from obs.otel_export import build_spans

        spans = build_spans(detail, events, include_content=False)
        assert sum(s.status_code == "ERROR" for s in spans) == 3
        assert client.post("/api/reindex").status_code == 200
        assert client.get("/api/sessions/cursor:session").json()["n_events"] == len(events)
        bubble("shell", "run_terminal_command_v2", {"command": "npm test"}, {"exitCode": 0, "output": "passed"})
        assert client.post("/api/reindex").status_code == 200
        updated = client.get("/api/sessions/cursor:session").json()
        assert updated["n_tool_errors"] == 2
        assert updated["n_events"] == len(events)
        # An unavailable database must preserve the last imported outcomes.
        with monkeypatch.context() as patch:
            patch.setattr(CursorAdapter, "session_metadata", lambda *args: None)
            assert client.post("/api/reindex").status_code == 200
            assert client.get("/api/sessions/cursor:session").json()["n_tool_errors"] == 2
        assert client.post("/api/reindex?full=true").status_code == 200
        assert client.get("/api/sessions/cursor:session").json()["n_events"] == len(events)
        assert path.read_bytes() == before
    db.close()
