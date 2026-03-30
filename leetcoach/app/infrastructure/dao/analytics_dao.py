from __future__ import annotations

from datetime import datetime
import sqlite3
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from leetcoach.app.application.shared.patterns import canonical_pattern_label


def _resolve_timezone(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _local_date(iso_ts: str, timezone_name: str) -> str:
    dt = datetime.fromisoformat(iso_ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(_resolve_timezone(timezone_name)).date().isoformat()


def list_aggregated_user_problems(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    group_by: str,
    metric: str,
    sort: str,
    limit: int,
    difficulty: str | None,
    pattern: str | None,
    solved_date_from: str | None,
    solved_date_to: str | None,
) -> list[sqlite3.Row]:
    conn.create_function("canonical_pattern_label", 1, canonical_pattern_label)
    conn.create_function("local_date", 2, _local_date)

    group_expr_map = {
        "none": "'all'",
        "difficulty": "lower(p.difficulty)",
        "pattern": "COALESCE(canonical_pattern_label(up.pattern), up.pattern)",
        "solved_date": "local_date(up.solved_at, u.timezone)",
        "solved_month": "substr(local_date(up.solved_at, u.timezone), 1, 7)",
    }
    metric_expr_map = {
        "problem_count": "COUNT(*)",
        "review_count_sum": "COALESCE(SUM(up.review_count), 0)",
        "strength_score": "COUNT(*) + COALESCE(SUM(up.review_count), 0)",
    }
    sort_expr_map = {
        "metric_desc": "metric_value DESC, group_value ASC",
        "metric_asc": "metric_value ASC, group_value ASC",
        "group_asc": "group_value ASC",
        "group_desc": "group_value DESC",
    }

    group_expr = group_expr_map[group_by]
    metric_expr = metric_expr_map[metric]
    sort_expr = sort_expr_map[sort]

    return conn.execute(
        f"""
        SELECT
            {group_expr} AS group_value,
            {metric_expr} AS metric_value
        FROM user_problems up
        JOIN problems p ON p.id = up.problem_id
        JOIN users u ON u.id = up.user_id
        WHERE up.user_id = ?
          AND (? IS NULL OR lower(p.difficulty) = ?)
          AND (? IS NULL OR canonical_pattern_label(up.pattern) = ?)
          AND (? IS NULL OR local_date(up.solved_at, u.timezone) >= ?)
          AND (? IS NULL OR local_date(up.solved_at, u.timezone) <= ?)
        GROUP BY {group_expr}
        ORDER BY {sort_expr}
        LIMIT ?
        """,
        (
            user_id,
            difficulty,
            difficulty,
            pattern,
            pattern,
            solved_date_from,
            solved_date_from,
            solved_date_to,
            solved_date_to,
            limit,
        ),
    ).fetchall()
