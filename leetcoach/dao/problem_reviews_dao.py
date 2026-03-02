from __future__ import annotations

from datetime import datetime, timedelta
import sqlite3


def _to_iso(dt: datetime) -> str:
    return dt.isoformat()


def _compute_due_windows(solved_at: str) -> list[tuple[int, str, str]]:
    solved_dt = datetime.fromisoformat(solved_at)
    windows: list[tuple[int, str, str]] = []
    for review_day in (7, 21):
        due_at = solved_dt + timedelta(days=review_day)
        buffer_until = due_at + timedelta(hours=48)
        windows.append((review_day, _to_iso(due_at), _to_iso(buffer_until)))
    return windows


def ensure_review_checkpoints(
    conn: sqlite3.Connection,
    *,
    user_problem_id: int,
    solved_at: str,
    now_iso: str,
) -> None:
    for review_day, due_at, buffer_until in _compute_due_windows(solved_at):
        conn.execute(
            """
            INSERT INTO problem_reviews (
                user_problem_id,
                review_day,
                due_at,
                buffer_until,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_problem_id, review_day) DO UPDATE SET
                due_at = excluded.due_at,
                buffer_until = excluded.buffer_until,
                updated_at = excluded.updated_at
            """,
            (user_problem_id, review_day, due_at, buffer_until, now_iso, now_iso),
        )

