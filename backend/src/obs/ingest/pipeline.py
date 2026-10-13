from __future__ import annotations

from pathlib import Path
import json
import logging

from obs.adapters.interface import Adapter
from obs.analytics.pricing import Pricing
from obs.config import AppConfig
from obs.db.repo import Store
from obs.db.serialization import build_event_row, project_fields
from obs.identity import event_id_for, session_id_for
from obs.ingest.scanner import path_under_source, resolve_sources, source_root
from obs.shared.lineio import to_iso

log = logging.getLogger("obs.ingest")


class SourceAccessError(PermissionError):
    def __init__(self, root: Path):
        super().__init__(
            f"Cannot read transcript source {root}. Check source permissions; "
            "with Docker, set PUID and PGID to your host user's UID and GID "
            "(id -u and id -g), then recreate the container. "
            "The index was not changed."
        )


class Ingestor:
    def __init__(self, config: AppConfig, store: Store, pricing: Pricing):
        self.config = config
        self.store = store
        self.pricing = pricing

    def run(self, *, full: bool = False) -> dict:
        self.pricing.refresh()
        pricing_fingerprint = self.pricing.fingerprint()
        stats = {
            "files_seen": 0,
            "files_parsed": 0,
            "files_skipped": 0,
            "files_removed": 0,
            "events": 0,
        }
        affected: set[str] = set()
        with self.store.transaction():
            if self.store.get_meta("pricing_fingerprint") != pricing_fingerprint:
                affected.update(row["id"] for row in self.store.index.execute("SELECT id FROM sessions"))
            if full:
                self.store.reset_index()
            for source, adapter in resolve_sources(self.config.sources):
                root = source_root(source)
                if adapter is None:
                    continue
                try:
                    if not root.exists():
                        continue
                    paths = adapter.discover(root)
                except PermissionError as exc:
                    raise SourceAccessError(root) from exc
                discovered: list[Path] = []
                for path in paths:
                    discovered.append(path)
                    stats["files_seen"] += 1
                    try:
                        added = self._ingest_file(path, adapter, affected)
                    except PermissionError as exc:
                        raise SourceAccessError(root) from exc
                    except Exception:
                        log.exception("failed to parse %s", path)
                        continue
                    if added is None:
                        stats["files_skipped"] += 1
                    else:
                        stats["files_parsed"] += 1
                        stats["events"] += added
                self._prune(root, discovered, affected)
                snapshot = adapter.read_metadata(root, self.config.cursor_user_data_dir)
                if snapshot is not None:
                    metadata = snapshot.entries
                    titles = snapshot.titles
                    sessions = list(self.store.index.execute(
                        "SELECT * FROM sessions WHERE agent = ?",
                        (adapter.name,),
                    ))
                    for session in sessions:
                        if not path_under_source(session["source_path"], source):
                            continue
                        if metadata is not None:
                            from obs.ingest.cursor_tools import sync_tools

                            if sync_tools(self.store, session, metadata.get(session["native_id"], {}).get("tools", [])):
                                affected.add(session["id"])
                        title = titles.get(session["native_id"])
                        created_at = (metadata or {}).get(session["native_id"], {}).get("started_at")
                        if metadata is not None:
                            entry = metadata.get(session["native_id"], {})
                            duration = entry.get("duration_sec")
                            if duration != session["source_duration_sec"]:
                                self.store.index.execute(
                                    "UPDATE sessions SET source_duration_sec = ? WHERE id = ?",
                                    (duration, session["id"]),
                                )
                                affected.add(session["id"])
                            cwd = entry.get("project_cwd")
                            cwd_key = f"{adapter.name}_workspace:{session['id']}"
                            previous_cwd = self.store.get_meta(cwd_key)
                            if cwd and (not session["project_cwd"] or session["project_cwd"] == previous_cwd):
                                identity = project_fields(adapter.name, cwd)
                                if identity["project_cwd"] != session["project_cwd"]:
                                    self.store.index.execute(
                                        "UPDATE sessions SET project_cwd = ?, project_id = ?, project_name = ? WHERE id = ?",
                                        (identity["project_cwd"], identity["project_id"], identity["project_name"], session["id"]),
                                    )
                                    affected.add(session["id"])
                                self.store.set_meta(cwd_key, identity["project_cwd"])
                            models_json = json.dumps(entry.get("models", []))
                            selected_model = entry.get("selected_model")
                            if models_json != session["source_models_json"] or selected_model != session["selected_model"]:
                                self.store.index.execute(
                                    "UPDATE sessions SET source_models_json = ?, selected_model = ? WHERE id = ?",
                                    (models_json, selected_model, session["id"]),
                                )
                                affected.add(session["id"])
                        if session["started_at"] is None and created_at:
                            self.store.index.execute(
                                "UPDATE sessions SET started_at = ? WHERE id = ?",
                                (created_at, session["id"]),
                            )
                            affected.add(session["id"])
                        if title != session["source_title"]:
                            self.store.index.execute(
                                "UPDATE sessions SET source_title = ? WHERE id = ?",
                                (title, session["id"]),
                            )
                            affected.add(session["id"])
            stats["files_removed"] += self._prune_outside_sources(affected)
            dismissals = {
                row["project_id"]: self.store.dismissal_prefixes(row["project_id"])
                for row in self.store.index.execute("SELECT DISTINCT project_id FROM sessions")
            }
            for session_id in list(affected):
                session = self.store.get_session(session_id)
                if session is None:
                    continue
                self.store.recompute(
                    session_id,
                    self.pricing,
                    allow_prefixes=self.config.boundary.allow_prefixes,
                    dismissals=dismissals.get(session["project_id"], []),
                )
            self.store.drop_empty_sessions()
            self.store.refresh_project_names()
            from obs.evals import backfill_case_metadata

            backfill_case_metadata(self.store)
            self.store.set_meta("pricing_fingerprint", pricing_fingerprint)
            from datetime import datetime, timezone

            self.store.set_meta(
                "last_indexed_at",
                datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            )
        stats["sessions"] = self._session_count()
        return stats

    def _session_count(self) -> int:
        with self.store.transaction():
            row = self.store.index.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()
            return int(row["n"])

    def _prune_outside_sources(self, affected: set[str]) -> int:
        removed = 0
        for row in self.store.list_files():
            if any(path_under_source(row["path"], source) for source in self.config.sources):
                continue
            affected.update(self.store.delete_events_for_path(row["path"]))
            if row["session_id"]:
                affected.add(row["session_id"])
            self.store.delete_file(row["path"])
            removed += 1
        return removed

    def _prune(self, root: Path, discovered: list[Path], affected: set[str]) -> None:
        found = {str(path) for path in discovered}
        for row in self.store.files_under(str(root.resolve())):
            if row["path"] in found:
                continue
            affected.update(self.store.delete_events_for_path(row["path"]))
            if row["session_id"]:
                affected.add(row["session_id"])
            self.store.delete_file(row["path"])

    def _ingest_file(self, path: Path, adapter: Adapter, affected: set[str]) -> int | None:
        stat = path.stat()
        previous = self.store.get_file(str(path))
        if (
            previous
            and previous["adapter_version"] == adapter.version
            and previous["agent"] == adapter.name
            and previous["size"] == stat.st_size
            and previous["mtime"] == stat.st_mtime
        ):
            return None
        full = (
            previous is None
            or previous["adapter_version"] != adapter.version
            or stat.st_size < previous["size"]
            or (stat.st_size == previous["size"] and stat.st_mtime != previous["mtime"])
        )
        if full and previous is not None:
            for session_id in self.store.delete_events_for_path(str(path)):
                affected.add(session_id)
        start = 0 if full or previous is None else int(previous["last_offset"])
        parsed = adapter.parse(path, start)
        native_id = parsed.native_id or adapter.native_id_from_path(path) or path.stem
        parent_native = parsed.parent_native_id or adapter.parent_native_id(path)
        session_id = session_id_for(adapter.name, native_id)
        existing = self.store.get_session(session_id)
        cwd = parsed.project_cwd or (existing["project_cwd"] if existing else None)
        identity = project_fields(adapter.name, cwd)
        if not cwd and parsed.project_key:
            # Workspace identifiers group transcripts without inventing a cwd.
            identity = project_fields(adapter.name, parsed.project_key)
            identity["project_cwd"] = None
            identity["project_name"] = parsed.project_name
        inserted = 0
        pending_seq = 0
        for event in parsed.events:
            eid = event_id_for(
                adapter.name,
                event.native_id,
                event.block_index,
                str(path),
                event.raw_offset,
            )
            if self.store.event_exists(eid):
                continue
            if inserted == 0:
                self.store.ensure_session(
                    {
                        "id": session_id,
                        "agent": adapter.name,
                        "native_id": native_id,
                        "source_path": str(path),
                        "project_cwd": identity["project_cwd"],
                        "project_name": identity["project_name"],
                        "project_id": identity["project_id"],
                        "git_branch": parsed.git_branch,
                        "parent_session_id": session_id_for(adapter.name, parent_native)
                        if parent_native
                        else None,
                        "started_at": to_iso(parsed.started_at),
                        "ended_at": to_iso(parsed.ended_at),
                        "title": None,
                    }
                )
            row = build_event_row(
                agent=adapter.name,
                session_id=session_id,
                event_id=eid,
                parsed=event,
                cwd=identity["project_cwd"],
                seq=pending_seq,
            )
            row["raw_path"] = str(path)
            if self.store.insert_event(row):
                inserted += 1
                pending_seq += 1
        self.store.upsert_file(
            path=str(path),
            agent=adapter.name,
            size=stat.st_size,
            mtime=stat.st_mtime,
            last_offset=parsed.end_offset,
            adapter_version=adapter.version,
            session_id=session_id if inserted or existing else None,
        )
        if inserted or (existing and full):
            self.store.resequence(session_id)
            affected.add(session_id)
        return inserted
