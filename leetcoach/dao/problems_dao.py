from __future__ import annotations

import sqlite3


def upsert_problem(
    conn: sqlite3.Connection,
    *,
    title: str,
    difficulty: str,
    leetcode_slug: str,
    neetcode_slug: str | None,
    now_iso: str,
) -> int:
    conn.execute(
        """
        INSERT INTO problems (
            title, difficulty, leetcode_slug, neetcode_slug, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(leetcode_slug) DO UPDATE SET
            title = excluded.title,
            difficulty = excluded.difficulty,
            neetcode_slug = COALESCE(excluded.neetcode_slug, problems.neetcode_slug),
            updated_at = excluded.updated_at
        """,
        (title, difficulty, leetcode_slug, neetcode_slug, now_iso, now_iso),
    )
    row = conn.execute(
        "SELECT id FROM problems WHERE leetcode_slug = ?",
        (leetcode_slug,),
    ).fetchone()
    if row is None:
        raise RuntimeError("Failed to upsert problem")
    return int(row["id"])

