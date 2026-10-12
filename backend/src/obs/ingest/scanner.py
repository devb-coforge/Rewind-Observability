from __future__ import annotations

from pathlib import Path

from obs.adapters import adapter_by_name
from obs.adapters.detect import infer_agent_from_path
from obs.config import SourceConfig


def source_root(source: SourceConfig) -> Path:
    return Path(source.path).expanduser()


def resolve_agent(source: SourceConfig) -> str | None:
    return infer_agent_from_path(source_root(source))


def resolve_sources(sources: list[SourceConfig]) -> list[tuple[SourceConfig, object | None]]:
    resolved: list[tuple[SourceConfig, object | None]] = []
    for source in sources:
        kind = resolve_agent(source)
        try:
            adapter = adapter_by_name(kind) if kind else None
        except KeyError:
            adapter = None
        resolved.append((source, adapter))
    return resolved


def path_under_source(path: str | Path, source: SourceConfig) -> bool:
    root = source_root(source).resolve()
    try:
        Path(path).expanduser().resolve().relative_to(root)
        return True
    except ValueError:
        return Path(path).expanduser().resolve() == root


def configured_source_roots(sources: list[SourceConfig]) -> list[Path]:
    return [source_root(source).resolve() for source in sources]
