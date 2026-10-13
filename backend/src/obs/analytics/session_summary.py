"""Session summary operations."""

from __future__ import annotations

from typing import TYPE_CHECKING
import json

from obs.analytics.pricing import Pricing
from obs.analytics.usage import load_usage
from obs.identity import classify_paths, path_is_allowed

if TYPE_CHECKING:
    from obs.db.repo import Store


def recompute(
    store: Store,
    session_id: str,
    pricing: Pricing,
    *,
    allow_prefixes: list[str],
    dismissals: list[str],
) -> None:
    session = store.get_session(session_id)
    if session is None:
        return
    rows = list(
        store.index.execute(
            "SELECT * FROM events WHERE session_id = ? ORDER BY seq, raw_offset, block_index",
            (session_id,),
        )
    )
    if not rows:
        store.index.execute("DELETE FROM session_models WHERE session_id = ?", (session_id,))
        store.index.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
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
    models: list[str] = json.loads(session["source_models_json"] or "[]")
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
            if session["agent"] == "claude_code":
                from obs.shared.transcripts import title_prompt

                title = title_prompt(row["text"])
            else:
                title = " ".join(row["text"].split())[:120]
        if row["role"] == "user" and row["kind"] == "message":
            n_user += 1
        if row["kind"] == "tool_call":
            n_tools += 1
        if row["kind"] == "tool_result" and row["is_error"]:
            n_errors += 1
            if row["tool_call_id"]:
                error_result_ids.add(row["tool_call_id"])

        usage = load_usage(row["usage_json"])
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
            store.index.execute(
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
        estimate = pricing.estimate(model, usage, cached_input_included=session["agent"] == "codex")
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
        if row["kind"] == "tool_call":
            from obs.identity import extract_path_refs

            paths = classify_paths(session["project_cwd"], extract_path_refs(
                row["tool_name"], json.loads(row["tool_input_json"] or "null")))
            store.index.execute("UPDATE events SET paths_json = ? WHERE id = ?",
                               (json.dumps(paths) if paths else None, row["id"]))
        if any(
            item.get("outside") and not path_is_allowed(item.get("resolved") or "", prefixes)
            for item in paths
        ):
            boundary += 1

    started = min((row["ts"] for row in rows if row["ts"]), default=session["started_at"])
    ended = max((row["ts"] for row in rows if row["ts"]), default=session["ended_at"])
    store.index.execute("DELETE FROM session_models WHERE session_id = ?", (session_id,))
    store.index.executemany(
        "INSERT INTO session_models(session_id, model) VALUES(?, ?)",
        [(session_id, model) for model in models],
    )
    store.index.execute(
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
