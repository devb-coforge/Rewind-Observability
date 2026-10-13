"""Serialization operations."""

from __future__ import annotations

import json
import sqlite3

from obs.analytics.duration import duration_seconds
from obs.analytics.usage import load_usage
from obs.identity import classify_paths, path_is_allowed, project_identity
from obs.models import ParsedEvent
from obs.shared.lineio import preview, to_iso


def session_dict(
    row: sqlite3.Row,
    *,
    group_paths: dict[str, str | None],
    project_hidden: bool,
    hidden: bool,
) -> dict:
    models = json.loads(row["models_json"] or "[]")
    duration = row["source_duration_sec"]
    if duration is None:
        duration = duration_seconds(row["started_at"], row["ended_at"])
    return {
        "id": row["id"],
        "agent": row["agent"],
        "native_id": row["native_id"],
        "source_path": row["source_path"],
        "project_cwd": row["project_cwd"],
        "project_group_cwd": group_paths.get(row["project_id"]),
        "project_name": row["project_name"],
        "project_id": row["project_id"],
        "project_hidden": project_hidden,
        "hidden": hidden,
        "git_branch": row["git_branch"],
        "models": models,
        "selected_model": row["selected_model"],
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


def event_dict(row: sqlite3.Row, dismissals: list[str] | None = None) -> dict:
    paths = json.loads(row["paths_json"] or "[]")
    for item in paths:
        item["dismissed"] = bool(dismissals) and path_is_allowed(item.get("resolved") or "", dismissals or [])
        item["allowed"] = (not item.get("outside")) or item["dismissed"]
    usage = load_usage(row["usage_json"])
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
        "is_declined": bool(row["is_declined"]),
        "model": row["model"],
        "usage": usage.as_dict() if usage else None,
        "raw": {"path": row["raw_path"], "offset": row["raw_offset"], "length": row["raw_length"]},
        "paths": paths,
    }


def build_event_row(
    *,
    agent: str,
    session_id: str,
    event_id: str,
    parsed: ParsedEvent,
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
