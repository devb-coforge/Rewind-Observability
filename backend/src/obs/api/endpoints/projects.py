"""Projects API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from obs.api.dependencies import state, now
from obs.api.schemas import HiddenBody, ProjectNameBody

router = APIRouter()


@router.get("/projects")
def projects(request: Request, include_hidden: bool = False) -> dict:
    obs = state(request)
    with obs.store.transaction():
        return {"projects": obs.store.list_projects(include_hidden)}


@router.patch("/projects/{project_id}")
def patch_project(project_id: str, body: HiddenBody, request: Request) -> dict:
    obs = state(request)
    with obs.store.transaction():
        obs.store.set_hidden(project_id, body.hidden, now())
        obs.store.refresh_boundary(project_id, obs.config.boundary.allow_prefixes)
    return {"project_id": project_id, "hidden": body.hidden}


@router.put("/projects/{project_id}/name")
def rename_project(project_id: str, body: ProjectNameBody, request: Request) -> dict:
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Project name cannot be blank")
    obs = state(request)
    with obs.store.transaction():
        if not obs.store.rename_project(project_id, name, now()):
            raise HTTPException(status_code=404, detail="Project not found")
    return {"project_id": project_id, "name": name}
