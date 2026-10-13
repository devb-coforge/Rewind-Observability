"""Decode normalized token usage stored with events."""

from __future__ import annotations

import json

from obs.models import Usage


def load_usage(raw: str | None) -> Usage | None:
    if not raw:
        return None
    data = json.loads(raw)
    usage = Usage(
        input_tokens=data.get("input_tokens"),
        output_tokens=data.get("output_tokens"),
        cache_read_tokens=data.get("cache_read_tokens"),
        cache_write_tokens=data.get("cache_write_tokens"),
    )
    return usage if usage.known() else None
