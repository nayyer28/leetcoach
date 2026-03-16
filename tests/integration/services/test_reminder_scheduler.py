from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from leetcoach.config import AppConfig
from leetcoach.dao.problem_reviews_dao import list_pending_review_candidates
from leetcoach.db.connection import get_connection
from leetcoach.db.migrate import migrate_database
from leetcoach.services.log_problem_service import LogProblemInput, log_problem
from leetcoach.reminder_scheduler import run_scheduler_once


class ReminderSchedulerIntegrationTest(unittest.TestCase):
    @patch("leetcoach.reminder_scheduler._send_telegram_message")
    def test_run_once_sets_last_reminded_and_skips_same_day(self, mock_send) -> None:
        mock_send.return_value = (True, "ok")
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "leetcoach-test.db"
            migrate_database(str(db_path))

            log_problem(
                str(db_path),
                LogProblemInput(
                    telegram_user_id="u-1",
                    telegram_chat_id="chat-1",
                    timezone="UTC",
                    title="Maximum Depth of Binary Tree",
                    difficulty="easy",
                    leetcode_slug="maximum-depth-of-binary-tree",
                    neetcode_slug="max-depth-of-binary-tree",
                    pattern="trees",
                    solved_at="2026-02-01T10:00:00+00:00",
                    notes="",
                ),
            )
            cfg = AppConfig(
                environment="test",
                log_level="INFO",
                timezone="UTC",
                db_path=str(db_path),
                telegram_bot_token="123:token",
                allowed_user_ids=frozenset(),
                reminder_hour_local=9,
                reminder_daily_max=2,
            )
            now_iso = "2026-02-10T09:00:00+00:00"
            first = run_scheduler_once(config=cfg, now_iso=now_iso)
            self.assertEqual(first.sent, 1)
            self.assertEqual(first.failed, 0)
            self.assertEqual(first.header_sent, 1)
            self.assertEqual(first.selected, 1)
            self.assertEqual(first.due_and_unsent, 1)
            self.assertEqual(mock_send.call_count, 2)
            first_message_text = mock_send.call_args_list[0].args[2]
            self.assertIn("Daily LeetCoach Review Plan", first_message_text)

            with get_connection(str(db_path)) as conn:
                row = conn.execute(
                    "SELECT last_reminded_at FROM problem_reviews WHERE review_day = 7"
                ).fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(str(row["last_reminded_at"]), now_iso)

            second = run_scheduler_once(config=cfg, now_iso="2026-02-10T09:30:00+00:00")
            self.assertEqual(second.sent, 0)
            self.assertEqual(second.skipped_already_reminded_today, 1)
            self.assertEqual(mock_send.call_count, 2)

    @patch("leetcoach.reminder_scheduler._send_telegram_message")
    def test_run_once_respects_send_hour(self, mock_send) -> None:
        mock_send.return_value = (True, "ok")
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "leetcoach-test.db"
            migrate_database(str(db_path))
            log_problem(
                str(db_path),
                LogProblemInput(
                    telegram_user_id="u-1",
                    telegram_chat_id="chat-1",
                    timezone="UTC",
                    title="Two Sum",
                    difficulty="easy",
                    leetcode_slug="two-sum",
                    neetcode_slug="two-sum",
                    pattern="arrays",
                    solved_at="2026-02-01T10:00:00+00:00",
                    notes="",
                ),
            )
            cfg = AppConfig(
                environment="test",
                log_level="INFO",
                timezone="UTC",
                db_path=str(db_path),
                telegram_bot_token="123:token",
                allowed_user_ids=frozenset(),
                reminder_hour_local=8,
                reminder_daily_max=2,
            )
            stats = run_scheduler_once(config=cfg, now_iso="2026-02-10T09:00:00+00:00")
            self.assertEqual(stats.sent, 0)
            self.assertEqual(stats.skipped_outside_send_hour, 1)
            self.assertEqual(stats.header_sent, 0)
            self.assertEqual(stats.selected, 0)
            self.assertEqual(mock_send.call_count, 0)

    @patch("leetcoach.reminder_scheduler._send_telegram_message")
    def test_run_once_records_failed_send_and_does_not_mark_reminded(self, mock_send) -> None:
        mock_send.return_value = (False, "network error")
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "leetcoach-test.db"
            migrate_database(str(db_path))

            log_problem(
                str(db_path),
                LogProblemInput(
                    telegram_user_id="u-1",
                    telegram_chat_id="chat-1",
                    timezone="UTC",
                    title="Binary Search",
                    difficulty="easy",
                    leetcode_slug="binary-search",
                    neetcode_slug="binary-search",
                    pattern="binary-search",
                    solved_at="2026-02-01T10:00:00+00:00",
                    notes="",
                ),
            )
            cfg = AppConfig(
                environment="test",
                log_level="INFO",
                timezone="UTC",
                db_path=str(db_path),
                telegram_bot_token="123:token",
                allowed_user_ids=frozenset(),
                reminder_hour_local=9,
                reminder_daily_max=2,
            )
            stats = run_scheduler_once(config=cfg, now_iso="2026-02-10T09:00:00+00:00")
            self.assertEqual(stats.sent, 0)
            self.assertEqual(stats.failed, 1)
            self.assertEqual(mock_send.call_count, 1)

            with get_connection(str(db_path)) as conn:
                row = conn.execute(
                    "SELECT last_reminded_at FROM problem_reviews WHERE review_day = 7"
                ).fetchone()
                self.assertIsNotNone(row)
                self.assertIsNone(row["last_reminded_at"])

    @patch("leetcoach.reminder_scheduler._send_telegram_message")
    def test_run_once_sends_only_one_batch_per_chat_per_day(self, mock_send) -> None:
        mock_send.return_value = (True, "ok")
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "leetcoach-test.db"
            migrate_database(str(db_path))

            for idx, title in enumerate(
                [
                    "Binary Search",
                    "Valid Palindrome",
                    "Maximum Subarray",
                ],
                start=1,
            ):
                log_problem(
                    str(db_path),
                    LogProblemInput(
                        telegram_user_id="u-1",
                        telegram_chat_id="chat-1",
                        timezone="UTC",
                        title=title,
                        difficulty="easy",
                        leetcode_slug=f"slug-{idx}",
                        neetcode_slug=f"neet-{idx}",
                        pattern="arrays",
                        solved_at=f"2026-02-0{idx}T10:00:00+00:00",
                        notes="",
                    ),
                )

            cfg = AppConfig(
                environment="test",
                log_level="INFO",
                timezone="UTC",
                db_path=str(db_path),
                telegram_bot_token="123:token",
                allowed_user_ids=frozenset(),
                reminder_hour_local=9,
                reminder_daily_max=2,
            )

            first = run_scheduler_once(config=cfg, now_iso="2026-02-10T09:00:00+00:00")
            self.assertEqual(first.sent, 2)
            self.assertEqual(first.header_sent, 1)
            self.assertEqual(mock_send.call_count, 3)

            second = run_scheduler_once(config=cfg, now_iso="2026-02-10T09:01:00+00:00")
            self.assertEqual(second.sent, 0)
            self.assertEqual(second.header_sent, 0)
            self.assertEqual(second.skipped_already_reminded_today, 2)
            self.assertEqual(mock_send.call_count, 3)

    @patch("leetcoach.reminder_scheduler._send_telegram_message")
    def test_run_once_continues_after_single_send_failure(self, mock_send) -> None:
        mock_send.side_effect = [(True, "ok"), (False, "network error"), (True, "ok")]
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "leetcoach-test.db"
            migrate_database(str(db_path))

            log_problem(
                str(db_path),
                LogProblemInput(
                    telegram_user_id="u-1",
                    telegram_chat_id="chat-1",
                    timezone="UTC",
                    title="Binary Search",
                    difficulty="easy",
                    leetcode_slug="binary-search",
                    neetcode_slug="binary-search",
                    pattern="binary-search",
                    solved_at="2026-02-01T10:00:00+00:00",
                    notes="",
                ),
            )
            log_problem(
                str(db_path),
                LogProblemInput(
                    telegram_user_id="u-1",
                    telegram_chat_id="chat-1",
                    timezone="UTC",
                    title="Valid Palindrome",
                    difficulty="easy",
                    leetcode_slug="valid-palindrome",
                    neetcode_slug="valid-palindrome",
                    pattern="two-pointers",
                    solved_at="2026-02-02T10:00:00+00:00",
                    notes="",
                ),
            )

            cfg = AppConfig(
                environment="test",
                log_level="INFO",
                timezone="UTC",
                db_path=str(db_path),
                telegram_bot_token="123:token",
                allowed_user_ids=frozenset(),
                reminder_hour_local=9,
                reminder_daily_max=2,
            )
            stats = run_scheduler_once(config=cfg, now_iso="2026-02-10T09:00:00+00:00")
            self.assertEqual(stats.sent, 1)
            self.assertEqual(stats.failed, 1)
            self.assertEqual(mock_send.call_count, 3)

    def test_pending_candidates_are_due_sorted_and_exclude_expired_or_completed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "leetcoach-test.db"
            migrate_database(str(db_path))

            log_problem(
                str(db_path),
                LogProblemInput(
                    telegram_user_id="u-1",
                    telegram_chat_id="chat-1",
                    timezone="UTC",
                    title="Two Sum",
                    difficulty="easy",
                    leetcode_slug="two-sum",
                    neetcode_slug="two-sum",
                    pattern="arrays",
                    solved_at="2026-02-01T10:00:00+00:00",
                    notes="",
                ),
            )
            log_problem(
                str(db_path),
                LogProblemInput(
                    telegram_user_id="u-1",
                    telegram_chat_id="chat-1",
                    timezone="UTC",
                    title="Longest Substring",
                    difficulty="medium",
                    leetcode_slug="longest-substring-without-repeating-characters",
                    neetcode_slug="longest-substring-without-duplicates",
                    pattern="sliding-window",
                    solved_at="2026-02-11T10:00:00+00:00",
                    notes="",
                ),
            )
            log_problem(
                str(db_path),
                LogProblemInput(
                    telegram_user_id="u-1",
                    telegram_chat_id="chat-1",
                    timezone="UTC",
                    title="Merge Two Sorted Lists",
                    difficulty="easy",
                    leetcode_slug="merge-two-sorted-lists",
                    neetcode_slug="merge-two-sorted-linked-lists",
                    pattern="linked-list",
                    solved_at="2026-01-01T10:00:00+00:00",
                    notes="",
                ),
            )
            log_problem(
                str(db_path),
                LogProblemInput(
                    telegram_user_id="u-1",
                    telegram_chat_id="chat-1",
                    timezone="UTC",
                    title="Contains Duplicate",
                    difficulty="easy",
                    leetcode_slug="contains-duplicate",
                    neetcode_slug="contains-duplicate",
                    pattern="arrays",
                    solved_at="2026-02-12T10:00:00+00:00",
                    notes="",
                ),
            )

            with get_connection(str(db_path)) as conn:
                # Mark first problem's day-7 review as completed.
                conn.execute(
                    """
                    UPDATE problem_reviews
                    SET completed_at = ?, updated_at = ?
                    WHERE user_problem_id = 1 AND review_day = 7
                    """,
                    ("2026-02-09T10:00:00+00:00", "2026-02-09T10:00:00+00:00"),
                )
                conn.commit()

                rows = list_pending_review_candidates(
                    conn, now_iso="2026-02-19T12:00:00+00:00"
                )

            # We should see due+active reviews sorted by due_at asc, including overdue backlog:
            # - Merge Two Sorted Lists day-7 (old overdue)
            # - Merge Two Sorted Lists day-21 (old overdue)
            # - Longest Substring day-7
            # - Contains Duplicate day-7
            # - Two Sum day-21 (due 2026-02-22) is not due yet and excluded
            self.assertEqual(len(rows), 4)
            self.assertEqual(str(rows[0]["title"]), "Merge Two Sorted Lists")
            self.assertEqual(int(rows[0]["review_day"]), 7)
            self.assertEqual(str(rows[1]["title"]), "Merge Two Sorted Lists")
            self.assertEqual(int(rows[1]["review_day"]), 21)
            self.assertEqual(str(rows[2]["title"]), "Longest Substring")
            self.assertEqual(int(rows[2]["review_day"]), 7)
            self.assertEqual(str(rows[3]["title"]), "Contains Duplicate")
            self.assertEqual(int(rows[3]["review_day"]), 7)


if __name__ == "__main__":
    unittest.main()
