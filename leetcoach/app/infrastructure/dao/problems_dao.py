from __future__ import annotations

import sqlite3


def upsert_problem(
    conn: sqlite3.Connection,
    *,
    title: str,
    difficulty: str,
    leetcode_slug: str | None,
    neetcode_slug: str,
    now_iso: str,
) -> int:
    conn.execute(
        """
        INSERT INTO problems (
            title, difficulty, leetcode_slug, neetcode_slug, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(neetcode_slug) DO UPDATE SET
            title = excluded.title,
            difficulty = excluded.difficulty,
            leetcode_slug = COALESCE(excluded.leetcode_slug, problems.leetcode_slug),
            updated_at = excluded.updated_at
        """,
        (title, difficulty, leetcode_slug, neetcode_slug, now_iso, now_iso),
    )
    row = conn.execute(
        "SELECT id FROM problems WHERE neetcode_slug = ?",
        (neetcode_slug,),
    ).fetchone()
    if row is None:
        raise RuntimeError("Failed to upsert problem")
    return int(row["id"])


def update_problem_metadata(
    conn: sqlite3.Connection,
    *,
    problem_id: int,
    title: str | None = None,
    difficulty: str | None = None,
    leetcode_slug: str | None = None,
    neetcode_slug: str | None = None,
    now_iso: str,
) -> bool:
    row = conn.execute(
        """
        SELECT title, difficulty, leetcode_slug, neetcode_slug
        FROM problems
        WHERE id = ?
        LIMIT 1
        """,
        (problem_id,),
    ).fetchone()
    if row is None:
        return False
    conn.execute(
        """
        UPDATE problems
        SET title = ?,
            difficulty = ?,
            leetcode_slug = ?,
            neetcode_slug = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            title if title is not None else row["title"],
            difficulty if difficulty is not None else row["difficulty"],
            leetcode_slug if leetcode_slug is not None else row["leetcode_slug"],
            neetcode_slug if neetcode_slug is not None else row["neetcode_slug"],
            now_iso,
            problem_id,
        ),
    )
    return True
