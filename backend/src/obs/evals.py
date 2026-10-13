"""Freeze a session slice into user.db. Cases are copies, not pointers."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from obs.analytics.pricing import Pricing
from obs.db.repo import Store, _load_usage
from obs.models import Usage


def freeze_case(
    store: Store,
    pricing: Pricing,
    *,
    session_id: str,
    from_seq: int | None,
    to_seq: int | None,
) -> dict:
    session = store.get_session(session_id)
    if session is None:
        raise KeyError(session_id)
    events = [
        event
        for event in store.events_for_session(session_id)
        if (from_seq is None or event["seq"] >= from_seq)
        and (to_seq is None or event["seq"] <= to_seq)
    ]
    prompt = None
    final = None
    for event in events:
        if prompt is None and event["role"] == "user" and event["kind"] == "message" and event["text"]:
            prompt = event["text"]
        if event["role"] == "assistant" and event["kind"] == "message" and event["text"]:
            final = event["text"]
    calls = {event["tool_call_id"]: event for event in events if event["kind"] == "tool_call"}
    results = {
        event["tool_call_id"]: event
        for event in events
        if event["kind"] == "tool_result" and event["tool_call_id"]
    }
    summary = []
    for call_id, call in calls.items():
        paths = [item.get("path") for item in json.loads(call["paths_json"] or "[]")]
        result = results.get(call_id)
        summary.append(
            {
                "tool_name": call["tool_name"],
                "paths": [path for path in paths if path],
                "is_error": bool(result["is_error"]) if result is not None else bool(call["is_error"]),
            }
        )
    tokens, cost, model = _usage_for(events, pricing, cached_input_included=session["agent"] == "codex")
    now = _now()
    case_id = str(uuid.uuid4())
    store.user.execute(
        """
        INSERT INTO eval_cases(
          id, session_id, project_id, project_cwd, project_name, agent, model, prompt,
          final_message, tool_summary_json, tokens_in, tokens_out, tokens_cache_read,
          tokens_cache_write, est_cost_usd, from_seq, to_seq, verdict, note, created_at, updated_at
        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'unset', NULL, ?, ?)
        """,
        (
            case_id,
            session_id,
            session["project_id"],
            session["project_cwd"],
            session["project_name"],
            session["agent"],
            model,
            prompt,
            final,
            json.dumps(summary),
            tokens["input_tokens"],
            tokens["output_tokens"],
            tokens["cache_read_tokens"],
            tokens["cache_write_tokens"],
            cost,
            from_seq,
            to_seq,
            now,
            now,
        ),
    )
    return case_dict(store.user.execute("SELECT * FROM eval_cases WHERE id = ?", (case_id,)).fetchone())


def list_cases(store: Store, *, project: str | None, model: str | None, verdict: str | None) -> list[dict]:
    clauses = ["1=1"]
    params: list = []
    if project:
        clauses.append("project_id = ?")
        params.append(project)
    if model:
        clauses.append("model = ?")
        params.append(model)
    if verdict:
        clauses.append("verdict = ?")
        params.append(verdict)
    rows = store.user.execute(
        f"SELECT * FROM eval_cases WHERE {' AND '.join(clauses)} ORDER BY created_at DESC",
        params,
    )
    return [case_dict(row, preview=True) for row in rows]


def get_case(store: Store, case_id: str) -> dict | None:
    row = store.user.execute("SELECT * FROM eval_cases WHERE id = ?", (case_id,)).fetchone()
    return None if row is None else case_dict(row)


def update_case(store: Store, case_id: str, *, verdict: str | None, note: str | None) -> dict | None:
    current = get_case(store, case_id)
    if current is None:
        return None
    if verdict is not None and verdict not in {"unset", "pass", "fail"}:
        raise ValueError("verdict must be unset, pass, or fail")
    store.user.execute(
        """
        UPDATE eval_cases
        SET verdict = COALESCE(?, verdict),
            note = CASE WHEN ? THEN note ELSE ? END,
            updated_at = ?
        WHERE id = ?
        """,
        (
            verdict,
            1 if note is None else 0,
            note,
            _now(),
            case_id,
        ),
    )
    return get_case(store, case_id)


def delete_case(store: Store, case_id: str) -> bool:
    cur = store.user.execute("DELETE FROM eval_cases WHERE id = ?", (case_id,))
    return cur.rowcount > 0


def summarize(store: Store, *, project: str | None) -> dict:
    clauses = ["1=1"]
    params: list = []
    if project:
        clauses.append("project_id = ?")
        params.append(project)
    rows = list(
        store.user.execute(
            f"SELECT * FROM eval_cases WHERE {' AND '.join(clauses)}",
            params,
        )
    )
    groups: dict[str, list] = {}
    for row in rows:
        groups.setdefault(row["model"] or "(unknown)", []).append(row)
    result = []
    for model, items in sorted(groups.items()):
        verdicts = [item["verdict"] for item in items if item["verdict"] in {"pass", "fail"}]
        passes = sum(1 for item in verdicts if item == "pass")
        costs = [item["est_cost_usd"] for item in items if item["est_cost_usd"] is not None]
        token_values = []
        for item in items:
            if item["tokens_in"] is None and item["tokens_out"] is None:
                continue
            token_values.append((item["tokens_in"] or 0) + (item["tokens_out"] or 0))
        result.append(
            {
                "model": model,
                "n": len(items),
                "n_verdict": len(verdicts),
                "pass_rate": (passes / len(verdicts)) if verdicts else None,
                "median_cost": _median(costs),
                "median_tokens": _median(token_values),
            }
        )
    return {
        "note": (
            "Models are compared only on the cases you chose to freeze. "
            "That is a biased sample of your work, and a verdict is a label you set."
        ),
        "groups": result,
    }


def case_dict(row, *, preview: bool = False) -> dict:
    prompt = row["prompt"] or ""
    return {
        "id": row["id"],
        "session_id": row["session_id"],
        "project_id": row["project_id"],
        "project_cwd": row["project_cwd"],
        "project_name": row["project_name"],
        "agent": row["agent"],
        "model": row["model"],
        "prompt": (prompt[:240] if preview else prompt) or None,
        "final_message": None if preview else row["final_message"],
        "tool_summary": json.loads(row["tool_summary_json"] or "[]"),
        "tokens_in": row["tokens_in"],
        "tokens_out": row["tokens_out"],
        "tokens_cache_read": row["tokens_cache_read"],
        "tokens_cache_write": row["tokens_cache_write"],
        "est_cost_usd": row["est_cost_usd"],
        "from_seq": row["from_seq"],
        "to_seq": row["to_seq"],
        "verdict": row["verdict"],
        "note": row["note"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _usage_for(events, pricing: Pricing, *, cached_input_included: bool = False) -> tuple[dict, float | None, str | None]:
    has_token_count = any(event["usage_origin"] == "token_count" and event["usage_json"] for event in events)
    seen: set[str] = set()
    totals = {
        "input_tokens": None,
        "output_tokens": None,
        "cache_read_tokens": None,
        "cache_write_tokens": None,
    }
    cost = 0.0
    any_cost = False
    last_model = None
    model = None
    for event in events:
        if event["model"]:
            last_model = event["model"]
            model = event["model"]
        usage = _load_usage(event["usage_json"])
        origin = event["usage_origin"]
        if not usage:
            continue
        if has_token_count and origin != "token_count":
            continue
        if event["message_id"]:
            if event["message_id"] in seen:
                continue
            seen.add(event["message_id"])
        for field in totals:
            value = getattr(usage, field)
            if value is not None:
                totals[field] = (totals[field] or 0) + value
        estimate = pricing.estimate(event["model"] or last_model, usage, cached_input_included=cached_input_included)
        if estimate is not None:
            any_cost = True
            cost += estimate
    return totals, cost if any_cost else None, model


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return float(ordered[mid - 1] + ordered[mid]) / 2


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
