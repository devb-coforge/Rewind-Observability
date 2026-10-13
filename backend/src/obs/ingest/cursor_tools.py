"""Reconcile SQLite tool outcomes with Cursor's transcript calls.

JSONL has no message identifiers. Only pair calls with compatible arguments;
unmatched results remain visible with their SQLite provenance.
"""
from __future__ import annotations

import hashlib
import json
import re

from obs.adapters.lineio import preview
from obs.tool_outcomes import user_declined

NAMES = {
    "read_file_v2": "Read", "run_terminal_command_v2": "Shell",
    "ripgrep_raw_search": "Grep", "glob_file_search": "Glob",
    "todo_write": "TodoWrite", "delete_file": "Delete",
    "read_lints": "ReadLints", "task_v2": "Task", "web_search": "WebSearch",
    "web_fetch": "WebFetch", "get_mcp_tools": "CallMcpTool",
}


def _object(value):
    if isinstance(value, dict):
        return value
    try:
        decoded = json.loads(value)
        return decoded if isinstance(decoded, dict) else {}
    except (ValueError, TypeError):
        return {}


def _args(value):
    aliases = {"targetfile": "path", "relativeworkspacepath": "path",
               "globpattern": "glob", "targetdirectory": "targetdirectory"}
    return {aliases.get(re.sub("_", "", k).lower(), re.sub("_", "", k).lower()): v
            for k, v in _object(value).items()}


def _compatible(call, tool):
    name = call["tool_name"]
    db_name = tool.get("name", "")
    if db_name == "edit_file_v2":
        same_tool = name in {"StrReplace", "Write", "Edit"}
    else:
        same_tool = name == NAMES.get(db_name, db_name)
    if not same_tool:
        return False
    expected = _args(call["tool_input_json"])
    actual = {**_args(tool.get("params")), **_args(tool.get("rawArgs"))}
    identity = {k: v for k, v in expected.items()
                if k not in {"toolcallid", "description", "requiredpermissions"}}
    return bool(identity) and all(k in actual and actual[k] == v for k, v in identity.items())


def sync_tools(store, session, records):
    sid = session["id"]
    # Rebuild this derived slice when SQLite changes, even when JSONL does not.
    unique = {record["key"]: record for record in records}
    fingerprint = hashlib.sha256(("declines-v1:" + json.dumps(unique, sort_keys=True)).encode()).hexdigest()
    meta_key = f"cursor_tools:{sid}"
    old = list(store.index.execute(
        "SELECT rowid, id FROM events WHERE session_id = ? AND id LIKE 'cursor-db:%'", (sid,)))
    if store.get_meta(meta_key) == fingerprint and (old or not records):
        return False
    for row in old:
        for table, column in (("events_fts", "event_id"), ("event_blobs", "event_id"),
                              ("event_raw", "event_id"), ("events", "id")):
            store.index.execute(f"DELETE FROM {table} WHERE {column} = ?", (row["id"],))
    calls = [dict(row) for row in store.index.execute(
        "SELECT * FROM events WHERE session_id = ? AND kind = 'tool_call' ORDER BY seq", (sid,))]
    used = set()
    # Restore previous inferred links; preserve native transcript call ids.
    for call in calls:
        if (call["tool_call_id"] or "").startswith("cursor-db:"):
            store.index.execute("UPDATE events SET tool_call_id = NULL WHERE id = ?", (call["id"],))
            call["tool_call_id"] = None
    ordered = sorted(unique.values(), key=lambda r: (
        r["bubble"].get("startedAtMs") or 0, r["key"]))
    for ordinal, record in enumerate(ordered):
        tool = record["bubble"]["toolFormerData"]
        output = tool.get("result")
        error = tool.get("error")
        declined = user_declined(tool) or user_declined(output)
        decoded = _object(output)
        code = decoded.get("exitCode")
        failed = (tool.get("status") in {"error", "failed"} or bool(error)
                  or bool(decoded.get("error")) or decoded.get("success") is False
                  or (isinstance(code, int) and not isinstance(code, bool) and code != 0))
        if output in (None, "") and not failed and not declined:
            continue
        eid = "cursor-db:" + record["key"]
        native_call_id = tool.get("toolCallId")
        call = next((c for c in calls if c["id"] not in used and native_call_id
                     and c["tool_call_id"] == native_call_id), None)
        if call is None:
            call = next((c for c in calls if c["id"] not in used and not c["tool_call_id"]
                         and _compatible(c, tool)), None)
        link = eid
        name = NAMES.get(tool.get("name"), tool.get("name") or "tool")
        if call is None and declined:
            # Preserve refused command arguments even when JSONL omitted the call.
            args = _object(tool.get("rawArgs")) or _object(tool.get("params"))
            store.insert_event({
                "id": eid + ":call", "session_id": sid, "kind": "tool_call", "role": "assistant",
                "tool_name": name, "tool_call_id": eid, "tool_input_json": json.dumps(args),
                "raw_path": session["source_path"], "raw_offset": 2**60 + ordinal,
                "raw_length": 0, "block_index": 0,
            })
            store.index.execute("INSERT INTO event_raw(event_id, content) VALUES (?, ?)",
                                (eid + ":call", json.dumps(record, ensure_ascii=False)))
        if call is not None:
            used.add(call["id"])
            link = call["tool_call_id"] or eid
            name = call["tool_name"]
            store.index.execute("UPDATE events SET tool_call_id = ? WHERE id = ?", (link, call["id"]))
            # A transcript-provided result already covers this call.
            existing_result = store.index.execute(
                "SELECT id FROM events WHERE session_id = ? AND kind = 'tool_result' AND tool_call_id = ?",
                (sid, link),
            ).fetchone()
            if existing_result:
                if declined:
                    store.index.execute("UPDATE events SET is_declined = 1, is_error = 0 WHERE id = ?",
                                        (existing_result["id"],))
                continue
        if not isinstance(output, str):
            output = json.dumps(output, ensure_ascii=False) if output is not None else ""
        if error:
            output += "\n" + (error if isinstance(error, str) else json.dumps(error))
        if declined and not output:
            output = "User declined this command."
        offset = call["raw_offset"] if call else 2**60 + ordinal
        block = call["block_index"] + 1 if call else 1
        store.insert_event({
            "id": eid, "session_id": sid, "kind": "tool_result", "role": "tool",
            "tool_name": name, "tool_call_id": link, "is_error": failed and not declined, "is_declined": declined,
            "tool_output": output, "tool_output_preview": preview(output), "fts_preview": output[:500],
            "raw_path": call["raw_path"] if call else session["source_path"],
            "raw_offset": offset, "raw_length": 0, "block_index": block,
        })
        store.index.execute("INSERT INTO event_raw(event_id, content) VALUES (?, ?)",
                            (eid, json.dumps(record, ensure_ascii=False)))
    store.set_meta(meta_key, fingerprint)
    store.resequence(sid)
    return True
