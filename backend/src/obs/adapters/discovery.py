"""Transcript discovery that reports unreadable directories instead of skipping them."""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path


def discover_files(base: Path, pattern: str) -> list[Path]:
    def raise_error(error: OSError) -> None:
        raise error

    found = []
    for directory, _, filenames in os.walk(base, onerror=raise_error):
        for name in filenames:
            if fnmatch.fnmatchcase(name, pattern):
                path = Path(directory) / name
                if path.is_file():
                    found.append(path)
    return sorted(found)
