"""Read Cursor's local Agent JSONL transcripts, leaving internal databases untouched."""

from __future__ import annotations

from pathlib import Path
import json
import logging
import math
import os
import sqlite3
import sys

from obs.adapters.claude_code import _blocks, _usage
from obs.adapters.detect import infer_agent_from_path
from obs.adapters.lineio import complete_lines, loads_obj, parse_ts, stringify, to_iso
from obs.models import ParsedEvent, ParseResult

log = logging.getLogger(__name__)


class CursorAdapter:
    name = "cursor"
    version = 2

    def detect(self, root: Path) -> bool:
        return infer_agent_from_path(root) == self.name

    def session_titles(self, root: Path, user_data_dir: Path | None = None) -> dict[str, str] | None:
        metadata = self.session_metadata(root, user_data_dir)
        return None if metadata is None else {
            sid: entry["title"] for sid, entry in metadata.items() if entry.get("title")
        }

    def session_metadata(self, root: Path, user_data_dir: Path | None = None) -> dict[str, dict] | None:
        """Read names, creation dates and model metadata without importing chat bodies.

        Unavailable metadata preserves previously imported names. A readable index
        without a name restores the transcript-derived title.
        """
        if user_data_dir is not None:
            base = Path(os.path.expandvars(str(user_data_dir))).expanduser()
        elif (root / "user-data").is_dir():
            base = root / "user-data"
        elif root.resolve() == (Path.home() / ".cursor").resolve():
            if sys.platform == "darwin":
                base = Path.home() / "Library/Application Support/Cursor/User"
            elif sys.platform == "win32":
                base = Path(os.environ.get("APPDATA", str(Path.home() / "AppData/Roaming"))) / "Cursor/User"
            else:
                base = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "Cursor/User"
        else:
            return None
        databases = sorted((base / "workspaceStorage").glob("*/state.vscdb"))
        global_db = base / "globalStorage/state.vscdb"
        if global_db.is_file():
            databases.append(global_db)
        if not databases:
            return None
        metadata: dict[str, dict] = {}
        try:
            for path in databases:
                # mode=ro reads the live WAL too; immutable=1 would miss recent renames.
                db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)
                try:
                    db.execute("PRAGMA query_only = ON")
                    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                    if "ItemTable" in tables:
                        row = db.execute("SELECT value FROM ItemTable WHERE key='composer.composerData'").fetchone()
                        if row:
                            data = json.loads(row[0])
                            entries = data.get("allComposers", []) if isinstance(data, dict) else []
                            if isinstance(entries, list):
                                for entry in entries:
                                    if isinstance(entry, dict):
                                        _save_metadata(metadata, entry.get("composerId"), entry)
                    if "cursorDiskKV" in tables:
                        # Project metadata inside SQLite rather than loading chat bodies.
                        for key, name, created_at, selected_model, workspace in db.execute("""
                            SELECT key, json_extract(value, '$.name'), json_extract(value, '$.createdAt'),
                                   json_extract(value, '$.modelConfig.modelName'),
                                   json_extract(value, '$.workspaceIdentifier') FROM cursorDiskKV
                            WHERE key LIKE 'composerData:%' AND json_valid(value)
                        """):
                            _save_metadata(metadata, key.removeprefix("composerData:"), {
                                "name": name, "createdAt": created_at,
                                "modelConfig": {"modelName": selected_model},
                                "workspaceIdentifier": json.loads(workspace) if workspace else None,
                            })
                        durations: dict[str, dict[str, float]] = {}
                        for key, duration in db.execute("""
                            SELECT key, json_extract(value, '$.turnDurationMs') FROM cursorDiskKV
                            WHERE key LIKE 'bubbleId:%' AND json_valid(value)
                              AND json_type(value, '$.turnDurationMs') IN ('integer', 'real')
                        """):
                            parts = key.split(":")
                            if len(parts) == 3 and math.isfinite(duration) and duration >= 0:
                                durations.setdefault(parts[1], {})[key] = duration
                        for sid, values in durations.items():
                            metadata.setdefault(sid, {}).setdefault("turn_durations", {}).update(values)
                        for key, value in db.execute("""
                            SELECT key, value FROM cursorDiskKV
                            WHERE key LIKE 'bubbleId:%' AND json_valid(value)
                              AND json_type(value, '$.toolFormerData') = 'object'
                        """):
                            parts = key.split(":")
                            if len(parts) == 3:
                                metadata.setdefault(parts[1], {}).setdefault("tools", []).append({
                                    "key": key, "database": str(path), "bubble": json.loads(value),
                                })
                        for key, model in db.execute("""
                            SELECT key, json_extract(value, '$.modelInfo.modelName') FROM cursorDiskKV
                            WHERE key LIKE 'bubbleId:%' AND json_valid(value)
                            ORDER BY key
                        """):
                            parts = key.split(":")
                            model = _concrete_model(model)
                            if len(parts) == 3 and parts[1] and model:
                                models = metadata.setdefault(parts[1], {}).setdefault("models", [])
                                if model not in models:
                                    models.append(model)
                    if "composerHeaders" in tables:
                        for sid, value in db.execute("SELECT composerId, value FROM composerHeaders"):
                            data = json.loads(value)
                            if isinstance(data, dict):
                                _save_metadata(metadata, sid, data)
                finally:
                    db.close()
        except (OSError, sqlite3.Error, ValueError, TypeError):
            log.warning("could not read Cursor session metadata from %s", base)
            return None
        for entry in metadata.values():
            if entry.get("turn_durations"):
                entry["duration_sec"] = sum(entry.pop("turn_durations").values()) / 1000
        return metadata

    def discover(self, root: Path) -> list[Path]:
        base = root / "projects"
        if not base.is_dir():
            return []
        return sorted(
            path for path in base.rglob("*.jsonl")
            if path.is_file() and "agent-transcripts" in path.relative_to(base).parts
        )

    def native_id_from_path(self, path: Path) -> str | None:
        if path.parent.name == "subagents":
            # Subagent names can repeat in different conversations.
            return f"{path.parent.parent.name}:{path.stem}"
        return path.stem or None

    def parent_native_id(self, path: Path) -> str | None:
        return path.parent.parent.name if path.parent.name == "subagents" else None

    def parse(self, path: Path, start_offset: int) -> ParseResult:
        lines, end = complete_lines(path.read_bytes(), start_offset)
        workspace = next((p.parent.name for p in path.parents if p.name == "agent-transcripts"), None)
        result = ParseResult(
            native_id=self.native_id_from_path(path),
            parent_native_id=self.parent_native_id(path),
            project_key=f"cursor-workspace:{workspace}" if workspace else None,
            project_name=workspace,
            end_offset=end,
        )
        for offset, length, payload in lines:
            obj, ok = loads_obj(payload)
            if obj is None and not payload.strip():
                continue
            ts = parse_ts(obj.get("timestamp")) if obj else None
            if ts is not None:
                result.started_at = min(result.started_at or ts, ts)
                result.ended_at = max(result.ended_at or ts, ts)
            if obj and isinstance(obj.get("cwd"), str) and obj["cwd"]:
                result.project_cwd = obj["cwd"]
            message = obj.get("message") if obj else None
            role = obj.get("role") if obj else None
            model = message.get("model") if isinstance(message, dict) else None
            model = model if isinstance(model, str) else None
            if model:
                result.models.append(model)
            usage = _usage(message.get("usage")) if isinstance(message, dict) else None
            if role in ("user", "assistant") and isinstance(message, dict):
                blocks = _blocks(message.get("content"), role)
            elif obj and obj.get("type") == "turn_ended":
                status = obj.get("status")
                blocks = [{
                    "role": "system", "kind": "system",
                    "text": f"Turn ended: {status}" + (f"\n{stringify(obj['error'])}" if obj.get("error") else ""),
                    "is_error": status in ("error", "failed") or bool(obj.get("error")),
                }]
            else:
                blocks = [{"role": "system", "kind": "unknown", "text": (
                    stringify(obj) if ok else payload.decode("utf-8", errors="replace")
                )[:2000]}]
            for index, block in enumerate(blocks):
                # Most Cursor records lack ids and metadata. Byte offsets provide
                # event identity; unavailable timestamps, model and usage stay null.
                result.events.append(ParsedEvent(
                    native_id=f"{result.native_id}:{offset}", parent_native_id=None, block_index=index,
                    ts=ts, model=model, raw_offset=offset, raw_length=length,
                    usage=usage if index == 0 else None,
                    usage_origin="message" if index == 0 and usage else None,
                    message_id=message.get("id") if isinstance(message, dict) and isinstance(message.get("id"), str) else None,
                    **block,
                ))
        result.models = list(dict.fromkeys(result.models))
        return result


def _save_metadata(metadata: dict[str, dict], sid, data: dict) -> None:
    if not isinstance(sid, str) or not sid:
        return
    entry = metadata.setdefault(sid, {})
    workspace = data.get("workspaceIdentifier")
    uri = workspace.get("uri") if isinstance(workspace, dict) else None
    cwd = uri.get("fsPath") if isinstance(uri, dict) and uri.get("scheme") == "file" else None
    if isinstance(cwd, str) and cwd.strip():
        entry["project_cwd"] = cwd
    name = data.get("name")
    if isinstance(name, str):
        entry["title"] = name.strip() or None
    config = data.get("modelConfig")
    if isinstance(config, dict):
        entry["selected_model"] = _concrete_model(config.get("modelName"))
    try:
        # createdAt is the recorded conversation creation time. lastUpdatedAt
        # is not an end time and must not become a duration estimate.
        created = parse_ts(data.get("createdAt"))
    except (ValueError, OverflowError, OSError):
        created = None
    if created is not None:
        entry["started_at"] = to_iso(created)


def _concrete_model(value) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value if value and value.lower() not in {"default", "auto"} else None
