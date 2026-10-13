"""Events API endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from obs.api.dependencies import state, allowed_source

router = APIRouter()


@router.get("/events/{event_id}/output")
def event_output(event_id: str, request: Request) -> dict:
    obs = state(request)
    with obs.store.transaction():
        event = obs.store.get_event(event_id)
        if event is None:
            raise HTTPException(404, "event not found")
        return {"event_id": event_id, "output": obs.store.get_output(event_id)}


@router.get("/events/{event_id}/raw", response_class=PlainTextResponse)
def event_raw(event_id: str, request: Request) -> PlainTextResponse:
    obs = state(request)
    with obs.store.transaction():
        event = obs.store.get_event(event_id)
    if event is None:
        raise HTTPException(404, "event not found")
    path = Path(event["raw_path"])
    if not allowed_source(path, obs.config.sources):
        raise HTTPException(404, "source file is not in a configured root")
    if not path.is_file():
        raise HTTPException(404, "source file is missing")
    with obs.store.transaction():
        saved = obs.store.index.execute(
            "SELECT content FROM event_raw WHERE event_id = ?", (event_id,)
        ).fetchone()
    if saved is not None:
        return PlainTextResponse(saved["content"])
    data = path.read_bytes()
    start = int(event["raw_offset"])
    length = int(event["raw_length"])
    return PlainTextResponse(data[start : start + length].decode("utf-8", errors="replace"))
