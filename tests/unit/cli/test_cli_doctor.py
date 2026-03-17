from __future__ import annotations

import io
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from click.testing import CliRunner

from leetcoach.cli import cli
from leetcoach.cli import _check_telegram_get_me, _mask_token
from leetcoach.db.migrate import migrate_database


class MainDoctorUnitTest(unittest.TestCase):
    def test_mask_token_handles_missing(self) -> None:
        self.assertEqual(_mask_token(None), "missing")
        self.assertEqual(_mask_token(""), "missing")

    def test_mask_token_masks_value(self) -> None:
        self.assertEqual(_mask_token("1234567890abcdef"), "12345678...cdef")

    def test_check_telegram_get_me_missing_token(self) -> None:
        ok, detail = _check_telegram_get_me(None)
        self.assertFalse(ok)
        self.assertIn("missing", detail.lower())

    @patch("leetcoach.cli.request.urlopen")
    def test_check_telegram_get_me_success(self, mock_urlopen) -> None:
        class _Resp:
            def read(self) -> bytes:
                return b'{"ok":true,"result":{"id":42,"username":"leetcoach_bot"}}'

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        mock_urlopen.return_value = _Resp()
        ok, detail = _check_telegram_get_me("123:token")
        self.assertTrue(ok)
        self.assertIn("@leetcoach_bot", detail)

    @patch("leetcoach.cli.request.urlopen")
    def test_check_telegram_get_me_http_error(self, mock_urlopen) -> None:
        err = HTTPError(
            url="https://api.telegram.org/bot123/getMe",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=io.BytesIO(b'{"ok":false,"error_code":404}'),
        )
        mock_urlopen.side_effect = err
        ok, detail = _check_telegram_get_me("123:token")
        self.assertFalse(ok)
        self.assertIn("HTTP 404", detail)

    def test_scheduler_doctor_fails_on_unmigrated_db(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "leetcoach-test.db"
            env = {
                "LEETCOACH_DB_PATH": str(db_path),
                "LEETCOACH_TELEGRAM_BOT_TOKEN": "123:token",
                "LEETCOACH_REMINDER_HOUR_LOCAL": "8",
                "LEETCOACH_REMINDER_DAILY_MAX": "2",
            }
            runner = CliRunner()
            with patch.dict("os.environ", env, clear=False):
                result = runner.invoke(cli, ["scheduler-doctor"])
            self.assertNotEqual(result.exit_code, 0)
            self.assertIn("scheduler_preflight: FAIL", result.output)

    def test_scheduler_doctor_ok_after_migrate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "leetcoach-test.db"
            migrate_database(str(db_path))
            env = {
                "LEETCOACH_DB_PATH": str(db_path),
                "LEETCOACH_TELEGRAM_BOT_TOKEN": "123:token",
                "LEETCOACH_REMINDER_HOUR_LOCAL": "8",
                "LEETCOACH_REMINDER_DAILY_MAX": "2",
            }
            runner = CliRunner()
            with patch.dict("os.environ", env, clear=False):
                result = runner.invoke(cli, ["scheduler-doctor"])
            self.assertEqual(result.exit_code, 0)
            self.assertIn("scheduler_preflight: OK", result.output)

    def test_reset_reminders_clears_only_requested_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "leetcoach-test.db"
            migrate_database(str(db_path))
            now_iso = "2026-03-18T08:00:00+00:00"
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                conn.execute(
                    """
                    INSERT INTO users (
                        telegram_user_id, telegram_chat_id, timezone,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    ("u-1", "chat-1", "UTC", now_iso, now_iso),
                )
                conn.execute(
                    """
                    INSERT INTO problems (
                        title, difficulty, leetcode_slug, neetcode_slug,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "Contains Duplicate",
                        "easy",
                        "contains-duplicate",
                        "contains-duplicate",
                        now_iso,
                        now_iso,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO user_problems (
                        user_id, problem_id, pattern, solved_at,
                        queue_position, review_count,
                        last_review_requested_at, last_reviewed_at,
                        created_at, updated_at
                    ) VALUES (
                        1, 1, 'Arrays & Hashing', ?, 10, 2, ?, ?, ?, ?
                    )
                    """,
                    (now_iso, now_iso, "2026-03-10T08:00:00+00:00", now_iso, now_iso),
                )
                conn.commit()

            env = {
                "LEETCOACH_DB_PATH": str(db_path),
                "LEETCOACH_TELEGRAM_BOT_TOKEN": "123:token",
            }
            runner = CliRunner()
            with patch.dict("os.environ", env, clear=False):
                result = runner.invoke(cli, ["reset-reminders"])

            self.assertEqual(result.exit_code, 0)
            self.assertIn("cleared outstanding reminder state for 1 problem", result.output)

            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    """
                    SELECT queue_position, review_count, last_review_requested_at, last_reviewed_at
                    FROM user_problems
                    """
                ).fetchone()
            self.assertEqual(int(row["queue_position"]), 10)
            self.assertEqual(int(row["review_count"]), 2)
            self.assertIsNone(row["last_review_requested_at"])
            self.assertEqual(str(row["last_reviewed_at"]), "2026-03-10T08:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
