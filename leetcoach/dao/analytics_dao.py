from __future__ import annotations

import sqlite3


def list_user_problem_analytics_rows(
    conn: sqlite3.Connection,
    *,
    user_id: int,
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT
            up.id AS user_problem_id,
            p.difficulty,
            up.pattern,
            up.solved_at,
            up.review_count,
            u.timezone
        FROM user_problems up
        JOIN problems p ON p.id = up.problem_id
        JOIN users u ON u.id = up.user_id
        WHERE up.user_id = ?
        ORDER BY up.solved_at ASC, up.id ASC
        """,
        (user_id,),
    ).fetchall()
