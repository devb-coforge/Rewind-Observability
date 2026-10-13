import json
import sqlite3

from obs.db.repo import Store

CODEX = "codex:codex-sess-1"
CLAUDE = "claude_code:11111111-1111-1111-1111-111111111111"


def write_name(path, name):
    path.write_text(json.dumps({"id": "codex-sess-1", "thread_name": name}) + "\n")


def test_names_refresh_without_transcript_changes_and_survive_rebuild(client, source_dirs):
    _, codex = source_dirs
    fallback = client.get(f"/api/sessions/{CODEX}").json()["title"]
    events = client.get(f"/api/sessions/{CODEX}/events").json()["events"]
    index = codex / "session_index.jsonl"
    write_name(index, "Improve system message UX")
    scan = client.post("/api/reindex").json()
    assert scan["files_parsed"] == 0
    assert client.get(f"/api/sessions/{CODEX}").json()["title"] == "Improve system message UX"
    listing = client.get("/api/sessions", params={"q": "Improve system message UX"}).json()["sessions"]
    assert [item["id"] for item in listing] == [CODEX]
    assert client.get(f"/api/sessions/{CLAUDE}").json()["title"] == "Please fix the parser"

    write_name(index, "Renamed conversation")
    client.post("/api/reindex")
    assert client.get(f"/api/sessions/{CODEX}").json()["title"] == "Renamed conversation"
    client.post("/api/reindex", params={"full": True})
    assert client.get(f"/api/sessions/{CODEX}").json()["title"] == "Renamed conversation"
    assert client.get(f"/api/sessions/{CODEX}/events").json()["events"] == events

    # Removing a saved name restores the title derived from the transcript.
    write_name(index, "")
    client.post("/api/reindex")
    assert client.get(f"/api/sessions/{CODEX}").json()["title"] == fallback


def test_transcript_append_does_not_replace_saved_name(client, source_dirs):
    _, codex = source_dirs
    write_name(codex / "session_index.jsonl", "Saved conversation")
    client.post("/api/reindex")
    transcript = next(codex.rglob("rollout-*.jsonl"))
    with transcript.open("a") as handle:
        handle.write(json.dumps({
            "type": "response_item", "timestamp": "2026-02-01T13:00:00Z",
            "payload": {"type": "message", "role": "user", "content": "New request"},
        }) + "\n")
    client.post("/api/reindex")
    assert client.get(f"/api/sessions/{CODEX}").json()["title"] == "Saved conversation"


def test_existing_index_schema_migrates_without_rebuild(tmp_path):
    path = tmp_path / "index.db"
    store = Store(tmp_path)
    store.close()
    with sqlite3.connect(path) as db:
        db.execute("ALTER TABLE sessions DROP COLUMN source_title")
    store = Store(tmp_path)
    assert "source_title" in {row["name"] for row in store.index.execute("PRAGMA table_info(sessions)")}
    store.close()
