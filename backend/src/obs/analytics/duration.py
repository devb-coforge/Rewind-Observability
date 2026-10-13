"""Duration calculations for recorded session timestamps."""

from __future__ import annotations

def duration_seconds(start: str | None, end: str | None) -> float | None:
    if not start or not end:
        return None
    from datetime import datetime

    def parse(value: str) -> datetime:
        text = value[:-1] + "+00:00" if value.endswith("Z") else value
        return datetime.fromisoformat(text)

    return (parse(end) - parse(start)).total_seconds()
