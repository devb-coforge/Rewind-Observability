from pathlib import Path

import pytest

from obs.adapters.claude_code import ClaudeCodeAdapter
from obs.adapters.codex import CodexAdapter


@pytest.mark.parametrize("full", [False, True])
@pytest.mark.parametrize("failure", ["discovery", "parse"])
def test_reindex_permission_failure_preserves_index(client, monkeypatch, full, failure):
    store = client.app.state.obs.store
    before = [dict(row) for row in store.index.execute("SELECT * FROM events ORDER BY id")]
    files_before = [dict(row) for row in store.list_files()]
    indexed_at = store.get_meta("last_indexed_at")
    assert before

    def denied(*args):
        raise PermissionError(13, "Permission denied", "/sources/claude/projects")

    with monkeypatch.context() as patch:
        if failure == "discovery":
            patch.setattr(ClaudeCodeAdapter, "discover", denied)
        else:
            # Force reparsing even for an incremental scan of unchanged fixtures.
            patch.setattr(ClaudeCodeAdapter, "version", 999)
            patch.setattr(ClaudeCodeAdapter, "parse", denied)
        response = client.post("/api/reindex", params={"full": full})

    assert response.status_code == 403
    assert "PUID and PGID" in response.json()["detail"]
    assert "index was not changed" in response.json()["detail"]
    assert [dict(row) for row in store.index.execute("SELECT * FROM events ORDER BY id")] == before
    assert [dict(row) for row in store.list_files()] == files_before
    assert store.get_meta("last_indexed_at") == indexed_at
    assert client.post("/api/reindex", params={"full": full}).status_code == 200


@pytest.mark.parametrize("adapter,subdir", [
    (ClaudeCodeAdapter(), "projects"),
    (CodexAdapter(), "sessions"),
])
def test_discovery_reports_unreadable_nested_directory(tmp_path, monkeypatch, adapter, subdir):
    import os

    base = tmp_path / subdir
    blocked = base / "private"
    blocked.mkdir(parents=True)
    original = os.scandir

    def scandir(path):
        if Path(path) == blocked:
            raise PermissionError(13, "Permission denied", str(blocked))
        return original(path)

    monkeypatch.setattr(os, "scandir", scandir)
    with pytest.raises(PermissionError):
        adapter.discover(tmp_path)
