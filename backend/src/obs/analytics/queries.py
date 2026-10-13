from __future__ import annotations

import re

from obs.analytics.pricing import Pricing
from obs.db.repo import Store, _escape_like

_FTS_TERM = re.compile(r"[\w./:+-]{2,}")


def to_fts(query: str) -> str:
    terms = _FTS_TERM.findall(query or "")
    if not terms:
        return ""
    return " AND ".join(f'"{term}"' for term in terms[:12])


def search(store: Store, *, q: str, agent: str | None, project: str | None, include_hidden: bool, limit: int) -> list[dict]:
    match = to_fts(q)
    if not match:
        return []
    filters = {
        "agent": agent,
        "project": project,
        "include_hidden": include_hidden,
    }
    where, params = store._session_filters(filters)
    rows = store.index.execute(
        f"""
        SELECT e.id AS event_id, e.session_id, e.seq, e.kind, e.ts,
               snippet(events_fts, 2, '', '', '…', 12) AS snippet,
               s.title AS session_title, s.project_name, s.agent, s.project_id
        FROM events_fts
        JOIN events e ON e.id = events_fts.event_id
        JOIN sessions s ON s.id = e.session_id
        WHERE events_fts MATCH ? AND {where}
        LIMIT ?
        """,
        [match, *params, min(limit, 100)],
    )
    return [
        {
            "event_id": row["event_id"],
            "session_id": row["session_id"],
            "seq": row["seq"],
            "kind": row["kind"],
            "ts": row["ts"],
            "snippet": row["snippet"],
            "session_title": row["session_title"],
            "project_name": row["project_name"],
            "agent": row["agent"],
            "project_id": row["project_id"],
        }
        for row in rows
    ]


def failed_tools(
    store: Store,
    *,
    agent: str | None,
    project: str | None,
    tool: str | None,
    q: str | None,
    include_hidden: bool,
    limit: int,
) -> dict:
    where, params = store._session_filters(
        {"agent": agent, "project": project, "include_hidden": include_hidden}
    )
    base = f"""
        FROM events r
        JOIN sessions s ON s.id = r.session_id
        LEFT JOIN events c
          ON c.session_id = r.session_id
         AND c.kind = 'tool_call'
         AND c.tool_call_id = r.tool_call_id
        WHERE r.kind = 'tool_result' AND r.is_error = 1 AND {where}
    """
    by_tool = [
        {"tool_name": row["tool_name"], "count": row["n"]}
        for row in store.index.execute(
            f"SELECT COALESCE(c.tool_name, r.tool_name, 'unknown') AS tool_name, COUNT(*) AS n {base} "
            "GROUP BY 1 ORDER BY n DESC",
            params,
        )
    ]
    extra = ""
    extra_params: list = []
    if tool:
        extra += " AND COALESCE(c.tool_name, r.tool_name, 'unknown') = ?"
        extra_params.append(tool)
    if q:
        like = f"%{_escape_like(q)}%"
        extra += (
            " AND (COALESCE(r.tool_output_preview, '') LIKE ? ESCAPE '\\'"
            " OR COALESCE(c.tool_input_json, '') LIKE ? ESCAPE '\\')"
        )
        extra_params.extend([like, like])
    rows = store.index.execute(
        f"""
        SELECT r.id AS event_id, r.session_id, r.seq, r.ts,
               COALESCE(c.tool_name, r.tool_name, 'unknown') AS tool_name,
               c.tool_input_json AS tool_input,
               r.tool_output_preview AS error_preview,
               s.title AS session_title, s.project_name, s.agent, s.project_id
        {base} {extra}
        ORDER BY COALESCE(r.ts, '') DESC
        LIMIT ?
        """,
        [*params, *extra_params, min(limit, 100)],
    )
    return {
        "by_tool": by_tool,
        "total": sum(item["count"] for item in by_tool),
        "hits": [dict(row) for row in rows],
    }


def summary(store: Store, filters: dict) -> dict:
    where, params = store._session_filters(filters)
    row = store.index.execute(
        f"""
        SELECT
          COUNT(*) AS sessions,
          SUM(CASE WHEN started_at IS NULL THEN 1 ELSE 0 END) AS missing_start,
          SUM(tokens_in) AS tokens_in,
          SUM(tokens_out) AS tokens_out,
          SUM(tokens_cache_read) AS tokens_cache_read,
          SUM(tokens_cache_write) AS tokens_cache_write,
          SUM(est_cost_usd) AS est_cost_usd,
          SUM(n_tool_calls) AS tool_calls,
          SUM(n_tool_errors) AS tool_errors,
          SUM(CASE WHEN usage_coverage = 'none' THEN 1 ELSE 0 END) AS missing_usage,
          SUM(CASE WHEN usage_coverage = 'partial' THEN 1 ELSE 0 END) AS partial_usage,
          SUM(CASE WHEN est_cost_usd IS NULL THEN 1 ELSE 0 END) AS missing_cost,
          SUM(cost_partial) AS partial_cost
        FROM sessions s
        WHERE {where}
        """,
        params,
    ).fetchone()
    from obs.db.repo import _duration

    seconds = []
    for item in store.index.execute(
        f"SELECT started_at, ended_at, source_duration_sec FROM sessions s WHERE {where}", params,
    ):
        value = item["source_duration_sec"]
        if value is None:
            value = _duration(item["started_at"], item["ended_at"])
        if value is not None:
            seconds.append(value)
    sessions = row["sessions"] or 0
    if sessions == 0 or (row["missing_usage"] == sessions):
        usage_coverage = "none"
    elif row["partial_usage"] or row["missing_usage"]:
        usage_coverage = "partial"
    else:
        usage_coverage = "complete"
    if sessions == 0 or row["missing_cost"] == sessions:
        cost_coverage = "none"
    elif row["partial_cost"] or row["missing_cost"]:
        cost_coverage = "partial"
    else:
        cost_coverage = "complete"
    return {
        "sessions": sessions,
        "sessions_missing_start": row["missing_start"] or 0,
        "tokens_in": row["tokens_in"],
        "tokens_out": row["tokens_out"],
        "tokens_cache_read": row["tokens_cache_read"],
        "tokens_cache_write": row["tokens_cache_write"],
        "est_cost_usd": row["est_cost_usd"],
        "usage_coverage": usage_coverage,
        "cost_coverage": cost_coverage,
        "tool_calls": row["tool_calls"] or 0,
        "tool_errors": row["tool_errors"] or 0,
        "median_duration_sec": _median(seconds),
        "sessions_missing_usage": row["missing_usage"] or 0,
    }


def timeseries(store: Store, filters: dict, *, metric: str, bucket: str, group_by: str | None) -> dict:
    where, params = store._session_filters(filters)
    bucket_expr = "substr(s.started_at, 1, 10)" if bucket != "week" else _week_expr("s.started_at")
    if group_by == "model":
        group_expr = "m.model"
        join = "JOIN session_models m ON m.session_id = s.id"
    elif group_by == "project":
        group_expr = "COALESCE(s.project_name, '(unknown)')"
        join = ""
    elif group_by == "agent":
        group_expr = "s.agent"
        join = ""
    else:
        group_expr = "'all'"
        join = ""
    value_expr = {
        "sessions": "COUNT(*)",
        "tokens": "SUM(CASE WHEN s.tokens_in IS NULL AND s.tokens_out IS NULL THEN NULL ELSE COALESCE(s.tokens_in, 0) + COALESCE(s.tokens_out, 0) END)",
        "cost": "SUM(s.est_cost_usd)",
        "duration": "AVG(COALESCE(s.source_duration_sec, (julianday(s.ended_at) - julianday(s.started_at)) * 86400.0))",
    }.get(metric, "COUNT(*)")
    rows = store.index.execute(
        f"""
        SELECT {bucket_expr} AS bucket, {group_expr} AS grp, {value_expr} AS value
        FROM sessions s
        {join}
        WHERE {where} AND s.started_at IS NOT NULL
        GROUP BY bucket, grp
        ORDER BY bucket, grp
        """,
        params,
    )
    return {
        "metric": metric,
        "bucket": bucket if bucket in {"day", "week"} else "day",
        "group_by": group_by,
        "points": [
            {"bucket": row["bucket"], "group": row["grp"], "value": row["value"]}
            for row in rows
            if row["bucket"]
        ],
    }


def tools(store: Store, filters: dict) -> dict:
    where, params = store._session_filters(filters)
    rows = store.index.execute(
        f"""
        WITH filtered AS (
            SELECT e.* FROM events e JOIN sessions s ON s.id = e.session_id WHERE {where}
        ), counts AS (
            SELECT tool_name, COUNT(*) AS calls, 0 AS errors
            FROM filtered WHERE kind = 'tool_call' AND tool_name IS NOT NULL
            GROUP BY tool_name
            UNION ALL
            SELECT COALESCE((SELECT c.tool_name FROM filtered c
                             WHERE c.kind = 'tool_call' AND c.session_id = r.session_id
                               AND c.tool_call_id = r.tool_call_id LIMIT 1), r.tool_name),
                   0, COUNT(*)
            FROM filtered r WHERE r.kind = 'tool_result' AND r.is_error = 1
            GROUP BY 1
            UNION ALL
            SELECT c.tool_name, 0, COUNT(*) FROM filtered c
            WHERE c.kind = 'tool_call' AND c.is_error = 1 AND NOT EXISTS (
                SELECT 1 FROM filtered r WHERE r.kind = 'tool_result'
                  AND r.session_id = c.session_id AND r.tool_call_id = c.tool_call_id AND r.is_error = 1
            ) GROUP BY c.tool_name
        )
        SELECT tool_name, SUM(calls) AS calls, SUM(errors) AS errors
        FROM counts WHERE tool_name IS NOT NULL GROUP BY tool_name
        ORDER BY calls DESC
        """,
        params,
    )
    items = []
    for row in rows:
        calls = row["calls"] or 0
        errors = row["errors"] or 0
        items.append(
            {
                "tool_name": row["tool_name"],
                "calls": calls,
                "errors": errors,
                "error_rate": (errors / calls) if calls else 0,
            }
        )
    return {"tools": items}


def _week_expr(column: str) -> str:
    trimmed = f"replace(substr({column}, 1, 19), 'T', ' ')"
    return f"strftime('%Y-W%W', {trimmed})"


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return float(ordered[mid - 1] + ordered[mid]) / 2


def pricing_unused(pricing: Pricing) -> None:
    """Pricing is applied at ingest; analytics reads stored estimates."""
    del pricing
