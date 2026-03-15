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


def search_user_problems(
    conn: sqlite3.Connection, *, user_id: int, query: str
) -> list[sqlite3.Row]:
    like = f"%{query.lower()}%"
    return conn.execute(
        """
        SELECT
            up.id AS user_problem_id,
            p.title,
            p.difficulty,
            p.leetcode_slug,
            p.neetcode_slug,
            up.pattern,
            up.solved_at
        FROM user_problems up
        JOIN problems p ON p.id = up.problem_id
        WHERE up.user_id = ?
          AND (
            lower(p.title) LIKE ?
            OR lower(up.pattern) LIKE ?
            OR lower(COALESCE(up.notes, '')) LIKE ?
            OR lower(COALESCE(up.concepts, '')) LIKE ?
          )
        ORDER BY up.solved_at DESC
        LIMIT 20
        """,
        (user_id, like, like, like, like),
    ).fetchall()


def list_user_problems_by_pattern(
    conn: sqlite3.Connection, *, user_id: int, pattern: str
) -> list[sqlite3.Row]:
    like = f"%{pattern.lower()}%"
    return conn.execute(
        """
        SELECT
            up.id AS user_problem_id,
            p.title,
            p.difficulty,
            p.leetcode_slug,
            p.neetcode_slug,
            up.pattern,
            up.solved_at
        FROM user_problems up
        JOIN problems p ON p.id = up.problem_id
        WHERE up.user_id = ?
          AND lower(up.pattern) LIKE ?
        ORDER BY up.solved_at DESC
        LIMIT 50
        """,
        (user_id, like),
    ).fetchall()


def list_user_problems(
    conn: sqlite3.Connection, *, user_id: int, limit: int = 100
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT
            up.id AS user_problem_id,
            p.title,
            p.difficulty,
            p.leetcode_slug,
            p.neetcode_slug,
            up.pattern,
            up.solved_at
        FROM user_problems up
        JOIN problems p ON p.id = up.problem_id
        WHERE up.user_id = ?
        ORDER BY up.solved_at DESC
        LIMIT ?
        """,
        (user_id, limit),
    ).fetchall()


def get_user_problem_detail(
    conn: sqlite3.Connection, *, user_id: int, user_problem_id: int
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT
            up.id AS user_problem_id,
            p.title,
            p.difficulty,
            p.leetcode_slug,
            p.neetcode_slug,
            up.pattern,
            up.solved_at,
            up.concepts,
            up.time_complexity,
            up.space_complexity,
            up.notes,
            up.created_at,
            up.updated_at
        FROM user_problems up
        JOIN problems p ON p.id = up.problem_id
        WHERE up.user_id = ?
          AND up.id = ?
        LIMIT 1
        """,
        (user_id, user_problem_id),
    ).fetchone()
