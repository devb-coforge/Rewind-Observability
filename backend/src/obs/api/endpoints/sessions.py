"""Sessions API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from obs.api.dependencies import state, now, bound_time
from obs.api.schemas import NoteBody, HiddenBody

router = APIRouter()


@router.get("/sessions")
def list_sessions(
    request: Request,
    agent: str | None = None,
    project: str | None = None,
    project_cwd: str | None = None,
    model: str | None = None,
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    q: str | None = None,
    sort: str = "started_at",
    cursor: str | None = None,
    limit: int = 50,
    include_hidden: bool = False,
) -> dict:
    obs = state(request)
    with obs.store.transaction():
        return obs.store.list_sessions(
            agent=agent,
            project=project,
            project_cwd=project_cwd,
            model=model,
            start=bound_time(from_, end=False),
            end=bound_time(to, end=True),
            q=q,
            sort=sort,
            cursor=cursor,
            limit=limit,
            include_hidden=include_hidden,
        )


@router.get("/sessions/{session_id}")
def get_session(session_id: str, request: Request) -> dict:
    obs = state(request)
    with obs.store.transaction():
        detail = obs.store.session_detail(session_id)
    if detail is None:
        raise HTTPException(404, "session not found")
    return detail


@router.patch("/sessions/{session_id}")
def patch_session(session_id: str, body: HiddenBody, request: Request) -> dict:
    obs = state(request)
    with obs.store.transaction():
        if obs.store.get_session(session_id) is None:
            raise HTTPException(404, "session not found")
        obs.store.set_session_hidden(session_id, body.hidden, now())
    return {"session_id": session_id, "hidden": body.hidden}


@router.get("/sessions/{session_id}/note")
def get_note(session_id: str, request: Request) -> dict:
    obs = state(request)
    with obs.store.transaction():
        note = obs.store.get_note(session_id)
    if note is None:
        return {"session_id": session_id, "text": "", "updated_at": None}
    return {"session_id": session_id, "text": note["text"], "updated_at": note["updated_at"]}


@router.put("/sessions/{session_id}/note")
def put_note(session_id: str, body: NoteBody, request: Request) -> dict:
    obs = state(request)
    with obs.store.transaction():
        obs.store.set_note(session_id, body.text, now())
        note = obs.store.get_note(session_id)
    if note is None:
        return {"session_id": session_id, "text": "", "updated_at": None}
    return {"session_id": session_id, "text": note["text"], "updated_at": note["updated_at"]}


@router.get("/sessions/{session_id}/events")
def get_events(
    session_id: str,
    request: Request,
    cursor: int | None = None,
    limit: int = 200,
    kinds: str | None = None,
) -> dict:
    obs = state(request)
    kind_list = [item for item in (kinds or "").split(",") if item] or None
    with obs.store.transaction():
        if obs.store.get_session(session_id) is None:
            raise HTTPException(404, "session not found")
        return obs.store.list_events(session_id, cursor=cursor, limit=limit, kinds=kind_list)
