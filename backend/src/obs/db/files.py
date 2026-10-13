"""Files operations."""

from __future__ import annotations

from typing import TYPE_CHECKING
import sqlite3

if TYPE_CHECKING:
    from obs.db.repo import Store


def get_file(store: Store, path: str) -> sqlite3.Row | None:
    return store.index.execute("SELECT * FROM files WHERE path = ?", (path,)).fetchone()


def upsert_file(
    store: Store,
    *,
    path: str,
    agent: str,
    size: int,
    mtime: float,
    last_offset: int,
    adapter_version: int,
    session_id: str | None,
) -> None:
    store.index.execute(
        """
        INSERT INTO files(path, agent, size, mtime, last_offset, adapter_version, session_id)
        VALUES(?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
          agent = excluded.agent,
          size = excluded.size,
          mtime = excluded.mtime,
          last_offset = excluded.last_offset,
          adapter_version = excluded.adapter_version,
          session_id = excluded.session_id
        """,
        (path, agent, size, mtime, last_offset, adapter_version, session_id),
    )


def files_under(store: Store, root: str) -> list[sqlite3.Row]:
    prefix = root.rstrip("/") + "/"
    return list(
        store.index.execute(
            "SELECT * FROM files WHERE path = ? OR path LIKE ?",
            (root, prefix + "%"),
        )
    )


def list_files(store: Store) -> list[sqlite3.Row]:
    return list(store.index.execute("SELECT * FROM files"))


def delete_file(store: Store, path: str) -> None:
    store.index.execute("DELETE FROM files WHERE path = ?", (path,))
