import json
import sqlite3

from fastapi.testclient import TestClient

from obs.config import AppConfig, SourceConfig
from obs.main import create_app


def test_cursor_duration_and_paths_backfill_refresh_rebuild(tmp_path):
    root = tmp_path / "cursor"
    transcript = root / "projects/workspace/agent-transcripts/s.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_text(json.dumps({"role": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Read", "input": {"path": "src/app.py"}},
        {"type": "tool_use", "name": "Shell", "input": {"command": "cat /other/secret"}},
    ]}}) + "\n")
    config = AppConfig(sources=[SourceConfig(path=str(root))], data_dir=tmp_path / "data", ingest_on_startup=False)
    with TestClient(create_app(config)) as client:
        client.post("/api/reindex")
        assert client.get("/api/sessions/cursor:s").json()["duration_sec"] is None
        path = root / "user-data/globalStorage/state.vscdb"
        path.parent.mkdir(parents=True)
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE cursorDiskKV(key TEXT PRIMARY KEY, value TEXT)")
            composer = {"createdAt": 1791806400000, "lastUpdatedAt": 1791810000000,
                        "workspaceIdentifier": {"uri": {"scheme": "file", "fsPath": "/work/proj"}}}
            db.execute("INSERT INTO cursorDiskKV VALUES (?, ?)", ("composerData:s", json.dumps(composer)))
            for bubble, duration in (("a", 61986), ("b", 2000), ("negative", -1),
                                     ("string", "9000"), ("boolean", True)):
                db.execute("INSERT INTO cursorDiskKV VALUES (?, ?)", (
                    f"bubbleId:s:{bubble}", json.dumps({"turnDurationMs": duration})))
            db.commit()
            assert client.post("/api/reindex").json()["files_parsed"] == 0
            session = client.get("/api/sessions/cursor:s").json()
            assert session["duration_sec"] == 63.986
            assert session["ended_at"] is None
            assert session["project_cwd"] == "/work/proj"
            assert session["boundary_count"] == 1
            events = client.get("/api/sessions/cursor:s/events").json()["events"]
            assert events[0]["paths"][0]["resolved"] == "/work/proj/src/app.py"
            assert events[1]["paths"][0]["outside"] is True
            assert client.get("/api/analytics/summary").json()["median_duration_sec"] == 63.986
            series = client.get("/api/analytics/timeseries?metric=duration&bucket=day").json()
            assert series["points"][0]["value"] == 63.986
            assert client.get("/api/sessions?sort=duration").json()["sessions"][0]["duration_sec"] == 63.986
            composer["workspaceIdentifier"]["uri"]["fsPath"] = "/other"
            db.execute("UPDATE cursorDiskKV SET value=? WHERE key='composerData:s'", (json.dumps(composer),))
            db.execute("UPDATE cursorDiskKV SET value=? WHERE key='bubbleId:s:b'", (json.dumps({"turnDurationMs": 4000}),))
            db.commit()
            client.post("/api/reindex")
            session = client.get("/api/sessions/cursor:s").json()
            assert session["duration_sec"] == 65.986
            assert session["project_cwd"] == "/other"
            assert session["boundary_count"] == 0
            client.post("/api/reindex?full=true")
            assert client.get("/api/sessions/cursor:s").json()["duration_sec"] == 65.986
            assert client.get("/api/sessions/cursor:s").json()["project_cwd"] == "/other"
            # Unavailable metadata preserves the imported duration and workspace.
            db.execute("ALTER TABLE cursorDiskKV RENAME TO savedKV")
            db.execute("CREATE TABLE cursorDiskKV(unrecognized TEXT)")
            db.commit()
            client.post("/api/reindex")
            assert client.get("/api/sessions/cursor:s").json()["duration_sec"] == 65.986
            assert client.get("/api/sessions/cursor:s").json()["project_cwd"] == "/other"


def test_explicit_transcript_cwd_wins_over_workspace_metadata(tmp_path):
    root = tmp_path / "cursor"
    transcript = root / "projects/workspace/agent-transcripts/s.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_text(json.dumps({"cwd": "/explicit", "role": "user", "message": {"content": "Hello"}}) + "\n")
    path = root / "user-data/globalStorage/state.vscdb"
    path.parent.mkdir(parents=True)
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE composerHeaders(composerId TEXT, value TEXT)")
        db.execute("INSERT INTO composerHeaders VALUES (?, ?)", ("s", json.dumps({
            "workspaceIdentifier": {"uri": {"scheme": "file", "fsPath": "/workspace"}},
        })))
    config = AppConfig(sources=[SourceConfig(path=str(root))], data_dir=tmp_path / "data", ingest_on_startup=False)
    with TestClient(create_app(config)) as client:
        client.post("/api/reindex")
        session = client.get("/api/sessions/cursor:s").json()
        assert session["project_cwd"] == "/explicit"
        assert session["duration_sec"] is None
