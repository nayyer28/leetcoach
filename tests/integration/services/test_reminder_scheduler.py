from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from leetcoach.app.infrastructure.config.app_config import AppConfig
from leetcoach.app.infrastructure.config.db import get_connection
from leetcoach.app.infrastructure.dao.review_queue_dao import (
    list_next_review_candidates_for_scheduler,
)
from leetcoach.app.misc.migrate import migrate_database
from leetcoach.app.application.problems.log_problem import LogProblemInput, log_problem
from leetcoach.app.application.reviews.reminder_engine import run_scheduler_once


def _cfg(db_path: Path, *, hour: int = 9) -> AppConfig:
    return AppConfig(
        environment="test",
        log_level="INFO",
        timezone="UTC",
        db_path=str(db_path),
        telegram_bot_token="123:token",
        allowed_user_ids=frozenset(),
        reminder_hour_local=hour,
        reminder_daily_max=2,
    )


def _log(db_path: Path, *, user: str, chat: str, title: str, slug: str, solved_at: str) -> None:
    log_problem(
        str(db_path),
        LogProblemInput(
            telegram_user_id=user,
            telegram_chat_id=chat,
            timezone="UTC",
            title=title,
            difficulty="easy",
            leetcode_slug=slug,
            neetcode_slug=slug,
            pattern="arrays",
            solved_at=solved_at,
            notes="",
        ),
    )


class ReminderSchedulerIntegrationTest(unittest.TestCase):
    @patch("leetcoach.app.application.reviews.reminder_engine._send_telegram_message")
    def test_run_once_sends_and_bumps_review_count_and_dedupes_same_day(
        self, mock_send
    ) -> None:
        mock_send.return_value = (True, "ok")
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "leetcoach-test.db"
            migrate_database(str(db_path))

            _log(
                db_path,
                user="u-1",
                chat="chat-1",
                title="Maximum Depth of Binary Tree",
                slug="maximum-depth-of-binary-tree",
                solved_at="2026-02-01T10:00:00+00:00",
            )
            cfg = _cfg(db_path)
            now_iso = "2026-02-10T09:00:00+00:00"

            first = run_scheduler_once(config=cfg, now_iso=now_iso)
            self.assertEqual(first.sent, 1)
            self.assertEqual(first.failed, 0)
            self.assertEqual(first.scanned, 1)
            self.assertEqual(mock_send.call_count, 1)
            first_message_text = mock_send.call_args_list[0].args[2]
            self.assertIn("LeetCoach Reminder", first_message_text)

            # After send: bucket bumped to 1, entered_at reset, user stamp set.
            with get_connection(str(db_path)) as conn:
                up_row = conn.execute(
                    "SELECT review_count, entered_at FROM user_problems"
                ).fetchone()
                self.assertEqual(int(up_row["review_count"]), 1)
                self.assertEqual(str(up_row["entered_at"]), now_iso)
                user_row = conn.execute(
                    "SELECT last_reminded_at FROM users WHERE telegram_user_id = ?",
                    ("u-1",),
                ).fetchone()
                self.assertEqual(str(user_row["last_reminded_at"]), now_iso)

            # A second tick the same local day is deduped by last_reminded_at.
            second = run_scheduler_once(config=cfg, now_iso="2026-02-10T09:30:00+00:00")
            self.assertEqual(second.sent, 0)
            self.assertEqual(second.skipped_already_reminded_today, 1)
            self.assertEqual(mock_send.call_count, 1)

    @patch("leetcoach.app.application.reviews.reminder_engine._send_telegram_message")
    def test_run_once_respects_send_hour(self, mock_send) -> None:
        mock_send.return_value = (True, "ok")
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "leetcoach-test.db"
            migrate_database(str(db_path))
            _log(
                db_path,
                user="u-1",
                chat="chat-1",
                title="Two Sum",
                slug="two-sum",
                solved_at="2026-02-01T10:00:00+00:00",
            )
            cfg = _cfg(db_path, hour=8)
            stats = run_scheduler_once(config=cfg, now_iso="2026-02-10T09:00:00+00:00")
            self.assertEqual(stats.sent, 0)
            self.assertEqual(stats.skipped_outside_send_hour, 1)
            self.assertEqual(mock_send.call_count, 0)

    @patch("leetcoach.app.application.reviews.reminder_engine._send_telegram_message")
    def test_run_once_records_failed_send_and_does_not_mark_reminded(
        self, mock_send
    ) -> None:
        mock_send.return_value = (False, "network error")
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "leetcoach-test.db"
            migrate_database(str(db_path))

            _log(
                db_path,
                user="u-1",
                chat="chat-1",
                title="Binary Search",
                slug="binary-search",
                solved_at="2026-02-01T10:00:00+00:00",
            )
            cfg = _cfg(db_path)
            stats = run_scheduler_once(config=cfg, now_iso="2026-02-10T09:00:00+00:00")
            self.assertEqual(stats.sent, 0)
            self.assertEqual(stats.failed, 1)
            self.assertEqual(mock_send.call_count, 1)

            with get_connection(str(db_path)) as conn:
                up_row = conn.execute(
                    "SELECT review_count FROM user_problems"
                ).fetchone()
                self.assertEqual(int(up_row["review_count"]), 0)
                user_row = conn.execute(
                    "SELECT last_reminded_at FROM users WHERE telegram_user_id = ?",
                    ("u-1",),
                ).fetchone()
                self.assertIsNone(user_row["last_reminded_at"])

    @patch("leetcoach.app.application.reviews.reminder_engine._send_telegram_message")
    def test_run_once_sends_only_one_problem_per_user_per_day(self, mock_send) -> None:
        mock_send.return_value = (True, "ok")
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "leetcoach-test.db"
            migrate_database(str(db_path))

            for idx, title in enumerate(
                ["Binary Search", "Valid Palindrome", "Maximum Subarray"], start=1
            ):
                _log(
                    db_path,
                    user="u-1",
                    chat="chat-1",
                    title=title,
                    slug=f"slug-{idx}",
                    solved_at=f"2026-02-0{idx}T10:00:00+00:00",
                )
            cfg = _cfg(db_path)

            first = run_scheduler_once(config=cfg, now_iso="2026-02-10T09:00:00+00:00")
            # One user → one problem sent, even with three in the queue.
            self.assertEqual(first.sent, 1)
            self.assertEqual(mock_send.call_count, 1)

            second = run_scheduler_once(config=cfg, now_iso="2026-02-10T09:01:00+00:00")
            self.assertEqual(second.sent, 0)
            self.assertEqual(second.skipped_already_reminded_today, 1)
            self.assertEqual(mock_send.call_count, 1)

    @patch("leetcoach.app.application.reviews.reminder_engine._send_telegram_message")
    def test_run_once_uses_user_specific_reminder_hour_override(self, mock_send) -> None:
        mock_send.return_value = (True, "ok")
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "leetcoach-test.db"
            migrate_database(str(db_path))

            _log(
                db_path,
                user="u-1",
                chat="chat-1",
                title="Binary Search",
                slug="binary-search",
                solved_at="2026-02-01T10:00:00+00:00",
            )
            with get_connection(str(db_path)) as conn:
                conn.execute(
                    "UPDATE users SET reminder_hour_local = 11 WHERE telegram_user_id = ?",
                    ("u-1",),
                )
                conn.commit()

            cfg = _cfg(db_path)
            skipped = run_scheduler_once(config=cfg, now_iso="2026-02-10T09:00:00+00:00")
            self.assertEqual(skipped.sent, 0)
            self.assertEqual(skipped.skipped_outside_send_hour, 1)

            sent = run_scheduler_once(config=cfg, now_iso="2026-02-10T11:00:00+00:00")
            self.assertEqual(sent.sent, 1)

    def test_scheduler_queue_orders_by_review_count_then_entered_at(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "leetcoach-test.db"
            migrate_database(str(db_path))

            fixtures = [
                ("Two Sum", "2026-02-01T10:00:00+00:00"),
                ("Longest Substring", "2026-02-11T10:00:00+00:00"),
                ("Merge Two Sorted Lists", "2026-01-01T10:00:00+00:00"),
            ]
            for idx, (title, solved_at) in enumerate(fixtures, start=1):
                _log(
                    db_path,
                    user="u-1",
                    chat="chat-1",
                    title=title,
                    slug=f"slug-{idx}",
                    solved_at=solved_at,
                )

            # entered_at is stamped as `now()` on insert. Pin it to the fixture's
            # solved_at so the priority-queue ordering is deterministic, then bump
            # "Two Sum" out of bucket 0 so we can verify the tie-break in bucket 0
            # falls to the earliest-entered row ("Merge Two Sorted Lists").
            with get_connection(str(db_path)) as conn:
                for title, entered_at in fixtures:
                    conn.execute(
                        """
                        UPDATE user_problems
                        SET entered_at = ?, updated_at = ?
                        WHERE problem_id = (
                            SELECT id FROM problems WHERE title = ?
                        )
                        """,
                        (entered_at, entered_at, title),
                    )
                conn.execute(
                    """
                    UPDATE user_problems
                    SET review_count = 1, entered_at = ?, updated_at = ?
                    WHERE problem_id = (
                        SELECT id FROM problems WHERE title = 'Two Sum'
                    )
                    """,
                    ("2026-02-19T10:00:00+00:00", "2026-02-19T10:00:00+00:00"),
                )
                conn.commit()

                rows = list_next_review_candidates_for_scheduler(conn)

            # One row per user, and it's the top of that user's queue: Merge Two Sorted Lists.
            self.assertEqual(len(rows), 1)
            self.assertEqual(str(rows[0]["title"]), "Merge Two Sorted Lists")

    def test_scheduler_excludes_paused_users(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "leetcoach-test.db"
            migrate_database(str(db_path))
            _log(
                db_path,
                user="u-1",
                chat="chat-1",
                title="Two Sum",
                slug="two-sum",
                solved_at="2026-01-01T10:00:00+00:00",
            )
            _log(
                db_path,
                user="u-2",
                chat="chat-2",
                title="Valid Anagram",
                slug="valid-anagram",
                solved_at="2026-01-01T10:00:00+00:00",
            )

            with get_connection(str(db_path)) as conn:
                rows = list_next_review_candidates_for_scheduler(conn)
                self.assertEqual(len(rows), 2)

                conn.execute(
                    "UPDATE users SET reminders_paused = 1 WHERE telegram_user_id = ?",
                    ("u-1",),
                )
                conn.commit()

                rows = list_next_review_candidates_for_scheduler(conn)

            self.assertEqual(len(rows), 1)
            self.assertEqual(str(rows[0]["title"]), "Valid Anagram")


if __name__ == "__main__":
    unittest.main()
