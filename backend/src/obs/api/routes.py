"""Assemble the feature routers under the public API prefix."""

from fastapi import APIRouter

from obs.api.endpoints import analytics, boundary, evals, events, projects, search, sessions, system

router = APIRouter(prefix="/api")

router.include_router(system.router)
router.include_router(projects.router)
router.include_router(sessions.router)
router.include_router(events.router)
router.include_router(search.router)
router.include_router(analytics.router)
router.include_router(boundary.router)
router.include_router(evals.router)
