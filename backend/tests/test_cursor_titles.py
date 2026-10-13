import json
import sqlite3

from fastapi.testclient import TestClient

from obs.adapters.cursor import CursorAdapter
from obs.config import AppConfig, SourceConfig, load_config
from obs.main import create_app


def test_saved_cursor_names_refresh_search_and_rebuild_without_transcript_changes(tmp_path):
    root = tmp_path / "cursor"
    path = root / "projects/workspace/agent-transcripts/session-1/session-1.jsonl"
    path.parent.mkdir(parents=True)
    raw = json.dumps({"role": "user", "message": {"content": "First prompt"}}) + "\n"
    path.write_text(raw)
    base = root / "user-data"
    metadata = base / "globalStorage/state.vscdb"
    metadata.parent.mkdir(parents=True)
    # Keep the writer open to verify names are read from the live WAL.
    with sqlite3.connect(metadata) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE composerHeaders(composerId TEXT PRIMARY KEY, value TEXT)")
        db.execute("INSERT INTO composerHeaders VALUES (?, ?)", ("session-1", json.dumps({"name": "Code usage inquiry"})))
        db.commit()
        config = AppConfig(sources=[SourceConfig(path=str(root))], data_dir=tmp_path / "data", ingest_on_startup=False)
        with TestClient(create_app(config)) as client:
            client.post("/api/reindex")
            assert client.get("/api/sessions/cursor:session-1").json()["title"] == "Code usage inquiry"
            events = client.get("/api/sessions/cursor:session-1/events").json()["events"]
            db.execute("UPDATE composerHeaders SET value=?", (json.dumps({"name": "Renamed agent"}),))
            db.commit()
            assert client.post("/api/reindex").json()["files_parsed"] == 0
            assert client.get("/api/sessions/cursor:session-1").json()["title"] == "Renamed agent"
            assert client.get("/api/sessions?q=Renamed%20agent").json()["sessions"][0]["id"] == "cursor:session-1"
            client.post("/api/reindex?full=true")
            assert client.get("/api/sessions/cursor:session-1").json()["title"] == "Renamed agent"
            assert client.get("/api/sessions/cursor:session-1/events").json()["events"] == events
            # A temporarily unavailable metadata mount preserves the imported name.
            db.execute("ALTER TABLE composerHeaders RENAME TO savedHeaders")
            db.execute("CREATE TABLE composerHeaders(unrecognized TEXT)")
            db.commit()
            client.post("/api/reindex")
            assert client.get("/api/sessions/cursor:session-1").json()["title"] == "Renamed agent"
            db.execute("DROP TABLE composerHeaders")
            db.execute("ALTER TABLE savedHeaders RENAME TO composerHeaders")
            db.execute("UPDATE composerHeaders SET value=?", (json.dumps({"name": ""}),))
            db.commit()
            client.post("/api/reindex")
            assert client.get("/api/sessions/cursor:session-1").json()["title"] == "First prompt"
        assert path.read_text() == raw
        assert db.execute("SELECT value FROM composerHeaders").fetchone()[0] == json.dumps({"name": ""})


def test_older_metadata_layouts_and_explicit_source_location(tmp_path):
    root = tmp_path / "cursor"
    base = tmp_path / "metadata"
    dbpath = base / "workspaceStorage/workspace/state.vscdb"
    dbpath.parent.mkdir(parents=True)
    with sqlite3.connect(dbpath) as db:
        db.execute("CREATE TABLE ItemTable(key TEXT PRIMARY KEY, value TEXT)")
        db.execute("INSERT INTO ItemTable VALUES (?, ?)", ("composer.composerData", json.dumps({
            "allComposers": [{"composerId": "session-1", "name": "Old sidebar title"}],
        })))
        db.execute("CREATE TABLE cursorDiskKV(key TEXT PRIMARY KEY, value TEXT)")
        db.execute("INSERT INTO cursorDiskKV VALUES (?, ?)", ("composerData:session-2", json.dumps({"name": "Saved KV title"})))
        db.execute("INSERT INTO cursorDiskKV VALUES ('composerData:invalid', 'not-json')")
    before = dbpath.read_bytes()
    assert CursorAdapter().session_titles(root, base) == {"session-1": "Old sidebar title", "session-2": "Saved KV title"}
    assert dbpath.read_bytes() == before
    assert CursorAdapter().session_titles(root) is None
    assert CursorAdapter().session_titles(root, tmp_path / "missing") is None


def test_metadata_path_environment_override(tmp_path, monkeypatch):
    monkeypatch.setenv("OBS_CURSOR_USER_DATA_DIR", str(tmp_path))
    assert load_config().cursor_user_data_dir == tmp_path


def test_creation_date_backfills_existing_sessions_and_daily_chart(tmp_path):
    root = tmp_path / "cursor"
    transcripts = root / "projects/workspace/agent-transcripts"
    transcripts.mkdir(parents=True)
    for sid in ("dated", "undated"):
        (transcripts / f"{sid}.jsonl").write_text(json.dumps({"role": "user", "message": {"content": "Prompt"}}) + "\n")
    config = AppConfig(sources=[SourceConfig(path=str(root))], data_dir=tmp_path / "data", ingest_on_startup=False)
    with TestClient(create_app(config)) as client:
        client.post("/api/reindex")
        assert client.get("/api/analytics/summary").json()["sessions_missing_start"] == 2
        path = root / "user-data/globalStorage/state.vscdb"
        path.parent.mkdir(parents=True)
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE composerHeaders(composerId TEXT PRIMARY KEY, value TEXT)")
            db.execute("INSERT INTO composerHeaders VALUES (?, ?)", ("dated", json.dumps({
                "name": "Saved conversation", "createdAt": 1791806400000,
                "lastUpdatedAt": 1791810000000,
            })))
        assert client.post("/api/reindex").json()["files_parsed"] == 0
        session = client.get("/api/sessions/cursor:dated").json()
        assert session["started_at"] == "2026-10-12T12:00:00.000Z"
        assert session["ended_at"] is None
        assert session["duration_sec"] is None
        events = client.get("/api/sessions/cursor:dated/events").json()["events"]
        assert all(event["ts"] is None for event in events)
        summary = client.get("/api/analytics/summary").json()
        assert summary["sessions"] == 2 and summary["sessions_missing_start"] == 1
        series = client.get("/api/analytics/timeseries?metric=sessions&bucket=day&group_by=agent").json()
        assert series["points"] == [{"bucket": "2026-10-12", "group": "cursor", "value": 1}]
        assert len(client.get("/api/sessions?from=2026-10-12&to=2026-10-12").json()["sessions"]) == 1
        client.post("/api/reindex?full=true")
        assert client.get("/api/sessions/cursor:dated").json()["started_at"] == session["started_at"]


def test_invalid_metadata_dates_stay_unknown(tmp_path):
    base = tmp_path / "metadata"
    path = base / "globalStorage/state.vscdb"
    path.parent.mkdir(parents=True)
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE composerHeaders(composerId TEXT PRIMARY KEY, value TEXT)")
        db.execute("INSERT INTO composerHeaders VALUES (?, ?)", ("session-1", json.dumps({
            "name": "Title", "createdAt": "invalid", "lastUpdatedAt": 1791810000000,
        })))
    assert CursorAdapter().session_metadata(tmp_path / "cursor", base) == {"session-1": {"title": "Title"}}
