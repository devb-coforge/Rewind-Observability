"""System API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from obs.api.dependencies import state
from obs.export_run import export_pending
from obs.ingest.pipeline import Ingestor, SourceAccessError
from obs.ingest.scanner import resolve_agent, resolve_sources, source_root

router = APIRouter()


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
    try:
        stats = Ingestor(obs.config, obs.store, obs.pricing).run(full=full)
    except SourceAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    export = export_pending(obs.config, obs.store, sender=obs.sender)
    stats["export"] = export
    return stats
