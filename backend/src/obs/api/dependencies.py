"""Application state and query helpers used by endpoint modules."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import Request

from obs.config import SourceConfig
from obs.ingest.scanner import path_under_source

if TYPE_CHECKING:
    from obs.main import ObsState


def state(request: Request) -> ObsState:
    return request.app.state.obs


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def bound_time(value: str | None, *, end: bool) -> str | None:
    if not value:
        return None
    if len(value) == 10:
        return value + ("T23:59:59.999Z" if end else "T00:00:00.000Z")
    return value


def build_filters(
    agent: str | None,
    project: str | None,
    model: str | None,
    start: str | None,
    end: str | None,
    include_hidden: bool,
) -> dict:
    return {
        "agent": agent,
        "project": project,
        "model": model,
        "start": bound_time(start, end=False),
        "end": bound_time(end, end=True),
        "include_hidden": include_hidden,
    }


def allowed_source(path: Path, sources: list[SourceConfig]) -> bool:
    return any(path_under_source(path, source) for source in sources)
