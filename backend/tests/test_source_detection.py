import shutil
from pathlib import Path

from obs.adapters.detect import infer_agent_from_path
from obs.analytics.pricing import Pricing
from obs.config import AppConfig, SourceConfig
from obs.db.repo import Store
from obs.ingest.pipeline import Ingestor
from obs.ingest.scanner import source_root

ROOT = Path(__file__).parent


def test_infer_agent_from_well_known_dir_names(tmp_path: Path):
    assert infer_agent_from_path(tmp_path / ".claude") == "claude_code"
    assert infer_agent_from_path(tmp_path / "claude") == "claude_code"
    assert infer_agent_from_path(tmp_path / ".codex") == "codex"
    assert infer_agent_from_path(tmp_path / "codex") == "codex"
    assert infer_agent_from_path(tmp_path / ".cursor") == "cursor"
    assert infer_agent_from_path(tmp_path / "cursor") == "cursor"
    assert infer_agent_from_path(tmp_path / "extra") is None


def test_classify_fixture_dirs_by_name(source_dirs):
    claude, codex = source_dirs
    assert infer_agent_from_path(claude) == "claude_code"
    assert infer_agent_from_path(codex) == "codex"


def test_source_roots_expand_environment_variables(source_dirs, monkeypatch):
    _, codex = source_dirs
    monkeypatch.setenv("OBS_TEST_SOURCE_PARENT", str(codex.parent))
    source = SourceConfig(path="$OBS_TEST_SOURCE_PARENT/codex")
    assert source_root(source) == codex


def test_names_import_from_environment_variable_source_root(source_dirs, tmp_path, monkeypatch):
    import json

    _, codex = source_dirs
    monkeypatch.setenv("OBS_TEST_SOURCE_PARENT", str(codex.parent))
    (codex / "session_index.jsonl").write_text(json.dumps({
        "id": "codex-sess-1", "thread_name": "Saved Codex name",
    }) + "\n")
    config = AppConfig(
        sources=[SourceConfig(path="$OBS_TEST_SOURCE_PARENT/codex")],
        data_dir=tmp_path / "data",
        ingest_on_startup=False,
    )
    store = Store(config.data_dir)
    try:
        Ingestor(config, store, Pricing.load(ROOT / "pricing.yaml")).run()
        assert store.get_session("codex:codex-sess-1")["title"] == "Saved Codex name"
    finally:
        store.close()


def test_ingest_removes_files_outside_configured_roots(source_dirs, tmp_path: Path):
    claude, codex = source_dirs
    data_dir = tmp_path / "data"
    pricing = Pricing.load(ROOT / "pricing.yaml")
    store = Store(data_dir)
    orphan_root = tmp_path / "extra" / "claude"
    orphan_root.mkdir(parents=True)
    sample = claude / "projects" / "-work-proj" / "11111111-1111-1111-1111-111111111111.jsonl"
    copied = orphan_root / sample.name
    shutil.copy(sample, copied)

    wide = AppConfig(
        sources=[
            SourceConfig(path=str(claude)),
            SourceConfig(path=str(codex)),
            SourceConfig(path=str(orphan_root)),
        ],
        data_dir=data_dir,
        pricing_file=ROOT / "pricing.yaml",
        ingest_on_startup=False,
    )
    Ingestor(wide, store, pricing).run()
    assert any(row["path"] == str(copied) for row in store.list_files())

    narrow = AppConfig(
        sources=[
            SourceConfig(path=str(claude)),
            SourceConfig(path=str(codex)),
        ],
        data_dir=data_dir,
        pricing_file=ROOT / "pricing.yaml",
        ingest_on_startup=False,
    )
    stats = Ingestor(narrow, store, pricing).run()
    paths = {row["path"] for row in store.list_files()}
    assert str(copied) not in paths
    assert stats["files_removed"] >= 1
