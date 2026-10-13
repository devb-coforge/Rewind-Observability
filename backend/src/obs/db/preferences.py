"""Preferences operations."""

from __future__ import annotations

from typing import TYPE_CHECKING
import sqlite3

if TYPE_CHECKING:
    from obs.db.repo import Store


def hidden_ids(store: Store) -> list[str]:
    return [
        row["project_id"]
        for row in store.user.execute(
            "SELECT project_id FROM project_preferences WHERE hidden = 1"
        )
    ]


def is_hidden(store: Store, project_id: str) -> bool:
    row = store.user.execute(
        "SELECT hidden FROM project_preferences WHERE project_id = ?",
        (project_id,),
    ).fetchone()
    return bool(row and row["hidden"])


def set_hidden(store: Store, project_id: str, hidden: bool, now: str) -> None:
    store.user.execute(
        """
        INSERT INTO project_preferences(project_id, hidden, updated_at)
        VALUES(?, ?, ?)
        ON CONFLICT(project_id) DO UPDATE SET hidden = excluded.hidden, updated_at = excluded.updated_at
        """,
        (project_id, 1 if hidden else 0, now),
    )


def hidden_session_ids(store: Store) -> list[str]:
    return [
        row["session_id"]
        for row in store.user.execute(
            "SELECT session_id FROM session_preferences WHERE hidden = 1"
        )
    ]


def is_session_hidden(store: Store, session_id: str) -> bool:
    row = store.user.execute(
        "SELECT hidden FROM session_preferences WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    return bool(row and row["hidden"])


def set_session_hidden(store: Store, session_id: str, hidden: bool, now: str) -> None:
    store.user.execute(
        """
        INSERT INTO session_preferences(session_id, hidden, updated_at)
        VALUES(?, ?, ?)
        ON CONFLICT(session_id) DO UPDATE SET hidden = excluded.hidden, updated_at = excluded.updated_at
        """,
        (session_id, 1 if hidden else 0, now),
    )


def get_note(store: Store, session_id: str) -> sqlite3.Row | None:
    return store.user.execute(
        "SELECT session_id, text, updated_at FROM session_notes WHERE session_id = ?",
        (session_id,),
    ).fetchone()


def set_note(store: Store, session_id: str, text: str, now: str) -> None:
    if text == "":
        store.user.execute("DELETE FROM session_notes WHERE session_id = ?", (session_id,))
        return
    store.user.execute(
        """
        INSERT INTO session_notes(session_id, text, updated_at) VALUES(?, ?, ?)
        ON CONFLICT(session_id) DO UPDATE SET text = excluded.text, updated_at = excluded.updated_at
        """,
        (session_id, text, now),
    )


def dismissal_prefixes(store: Store, project_id: str) -> list[str]:
    return [
        row["path_prefix"]
        for row in store.user.execute(
            "SELECT path_prefix FROM boundary_dismissals WHERE project_id = ?",
            (project_id,),
        )
    ]


def dismiss(store: Store, project_id: str, path_prefix: str, now: str) -> None:
    store.user.execute(
        """
        INSERT INTO boundary_dismissals(project_id, path_prefix, updated_at)
        VALUES(?, ?, ?)
        ON CONFLICT(project_id, path_prefix) DO UPDATE SET updated_at = excluded.updated_at
        """,
        (project_id, path_prefix, now),
    )


def undismiss(store: Store, project_id: str, path_prefix: str) -> None:
    store.user.execute(
        "DELETE FROM boundary_dismissals WHERE project_id = ? AND path_prefix = ?",
        (project_id, path_prefix),
    )
