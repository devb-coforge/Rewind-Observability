"""Index and local user-data access. The two SQLite files are never mixed on write."""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from obs.adapters.lineio import preview, to_iso
from obs.analytics.pricing import Pricing
from obs.identity import classify_paths, path_is_allowed, project_identity
from obs.models import Usage

SCHEMA = (Path(__file__).with_name("schema.sql")).read_text()
USER_SCHEMA = (Path(__file__).with_name("user_schema.sql")).read_text()


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


class Store:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.index_path = data_dir / "index.db"
        self.user_path = data_dir / "user.db"
        self.index = connect(self.index_path)
        self.user = connect(self.user_path)
        self.index.executescript(SCHEMA)
        columns = {row["name"] for row in self.index.execute("PRAGMA table_info(sessions)")}
        if "source_title" not in columns:
            self.index.execute("ALTER TABLE sessions ADD COLUMN source_title TEXT")
        self.user.executescript(USER_SCHEMA)
        self.index.commit()
        self.user.commit()
        self._lock = threading.RLock()
        self._depth = 0

    @contextmanager
    def transaction(self):
        self._lock.acquire()
        self._depth += 1
        try:
            yield self
            if self._depth == 1:
                self.index.commit()
                self.user.commit()
        except Exception:
            if self._depth == 1:
                self.index.rollback()
                self.user.rollback()
            raise
        finally:
            self._depth -= 1
            self._lock.release()

    def close(self) -> None:
        self.index.close()
        self.user.close()

    def reset_index(self) -> None:
        self.index.execute("DELETE FROM events_fts")
        self.index.execute("DELETE FROM event_blobs")
        self.index.execute("DELETE FROM events")
        self.index.execute("DELETE FROM session_models")
        self.index.execute("DELETE FROM sessions")
        self.index.execute("DELETE FROM files")
        self.index.execute("DELETE FROM export_state")

    def get_meta(self, key: str) -> str | None:
        row = self.index.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return None if row is None else row["value"]

    def set_meta(self, key: str, value: str | None) -> None:
        if value is None:
            self.index.execute("DELETE FROM meta WHERE key = ?", (key,))
        else:
            self.index.execute(
                "INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def get_file(self, path: str) -> sqlite3.Row | None:
        return self.index.execute("SELECT * FROM files WHERE path = ?", (path,)).fetchone()

    def upsert_file(
        self,
        *,
        path: str,
        agent: str,
        size: int,
        mtime: float,
        last_offset: int,
        adapter_version: int,
        session_id: str | None,
    ) -> None:
        self.index.execute(
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

    def files_under(self, root: str) -> list[sqlite3.Row]:
        prefix = root.rstrip("/") + "/"
        return list(
            self.index.execute(
                "SELECT * FROM files WHERE path = ? OR path LIKE ?",
                (root, prefix + "%"),
            )
        )

    def list_files(self) -> list[sqlite3.Row]:
        return list(self.index.execute("SELECT * FROM files"))

    def delete_events_for_path(self, path: str) -> list[str]:
        rows = list(
            self.index.execute("SELECT rowid, id, session_id FROM events WHERE raw_path = ?", (path,))
        )
        sessions = []
        for row in rows:
            self.index.execute("DELETE FROM events_fts WHERE rowid = ?", (row["rowid"],))
            self.index.execute("DELETE FROM event_blobs WHERE event_id = ?", (row["id"],))
            sessions.append(row["session_id"])
        self.index.execute("DELETE FROM events WHERE raw_path = ?", (path,))
        return sessions

    def delete_file(self, path: str) -> None:
        self.index.execute("DELETE FROM files WHERE path = ?", (path,))

    def get_session(self, session_id: str) -> sqlite3.Row | None:
        return self.index.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()

    def event_exists(self, event_id: str) -> bool:
        row = self.index.execute("SELECT 1 FROM events WHERE id = ?", (event_id,)).fetchone()
        return row is not None

    def ensure_session(self, fields: dict) -> None:
        self.index.execute(
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

    def insert_event(self, event: dict) -> bool:
        cur = self.index.execute(
            """
            INSERT OR IGNORE INTO events(
              id, session_id, parent_id, seq, ts, role, kind, text, tool_name, tool_call_id,
              tool_input_json, tool_output_preview, is_error, model, usage_json, usage_origin,
              message_id, raw_path, raw_offset, raw_length, paths_json, block_index
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                1 if event.get("is_error") else 0,
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
        self.index.execute(
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
            self.index.execute(
                "INSERT OR REPLACE INTO event_blobs(event_id, tool_output) VALUES(?, ?)",
                (event["id"], event["tool_output"]),
            )
        return True

    def resequence(self, session_id: str) -> None:
        rows = list(
            self.index.execute(
                """
                SELECT id FROM events
                WHERE session_id = ?
                ORDER BY COALESCE(ts, '9999'), raw_offset, block_index, id
                """,
                (session_id,),
            )
        )
        for seq, row in enumerate(rows):
            self.index.execute("UPDATE events SET seq = ? WHERE id = ?", (seq, row["id"]))

    def drop_empty_sessions(self) -> None:
        self.index.execute(
            """
            DELETE FROM session_models WHERE session_id NOT IN (SELECT DISTINCT session_id FROM events)
            """
        )
        self.index.execute(
            "DELETE FROM sessions WHERE id NOT IN (SELECT DISTINCT session_id FROM events)"
        )
        self.index.execute(
            "DELETE FROM export_state WHERE session_id NOT IN (SELECT id FROM sessions)"
        )

    def recompute(
        self,
        session_id: str,
        pricing: Pricing,
        *,
        allow_prefixes: list[str],
        dismissals: list[str],
    ) -> None:
        session = self.get_session(session_id)
        if session is None:
            return
        rows = list(
            self.index.execute(
                "SELECT * FROM events WHERE session_id = ? ORDER BY seq, raw_offset, block_index",
                (session_id,),
            )
        )
        if not rows:
            self.index.execute("DELETE FROM session_models WHERE session_id = ?", (session_id,))
            self.index.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            return
        has_token_count = any(
            row["usage_origin"] == "token_count" and row["usage_json"] for row in rows
        )
        seen_messages: set[str] = set()
        totals = {
            "input_tokens": None,
            "output_tokens": None,
            "cache_read_tokens": None,
            "cache_write_tokens": None,
        }
        cost = 0.0
        any_cost = False
        missing_price = False
        any_usage = False
        last_model = None
        models: list[str] = []
        title = session["source_title"]
        n_user = 0
        n_tools = 0
        error_result_ids: set[str] = set()
        n_errors = 0
        coverage_gap = False
        assistant_seen: set[str] = set()
        assistant_with_usage: set[str] = set()

        for row in rows:
            if row["model"]:
                last_model = row["model"]
                if row["model"] not in models:
                    models.append(row["model"])
            if title is None and row["role"] == "user" and row["kind"] == "message" and row["text"]:
                title = " ".join(row["text"].split())[:120]
            if row["role"] == "user" and row["kind"] == "message":
                n_user += 1
            if row["kind"] == "tool_call":
                n_tools += 1
            if row["kind"] == "tool_result" and row["is_error"]:
                n_errors += 1
                if row["tool_call_id"]:
                    error_result_ids.add(row["tool_call_id"])

            usage = _load_usage(row["usage_json"])
            origin = row["usage_origin"]
            drop = False
            if usage and origin == "token_record" and has_token_count:
                drop = True
            if usage and has_token_count and origin == "message":
                drop = True
            message_id = row["message_id"]
            if usage and message_id and not drop:
                if message_id in seen_messages:
                    drop = True
                else:
                    seen_messages.add(message_id)
            if drop and row["usage_json"]:
                self.index.execute(
                    "UPDATE events SET usage_json = NULL, usage_origin = NULL WHERE id = ?",
                    (row["id"],),
                )
                usage = None
            if row["role"] == "assistant" and row["kind"] == "message":
                key = message_id or row["id"]
                assistant_seen.add(key)
                if (usage and origin == "message") or (message_id and message_id in seen_messages):
                    assistant_with_usage.add(key)
            if not usage or (has_token_count and origin != "token_count"):
                continue
            any_usage = True
            for field in totals:
                value = getattr(usage, field)
                if value is None:
                    continue
                totals[field] = (totals[field] or 0) + value
            model = row["model"] or last_model
            estimate = pricing.estimate(model, usage)
            if estimate is None:
                missing_price = True
            else:
                any_cost = True
                cost += estimate

        for row in rows:
            if (
                row["kind"] == "tool_call"
                and row["is_error"]
                and row["tool_call_id"]
                and row["tool_call_id"] not in error_result_ids
            ):
                n_errors += 1

        if not any_usage:
            coverage = "none"
        elif has_token_count or (
            assistant_seen and assistant_seen <= assistant_with_usage
        ) or not assistant_seen:
            coverage = "complete"
        else:
            coverage = "partial"
            coverage_gap = True
        if any_usage and assistant_seen and not has_token_count and assistant_seen - assistant_with_usage:
            coverage = "partial"
            coverage_gap = True

        prefixes = list(allow_prefixes) + list(dismissals)
        boundary = 0
        for row in rows:
            paths = json.loads(row["paths_json"] or "[]")
            if any(
                item.get("outside") and not path_is_allowed(item.get("resolved") or "", prefixes)
                for item in paths
            ):
                boundary += 1

        started = min((row["ts"] for row in rows if row["ts"]), default=session["started_at"])
        ended = max((row["ts"] for row in rows if row["ts"]), default=session["ended_at"])
        self.index.execute("DELETE FROM session_models WHERE session_id = ?", (session_id,))
        self.index.executemany(
            "INSERT INTO session_models(session_id, model) VALUES(?, ?)",
            [(session_id, model) for model in models],
        )
        self.index.execute(
            """
            UPDATE sessions SET
              title = ?,
              models_json = ?,
              started_at = COALESCE(?, started_at),
              ended_at = COALESCE(?, ended_at),
              n_events = ?,
              n_user_msgs = ?,
              n_tool_calls = ?,
              n_tool_errors = ?,
              tokens_in = ?,
              tokens_out = ?,
              tokens_cache_read = ?,
              tokens_cache_write = ?,
              est_cost_usd = ?,
              cost_partial = ?,
              usage_coverage = ?,
              boundary_count = ?
            WHERE id = ?
            """,
            (
                title,
                json.dumps(models),
                started,
                ended,
                len(rows),
                n_user,
                n_tools,
                n_errors,
                totals["input_tokens"],
                totals["output_tokens"],
                totals["cache_read_tokens"],
                totals["cache_write_tokens"],
                cost if any_cost else None,
                1 if any_cost and missing_price else 0,
                coverage if not coverage_gap or coverage == "partial" else coverage,
                boundary,
                session_id,
            ),
        )

    def refresh_boundary(self, project_id: str | None, allow_prefixes: list[str]) -> None:
        if project_id:
            sessions = list(
                self.index.execute("SELECT id, project_id FROM sessions WHERE project_id = ?", (project_id,))
            )
        else:
            sessions = list(self.index.execute("SELECT id, project_id FROM sessions"))
        for session in sessions:
            dismissals = self.dismissal_prefixes(session["project_id"])
            self.recompute_boundary_only(session["id"], allow_prefixes, dismissals)

    def recompute_boundary_only(self, session_id: str, allow_prefixes: list[str], dismissals: list[str]) -> None:
        prefixes = list(allow_prefixes) + list(dismissals)
        rows = list(
            self.index.execute(
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
        self.index.execute(
            "UPDATE sessions SET boundary_count = ? WHERE id = ?",
            (boundary, session_id),
        )

    def hidden_ids(self) -> list[str]:
        return [
            row["project_id"]
            for row in self.user.execute(
                "SELECT project_id FROM project_preferences WHERE hidden = 1"
            )
        ]

    def is_hidden(self, project_id: str) -> bool:
        row = self.user.execute(
            "SELECT hidden FROM project_preferences WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        return bool(row and row["hidden"])

    def set_hidden(self, project_id: str, hidden: bool, now: str) -> None:
        self.user.execute(
            """
            INSERT INTO project_preferences(project_id, hidden, updated_at)
            VALUES(?, ?, ?)
            ON CONFLICT(project_id) DO UPDATE SET hidden = excluded.hidden, updated_at = excluded.updated_at
            """,
            (project_id, 1 if hidden else 0, now),
        )

    def get_note(self, session_id: str) -> sqlite3.Row | None:
        return self.user.execute(
            "SELECT session_id, text, updated_at FROM session_notes WHERE session_id = ?",
            (session_id,),
        ).fetchone()

    def set_note(self, session_id: str, text: str, now: str) -> None:
        if text == "":
            self.user.execute("DELETE FROM session_notes WHERE session_id = ?", (session_id,))
            return
        self.user.execute(
            """
            INSERT INTO session_notes(session_id, text, updated_at) VALUES(?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET text = excluded.text, updated_at = excluded.updated_at
            """,
            (session_id, text, now),
        )

    def dismissal_prefixes(self, project_id: str) -> list[str]:
        return [
            row["path_prefix"]
            for row in self.user.execute(
                "SELECT path_prefix FROM boundary_dismissals WHERE project_id = ?",
                (project_id,),
            )
        ]

    def dismiss(self, project_id: str, path_prefix: str, now: str) -> None:
        self.user.execute(
            """
            INSERT INTO boundary_dismissals(project_id, path_prefix, updated_at)
            VALUES(?, ?, ?)
            ON CONFLICT(project_id, path_prefix) DO UPDATE SET updated_at = excluded.updated_at
            """,
            (project_id, path_prefix, now),
        )

    def undismiss(self, project_id: str, path_prefix: str) -> None:
        self.user.execute(
            "DELETE FROM boundary_dismissals WHERE project_id = ? AND path_prefix = ?",
            (project_id, path_prefix),
        )

    def list_projects(self, include_hidden: bool) -> list[dict]:
        hidden = set(self.hidden_ids())
        rows = list(
            self.index.execute(
                """
                SELECT project_id, agent, project_name, project_cwd, COUNT(*) AS n_sessions
                FROM sessions
                GROUP BY project_id
                ORDER BY project_name IS NULL, project_name, agent
                """
            )
        )
        projects = []
        for row in rows:
            is_hidden = row["project_id"] in hidden
            if is_hidden and not include_hidden:
                continue
            projects.append(
                {
                    "project_id": row["project_id"],
                    "agent": row["agent"],
                    "name": row["project_name"] or "(unknown)",
                    "cwd": row["project_cwd"],
                    "hidden": is_hidden,
                    "n_sessions": row["n_sessions"],
                }
            )
        return projects

    def list_sessions(self, **filters) -> dict:
        where, params = self._session_filters(filters)
        sort = filters.get("sort") or "started_at"
        order, cursor_sql, cursor_params = _sort_clause(sort, filters.get("cursor"))
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
        rows = list(self.index.execute(query, [*params, *cursor_params, limit, offset if not cursor_sql else 0]))
        next_cursor = None
        if len(rows) == limit:
            if sort == "started_at":
                last = rows[-1]
                next_cursor = f"{last['started_at'] or ''}|{last['id']}"
            else:
                next_cursor = f"off:{offset + limit}"
        return {
            "sessions": [self.session_dict(row) for row in rows],
            "next_cursor": next_cursor,
        }

    def session_dict(self, row: sqlite3.Row) -> dict:
        models = json.loads(row["models_json"] or "[]")
        duration = _duration(row["started_at"], row["ended_at"])
        return {
            "id": row["id"],
            "agent": row["agent"],
            "native_id": row["native_id"],
            "source_path": row["source_path"],
            "project_cwd": row["project_cwd"],
            "project_name": row["project_name"],
            "project_id": row["project_id"],
            "project_hidden": self.is_hidden(row["project_id"]),
            "git_branch": row["git_branch"],
            "models": models,
            "parent_session_id": row["parent_session_id"],
            "started_at": row["started_at"],
            "ended_at": row["ended_at"],
            "duration_sec": duration,
            "title": row["title"],
            "n_events": row["n_events"],
            "n_user_msgs": row["n_user_msgs"],
            "n_tool_calls": row["n_tool_calls"],
            "n_tool_errors": row["n_tool_errors"],
            "tokens_in": row["tokens_in"],
            "tokens_out": row["tokens_out"],
            "tokens_cache_read": row["tokens_cache_read"],
            "tokens_cache_write": row["tokens_cache_write"],
            "est_cost_usd": row["est_cost_usd"],
            "cost_partial": bool(row["cost_partial"]),
            "usage_coverage": row["usage_coverage"],
            "boundary_count": row["boundary_count"],
        }

    def session_detail(self, session_id: str) -> dict | None:
        row = self.get_session(session_id)
        if row is None:
            return None
        data = self.session_dict(row)
        children = list(
            self.index.execute(
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
        note = self.get_note(session_id)
        data["note"] = None if note is None else {"text": note["text"], "updated_at": note["updated_at"]}
        return data

    def list_events(self, session_id: str, *, cursor: int | None, limit: int, kinds: list[str] | None) -> dict:
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
            self.index.execute(
                f"""
                SELECT * FROM events
                WHERE {' AND '.join(clauses)}
                ORDER BY seq
                LIMIT ?
                """,
                [*params, limit],
            )
        )
        session = self.get_session(session_id)
        dismissals = self.dismissal_prefixes(session["project_id"]) if session else []
        next_cursor = rows[-1]["seq"] if len(rows) == limit else None
        return {
            "events": [self.event_dict(row, dismissals) for row in rows],
            "next_cursor": next_cursor,
        }

    def event_dict(self, row: sqlite3.Row, dismissals: list[str] | None = None) -> dict:
        paths = json.loads(row["paths_json"] or "[]")
        for item in paths:
            item["dismissed"] = bool(dismissals) and path_is_allowed(item.get("resolved") or "", dismissals or [])
            item["allowed"] = (not item.get("outside")) or item["dismissed"]
        usage = _load_usage(row["usage_json"])
        tool_input = json.loads(row["tool_input_json"]) if row["tool_input_json"] else None
        return {
            "id": row["id"],
            "session_id": row["session_id"],
            "parent_id": row["parent_id"],
            "seq": row["seq"],
            "ts": row["ts"],
            "role": row["role"],
            "kind": row["kind"],
            "text": row["text"],
            "tool_name": row["tool_name"],
            "tool_call_id": row["tool_call_id"],
            "tool_input": tool_input,
            "tool_output_preview": row["tool_output_preview"],
            "is_error": bool(row["is_error"]),
            "model": row["model"],
            "usage": usage.as_dict() if usage else None,
            "raw": {"path": row["raw_path"], "offset": row["raw_offset"], "length": row["raw_length"]},
            "paths": paths,
        }

    def get_event(self, event_id: str) -> sqlite3.Row | None:
        return self.index.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()

    def get_output(self, event_id: str) -> str | None:
        row = self.index.execute(
            "SELECT tool_output FROM event_blobs WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        if row is not None:
            return row["tool_output"]
        event = self.get_event(event_id)
        if event is None:
            return None
        return event["tool_output_preview"]

    def events_for_session(self, session_id: str) -> list[sqlite3.Row]:
        return list(
            self.index.execute(
                "SELECT * FROM events WHERE session_id = ? ORDER BY seq",
                (session_id,),
            )
        )

    def _session_filters(self, filters: dict) -> tuple[str, list]:
        clauses = ["1=1"]
        params: list = []
        if filters.get("agent"):
            clauses.append("s.agent = ?")
            params.append(filters["agent"])
        if filters.get("project"):
            clauses.append("s.project_id = ?")
            params.append(filters["project"])
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
            like = f"%{_escape_like(filters['q'])}%"
            clauses.append("COALESCE(s.title, '') LIKE ? ESCAPE '\\'")
            params.append(like)
        if not filters.get("include_hidden"):
            hidden = self.hidden_ids()
            if hidden:
                marks = ",".join("?" for _ in hidden)
                clauses.append(f"s.project_id NOT IN ({marks})")
                params.extend(hidden)
        if filters.get("boundary_only"):
            clauses.append("s.boundary_count > 0")
        return " AND ".join(clauses), params


def _sort_clause(sort: str, cursor: str | None) -> tuple[str, str, list]:
    orders = {
        "started_at": "COALESCE(s.started_at, '') DESC, s.id DESC",
        "cost": "COALESCE(s.est_cost_usd, -1) DESC, s.id DESC",
        "tokens": "(COALESCE(s.tokens_in, 0) + COALESCE(s.tokens_out, 0)) DESC, s.id DESC",
        "duration": "(julianday(s.ended_at) - julianday(s.started_at)) DESC, s.id DESC",
        "errors": "s.n_tool_errors DESC, s.id DESC",
    }
    order = orders.get(sort, orders["started_at"])
    if not cursor:
        return order, "", []
    if str(cursor).startswith("off:"):
        return order, "", []
    if sort != "started_at" or "|" not in str(cursor):
        return order, "", []
    ts, sid = str(cursor).split("|", 1)
    sql = " AND (COALESCE(s.started_at, '') < ? OR (COALESCE(s.started_at, '') = ? AND s.id < ?))"
    return order, sql, [ts, ts, sid]


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _load_usage(raw: str | None) -> Usage | None:
    if not raw:
        return None
    data = json.loads(raw)
    usage = Usage(
        input_tokens=data.get("input_tokens"),
        output_tokens=data.get("output_tokens"),
        cache_read_tokens=data.get("cache_read_tokens"),
        cache_write_tokens=data.get("cache_write_tokens"),
    )
    return usage if usage.known() else None


def _duration(start: str | None, end: str | None) -> float | None:
    if not start or not end:
        return None
    from datetime import datetime

    def parse(value: str) -> datetime:
        text = value[:-1] + "+00:00" if value.endswith("Z") else value
        return datetime.fromisoformat(text)

    return (parse(end) - parse(start)).total_seconds()


def build_event_row(
    *,
    agent: str,
    session_id: str,
    event_id: str,
    parsed,
    cwd: str | None,
    seq: int,
) -> dict:
    paths = []
    if parsed.kind == "tool_call":
        from obs.identity import extract_path_refs

        refs = extract_path_refs(parsed.tool_name, parsed.tool_input)
        paths = classify_paths(cwd, refs)
    tool_input_json = json.dumps(parsed.tool_input) if parsed.tool_input is not None else None
    output_preview = preview(parsed.tool_output, 500)
    fts_bits = []
    if tool_input_json:
        fts_bits.append(tool_input_json[:400])
    if output_preview:
        fts_bits.append(output_preview)
    parent_id = None
    if parsed.parent_native_id:
        parent_id = f"{agent}:{parsed.parent_native_id}:0"
    return {
        "id": event_id,
        "session_id": session_id,
        "parent_id": parent_id,
        "seq": seq,
        "ts": to_iso(parsed.ts),
        "role": parsed.role,
        "kind": parsed.kind,
        "text": parsed.text,
        "tool_name": parsed.tool_name,
        "tool_call_id": parsed.tool_call_id,
        "tool_input_json": tool_input_json,
        "tool_output_preview": output_preview,
        "tool_output": parsed.tool_output,
        "is_error": parsed.is_error,
        "model": parsed.model,
        "usage_json": json.dumps(parsed.usage.as_dict()) if parsed.usage and parsed.usage.known() else None,
        "usage_origin": parsed.usage_origin,
        "message_id": parsed.message_id,
        "raw_path": None,
        "raw_offset": parsed.raw_offset,
        "raw_length": parsed.raw_length,
        "paths_json": json.dumps(paths) if paths else None,
        "block_index": parsed.block_index,
        "fts_preview": "\n".join(fts_bits),
    }


def project_fields(agent: str, cwd: str | None) -> dict:
    project_id, norm, name = project_identity(agent, cwd)
    return {"project_id": project_id, "project_cwd": norm, "project_name": name}
