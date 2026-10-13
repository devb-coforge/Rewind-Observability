"""Index and local user-data access. The two SQLite files are never mixed on write."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3
import threading

from obs.analytics import session_summary
from obs.analytics.pricing import Pricing
from obs.db import boundaries, events, files, preferences, projects, serialization, sessions

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
        if "source_models_json" not in columns:
            self.index.execute("ALTER TABLE sessions ADD COLUMN source_models_json TEXT NOT NULL DEFAULT '[]'")
        if "selected_model" not in columns:
            self.index.execute("ALTER TABLE sessions ADD COLUMN selected_model TEXT")
        if "source_duration_sec" not in columns:
            self.index.execute("ALTER TABLE sessions ADD COLUMN source_duration_sec REAL")
        event_columns = {row["name"] for row in self.index.execute("PRAGMA table_info(events)")}
        if "is_declined" not in event_columns:
            self.index.execute("ALTER TABLE events ADD COLUMN is_declined INTEGER NOT NULL DEFAULT 0")
        self.user.executescript(USER_SCHEMA)
        user_tables = {
            row["name"] for row in self.user.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        if "benchmark_cases" in user_tables and "eval_cases" not in user_tables:
            self.user.execute("ALTER TABLE benchmark_cases RENAME TO eval_cases")
        case_columns = {row["name"] for row in self.user.execute("PRAGMA table_info(eval_cases)")}
        if "session_title" not in case_columns:
            self.user.execute("ALTER TABLE eval_cases ADD COLUMN session_title TEXT")
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
        self.index.execute("DELETE FROM event_raw")
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
        return files.get_file(self, path)

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
        files.upsert_file(
            self,
            path=path,
            agent=agent,
            size=size,
            mtime=mtime,
            last_offset=last_offset,
            adapter_version=adapter_version,
            session_id=session_id,
        )

    def files_under(self, root: str) -> list[sqlite3.Row]:
        return files.files_under(self, root)

    def list_files(self) -> list[sqlite3.Row]:
        return files.list_files(self)

    def delete_events_for_path(self, path: str) -> list[str]:
        return events.delete_events_for_path(self, path)

    def delete_file(self, path: str) -> None:
        files.delete_file(self, path)

    def get_session(self, session_id: str) -> sqlite3.Row | None:
        return sessions.get_session(self, session_id)

    def event_exists(self, event_id: str) -> bool:
        return events.event_exists(self, event_id)

    def ensure_session(self, fields: dict) -> None:
        sessions.ensure_session(self, fields)

    def insert_event(self, event: dict) -> bool:
        return events.insert_event(self, event)

    def resequence(self, session_id: str) -> None:
        sessions.resequence(self, session_id)

    def drop_empty_sessions(self) -> None:
        sessions.drop_empty_sessions(self)

    def recompute(
        self,
        session_id: str,
        pricing: Pricing,
        *,
        allow_prefixes: list[str],
        dismissals: list[str],
    ) -> None:
        session_summary.recompute(
            self,
            session_id,
            pricing,
            allow_prefixes=allow_prefixes,
            dismissals=dismissals,
        )

    def refresh_boundary(self, project_id: str | None, allow_prefixes: list[str]) -> None:
        boundaries.refresh_boundary(self, project_id, allow_prefixes)

    def recompute_boundary_only(self, session_id: str, allow_prefixes: list[str], dismissals: list[str]) -> None:
        boundaries.recompute_boundary_only(self, session_id, allow_prefixes, dismissals)

    def hidden_ids(self) -> list[str]:
        return preferences.hidden_ids(self)

    def is_hidden(self, project_id: str) -> bool:
        return preferences.is_hidden(self, project_id)

    def set_hidden(self, project_id: str, hidden: bool, now: str) -> None:
        preferences.set_hidden(self, project_id, hidden, now)

    def hidden_session_ids(self) -> list[str]:
        return preferences.hidden_session_ids(self)

    def is_session_hidden(self, session_id: str) -> bool:
        return preferences.is_session_hidden(self, session_id)

    def set_session_hidden(self, session_id: str, hidden: bool, now: str) -> None:
        preferences.set_session_hidden(self, session_id, hidden, now)

    def get_note(self, session_id: str) -> sqlite3.Row | None:
        return preferences.get_note(self, session_id)

    def set_note(self, session_id: str, text: str, now: str) -> None:
        preferences.set_note(self, session_id, text, now)

    def dismissal_prefixes(self, project_id: str) -> list[str]:
        return preferences.dismissal_prefixes(self, project_id)

    def dismiss(self, project_id: str, path_prefix: str, now: str) -> None:
        preferences.dismiss(self, project_id, path_prefix, now)

    def undismiss(self, project_id: str, path_prefix: str) -> None:
        preferences.undismiss(self, project_id, path_prefix)

    @staticmethod
    def project_name_key(cwd: str | None, project_id: str) -> str:
        return projects.project_name_key(cwd, project_id)

    def project_group_paths(self) -> dict[str, str | None]:
        return projects.project_group_paths(self)

    def refresh_project_names(self) -> None:
        projects.refresh_project_names(self)

    def rename_project(self, project_id: str, name: str, now: str) -> bool:
        return projects.rename_project(self, project_id, name, now)

    def list_projects(self, include_hidden: bool) -> list[dict]:
        return projects.list_projects(self, include_hidden)

    def list_sessions(self, **filters) -> dict:
        return sessions.list_sessions(self, **filters)

    def session_dict(self, row: sqlite3.Row, group_paths: dict[str, str | None] | None = None) -> dict:
        return serialization.session_dict(
            row,
            group_paths=group_paths if group_paths is not None else self.project_group_paths(),
            project_hidden=self.is_hidden(row['project_id']),
            hidden=self.is_session_hidden(row['id']),
        )

    def session_detail(self, session_id: str) -> dict | None:
        return sessions.session_detail(self, session_id)

    def list_events(self, session_id: str, *, cursor: int | None, limit: int, kinds: list[str] | None) -> dict:
        return events.list_events(self, session_id, cursor=cursor, limit=limit, kinds=kinds)

    def event_dict(self, row: sqlite3.Row, dismissals: list[str] | None = None) -> dict:
        return serialization.event_dict(row, dismissals)

    def get_event(self, event_id: str) -> sqlite3.Row | None:
        return events.get_event(self, event_id)

    def get_output(self, event_id: str) -> str | None:
        return events.get_output(self, event_id)

    def events_for_session(self, session_id: str) -> list[sqlite3.Row]:
        return events.events_for_session(self, session_id)

    def session_filters(self, filters: dict) -> tuple[str, list]:
        return sessions.session_filters(self, filters)
