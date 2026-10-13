"""Boundaries operations."""

from __future__ import annotations

from typing import TYPE_CHECKING
import json

from obs.identity import path_is_allowed

if TYPE_CHECKING:
    from obs.db.repo import Store


def refresh_boundary(store: Store, project_id: str | None, allow_prefixes: list[str]) -> None:
    if project_id:
        sessions = list(
            store.index.execute("SELECT id, project_id FROM sessions WHERE project_id = ?", (project_id,))
        )
    else:
        sessions = list(store.index.execute("SELECT id, project_id FROM sessions"))
    for session in sessions:
        dismissals = store.dismissal_prefixes(session["project_id"])
        store.recompute_boundary_only(session["id"], allow_prefixes, dismissals)


def recompute_boundary_only(store: Store, session_id: str, allow_prefixes: list[str], dismissals: list[str]) -> None:
    prefixes = list(allow_prefixes) + list(dismissals)
    rows = list(
        store.index.execute(
            "SELECT paths_json FROM events WHERE session_id = ?",
            (session_id,),
        )
    )
    boundary = 0
    for row in rows:
        paths = json.loads(row["paths_json"] or "[]")
        if any(
            item.get("outside") and not path_is_allowed(item.get("resolved") or "", prefixes)
            for item in paths
        ):
            boundary += 1
    store.index.execute(
        "UPDATE sessions SET boundary_count = ? WHERE id = ?",
        (boundary, session_id),
    )
