"""Shared JSONL helpers for transcript adapters."""

from __future__ import annotations

import json
from datetime import datetime, timezone


def complete_lines(data: bytes, start: int) -> tuple[list[tuple[int, int, bytes]], int]:
    """Return full lines as (offset, length including newline, payload) and the consumed end.

    A trailing partial line is left unconsumed so a later append can finish it.
    """
    if start < 0:
        start = 0
    if start > len(data):
        start = 0
    if start == len(data):
        return [], start
    last_nl = data.rfind(b"\n", start)
    if last_nl == -1:
        return [], start
    consumed_end = last_nl + 1
    lines: list[tuple[int, int, bytes]] = []
    index = start
    while index < consumed_end:
        newline = data.find(b"\n", index, consumed_end)
        if newline == -1:
            break
        payload = data[index:newline]
        if payload.endswith(b"\r"):
            payload = payload[:-1]
        lines.append((index, newline + 1 - index, payload))
        index = newline + 1
    return lines, consumed_end


def parse_ts(value) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        seconds = float(value)
        if seconds > 10_000_000_000:
            seconds = seconds / 1000
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    value = value.astimezone(timezone.utc)
    return value.strftime("%Y-%m-%dT%H:%M:%S.") + f"{value.microsecond // 1000:03d}Z"


def loads_obj(payload: bytes) -> tuple[dict | None, bool]:
    text = payload.decode("utf-8", errors="replace").strip()
    if not text:
        return None, True
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return None, False
    if isinstance(obj, dict):
        return obj, True
    return None, False


def stringify(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(stringify(item) for item in value)
    if isinstance(value, dict):
        if isinstance(value.get("text"), str):
            return value["text"]
        if "content" in value:
            return stringify(value["content"])
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def preview(value: str | None, limit: int = 500) -> str | None:
    if value is None:
        return None
    cleaned = value.replace("\x00", "")
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit]


def int_or_none(value) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None
