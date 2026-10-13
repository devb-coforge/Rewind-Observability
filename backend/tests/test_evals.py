CLAUDE = "claude_code:11111111-1111-1111-1111-111111111111"


def test_freeze_survives_reindex_and_summary_groups_by_model(client):
    created = client.post("/api/evals/cases", json={"session_id": CLAUDE}).json()
    assert "Please fix the parser" in created["prompt"]
    assert created["model"].startswith("claude-sonnet-4")
    assert created["session_title"] == client.get(f"/api/sessions/{CLAUDE}").json()["title"]
    assert created["tokens_in"] == 110
    assert created["est_cost_usd"] is not None
    assert any(item["tool_name"] == "Read" for item in created["tool_summary"])
    assert "print" not in json_dumps(created["tool_summary"])
    client.post("/api/reindex", params={"full": "true"})
    again = client.get(f"/api/evals/cases/{created['id']}").json()
    assert again["prompt"] == created["prompt"]
    patched = client.patch(
        f"/api/evals/cases/{created['id']}",
        json={"verdict": "pass", "note": "looks right"},
    ).json()
    assert patched["verdict"] == "pass"
    summary = client.get("/api/evals/summary").json()
    assert "biased" in summary["note"]
    group = next(item for item in summary["groups"] if item["model"] == created["model"])
    assert group["pass_rate"] == 1
    assert group["n"] == 1
    client.delete(f"/api/evals/cases/{created['id']}")
    assert client.get(f"/api/evals/cases/{created['id']}").status_code == 404
    remaining = client.get("/api/evals/cases").json()["cases"]
    assert remaining == []


def json_dumps(value) -> str:
    import json

    return json.dumps(value)


def test_cursor_eval_metadata_backfill_and_snapshot_preservation(tmp_path):
    import json
    import sqlite3
    from fastapi.testclient import TestClient
    from obs.config import AppConfig, SourceConfig
    from obs.main import create_app

    root = tmp_path / "cursor"
    transcript = root / "projects/workspace/agent-transcripts/session.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_text(json.dumps({"role": "user", "message": {"content": "Long prompt"}}) + "\n")
    config = AppConfig(sources=[SourceConfig(path=str(root))], data_dir=tmp_path / "data", ingest_on_startup=False)
    with TestClient(create_app(config)) as client:
        client.post("/api/reindex")
        old = client.post("/api/evals/cases", json={"session_id": "cursor:session"}).json()
        assert old["model"] is None
        store = client.app.state.obs.store
        with store.transaction():
            store.user.execute("UPDATE eval_cases SET session_title=NULL, verdict='pass', note='Keep me' WHERE id=?", (old["id"],))
        path = root / "user-data/globalStorage/state.vscdb"
        path.parent.mkdir(parents=True)
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE cursorDiskKV(key TEXT PRIMARY KEY, value TEXT)")
            db.execute("INSERT INTO cursorDiskKV VALUES (?, ?)", ("composerData:session", json.dumps({
                "name": "Compatibility shims removal", "modelConfig": {"modelName": "different-selection"},
            })))
            db.execute("INSERT INTO cursorDiskKV VALUES (?, ?)", ("bubbleId:session:a", json.dumps({
                "modelInfo": {"modelName": "composer-2.5"},
            })))
        client.post("/api/reindex")
        repaired = client.get(f"/api/evals/cases/{old['id']}").json()
        assert repaired["model"] == "composer-2.5"
        assert repaired["session_title"] == "Compatibility shims removal"
        assert repaired["prompt"] == old["prompt"]
        assert repaired["verdict"] == "pass" and repaired["note"] == "Keep me"
        assert repaired["tokens_in"] is None and repaired["est_cost_usd"] is None
        assert client.get("/api/evals/cases?model=composer-2.5").json()["cases"][0]["id"] == old["id"]
        new = client.post("/api/evals/cases", json={"session_id": "cursor:session", "from_seq": 0, "to_seq": 0}).json()
        assert new["model"] == "composer-2.5" and new["session_title"] == repaired["session_title"]
        with sqlite3.connect(path) as db:
            db.execute("INSERT INTO cursorDiskKV VALUES (?, ?)", ("bubbleId:session:b", json.dumps({
                "modelInfo": {"modelName": "another-model"},
            })))
            db.execute("UPDATE cursorDiskKV SET value=? WHERE key='composerData:session'", (json.dumps({"name": "Renamed"}),))
        client.post("/api/reindex?full=true")
        ambiguous = client.post("/api/evals/cases", json={"session_id": "cursor:session"}).json()
        assert ambiguous["model"] is None
        assert ambiguous["session_title"] == "Renamed"
        assert client.get(f"/api/evals/cases/{old['id']}").json() == repaired
