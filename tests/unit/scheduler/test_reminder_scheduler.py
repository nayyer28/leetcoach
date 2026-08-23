from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from leetcoach.app.infrastructure.config.app_config import AppConfig
from leetcoach.app.misc.migrate import migrate_database
from leetcoach.app.application.reviews.reminder_engine import (
    ReminderCandidate,
    build_reminder_message,
    scheduler_preflight,
    was_user_reminded_today,
)


def _candidate(
    *,
    title: str = "X",
    review_count: int = 0,
    entered_at: str = "2026-03-01T10:00:00+00:00",
    solved_at: str = "2026-03-01T10:00:00+00:00",
    timezone: str = "UTC",
    last_reminded_at: str | None = None,
) -> ReminderCandidate:
    return ReminderCandidate(
        user_problem_id=1,
        display_id=1,
        problem_ref="P1",
        user_id=1,
        review_count=review_count,
        entered_at=entered_at,
        solved_at=solved_at,
        title=title,
        leetcode_slug="x",
        neetcode_slug="x",
        telegram_chat_id="chat-1",
        timezone=timezone,
        reminder_daily_max=None,
        reminder_hour_local=None,
        last_reminded_at=last_reminded_at,
    )


class ReminderSchedulerUnitTest(unittest.TestCase):
    def test_was_user_reminded_today_false_when_never_reminded(self) -> None:
        self.assertFalse(
            was_user_reminded_today(
                last_reminded_at=None,
                now_iso="2026-03-08T12:00:00+00:00",
                timezone_name="Europe/Berlin",
            )
        )

    def test_was_user_reminded_today_true_same_local_day(self) -> None:
        self.assertTrue(
            was_user_reminded_today(
                last_reminded_at="2026-03-08T08:00:00+00:00",
                now_iso="2026-03-08T20:00:00+00:00",
                timezone_name="Europe/Berlin",
            )
        )

    def test_was_user_reminded_today_false_on_new_local_day_even_same_utc_day(
        self,
    ) -> None:
        # Kiritimati is UTC+14 — 10:15 UTC is already the next calendar day locally.
        self.assertFalse(
            was_user_reminded_today(
                last_reminded_at="2026-03-09T09:30:00+00:00",
                now_iso="2026-03-09T10:15:00+00:00",
                timezone_name="Pacific/Kiritimati",
            )
        )

    def test_build_reminder_message_contains_key_fields(self) -> None:
        candidate = _candidate(
            title="LRU Cache",
            review_count=2,
            entered_at="2026-03-15T10:00:00+00:00",
            solved_at="2026-03-01T10:00:00+00:00",
        )
        text = build_reminder_message(candidate)
        self.assertIn("LeetCoach Reminder", text)
        self.assertIn("ID: P1", text)
        self.assertIn("LRU Cache", text)
        self.assertIn("Reviews completed: 2", text)
        self.assertNotIn("Queue position", text)
        self.assertNotIn("Last reviewed", text)
        self.assertIn("Use /reviewed <id>", text)

    def test_scheduler_preflight_fails_when_token_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "leetcoach-test.db"
            migrate_database(str(db_path))
            cfg = AppConfig(
                environment="test",
                log_level="INFO",
                timezone="UTC",
                db_path=str(db_path),
                telegram_bot_token=None,
                allowed_user_ids=frozenset(),
                reminder_hour_local=8,
                reminder_daily_max=2,
            )
            result = scheduler_preflight(cfg)
            self.assertFalse(result.ok)
            self.assertTrue(
                any(
                    "LEETCOACH_TELEGRAM_BOT_TOKEN is missing" in issue
                    for issue in result.issues
                )
            )

    def test_scheduler_preflight_fails_on_unmigrated_db(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "leetcoach-test.db"
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
            result = scheduler_preflight(cfg)
            self.assertFalse(result.ok)
            self.assertTrue(any("run `lch migrate`" in issue for issue in result.issues))

    def test_scheduler_preflight_ok_after_migrate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "leetcoach-test.db"
            migrate_database(str(db_path))
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
            result = scheduler_preflight(cfg)
            self.assertTrue(result.ok)


if __name__ == "__main__":
    unittest.main()
