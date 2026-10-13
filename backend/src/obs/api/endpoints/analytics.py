"""Analytics API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from obs.analytics import queries
from obs.api.dependencies import state, build_filters

router = APIRouter()


@router.get("/analytics/summary")
def analytics_summary(
    request: Request,
    agent: str | None = None,
    project: str | None = None,
    project_cwd: str | None = None,
    model: str | None = None,
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    include_hidden: bool = False,
) -> dict:
    obs = state(request)
    filters = build_filters(agent, project, model, from_, to, include_hidden)
    filters["project_cwd"] = project_cwd
    with obs.store.transaction():
        return queries.summary(obs.store, filters)


@router.get("/analytics/timeseries")
def analytics_series(
    request: Request,
    metric: str = "sessions",
    bucket: str = "day",
    group_by: str | None = None,
    agent: str | None = None,
    project: str | None = None,
    project_cwd: str | None = None,
    model: str | None = None,
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    include_hidden: bool = False,
) -> dict:
    obs = state(request)
    filters = build_filters(agent, project, model, from_, to, include_hidden)
    filters["project_cwd"] = project_cwd
    with obs.store.transaction():
        return queries.timeseries(obs.store, filters, metric=metric, bucket=bucket, group_by=group_by)


@router.get("/analytics/tools")
def analytics_tools(
    request: Request,
    agent: str | None = None,
    project: str | None = None,
    project_cwd: str | None = None,
    model: str | None = None,
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    include_hidden: bool = False,
) -> dict:
    obs = state(request)
    filters = build_filters(agent, project, model, from_, to, include_hidden)
    filters["project_cwd"] = project_cwd
    with obs.store.transaction():
        return queries.tools(obs.store, filters)
