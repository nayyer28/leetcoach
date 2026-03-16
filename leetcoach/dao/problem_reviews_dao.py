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


def list_due_reviews_for_user(
    conn: sqlite3.Connection, *, user_id: int, now_iso: str
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT
            pr.user_problem_id,
            pr.review_day,
            pr.due_at,
            pr.buffer_until,
            pr.completed_at,
            up.solved_at,
            p.title,
            p.leetcode_slug,
            p.neetcode_slug
        FROM problem_reviews pr
        JOIN user_problems up ON up.id = pr.user_problem_id
        JOIN problems p ON p.id = up.problem_id
        WHERE up.user_id = ?
          AND pr.completed_at IS NULL
          AND pr.due_at <= ?
        ORDER BY pr.due_at ASC
        """,
        (user_id, now_iso),
    ).fetchall()


def list_pending_review_candidates(
    conn: sqlite3.Connection, *, now_iso: str
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT
            pr.id AS review_id,
            pr.user_problem_id,
            pr.review_day,
            pr.due_at,
            pr.buffer_until,
            pr.last_reminded_at,
            up.solved_at,
            p.title,
            p.leetcode_slug,
            p.neetcode_slug,
            u.telegram_chat_id,
            u.timezone,
            u.reminder_daily_max,
            u.reminder_hour_local
        FROM problem_reviews pr
        JOIN user_problems up ON up.id = pr.user_problem_id
        JOIN problems p ON p.id = up.problem_id
        JOIN users u ON u.id = up.user_id
        WHERE pr.completed_at IS NULL
          AND pr.due_at <= ?
        ORDER BY pr.due_at ASC
        """,
        (now_iso,),
    ).fetchall()


def list_pending_review_candidates_for_user(
    conn: sqlite3.Connection, *, user_id: int, now_iso: str
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT
            pr.id AS review_id,
            pr.user_problem_id,
            pr.review_day,
            pr.due_at,
            pr.buffer_until,
            pr.last_reminded_at,
            up.solved_at,
            p.title,
            p.leetcode_slug,
            p.neetcode_slug,
            u.telegram_chat_id,
            u.timezone,
            u.reminder_daily_max,
            u.reminder_hour_local
        FROM problem_reviews pr
        JOIN user_problems up ON up.id = pr.user_problem_id
        JOIN problems p ON p.id = up.problem_id
        JOIN users u ON u.id = up.user_id
        WHERE pr.completed_at IS NULL
          AND up.user_id = ?
          AND pr.due_at <= ?
        ORDER BY pr.due_at ASC
        """,
        (user_id, now_iso),
    ).fetchall()


def list_last_reminded_batch_for_user(
    conn: sqlite3.Connection, *, user_id: int
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        WITH last_batch AS (
            SELECT MAX(pr.last_reminded_at) AS last_reminded_at
            FROM problem_reviews pr
            JOIN user_problems up ON up.id = pr.user_problem_id
            WHERE up.user_id = ?
        )
        SELECT
            pr.id AS review_id,
            pr.user_problem_id,
            pr.review_day,
            pr.due_at,
            pr.buffer_until,
            pr.last_reminded_at,
            up.solved_at,
            p.title,
            p.leetcode_slug,
            p.neetcode_slug,
            u.telegram_chat_id,
            u.timezone,
            u.reminder_daily_max,
            u.reminder_hour_local
        FROM problem_reviews pr
        JOIN user_problems up ON up.id = pr.user_problem_id
        JOIN problems p ON p.id = up.problem_id
        JOIN users u ON u.id = up.user_id
        JOIN last_batch lb ON lb.last_reminded_at = pr.last_reminded_at
        WHERE up.user_id = ?
          AND pr.last_reminded_at IS NOT NULL
        ORDER BY pr.due_at ASC, pr.id ASC
        """,
        (user_id, user_id),
    ).fetchall()


def mark_review_reminded(
    conn: sqlite3.Connection, *, review_id: int, reminded_at: str
) -> bool:
    cur = conn.execute(
        """
        UPDATE problem_reviews
        SET last_reminded_at = ?, updated_at = ?
        WHERE id = ?
          AND completed_at IS NULL
        """,
        (reminded_at, reminded_at, review_id),
    )
    return cur.rowcount > 0


def mark_review_done(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    user_problem_id: int,
    review_day: int,
    completed_at: str,
) -> bool:
    cur = conn.execute(
        """
        UPDATE problem_reviews
        SET completed_at = ?, updated_at = ?
        WHERE user_problem_id = ?
          AND review_day = ?
          AND completed_at IS NULL
          AND EXISTS (
            SELECT 1
            FROM user_problems up
            WHERE up.id = problem_reviews.user_problem_id
              AND up.user_id = ?
          )
        """,
        (completed_at, completed_at, user_problem_id, review_day, user_id),
    )
    return cur.rowcount > 0
