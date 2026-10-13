from pathlib import Path

from obs.adapters.codex import CodexAdapter
from obs.adapters.interface import MetadataSnapshot
from obs.analytics.pricing import Pricing
from obs.config import AppConfig, SourceConfig
from obs.db.repo import Store
from obs.ingest.pipeline import Ingestor


def test_supplementary_metadata_is_polymorphic_and_failed_reads_preserve_it(
    source_dirs, tmp_path, monkeypatch
):
    """Metadata behavior depends on adapter capabilities, not its agent name."""
    _, codex = source_dirs
    source = SourceConfig(path=str(codex))

    class MetadataAdapter(CodexAdapter):
        snapshot = MetadataSnapshot(
            titles={"codex-sess-1": "Imported title"},
            entries={
                "codex-sess-1": {
                    "duration_sec": 42.0,
                    "models": ["saved-model"],
                    "selected_model": "saved-model",
                }
            },
        )

        def read_metadata(self, root: Path, user_data_dir: Path | None = None):
            return self.snapshot

    adapter = MetadataAdapter()
    monkeypatch.setattr("obs.ingest.pipeline.resolve_sources", lambda sources: [(source, adapter)])
    config = AppConfig(sources=[source], data_dir=tmp_path / "data", ingest_on_startup=False)
    pricing = Pricing.load(Path(__file__).with_name("pricing.yaml"))
    store = Store(config.data_dir)
    try:
        ingestor = Ingestor(config, store, pricing)
        ingestor.run()
        initial = store.session_detail("codex:codex-sess-1")
        assert initial["title"] == "Imported title"
        assert initial["duration_sec"] == 42.0
        assert "saved-model" in initial["models"]
        assert initial["selected_model"] == "saved-model"

        adapter.snapshot = None
        assert ingestor.run()["files_parsed"] == 0
        assert store.session_detail("codex:codex-sess-1") == initial

        adapter.snapshot = MetadataSnapshot(titles={}, entries={})
        assert ingestor.run()["files_parsed"] == 0
        refreshed = store.session_detail("codex:codex-sess-1")
        assert store.get_session("codex:codex-sess-1")["source_title"] is None
        assert refreshed["title"] != "Imported title"
        assert refreshed["duration_sec"] != 42.0
        assert "saved-model" not in refreshed["models"]
        assert refreshed["selected_model"] is None
        assert refreshed["n_events"] == initial["n_events"]
    finally:
        store.close()
