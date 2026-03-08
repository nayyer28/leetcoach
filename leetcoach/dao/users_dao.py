from __future__ import annotations

import sqlite3


def upsert_user(
    conn: sqlite3.Connection,
    *,
    telegram_user_id: str,
    telegram_chat_id: str,
    timezone: str,
    now_iso: str,
) -> int:
    conn.execute(
        """
        INSERT INTO users (
            telegram_user_id, telegram_chat_id, timezone, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(telegram_user_id) DO UPDATE SET
            telegram_chat_id = excluded.telegram_chat_id,
            timezone = excluded.timezone,
            updated_at = excluded.updated_at
        """,
        (telegram_user_id, telegram_chat_id, timezone, now_iso, now_iso),
    )
    row = conn.execute(
        "SELECT id FROM users WHERE telegram_user_id = ?",
        (telegram_user_id,),
    ).fetchone()
    if row is None:
        raise RuntimeError("Failed to upsert user")
    return int(row["id"])


def get_user_id_by_telegram_user_id(
    conn: sqlite3.Connection, *, telegram_user_id: str
) -> int | None:
    row = conn.execute(
        "SELECT id FROM users WHERE telegram_user_id = ?",
        (telegram_user_id,),
    ).fetchone()
    if row is None:
        return None
    return int(row["id"])
