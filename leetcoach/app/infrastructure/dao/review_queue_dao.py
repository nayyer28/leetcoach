from __future__ import annotations

import sqlite3


# Peek the top of one user's review queue: least-reviewed first, oldest bucket-entry
# breaks ties. Served by idx_user_problems_user_review_count_entered_at.
def peek_next_review_candidate_for_user(
    conn: sqlite3.Connection, *, user_id: int
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT
            up.id AS user_problem_id,
            up.display_id,
            up.user_id,
            p.title,
            p.leetcode_slug,
            p.neetcode_slug,
            up.solved_at,
            up.review_count,
            up.entered_at,
            u.telegram_chat_id,
            u.timezone,
            u.reminder_daily_max,
            u.reminder_hour_local,
            u.last_reminded_at
        FROM user_problems up
        JOIN problems p ON p.id = up.problem_id
        JOIN users u ON u.id = up.user_id
        WHERE up.user_id = ?
        ORDER BY up.review_count ASC, up.entered_at ASC, up.id ASC
        LIMIT 1
        """,
        (user_id,),
    ).fetchone()


# One row per user with reminders enabled — the top of each user's queue.
# Used by the scheduler to iterate all users in a single pass.
def list_next_review_candidates_for_scheduler(
    conn: sqlite3.Connection,
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT
            up.id AS user_problem_id,
            up.display_id,
            up.user_id,
            p.title,
            p.leetcode_slug,
            p.neetcode_slug,
            up.solved_at,
            up.review_count,
            up.entered_at,
            u.telegram_chat_id,
            u.timezone,
            u.reminder_daily_max,
            u.reminder_hour_local,
            u.last_reminded_at
        FROM user_problems up
        JOIN problems p ON p.id = up.problem_id
        JOIN users u ON u.id = up.user_id
        WHERE u.reminders_paused = 0
          AND up.id = (
            SELECT up2.id
            FROM user_problems up2
            WHERE up2.user_id = up.user_id
            ORDER BY up2.review_count ASC, up2.entered_at ASC, up2.id ASC
            LIMIT 1
          )
        ORDER BY u.id ASC
        """
    ).fetchall()


# Mark a problem as reviewed: bump the bucket and reset the tie-breaker. This is the
# only write path that changes queue position — the B-tree reindexes automatically.
def mark_reviewed(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    user_problem_id: int,
    reviewed_at: str,
) -> bool:
    cur = conn.execute(
        """
        UPDATE user_problems
        SET review_count = review_count + 1,
            entered_at = ?,
            updated_at = ?
        WHERE id = ?
          AND user_id = ?
        """,
        (reviewed_at, reviewed_at, user_problem_id, user_id),
    )
    return cur.rowcount > 0
