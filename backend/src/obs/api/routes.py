from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from obs.benchmark import delete_case, freeze_case, get_case, list_cases, summarize, update_case
from obs.analytics import queries
from obs.export_run import export_pending
from obs.ingest.pipeline import Ingestor
from obs.ingest.scanner import path_under_source, resolve_agent, resolve_sources, source_root

router = APIRouter(prefix="/api")


def state(request: Request):
    return request.app.state.obs


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def bound_time(value: str | None, *, end: bool) -> str | None:
    if not value:
        return None
    if len(value) == 10:
        return value + ("T23:59:59.999Z" if end else "T00:00:00.000Z")
    return value


class NoteBody(BaseModel):
    text: str = ""


class HiddenBody(BaseModel):
    hidden: bool


class DismissalBody(BaseModel):
    project_id: str
    path_prefix: str


class FreezeBody(BaseModel):
    session_id: str
    from_seq: int | None = None
    to_seq: int | None = None


class CasePatch(BaseModel):
    verdict: str | None = None
    note: str | None = None


class Ok(BaseModel):
    status: str = "ok"


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/sources")
def sources(request: Request) -> dict:
    obs = state(request)
    with obs.store.transaction():
        items = []
        for source, adapter in resolve_sources(obs.config.sources):
            root = source_root(source)
            files = obs.store.files_under(str(root.resolve())) if root.exists() else []
            session_ids = {row["session_id"] for row in files if row["session_id"]}
            items.append(
                {
                    "path": source.path,
                    "agent": adapter.name if adapter else resolve_agent(source),
                    "detected": adapter is not None and root.exists(),
                    "exists": root.exists(),
                    "files": len(files),
                    "sessions": len(session_ids),
                }
            )
        return {
            "sources": items,
            "last_indexed_at": obs.store.get_meta("last_indexed_at"),
            "otel": {
                "enabled": bool(obs.config.otel.endpoint),
                "endpoint": obs.config.otel.endpoint,
                "include_content": obs.config.otel.include_content,
                "protocol": obs.config.otel.protocol,
                "last_error": obs.store.get_meta("otel_last_error"),
            },
        }


@router.post("/reindex")
def reindex(request: Request, full: bool = False) -> dict:
    obs = state(request)
    stats = Ingestor(obs.config, obs.store, obs.pricing).run(full=full)
    export = export_pending(obs.config, obs.store, sender=obs.sender)
    stats["export"] = export
    return stats


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


@router.get("/sessions")
def list_sessions(
    request: Request,
    agent: str | None = None,
    project: str | None = None,
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
    if not _allowed_source(path, obs.config.sources):
        raise HTTPException(404, "source file is not in a configured root")
    if not path.is_file():
        raise HTTPException(404, "source file is missing")
    data = path.read_bytes()
    start = int(event["raw_offset"])
    length = int(event["raw_length"])
    return PlainTextResponse(data[start : start + length].decode("utf-8", errors="replace"))


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


@router.get("/analytics/summary")
def analytics_summary(
    request: Request,
    agent: str | None = None,
    project: str | None = None,
    model: str | None = None,
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    include_hidden: bool = False,
) -> dict:
    obs = state(request)
    filters = _filters(agent, project, model, from_, to, include_hidden)
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
    model: str | None = None,
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    include_hidden: bool = False,
) -> dict:
    obs = state(request)
    filters = _filters(agent, project, model, from_, to, include_hidden)
    with obs.store.transaction():
        return queries.timeseries(obs.store, filters, metric=metric, bucket=bucket, group_by=group_by)


@router.get("/analytics/tools")
def analytics_tools(
    request: Request,
    agent: str | None = None,
    project: str | None = None,
    model: str | None = None,
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    include_hidden: bool = False,
) -> dict:
    obs = state(request)
    filters = _filters(agent, project, model, from_, to, include_hidden)
    with obs.store.transaction():
        return queries.tools(obs.store, filters)


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
            dismissed = _prefix_hit(item.get("resolved") or "", dismissals)
            config_ok = _prefix_hit(item.get("resolved") or "", allows)
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


@router.post("/benchmark/cases")
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


@router.get("/benchmark/cases")
def get_cases(
    request: Request,
    project: str | None = None,
    model: str | None = None,
    verdict: str | None = None,
) -> dict:
    obs = state(request)
    with obs.store.transaction():
        return {"cases": list_cases(obs.store, project=project, model=model, verdict=verdict)}


@router.get("/benchmark/cases/{case_id}")
def get_one_case(case_id: str, request: Request) -> dict:
    obs = state(request)
    with obs.store.transaction():
        case = get_case(obs.store, case_id)
    if case is None:
        raise HTTPException(404, "case not found")
    return case


@router.patch("/benchmark/cases/{case_id}")
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


@router.delete("/benchmark/cases/{case_id}")
def remove_case(case_id: str, request: Request) -> dict:
    obs = state(request)
    with obs.store.transaction():
        deleted = delete_case(obs.store, case_id)
    if not deleted:
        raise HTTPException(404, "case not found")
    return {"deleted": case_id}


@router.get("/benchmark/summary")
def benchmark_summary(request: Request, project: str | None = None, group_by: str = "model") -> dict:
    del group_by
    obs = state(request)
    with obs.store.transaction():
        return summarize(obs.store, project=project)


def _filters(agent, project, model, start, end, include_hidden) -> dict:
    return {
        "agent": agent,
        "project": project,
        "model": model,
        "start": bound_time(start, end=False),
        "end": bound_time(end, end=True),
        "include_hidden": include_hidden,
    }


def _allowed_source(path: Path, sources) -> bool:
    return any(path_under_source(path, source) for source in sources)


def _prefix_hit(path: str, prefixes: list[str]) -> bool:
    from obs.identity import path_is_allowed

    return path_is_allowed(path, prefixes)
