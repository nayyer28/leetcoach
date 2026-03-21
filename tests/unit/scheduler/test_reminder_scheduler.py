from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from leetcoach.app.infrastructure.config.app_config import AppConfig
from leetcoach.app.misc.migrate import migrate_database
from leetcoach.app.application.reviews.reminder_engine import (
    ReminderCandidate,
    build_daily_header_message,
    build_reminder_message,
    scheduler_preflight,
    select_candidates_for_batch,
    should_send_today,
    was_group_reminded_today,
)


class ReminderSchedulerUnitTest(unittest.TestCase):
    def _candidate(
        self,
        *,
        title: str = "X",
        queue_position: int = 10,
        last_review_requested_at: str | None = None,
        last_reviewed_at: str | None = None,
        review_count: int = 0,
        timezone: str = "UTC",
    ) -> ReminderCandidate:
        return ReminderCandidate(
            user_problem_id=1,
            user_id=1,
            queue_position=queue_position,
            last_review_requested_at=last_review_requested_at,
            last_reviewed_at=last_reviewed_at,
            review_count=review_count,
            solved_at="2026-03-01T10:00:00+00:00",
            title=title,
            leetcode_slug="x",
            neetcode_slug="x",
            telegram_chat_id="chat-1",
            timezone=timezone,
            reminder_daily_max=None,
            reminder_hour_local=None,
        )

    def test_should_send_today_true_when_never_reminded(self) -> None:
        candidate = self._candidate(timezone="Europe/Berlin")
        self.assertTrue(should_send_today(candidate, "2026-03-08T12:00:00+00:00"))

    def test_should_send_today_false_same_local_day(self) -> None:
        candidate = self._candidate(
            timezone="Europe/Berlin",
            last_review_requested_at="2026-03-08T08:00:00+00:00",
        )
        self.assertFalse(should_send_today(candidate, "2026-03-08T20:00:00+00:00"))

    def test_build_reminder_message_contains_key_fields(self) -> None:
        candidate = ReminderCandidate(
            user_problem_id=1,
            user_id=1,
            queue_position=30,
            last_review_requested_at=None,
            last_reviewed_at="2026-03-15T10:00:00+00:00",
            review_count=2,
            solved_at="2026-03-01T10:00:00+00:00",
            title="LRU Cache",
            leetcode_slug="lru-cache",
            neetcode_slug="lru-cache",
            telegram_chat_id="chat-1",
            timezone="UTC",
            reminder_daily_max=None,
            reminder_hour_local=None,
        )
        text = build_reminder_message(candidate)
        self.assertIn("LeetCoach Reminder", text)
        self.assertIn("LRU Cache", text)
        self.assertIn("Reviews completed: 2", text)
        self.assertNotIn("Queue position", text)
        self.assertIn("Use /due, then /reviewed <token>", text)

    def test_should_send_today_true_on_new_local_day_even_same_utc_day(self) -> None:
        candidate = self._candidate(
            timezone="Pacific/Kiritimati",
            last_review_requested_at="2026-03-09T09:30:00+00:00",
        )
        self.assertTrue(should_send_today(candidate, "2026-03-09T10:15:00+00:00"))

    def test_was_group_reminded_today_true_when_any_candidate_was_sent_today(self) -> None:
        candidates = [
            self._candidate(title="A"),
            self._candidate(title="B", last_review_requested_at="2026-03-09T08:00:00+00:00"),
        ]
        self.assertTrue(
            was_group_reminded_today(candidates, "2026-03-09T12:00:00+00:00", "UTC")
        )

    def test_select_candidates_for_batch_uses_queue_order(self) -> None:
        selected = select_candidates_for_batch(
            [
                self._candidate(title="Second", queue_position=20),
                self._candidate(title="First", queue_position=10),
                self._candidate(
                    title="Already requested today",
                    queue_position=5,
                    last_review_requested_at="2026-03-09T07:00:00+00:00",
                ),
            ],
            now_iso="2026-03-09T09:00:00+00:00",
            daily_max=2,
        )
        self.assertEqual([candidate.title for candidate in selected], ["First", "Second"])

    def test_build_daily_header_message(self) -> None:
        text = build_daily_header_message()
        self.assertIn("Daily LeetCoach Review Plan", text)
        self.assertIn("messages below", text.lower())

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
                any("LEETCOACH_TELEGRAM_BOT_TOKEN is missing" in issue for issue in result.issues)
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
