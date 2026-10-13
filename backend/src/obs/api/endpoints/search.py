"""Search API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request

from obs.analytics import queries
from obs.api.dependencies import state

router = APIRouter()


@router.get("/search")
def search(
    request: Request,
    q: str = "",
    agent: str | None = None,
    project: str | None = None,
    include_hidden: bool = False,
    limit: int = 50,
) -> dict:
    obs = state(request)
    with obs.store.transaction():
        return {
            "hits": queries.search(
                obs.store,
                q=q,
                agent=agent,
                project=project,
                include_hidden=include_hidden,
                limit=limit,
            )
        }


@router.get("/search/failures")
def search_failures(
    request: Request,
    agent: str | None = None,
    project: str | None = None,
    tool: str | None = None,
    q: str | None = None,
    include_hidden: bool = False,
    limit: int = 50,
) -> dict:
    obs = state(request)
    with obs.store.transaction():
        return queries.failed_tools(
            obs.store,
            agent=agent,
            project=project,
            tool=tool,
            q=q,
            include_hidden=include_hidden,
            limit=limit,
        )


@router.get("/search/declined")
def search_declined(
    request: Request,
    agent: str | None = None,
    project: str | None = None,
    tool: str | None = None,
    q: str | None = None,
    include_hidden: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    obs = state(request)
    with obs.store.transaction():
        return queries.failed_tools(
            obs.store, agent=agent, project=project, tool=tool, q=q,
            include_hidden=include_hidden, limit=limit, declined=True, offset=max(0, offset),
        )
