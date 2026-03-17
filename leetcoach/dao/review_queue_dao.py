from __future__ import annotations

import sqlite3


def next_queue_position(conn: sqlite3.Connection, *, user_id: int) -> int:
    row = conn.execute(
        """
        SELECT COALESCE(MAX(queue_position), 0) AS max_position
        FROM user_problems
        WHERE user_id = ?
        """,
        (user_id,),
    ).fetchone()
    max_position = int(row["max_position"]) if row is not None else 0
    return max_position + 10


def ensure_review_queue_state(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    user_problem_id: int,
    now_iso: str,
) -> None:
    row = conn.execute(
        """
        SELECT queue_position
        FROM user_problems
        WHERE id = ?
          AND user_id = ?
        """,
        (user_problem_id, user_id),
    ).fetchone()
    if row is None:
        raise RuntimeError("user_problem not found for queue initialization")
    if int(row["queue_position"]) > 0:
        return
    conn.execute(
        """
        UPDATE user_problems
        SET queue_position = ?, updated_at = ?
        WHERE id = ?
          AND user_id = ?
        """,
        (next_queue_position(conn, user_id=user_id), now_iso, user_problem_id, user_id),
    )


def list_outstanding_reviews_for_user(
    conn: sqlite3.Connection, *, user_id: int
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT
            up.id AS user_problem_id,
            up.user_id,
            p.title,
            p.leetcode_slug,
            p.neetcode_slug,
            up.solved_at,
            up.review_count,
            up.last_review_requested_at,
            up.last_reviewed_at,
            up.queue_position
        FROM user_problems up
        JOIN problems p ON p.id = up.problem_id
        WHERE up.user_id = ?
          AND up.last_review_requested_at IS NOT NULL
          AND (
            up.last_reviewed_at IS NULL
            OR up.last_review_requested_at > up.last_reviewed_at
          )
        ORDER BY up.last_review_requested_at ASC, up.queue_position ASC
        """,
        (user_id,),
    ).fetchall()


def list_next_review_candidates_for_user(
    conn: sqlite3.Connection, *, user_id: int
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT
            up.id AS user_problem_id,
            up.user_id,
            p.title,
            p.leetcode_slug,
            p.neetcode_slug,
            up.solved_at,
            up.review_count,
            up.last_review_requested_at,
            up.last_reviewed_at,
            up.queue_position,
            u.telegram_chat_id,
            u.timezone,
            u.reminder_daily_max,
            u.reminder_hour_local
        FROM user_problems up
        JOIN problems p ON p.id = up.problem_id
        JOIN users u ON u.id = up.user_id
        WHERE up.user_id = ?
          AND (
            up.last_review_requested_at IS NULL
            OR (
              up.last_reviewed_at IS NOT NULL
              AND up.last_review_requested_at <= up.last_reviewed_at
            )
          )
        ORDER BY up.queue_position ASC
        """,
        (user_id,),
    ).fetchall()


def list_next_review_candidates_for_scheduler(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT
            up.id AS user_problem_id,
            up.user_id,
            p.title,
            p.leetcode_slug,
            p.neetcode_slug,
            up.solved_at,
            up.review_count,
            up.last_review_requested_at,
            up.last_reviewed_at,
            up.queue_position,
            u.telegram_chat_id,
            u.timezone,
            u.reminder_daily_max,
            u.reminder_hour_local
        FROM user_problems up
        JOIN problems p ON p.id = up.problem_id
        JOIN users u ON u.id = up.user_id
        WHERE (
            up.last_review_requested_at IS NULL
            OR (
              up.last_reviewed_at IS NOT NULL
              AND up.last_review_requested_at <= up.last_reviewed_at
            )
          )
        ORDER BY u.id ASC, up.queue_position ASC
        """
    ).fetchall()


def list_last_requested_batch_for_user(
    conn: sqlite3.Connection, *, user_id: int
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        WITH last_batch AS (
            SELECT MAX(last_review_requested_at) AS requested_at
            FROM user_problems
            WHERE user_id = ?
        )
        SELECT
            up.id AS user_problem_id,
            up.user_id,
            p.title,
            p.leetcode_slug,
            p.neetcode_slug,
            up.solved_at,
            up.review_count,
            up.last_review_requested_at,
            up.last_reviewed_at,
            up.queue_position
            ,
            u.telegram_chat_id,
            u.timezone,
            u.reminder_daily_max,
            u.reminder_hour_local
        FROM user_problems up
        JOIN problems p ON p.id = up.problem_id
        JOIN users u ON u.id = up.user_id
        JOIN last_batch lb ON lb.requested_at = up.last_review_requested_at
        WHERE up.user_id = ?
          AND up.last_review_requested_at IS NOT NULL
        ORDER BY up.queue_position ASC, up.id ASC
        """,
        (user_id, user_id),
    ).fetchall()


def get_last_review_requested_at_for_user(
    conn: sqlite3.Connection, *, user_id: int
) -> str | None:
    row = conn.execute(
        """
        SELECT MAX(last_review_requested_at) AS requested_at
        FROM user_problems
        WHERE user_id = ?
        """,
        (user_id,),
    ).fetchone()
    if row is None or row["requested_at"] is None:
        return None
    return str(row["requested_at"])


def mark_review_requested(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    user_problem_id: int,
    requested_at: str,
) -> bool:
    cur = conn.execute(
        """
        UPDATE user_problems
        SET last_review_requested_at = ?, updated_at = ?
        WHERE id = ?
          AND user_id = ?
        """,
        (requested_at, requested_at, user_problem_id, user_id),
    )
    return cur.rowcount > 0


def mark_reviewed(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    user_problem_id: int,
    reviewed_at: str,
) -> bool:
    new_position = next_queue_position(conn, user_id=user_id)
    cur = conn.execute(
        """
        UPDATE user_problems
        SET review_count = review_count + 1,
            last_reviewed_at = ?,
            queue_position = ?,
            updated_at = ?
        WHERE id = ?
          AND user_id = ?
        """,
        (reviewed_at, new_position, reviewed_at, user_problem_id, user_id),
    )
    return cur.rowcount > 0
