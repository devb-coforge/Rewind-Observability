import json
import os
from pathlib import Path

import pytest


CLAUDE = "claude_code:11111111-1111-1111-1111-111111111111"
CODEX = "codex:codex-sess-1"


def test_indexes_both_agents(client):
    sessions = client.get("/api/sessions").json()["sessions"]
    ids = {item["id"] for item in sessions}
    assert CLAUDE in ids
    assert CODEX in ids
    claude = next(item for item in sessions if item["id"] == CLAUDE)
    assert claude["tokens_in"] == 110
    assert claude["tokens_out"] == 25
    assert claude["tokens_cache_read"] == 5
    assert claude["tokens_cache_write"] == 2
    assert claude["n_tool_calls"] == 2
    assert claude["n_tool_errors"] == 1
    assert claude["title"] == "Please fix the parser"
    assert claude["project_name"] == "proj"
    assert claude["est_cost_usd"] == pytest.approx(0.000714)
    codex = next(item for item in sessions if item["id"] == CODEX)
    assert codex["tokens_in"] == 30
    assert codex["tokens_out"] == 12
    assert codex["tokens_cache_read"] == 4
    assert codex["git_branch"] == "feature"
    detail = client.get(f"/api/sessions/{CLAUDE}").json()
    assert any(child["id"] == "claude_code:agent-1" for child in detail["children"])


def test_events_pair_and_unknown_kept(client):
    events = client.get(f"/api/sessions/{CLAUDE}/events").json()["events"]
    kinds = [event["kind"] for event in events]
    assert "unknown" in kinds
    assert "thinking" in kinds
    calls = [event for event in events if event["kind"] == "tool_call"]
    assert calls[0]["tool_call_id"] == "toolu_1"
    raw = client.get(f"/api/events/{calls[0]['id']}/raw")
    assert raw.status_code == 200
    assert "toolu_1" in raw.text
    output = client.get("/api/events/" + [e["id"] for e in events if e["kind"] == "tool_result"][0] + "/output")
    assert "print" in output.json()["output"]


def test_incremental_append_parses_only_new_line(client, source_dirs):
    claude, _codex = source_dirs
    path = next(claude.rglob("11111111*.jsonl"))
    before = client.get(f"/api/sessions/{CLAUDE}").json()["n_events"]
    with path.open("a") as handle:
        handle.write(
            "\n"
            + json.dumps(
                {
                    "type": "user",
                    "uuid": "u-new",
                    "sessionId": "11111111-1111-1111-1111-111111111111",
                    "cwd": "/work/proj",
                    "timestamp": "2026-01-02T16:00:00.000Z",
                    "message": {"role": "user", "content": "One more thing"},
                }
            )
            + "\n"
        )
    client.post("/api/reindex")
    after = client.get(f"/api/sessions/{CLAUDE}").json()
    assert after["n_events"] == before + 1
    events = client.get(f"/api/sessions/{CLAUDE}/events?limit=500").json()["events"]
    assert any(event["text"] == "One more thing" for event in events)


def test_truncated_line_waits_for_newline(tmp_path):
    claude_home = tmp_path / "trunc" / "claude"
    root = claude_home / "projects" / "p"
    root.mkdir(parents=True)
    path = root / "sess.jsonl"
    path.write_text(
        json.dumps(
            {
                "type": "user",
                "uuid": "only",
                "sessionId": "sess",
                "cwd": "/work/proj",
                "timestamp": "2026-03-01T00:00:00.000Z",
                "message": {"role": "user", "content": "complete"},
            }
        )
        + "\n{\"type\":\"user\""
    )
    from obs.config import AppConfig, SourceConfig
    from obs.main import create_app
    from fastapi.testclient import TestClient

    app = create_app(
        AppConfig(
            sources=[SourceConfig(path=str(claude_home))],
            data_dir=tmp_path / "data2",
            pricing_file=Path(__file__).parent / "pricing.yaml",
            ingest_on_startup=False,
        )
    )
    with TestClient(app) as test:
        test.post("/api/reindex")
        listing = test.get("/api/sessions").json()["sessions"]
        assert len(listing) == 1
        assert listing[0]["n_events"] == 1
        with path.open("a") as handle:
            handle.write(',"uuid":"two","sessionId":"sess","cwd":"/work/proj","timestamp":"2026-03-01T00:00:01.000Z","message":{"role":"user","content":"finished"}}\n')
        os.utime(path, None)
        test.post("/api/reindex")
        again = test.get("/api/sessions").json()["sessions"][0]
        assert again["n_events"] == 2


def test_forked_uuid_is_not_duplicated(make_client, source_dirs):
    claude, _codex = source_dirs
    projects = claude / "projects" / "-work-proj"
    fork = projects / "22222222-2222-2222-2222-222222222222.jsonl"
    fork.write_text(
        json.dumps(
            {
                "type": "user",
                "uuid": "u1",
                "sessionId": "22222222-2222-2222-2222-222222222222",
                "cwd": "/work/proj",
                "timestamp": "2026-01-03T00:00:00.000Z",
                "message": {"role": "user", "content": "Please fix the parser"},
            }
        )
        + "\n"
        + json.dumps(
            {
                "type": "user",
                "uuid": "fresh",
                "sessionId": "22222222-2222-2222-2222-222222222222",
                "cwd": "/work/proj",
                "timestamp": "2026-01-03T00:00:01.000Z",
                "message": {"role": "user", "content": "brand new"},
            }
        )
        + "\n"
    )
    with make_client() as test:
        test.post("/api/reindex")
        original = test.get(f"/api/sessions/{CLAUDE}/events?limit=500").json()["events"]
        assert sum(1 for event in original if event["text"] == "Please fix the parser") == 1
        forked = test.get("/api/sessions/claude_code:22222222-2222-2222-2222-222222222222/events").json()["events"]
        assert [event["text"] for event in forked] == ["brand new"]


def test_search_and_sources(client):
    hits = client.get("/api/search", params={"q": "parser"}).json()["hits"]
    assert hits
    assert hits[0]["session_id"] == CLAUDE
    sources = client.get("/api/sources").json()
    assert sources["last_indexed_at"]
    assert {item["agent"] for item in sources["sources"]} == {"claude_code", "codex"}
    assert all(item["files"] >= 1 for item in sources["sources"])


def test_search_failures(client):
    body = client.get("/api/search/failures").json()
    assert body["total"] >= 1
    assert body["hits"]
    assert sum(item["count"] for item in body["by_tool"]) == body["total"]
    first = body["hits"][0]
    assert first["tool_name"] and first["session_id"]
    narrowed = client.get("/api/search/failures", params={"tool": first["tool_name"]}).json()
    assert narrowed["hits"] and all(h["tool_name"] == first["tool_name"] for h in narrowed["hits"])
    assert client.get("/api/search/failures", params={"q": "zzz-no-such-text"}).json()["hits"] == []
