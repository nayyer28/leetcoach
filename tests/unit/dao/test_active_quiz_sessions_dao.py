from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import tempfile
import unittest

from leetcoach.dao.active_quiz_sessions_dao import (
    close_quiz_session,
    delete_expired_terminal_sessions,
    get_active_quiz_session_by_user_id,
    mark_quiz_answered,
    mark_quiz_revealed,
    upsert_active_quiz_session,
)
from leetcoach.db.connection import get_connection
from leetcoach.db.migrate import migrate_database


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class ActiveQuizSessionsDaoUnitTest(unittest.TestCase):
    def _seed_user(self, db_path: str) -> int:
        now = _now_iso()
        with get_connection(db_path) as conn:
            conn.execute(
                """
                INSERT INTO users (
                    telegram_user_id,
                    telegram_chat_id,
                    timezone,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                ("u-1", "chat-1", "UTC", now, now),
            )
            user_id = int(conn.execute("SELECT id FROM users LIMIT 1").fetchone()["id"])
            conn.commit()
            return user_id

    def test_upsert_replaces_existing_active_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "leetcoach-test.db")
            migrate_database(db_path)
            user_id = self._seed_user(db_path)

            asked_at = "2026-03-11T08:00:00+00:00"
            now_iso = "2026-03-11T08:00:00+00:00"
            expires_at = "2026-03-12T08:00:00+00:00"
            with get_connection(db_path) as conn:
                first_id = upsert_active_quiz_session(
                    conn,
                    user_id=user_id,
                    topic="graphs",
                    question_payload_json='{"question":"Q1"}',
                    model_used="gemini-2.5-pro",
                    status="asked",
                    asked_at=asked_at,
                    expires_at=expires_at,
                    now_iso=now_iso,
                )
                conn.commit()

            with get_connection(db_path) as conn:
                second_id = upsert_active_quiz_session(
                    conn,
                    user_id=user_id,
                    topic="dp",
                    question_payload_json='{"question":"Q2"}',
                    model_used="gemini-2.5-flash",
                    status="asked",
                    asked_at="2026-03-11T09:00:00+00:00",
                    expires_at="2026-03-12T09:00:00+00:00",
                    now_iso="2026-03-11T09:00:00+00:00",
                )
                row = get_active_quiz_session_by_user_id(conn, user_id=user_id)
                self.assertIsNotNone(row)
                self.assertEqual(first_id, second_id)
                self.assertEqual(str(row["topic"]), "dp")
                self.assertEqual(str(row["model_used"]), "gemini-2.5-flash")
                self.assertEqual(str(row["status"]), "asked")
                self.assertIsNone(row["user_answer_text"])

    def test_answer_and_reveal_transitions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "leetcoach-test.db")
            migrate_database(db_path)
            user_id = self._seed_user(db_path)
            with get_connection(db_path) as conn:
                upsert_active_quiz_session(
                    conn,
                    user_id=user_id,
                    topic=None,
                    question_payload_json='{"question":"Q"}',
                    model_used="gemini-2.5-pro",
                    status="asked",
                    asked_at="2026-03-11T08:00:00+00:00",
                    expires_at="2026-03-12T08:00:00+00:00",
                    now_iso="2026-03-11T08:00:00+00:00",
                )
                answered = mark_quiz_answered(
                    conn,
                    user_id=user_id,
                    user_answer_text="I think B",
                    answer_feedback_json='{"is_correct": false}',
                    answered_at="2026-03-11T08:01:00+00:00",
                    now_iso="2026-03-11T08:01:00+00:00",
                )
                self.assertTrue(answered)
                revealed = mark_quiz_revealed(
                    conn,
                    user_id=user_id,
                    revealed_at="2026-03-11T08:02:00+00:00",
                    expires_at="2026-03-12T08:02:00+00:00",
                    now_iso="2026-03-11T08:02:00+00:00",
                )
                self.assertTrue(revealed)
                row = get_active_quiz_session_by_user_id(conn, user_id=user_id)
                self.assertIsNotNone(row)
                self.assertEqual(str(row["status"]), "revealed")
                self.assertEqual(str(row["user_answer_text"]), "I think B")
                conn.commit()

    def test_cleanup_deletes_only_expired_terminal_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "leetcoach-test.db")
            migrate_database(db_path)
            user_id = self._seed_user(db_path)
            base = datetime(2026, 3, 11, 8, 0, tzinfo=UTC)
            with get_connection(db_path) as conn:
                upsert_active_quiz_session(
                    conn,
                    user_id=user_id,
                    topic="trees",
                    question_payload_json='{"question":"Q"}',
                    model_used="gemini-2.5-pro",
                    status="revealed",
                    asked_at=base.isoformat(),
                    expires_at=(base + timedelta(hours=1)).isoformat(),
                    now_iso=base.isoformat(),
                )
                closed = close_quiz_session(
                    conn,
                    user_id=user_id,
                    closed_at=(base + timedelta(minutes=5)).isoformat(),
                    expires_at=(base + timedelta(hours=1)).isoformat(),
                    now_iso=(base + timedelta(minutes=5)).isoformat(),
                )
                self.assertTrue(closed)

                # Add a non-terminal row that should never be deleted by TTL cleanup.
                conn.execute(
                    """
                    INSERT INTO active_quiz_sessions (
                        user_id, topic, question_payload_json, model_used, status,
                        asked_at, expires_at, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        status = excluded.status,
                        expires_at = excluded.expires_at,
                        updated_at = excluded.updated_at
                    """,
                    (
                        user_id,
                        "arrays",
                        '{"question":"Q2"}',
                        "gemini-2.5-flash",
                        "asked",
                        (base + timedelta(hours=2)).isoformat(),
                        (base + timedelta(hours=2)).isoformat(),
                        (base + timedelta(hours=2)).isoformat(),
                        (base + timedelta(hours=2)).isoformat(),
                    ),
                )
                conn.commit()

                deleted = delete_expired_terminal_sessions(
                    conn, now_iso=(base + timedelta(hours=3)).isoformat()
                )
                self.assertEqual(deleted, 0)
                conn.commit()

                # Force row to terminal+expired and verify deletion.
                conn.execute(
                    """
                    UPDATE active_quiz_sessions
                    SET status = 'closed', expires_at = ?
                    WHERE user_id = ?
                    """,
                    ((base + timedelta(minutes=30)).isoformat(), user_id),
                )
                conn.commit()
                deleted = delete_expired_terminal_sessions(
                    conn, now_iso=(base + timedelta(hours=3)).isoformat()
                )
                self.assertEqual(deleted, 1)
                conn.commit()


if __name__ == "__main__":
    unittest.main()
