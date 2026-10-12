import json
from pathlib import Path

from fastapi.testclient import TestClient

from obs.config import AppConfig, BoundaryConfig, SourceConfig
from obs.main import create_app

PRICING = Path(__file__).parent / "pricing.yaml"


def _write(root: Path, name: str, lines: list[dict]) -> None:
    project = root / "projects" / "p"
    project.mkdir(parents=True, exist_ok=True)
    path = project / name
    path.write_text("".join(json.dumps(line) + "\n" for line in lines))


def _line(uuid: str, session: str, cwd: str | None, content, tool=None) -> dict:
    message: dict = {"role": "assistant" if tool else "user", "content": content}
    if tool:
        message = {
            "role": "assistant",
            "model": "claude-sonnet-4",
            "id": uuid,
            "content": [{"type": "tool_use", "id": uuid, "name": tool[0], "input": tool[1]}],
        }
    body = {
        "type": "assistant" if tool else "user",
        "uuid": uuid,
        "sessionId": session,
        "timestamp": "2026-04-01T00:00:00.000Z",
        "message": message,
    }
    if cwd is not None:
        body["cwd"] = cwd
    return body


def _client(tmp_path: Path, root: Path, allow=None) -> TestClient:
    app = create_app(
        AppConfig(
            sources=[SourceConfig(path=str(root))],
            data_dir=tmp_path / "data",
            pricing_file=PRICING,
            ingest_on_startup=False,
            boundary=BoundaryConfig(allow_prefixes=allow or []),
        )
    )
    client = TestClient(app)
    client.__enter__()
    client.post("/api/reindex")
    return client


def test_file_inside_is_quiet_and_parent_and_absolute_alert(tmp_path: Path):
    root = tmp_path / "claude"
    _write(
        root,
        "s.jsonl",
        [
            _line("inside", "s", "/work/proj", "x", ("Read", {"file_path": "src/a.py"})),
            _line("parent", "s", "/work/proj", "x", ("Read", {"file_path": "../secret.txt"})),
            _line("abs", "s", "/work/proj", "x", ("Read", {"file_path": "/tmp/secret.txt"})),
            _line("shell-in", "s", "/work/proj", "x", ("Bash", {"command": "cat src/a.py"})),
            _line("shell-out", "s", "/work/proj", "x", ("Bash", {"command": "cat /tmp/secret.txt"})),
            _line("shell-rel", "s", "/work/proj", "x", ("Bash", {"command": "cat ../secret.txt"})),
        ],
    )
    client = _client(tmp_path, root)
    body = client.get("/api/sessions/claude_code:s/boundary").json()
    flagged = {item["path"] for item in body["paths"] if not item["allowed"]}
    assert "src/a.py" not in flagged
    assert "../secret.txt" in flagged
    assert "/tmp/secret.txt" in flagged
    assert all("src/a.py" not in path for path in flagged)
    resolved = {item["path"]: item["resolved"] for item in body["paths"]}
    assert resolved["../secret.txt"] == "/work/secret.txt"
    client.__exit__(None, None, None)


def test_missing_cwd_does_not_alert(tmp_path: Path):
    root = tmp_path / "claude"
    _write(
        root,
        "s.jsonl",
        [_line("t", "s", None, "x", ("Read", {"file_path": "/tmp/secret.txt"}))],
    )
    client = _client(tmp_path, root)
    body = client.get("/api/sessions/claude_code:s/boundary").json()
    assert body["count"] == 0
    assert body["paths"] == []
    client.__exit__(None, None, None)


def test_dismissal_hides_prefix_and_survives_reindex(tmp_path: Path):
    root = tmp_path / "claude"
    _write(
        root,
        "s.jsonl",
        [_line("abs", "s", "/work/proj", "x", ("Read", {"file_path": "/tmp/secret.txt"}))],
    )
    client = _client(tmp_path, root)
    session = client.get("/api/sessions/claude_code:s").json()
    assert session["boundary_count"] == 1
    client.put(
        "/api/boundary/dismissals",
        json={"project_id": session["project_id"], "path_prefix": "/tmp"},
    )
    after = client.get("/api/sessions/claude_code:s/boundary").json()
    assert after["count"] == 0
    assert after["paths"][0]["dismissed"] is True
    client.post("/api/reindex", params={"full": "true"})
    again = client.get("/api/sessions/claude_code:s/boundary").json()
    assert again["count"] == 0
    assert again["paths"][0]["dismissed"] is True
    listed = client.get("/api/boundary").json()["sessions"]
    assert listed == []
    client.__exit__(None, None, None)
