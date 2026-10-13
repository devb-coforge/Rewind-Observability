"""Structural contract for interchangeable transcript adapters."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from obs.models import AgentName, ParseResult


@dataclass
class MetadataSnapshot:
    """Imported titles and optional supplementary session metadata.

    A missing snapshot means reading failed: preserve previously imported data.
    An empty successful snapshot lets ingestion clear stale titles.
    ``entries=None`` means supplementary metadata is unavailable for this source.
    """

    titles: Mapping[str, str | None]
    entries: dict[str, dict] | None = None


@runtime_checkable
class Adapter(Protocol):
    name: AgentName
    version: int

    def detect(self, root: Path) -> bool: ...

    def discover(self, root: Path) -> list[Path]: ...

    def native_id_from_path(self, path: Path) -> str | None: ...

    def parent_native_id(self, path: Path) -> str | None: ...

    def parse(self, path: Path, start_offset: int) -> ParseResult: ...

    def read_metadata(
        self, root: Path, user_data_dir: Path | None = None
    ) -> MetadataSnapshot | None: ...
