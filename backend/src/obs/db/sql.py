"""SQL escaping and stable session pagination."""

from __future__ import annotations

def escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def sort_clause(sort: str, cursor: str | None) -> tuple[str, str, list]:
    orders = {
        "started_at": "COALESCE(s.started_at, '') DESC, s.id DESC",
        "cost": "COALESCE(s.est_cost_usd, -1) DESC, s.id DESC",
        "tokens": "(COALESCE(s.tokens_in, 0) + COALESCE(s.tokens_out, 0)) DESC, s.id DESC",
        "duration": "COALESCE(s.source_duration_sec, (julianday(s.ended_at) - julianday(s.started_at)) * 86400.0) DESC, s.id DESC",
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
