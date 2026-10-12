"""Run OpenTelemetry export after a successful ingest. Export failure does not undo ingest."""

from __future__ import annotations

import logging

from obs.config import AppConfig
from obs.db.repo import Store
from obs.identity import path_is_allowed
from obs.otel_export import ExportError, deliver, export_payload

log = logging.getLogger("obs.export")


def export_pending(config: AppConfig, store: Store, sender=None) -> dict:
    if not config.otel.endpoint:
        return {"exported": 0, "skipped": True}
    with store.transaction():
        pending = _pending_ids(store)
        bundles = []
        for session_id in pending:
            detail = store.session_detail(session_id)
            if detail is None:
                continue
            events = store.list_events(session_id, cursor=None, limit=100000, kinds=None)["events"]
            _apply_config_allows(events, config.boundary.allow_prefixes)
            bundles.append((detail, events))
        try:
            encoded = export_payload(
                bundles,
                include_content=config.otel.include_content,
                protocol=config.otel.protocol,
            )
            if encoded is None:
                _mark_success(store, pending)
                store.set_meta("otel_last_error", None)
                return {"exported": 0, "skipped": False}
            payload, content_type = encoded
            deliver(config.otel.endpoint, payload, content_type, sender=sender)
        except Exception as exc:
            message = str(exc)
            log.warning("otel export failed: %s", message)
            store.set_meta("otel_last_error", message)
            _mark_failure(store, pending, message)
            return {"exported": 0, "error": message}
        _mark_success(store, pending)
        store.set_meta("otel_last_error", None)
        return {"exported": len(pending), "skipped": False}


def _pending_ids(store: Store) -> list[str]:
    rows = store.index.execute("SELECT id FROM sessions").fetchall()
    pending = []
    for row in rows:
        state = store.index.execute(
            "SELECT last_seq, last_error FROM export_state WHERE session_id = ?",
            (row["id"],),
        ).fetchone()
        max_seq = store.index.execute(
            "SELECT COALESCE(MAX(seq), -1) AS m FROM events WHERE session_id = ?",
            (row["id"],),
        ).fetchone()["m"]
        if state is None or state["last_error"] or state["last_seq"] < max_seq:
            pending.append(row["id"])
    return pending


def _mark_success(store: Store, session_ids: list[str]) -> None:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    for session_id in session_ids:
        max_seq = store.index.execute(
            "SELECT COALESCE(MAX(seq), -1) AS m FROM events WHERE session_id = ?",
            (session_id,),
        ).fetchone()["m"]
        store.index.execute(
            """
            INSERT INTO export_state(session_id, last_seq, last_error, updated_at)
            VALUES(?, ?, NULL, ?)
            ON CONFLICT(session_id) DO UPDATE SET
              last_seq = excluded.last_seq,
              last_error = NULL,
              updated_at = excluded.updated_at
            """,
            (session_id, max_seq, now),
        )


def _mark_failure(store: Store, session_ids: list[str], message: str) -> None:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    for session_id in session_ids:
        store.index.execute(
            """
            INSERT INTO export_state(session_id, last_seq, last_error, updated_at)
            VALUES(?, -1, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
              last_error = excluded.last_error,
              updated_at = excluded.updated_at
            """,
            (session_id, message, now),
        )


def _apply_config_allows(events: list[dict], prefixes: list[str]) -> None:
    for event in events:
        for item in event.get("paths") or []:
            if item.get("outside") and path_is_allowed(item.get("resolved") or "", prefixes):
                item["dismissed"] = True
