from __future__ import annotations

import sqlite3


def upsert_user_problem(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    problem_id: int,
    pattern: str,
    solved_at: str,
    concepts: str | None,
    time_complexity: str | None,
    space_complexity: str | None,
    notes: str | None,
    now_iso: str,
) -> int:
    conn.execute(
        """
        INSERT INTO user_problems (
            user_id,
            problem_id,
            pattern,
            solved_at,
            concepts,
            time_complexity,
            space_complexity,
            notes,
            created_at,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, problem_id) DO UPDATE SET
            pattern = excluded.pattern,
            solved_at = excluded.solved_at,
            concepts = excluded.concepts,
            time_complexity = excluded.time_complexity,
            space_complexity = excluded.space_complexity,
            notes = excluded.notes,
            updated_at = excluded.updated_at
        """,
        (
            user_id,
            problem_id,
            pattern,
            solved_at,
            concepts,
            time_complexity,
            space_complexity,
            notes,
            now_iso,
            now_iso,
        ),
    )
    row = conn.execute(
        "SELECT id FROM user_problems WHERE user_id = ? AND problem_id = ?",
        (user_id, problem_id),
    ).fetchone()
    if row is None:
        raise RuntimeError("Failed to upsert user_problem")
    return int(row["id"])

