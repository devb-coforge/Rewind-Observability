from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from obs.analytics.pricing import Pricing
from obs.api.routes import router
from obs.config import AppConfig, load_config
from obs.db.repo import Store
from obs.export_run import export_pending
from obs.ingest.pipeline import Ingestor

log = logging.getLogger("obs")

HELLO = """<!doctype html>
<html lang="en">
<meta charset="utf-8">
<title>Obs</title>
<body style="font-family: ui-sans-serif, system-ui; margin: 3rem; background: #14160f; color: #f3efe4">
  <h1>Obs</h1>
  <p>The transcript index is up. The web UI has not been built into this image yet.</p>
  <p><a style="color:#e2b340" href="/api/health">/api/health</a></p>
</body>
</html>
"""


@dataclass
class ObsState:
    config: AppConfig
    store: Store
    pricing: Pricing
    sender: object | None = None


def create_app(config: AppConfig | None = None, *, sender=None) -> FastAPI:
    settings = config or load_config()
    store = Store(settings.data_dir)
    pricing = Pricing.load(settings.pricing_file) if settings.pricing_file else Pricing.openrouter(settings.data_dir)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        from starlette.concurrency import run_in_threadpool

        await run_in_threadpool(pricing.refresh)
        if settings.ingest_on_startup and settings.sources:
            try:
                Ingestor(settings, store, pricing).run(full=False)
                export_pending(settings, store, sender=sender)
            except Exception:
                log.exception("startup ingest failed")
        yield
        store.close()

    app = FastAPI(title="Obs", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.obs = ObsState(config=settings, store=store, pricing=pricing, sender=sender)
    app.include_router(router)

    static = settings.static_dir
    if static and (static / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        if full_path.startswith("api/") or full_path == "api":
            return HTMLResponse("not found", status_code=404)
        if static:
            candidate = (static / full_path).resolve() if full_path else static / "index.html"
            try:
                candidate.relative_to(static.resolve())
            except ValueError:
                candidate = static / "index.html"
            if candidate.is_file():
                return FileResponse(candidate)
            index = static / "index.html"
            if index.is_file():
                return FileResponse(index)
        return HTMLResponse(HELLO)

    return app


def app() -> FastAPI:
    return create_app()
