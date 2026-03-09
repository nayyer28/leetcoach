from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from leetcoach.config import AppConfig
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
            )
            now_iso = "2026-02-10T09:00:00+00:00"
            first = run_scheduler_once(config=cfg, now_iso=now_iso)
            self.assertEqual(first.sent, 1)
            self.assertEqual(first.failed, 0)
            self.assertEqual(mock_send.call_count, 1)

            with get_connection(str(db_path)) as conn:
                row = conn.execute(
                    "SELECT last_reminded_at FROM problem_reviews WHERE review_day = 7"
                ).fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(str(row["last_reminded_at"]), now_iso)

            second = run_scheduler_once(config=cfg, now_iso="2026-02-10T09:30:00+00:00")
            self.assertEqual(second.sent, 0)
            self.assertEqual(second.skipped_already_reminded_today, 1)
            self.assertEqual(mock_send.call_count, 1)


if __name__ == "__main__":
    unittest.main()
