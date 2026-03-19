from __future__ import annotations

import sqlite3


VALID_STATUSES = ("asked", "answered", "revealed", "closed")


def upsert_active_quiz_session(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    topic: str | None,
    question_payload_json: str,
    model_used: str,
    status: str,
    asked_at: str,
    expires_at: str,
    now_iso: str,
) -> int:
    if status not in VALID_STATUSES:
        raise ValueError(f"Unsupported status: {status}")

    conn.execute(
        """
        INSERT INTO active_quiz_sessions (
            user_id,
            topic,
            question_payload_json,
            model_used,
            status,
            asked_at,
            expires_at,
            created_at,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            topic = excluded.topic,
            question_payload_json = excluded.question_payload_json,
            model_used = excluded.model_used,
            status = excluded.status,
            user_answer_text = NULL,
            answer_feedback_json = NULL,
            asked_at = excluded.asked_at,
            answered_at = NULL,
            revealed_at = NULL,
            closed_at = NULL,
            expires_at = excluded.expires_at,
            updated_at = excluded.updated_at
        """,
        (
            user_id,
            topic,
            question_payload_json,
            model_used,
            status,
            asked_at,
            expires_at,
            now_iso,
            now_iso,
        ),
    )
    row = conn.execute(
        "SELECT id FROM active_quiz_sessions WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    if row is None:
        raise RuntimeError("Failed to upsert active quiz session")
    return int(row["id"])


def get_active_quiz_session_by_user_id(
    conn: sqlite3.Connection, *, user_id: int
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM active_quiz_sessions
        WHERE user_id = ?
        LIMIT 1
        """,
        (user_id,),
    ).fetchone()


def mark_quiz_answered(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    user_answer_text: str,
    answer_feedback_json: str,
    answered_at: str,
    now_iso: str,
) -> bool:
    cur = conn.execute(
        """
        UPDATE active_quiz_sessions
        SET
            status = 'answered',
            user_answer_text = ?,
            answer_feedback_json = ?,
            answered_at = ?,
            updated_at = ?
        WHERE user_id = ?
          AND status IN ('asked', 'answered')
        """,
        (user_answer_text, answer_feedback_json, answered_at, now_iso, user_id),
    )
    return cur.rowcount > 0


def mark_quiz_revealed(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    revealed_at: str,
    expires_at: str,
    now_iso: str,
) -> bool:
    cur = conn.execute(
        """
        UPDATE active_quiz_sessions
        SET
            status = 'revealed',
            revealed_at = CASE
                WHEN revealed_at IS NULL THEN ?
                ELSE revealed_at
            END,
            expires_at = ?,
            updated_at = ?
        WHERE user_id = ?
          AND status IN ('asked', 'answered', 'revealed')
        """,
        (revealed_at, expires_at, now_iso, user_id),
    )
    return cur.rowcount > 0


def close_quiz_session(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    closed_at: str,
    expires_at: str,
    now_iso: str,
) -> bool:
    cur = conn.execute(
        """
        UPDATE active_quiz_sessions
        SET
            status = 'closed',
            closed_at = ?,
            expires_at = ?,
            updated_at = ?
        WHERE user_id = ?
          AND status IN ('asked', 'answered', 'revealed', 'closed')
        """,
        (closed_at, expires_at, now_iso, user_id),
    )
    return cur.rowcount > 0


def delete_expired_terminal_sessions(
    conn: sqlite3.Connection, *, now_iso: str
) -> int:
    cur = conn.execute(
        """
        DELETE FROM active_quiz_sessions
        WHERE status IN ('revealed', 'closed')
          AND expires_at < ?
        """,
        (now_iso,),
    )
    return cur.rowcount
