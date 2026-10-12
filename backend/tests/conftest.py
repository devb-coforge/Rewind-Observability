from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from obs.config import AppConfig, OtelConfig, SourceConfig
from obs.main import create_app

ROOT = Path(__file__).parent
FIXTURES = ROOT / "fixtures"


@pytest.fixture
def source_dirs(tmp_path: Path) -> tuple[Path, Path]:
    claude = tmp_path / "claude"
    codex = tmp_path / "codex"
    shutil.copytree(FIXTURES / "claude", claude)
    shutil.copytree(FIXTURES / "codex", codex)
    return claude, codex


@pytest.fixture
def make_client(tmp_path: Path, source_dirs: tuple[Path, Path]):
    claude, codex = source_dirs

    def _make(*, endpoint: str = "", include_content: bool = False, sender=None, allow_prefixes=None):
        config = AppConfig(
            sources=[
                SourceConfig(path=str(claude), agent="claude_code"),
                SourceConfig(path=str(codex), agent="codex"),
            ],
            data_dir=tmp_path / "data",
            pricing_file=ROOT / "pricing.yaml",
            ingest_on_startup=False,
            otel=OtelConfig(endpoint=endpoint, include_content=include_content),
            boundary={"allow_prefixes": allow_prefixes or []},
        )
        app = create_app(config, sender=sender)
        return TestClient(app)

    return _make


@pytest.fixture
def client(make_client):
    with make_client() as test:
        test.post("/api/reindex")
        yield test
