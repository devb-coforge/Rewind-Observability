from __future__ import annotations

from pathlib import Path

from obs.adapters import ADAPTERS, adapter_by_name
from obs.config import SourceConfig


def resolve_sources(sources: list[SourceConfig]) -> list[tuple[SourceConfig, object | None]]:
    resolved: list[tuple[SourceConfig, object | None]] = []
    for source in sources:
        root = Path(source.path)
        if source.agent:
            try:
                adapter = adapter_by_name(source.agent)
            except KeyError:
                adapter = None
        elif root.exists():
            adapter = next((item for item in ADAPTERS if item.detect(root)), None)
        else:
            adapter = None
        resolved.append((source, adapter))
    return resolved
