from __future__ import annotations

from pathlib import Path
from typing import Iterable, Protocol

from obs.models import ParseResult


class Adapter(Protocol):
    name: str
    version: int

    def detect(self, root: Path) -> bool: ...

    def discover(self, root: Path) -> Iterable[Path]: ...

    def parse(self, path: Path, start_offset: int) -> ParseResult: ...

    def native_id_from_path(self, path: Path) -> str | None: ...

    def parent_native_id(self, path: Path) -> str | None: ...
