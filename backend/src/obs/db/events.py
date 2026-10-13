"""Events operations."""

from __future__ import annotations

from typing import TYPE_CHECKING
import sqlite3

from obs.tool_outcomes import user_declined

if TYPE_CHECKING:
    from obs.db.repo import Store


def delete_events_for_path(store: Store, path: str) -> list[str]:
    rows = list(
        store.index.execute("SELECT rowid, id, session_id FROM events WHERE raw_path = ?", (path,))
    )
    sessions = []
    for row in rows:
        store.index.execute("DELETE FROM events_fts WHERE rowid = ?", (row["rowid"],))
        store.index.execute("DELETE FROM event_blobs WHERE event_id = ?", (row["id"],))
        store.index.execute("DELETE FROM event_raw WHERE event_id = ?", (row["id"],))
        sessions.append(row["session_id"])
    store.index.execute("DELETE FROM events WHERE raw_path = ?", (path,))
    return sessions


def event_exists(store: Store, event_id: str) -> bool:
    row = store.index.execute("SELECT 1 FROM events WHERE id = ?", (event_id,)).fetchone()
    return row is not None


def insert_event(store: Store, event: dict) -> bool:
    declined = event.get("is_declined", False) or (event["kind"] == "tool_result" and user_declined(event.get("tool_output") or event.get("text")))
    cur = store.index.execute(
        """
        INSERT OR IGNORE INTO events(
          id, session_id, parent_id, seq, ts, role, kind, text, tool_name, tool_call_id,
          tool_input_json, tool_output_preview, is_error, is_declined, model, usage_json, usage_origin,
          message_id, raw_path, raw_offset, raw_length, paths_json, block_index
        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event["id"],
            event["session_id"],
            event.get("parent_id"),
            event.get("seq", 0),
            event.get("ts"),
            event["role"],
            event["kind"],
            event.get("text"),
            event.get("tool_name"),
            event.get("tool_call_id"),
            event.get("tool_input_json"),
            event.get("tool_output_preview"),
            1 if event.get("is_error") and not declined else 0,
            1 if declined else 0,
            event.get("model"),
            event.get("usage_json"),
            event.get("usage_origin"),
            event.get("message_id"),
            event["raw_path"],
            event["raw_offset"],
            event["raw_length"],
            event.get("paths_json"),
            event.get("block_index", 0),
        ),
    )
    if cur.rowcount == 0:
        return False
    rowid = cur.lastrowid
    store.index.execute(
        """
        INSERT INTO events_fts(rowid, event_id, session_id, text, tool_name, preview)
        VALUES(?, ?, ?, ?, ?, ?)
        """,
        (
            rowid,
            event["id"],
            event["session_id"],
            event.get("text") or "",
            event.get("tool_name") or "",
            event.get("fts_preview") or "",
        ),
    )
    if event.get("tool_output"):
        store.index.execute(
            "INSERT OR REPLACE INTO event_blobs(event_id, tool_output) VALUES(?, ?)",
            (event["id"], event["tool_output"]),
        )
    return True


def list_events(store: Store, session_id: str, *, cursor: int | None, limit: int, kinds: list[str] | None) -> dict:
    clauses = ["session_id = ?"]
    params: list = [session_id]
    if cursor is not None:
        clauses.append("seq > ?")
        params.append(cursor)
    if kinds:
        clauses.append(f"kind IN ({','.join('?' for _ in kinds)})")
        params.extend(kinds)
    limit = min(limit, 500)
    rows = list(
        store.index.execute(
            f"""
            SELECT * FROM events
            WHERE {' AND '.join(clauses)}
            ORDER BY seq
            LIMIT ?
            """,
            [*params, limit],
        )
    )
    session = store.get_session(session_id)
    dismissals = store.dismissal_prefixes(session["project_id"]) if session else []
    next_cursor = rows[-1]["seq"] if len(rows) == limit else None
    return {
        "events": [store.event_dict(row, dismissals) for row in rows],
        "next_cursor": next_cursor,
    }


def get_event(store: Store, event_id: str) -> sqlite3.Row | None:
    return store.index.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()


def get_output(store: Store, event_id: str) -> str | None:
    row = store.index.execute(
        "SELECT tool_output FROM event_blobs WHERE event_id = ?",
        (event_id,),
    ).fetchone()
    if row is not None:
        return row["tool_output"]
    event = store.get_event(event_id)
    if event is None:
        return None
    return event["tool_output_preview"]


def events_for_session(store: Store, session_id: str) -> list[sqlite3.Row]:
    return list(
        store.index.execute(
            "SELECT * FROM events WHERE session_id = ? ORDER BY seq",
            (session_id,),
        )
    )
