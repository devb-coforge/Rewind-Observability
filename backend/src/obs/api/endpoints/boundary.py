"""Boundary API endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query, Request

from obs.api.dependencies import state, now, bound_time
from obs.api.schemas import DismissalBody
from obs.identity import path_is_allowed

router = APIRouter()


@router.get("/boundary")
def boundary_sessions(
    request: Request,
    project: str | None = None,
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    include_hidden: bool = False,
) -> dict:
    obs = state(request)
    with obs.store.transaction():
        listed = obs.store.list_sessions(
            project=project,
            start=bound_time(from_, end=False),
            end=bound_time(to, end=True),
            include_hidden=include_hidden,
            boundary_only=True,
            limit=200,
            sort="started_at",
        )
    return {
        "sessions": [
            {
                "session_id": item["id"],
                "title": item["title"],
                "project_id": item["project_id"],
                "project_name": item["project_name"],
                "count": item["boundary_count"],
                "started_at": item["started_at"],
                "agent": item["agent"],
            }
            for item in listed["sessions"]
        ]
    }


@router.get("/sessions/{session_id}/boundary")
def session_boundary(session_id: str, request: Request) -> dict:
    obs = state(request)
    with obs.store.transaction():
        session = obs.store.get_session(session_id)
        if session is None:
            raise HTTPException(404, "session not found")
        dismissals = obs.store.dismissal_prefixes(session["project_id"])
        events = obs.store.events_for_session(session_id)
    paths = []
    alerts = 0
    allows = obs.config.boundary.allow_prefixes
    for event in events:
        for item in json.loads(event["paths_json"] or "[]"):
            if not item.get("outside"):
                continue
            dismissed = path_is_allowed(item.get("resolved") or "", dismissals)
            config_ok = path_is_allowed(item.get("resolved") or "", allows)
            if not dismissed and not config_ok:
                alerts += 1
            paths.append(
                {
                    "path": item.get("path"),
                    "resolved": item.get("resolved"),
                    "kind": item.get("kind"),
                    "event_id": event["id"],
                    "dismissed": dismissed,
                    "allowed": dismissed or config_ok,
                }
            )
    return {"paths": paths, "count": alerts}


@router.put("/boundary/dismissals")
def put_dismissal(body: DismissalBody, request: Request) -> dict:
    obs = state(request)
    with obs.store.transaction():
        obs.store.dismiss(body.project_id, body.path_prefix, now())
        obs.store.refresh_boundary(body.project_id, obs.config.boundary.allow_prefixes)
    return {"project_id": body.project_id, "path_prefix": body.path_prefix}


@router.delete("/boundary/dismissals")
def delete_dismissal(request: Request, project_id: str, path_prefix: str) -> dict:
    obs = state(request)
    with obs.store.transaction():
        obs.store.undismiss(project_id, path_prefix)
        obs.store.refresh_boundary(project_id, obs.config.boundary.allow_prefixes)
    return {"project_id": project_id, "path_prefix": path_prefix}
