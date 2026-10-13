"""Sessions operations."""

from __future__ import annotations

from typing import TYPE_CHECKING
import sqlite3

from obs.db.sql import escape_like, sort_clause
from obs.gitroot import git_worktree_root

if TYPE_CHECKING:
    from obs.db.repo import Store


def get_session(store: Store, session_id: str) -> sqlite3.Row | None:
    return store.index.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()


def ensure_session(store: Store, fields: dict) -> None:
    fields = dict(fields)
    cwd = fields.get("project_cwd")
    key = store.project_name_key(git_worktree_root(cwd) or cwd, fields["project_id"])
    custom = store.user.execute("SELECT project_name FROM project_names WHERE project_key = ?", (key,)).fetchone()
    if custom:
        fields["project_name"] = custom["project_name"]
    store.index.execute(
        """
        INSERT INTO sessions(
          id, agent, native_id, source_path, project_cwd, project_name, project_id,
          git_branch, parent_session_id, started_at, ended_at, title, models_json
        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]')
        ON CONFLICT(id) DO UPDATE SET
          source_path = excluded.source_path,
          project_cwd = COALESCE(excluded.project_cwd, sessions.project_cwd),
          project_name = COALESCE(excluded.project_name, sessions.project_name),
          project_id = CASE
            WHEN excluded.project_cwd IS NOT NULL THEN excluded.project_id
            ELSE sessions.project_id
          END,
          git_branch = COALESCE(excluded.git_branch, sessions.git_branch),
          parent_session_id = COALESCE(sessions.parent_session_id, excluded.parent_session_id),
          started_at = CASE
            WHEN sessions.started_at IS NULL OR (
              excluded.started_at IS NOT NULL AND excluded.started_at < sessions.started_at
            ) THEN excluded.started_at
            ELSE sessions.started_at
          END,
          ended_at = CASE
            WHEN excluded.ended_at IS NOT NULL AND (
              sessions.ended_at IS NULL OR excluded.ended_at > sessions.ended_at
            ) THEN excluded.ended_at
            ELSE sessions.ended_at
          END
        """,
        (
            fields["id"],
            fields["agent"],
            fields["native_id"],
            fields["source_path"],
            fields.get("project_cwd"),
            fields.get("project_name"),
            fields["project_id"],
            fields.get("git_branch"),
            fields.get("parent_session_id"),
            fields.get("started_at"),
            fields.get("ended_at"),
            fields.get("title"),
        ),
    )


def resequence(store: Store, session_id: str) -> None:
    rows = list(
        store.index.execute(
            """
            SELECT id FROM events
            WHERE session_id = ?
            ORDER BY COALESCE(ts, '9999'), raw_offset, block_index, id
            """,
            (session_id,),
        )
    )
    for seq, row in enumerate(rows):
        store.index.execute("UPDATE events SET seq = ? WHERE id = ?", (seq, row["id"]))


def drop_empty_sessions(store: Store) -> None:
    store.index.execute(
        """
        DELETE FROM session_models WHERE session_id NOT IN (SELECT DISTINCT session_id FROM events)
        """
    )
    store.index.execute(
        "DELETE FROM sessions WHERE id NOT IN (SELECT DISTINCT session_id FROM events)"
    )
    store.index.execute(
        "DELETE FROM export_state WHERE session_id NOT IN (SELECT id FROM sessions)"
    )


def list_sessions(store: Store, **filters) -> dict:
    group_paths = store.project_group_paths()
    where, params = store.session_filters(filters)
    sort = filters.get("sort") or "started_at"
    order, cursor_sql, cursor_params = sort_clause(sort, filters.get("cursor"))
    limit = min(int(filters.get("limit") or 50), 200)
    offset = 0
    cursor = filters.get("cursor")
    if cursor and str(cursor).startswith("off:"):
        offset = int(str(cursor)[4:])
    query = f"""
        SELECT s.* FROM sessions s
        WHERE {where} {cursor_sql}
        ORDER BY {order}
        LIMIT ? OFFSET ?
    """
    rows = list(store.index.execute(query, [*params, *cursor_params, limit, offset if not cursor_sql else 0]))
    next_cursor = None
    if len(rows) == limit:
        if sort == "started_at":
            last = rows[-1]
            next_cursor = f"{last['started_at'] or ''}|{last['id']}"
        else:
            next_cursor = f"off:{offset + limit}"
    return {
        "sessions": [store.session_dict(row, group_paths) for row in rows],
        "next_cursor": next_cursor,
    }


def session_detail(store: Store, session_id: str) -> dict | None:
    row = store.get_session(session_id)
    if row is None:
        return None
    data = store.session_dict(row)
    children = list(
        store.index.execute(
            """
            SELECT id, title, agent, started_at FROM sessions
            WHERE parent_session_id = ?
            ORDER BY started_at
            """,
            (session_id,),
        )
    )
    data["children"] = [
        {
            "id": child["id"],
            "title": child["title"],
            "agent": child["agent"],
            "started_at": child["started_at"],
        }
        for child in children
    ]
    note = store.get_note(session_id)
    data["note"] = None if note is None else {"text": note["text"], "updated_at": note["updated_at"]}
    return data


def session_filters(store: Store, filters: dict) -> tuple[str, list]:
    clauses = ["1=1"]
    params: list = []
    if filters.get("agent"):
        clauses.append("s.agent = ?")
        params.append(filters["agent"])
    if filters.get("project"):
        clauses.append("s.project_id = ?")
        params.append(filters["project"])
    if filters.get("project_cwd"):
        ids = [pid for pid, cwd in store.project_group_paths().items() if cwd == filters["project_cwd"]]
        if ids:
            clauses.append(f"s.project_id IN ({','.join('?' for _ in ids)})")
            params.extend(ids)
        else:
            clauses.append("0=1")
    if filters.get("model"):
        clauses.append(
            "EXISTS (SELECT 1 FROM session_models m WHERE m.session_id = s.id AND m.model = ?)"
        )
        params.append(filters["model"])
    if filters.get("start"):
        clauses.append("COALESCE(s.started_at, '') >= ?")
        params.append(filters["start"])
    if filters.get("end"):
        clauses.append("COALESCE(s.started_at, '') <= ?")
        params.append(filters["end"])
    if filters.get("q"):
        like = f"%{escape_like(filters['q'])}%"
        clauses.append("COALESCE(s.title, '') LIKE ? ESCAPE '\\'")
        params.append(like)
    if not filters.get("include_hidden"):
        hidden_projects = store.hidden_ids()
        if hidden_projects:
            marks = ",".join("?" for _ in hidden_projects)
            clauses.append(f"s.project_id NOT IN ({marks})")
            params.extend(hidden_projects)
        hidden_sessions = store.hidden_session_ids()
        if hidden_sessions:
            marks = ",".join("?" for _ in hidden_sessions)
            clauses.append(f"s.id NOT IN ({marks})")
            params.extend(hidden_sessions)
    if filters.get("boundary_only"):
        clauses.append("s.boundary_count > 0")
    return " AND ".join(clauses), params
