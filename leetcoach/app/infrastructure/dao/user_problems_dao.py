from __future__ import annotations

import sqlite3


def next_display_id(conn: sqlite3.Connection, *, user_id: int) -> int:
    row = conn.execute(
        """
        SELECT COALESCE(MAX(display_id), 0) AS max_display_id
        FROM user_problems
        WHERE user_id = ?
        """,
        (user_id,),
    ).fetchone()
    max_display_id = int(row["max_display_id"]) if row is not None else 0
    return max_display_id + 1


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
    row = conn.execute(
        """
        SELECT COALESCE(MAX(queue_position), 0) AS max_position
        FROM user_problems
        WHERE user_id = ?
        """,
        (user_id,),
    ).fetchone()
    next_queue_position = int(row["max_position"]) + 10 if row is not None else 10
    conn.execute(
        """
        INSERT INTO user_problems (
            user_id,
            problem_id,
            display_id,
            pattern,
            solved_at,
            concepts,
            time_complexity,
            space_complexity,
            notes,
            queue_position,
            created_at,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            next_display_id(conn, user_id=user_id),
            pattern,
            solved_at,
            concepts,
            time_complexity,
            space_complexity,
            notes,
            next_queue_position,
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
            up.display_id,
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
            OR lower(COALESCE(p.difficulty, '')) LIKE ?
            OR lower(COALESCE(p.leetcode_slug, '')) LIKE ?
            OR lower(COALESCE(p.neetcode_slug, '')) LIKE ?
            OR lower(up.pattern) LIKE ?
            OR lower(COALESCE(up.solved_at, '')) LIKE ?
            OR lower(COALESCE(
                CASE strftime('%m', up.solved_at)
                    WHEN '01' THEN 'january'
                    WHEN '02' THEN 'february'
                    WHEN '03' THEN 'march'
                    WHEN '04' THEN 'april'
                    WHEN '05' THEN 'may'
                    WHEN '06' THEN 'june'
                    WHEN '07' THEN 'july'
                    WHEN '08' THEN 'august'
                    WHEN '09' THEN 'september'
                    WHEN '10' THEN 'october'
                    WHEN '11' THEN 'november'
                    WHEN '12' THEN 'december'
                END,
                ''
            )) LIKE ?
            OR lower(COALESCE(up.time_complexity, '')) LIKE ?
            OR lower(COALESCE(up.space_complexity, '')) LIKE ?
            OR lower(COALESCE(up.notes, '')) LIKE ?
            OR lower(COALESCE(up.concepts, '')) LIKE ?
          )
        ORDER BY up.solved_at DESC
        LIMIT 20
        """,
        (user_id, like, like, like, like, like, like, like, like, like, like, like),
    ).fetchall()


def list_user_problems_by_pattern(
    conn: sqlite3.Connection, *, user_id: int, pattern: str
) -> list[sqlite3.Row]:
    like = f"%{pattern.lower()}%"
    return conn.execute(
        """
        SELECT
            up.id AS user_problem_id,
            up.display_id,
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
        ORDER BY up.solved_at ASC, up.id ASC
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
            up.display_id,
            p.title,
            p.difficulty,
            p.leetcode_slug,
            p.neetcode_slug,
            up.pattern,
            up.solved_at
        FROM user_problems up
        JOIN problems p ON p.id = up.problem_id
        WHERE up.user_id = ?
        ORDER BY up.solved_at ASC, up.id ASC
        LIMIT ?
        """,
        (user_id, limit),
    ).fetchall()


def list_recent_user_problems(
    conn: sqlite3.Connection, *, user_id: int, limit: int = 1
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT
            up.id AS user_problem_id,
            up.display_id,
            p.title,
            p.difficulty,
            p.leetcode_slug,
            p.neetcode_slug,
            up.pattern,
            up.solved_at
        FROM user_problems up
        JOIN problems p ON p.id = up.problem_id
        WHERE up.user_id = ?
        ORDER BY up.solved_at DESC, up.id DESC
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
            up.display_id,
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


def get_user_problem_detail_by_display_id(
    conn: sqlite3.Connection, *, user_id: int, display_id: int
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT
            up.id AS user_problem_id,
            up.display_id,
            p.id AS problem_id,
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
          AND up.display_id = ?
        LIMIT 1
        """,
        (user_id, display_id),
    ).fetchone()


def resolve_user_problem_id_by_display_id(
    conn: sqlite3.Connection, *, user_id: int, display_id: int
) -> int | None:
    row = conn.execute(
        """
        SELECT id
        FROM user_problems
        WHERE user_id = ?
          AND display_id = ?
        LIMIT 1
        """,
        (user_id, display_id),
    ).fetchone()
    if row is None:
        return None
    return int(row["id"])


def update_user_problem_metadata(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    user_problem_id: int,
    pattern: str | None = None,
    concepts: str | None = None,
    time_complexity: str | None = None,
    space_complexity: str | None = None,
    notes: str | None = None,
    now_iso: str,
) -> bool:
    row = conn.execute(
        """
        SELECT id, pattern, concepts, time_complexity, space_complexity, notes
        FROM user_problems
        WHERE id = ?
          AND user_id = ?
        LIMIT 1
        """,
        (user_problem_id, user_id),
    ).fetchone()
    if row is None:
        return False
    conn.execute(
        """
        UPDATE user_problems
        SET pattern = ?,
            concepts = ?,
            time_complexity = ?,
            space_complexity = ?,
            notes = ?,
            updated_at = ?
        WHERE id = ?
          AND user_id = ?
        """,
        (
            pattern if pattern is not None else row["pattern"],
            concepts if concepts is not None else row["concepts"],
            time_complexity if time_complexity is not None else row["time_complexity"],
            space_complexity if space_complexity is not None else row["space_complexity"],
            notes if notes is not None else row["notes"],
            now_iso,
            user_problem_id,
            user_id,
        ),
    )
    return True
