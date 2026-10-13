"""Evals API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from obs.api.dependencies import state
from obs.api.schemas import FreezeBody, CasePatch
from obs.evals import delete_case, freeze_case, get_case, list_cases, summarize, update_case

router = APIRouter()


@router.post("/evals/cases")
def post_case(body: FreezeBody, request: Request) -> dict:
    obs = state(request)
    with obs.store.transaction():
        try:
            return freeze_case(
                obs.store,
                obs.pricing,
                session_id=body.session_id,
                from_seq=body.from_seq,
                to_seq=body.to_seq,
            )
        except KeyError:
            raise HTTPException(404, "session not found") from None


@router.get("/evals/cases")
def get_cases(
    request: Request,
    project: str | None = None,
    project_cwd: str | None = None,
    model: str | None = None,
    verdict: str | None = None,
) -> dict:
    obs = state(request)
    with obs.store.transaction():
        return {"cases": list_cases(obs.store, project=project, project_cwd=project_cwd, model=model, verdict=verdict)}


@router.get("/evals/cases/{case_id}")
def get_one_case(case_id: str, request: Request) -> dict:
    obs = state(request)
    with obs.store.transaction():
        case = get_case(obs.store, case_id)
    if case is None:
        raise HTTPException(404, "case not found")
    return case


@router.patch("/evals/cases/{case_id}")
def patch_case(case_id: str, body: CasePatch, request: Request) -> dict:
    obs = state(request)
    with obs.store.transaction():
        try:
            case = update_case(obs.store, case_id, verdict=body.verdict, note=body.note)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
    if case is None:
        raise HTTPException(404, "case not found")
    return case


@router.delete("/evals/cases/{case_id}")
def remove_case(case_id: str, request: Request) -> dict:
    obs = state(request)
    with obs.store.transaction():
        deleted = delete_case(obs.store, case_id)
    if not deleted:
        raise HTTPException(404, "case not found")
    return {"deleted": case_id}


@router.get("/evals/summary")
def evals_summary(
    request: Request, project: str | None = None, group_by: str = "model",
    project_cwd: str | None = None,
) -> dict:
    del group_by
    obs = state(request)
    with obs.store.transaction():
        return summarize(obs.store, project=project, project_cwd=project_cwd)
