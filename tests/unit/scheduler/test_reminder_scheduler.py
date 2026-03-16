from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from leetcoach.config import AppConfig
from leetcoach.db.migrate import migrate_database
from leetcoach.reminder_scheduler import (
    ReminderCandidate,
    build_daily_header_message,
    build_reminder_message,
    scheduler_preflight,
    select_candidates_for_batch,
    should_send_today,
    was_group_reminded_today,
)


class ReminderSchedulerUnitTest(unittest.TestCase):
    def test_should_send_today_true_when_never_reminded(self) -> None:
        candidate = ReminderCandidate(
            review_id=1,
            user_problem_id=1,
            review_day=7,
            due_at="2026-03-08T10:00:00+00:00",
            buffer_until="2026-03-10T10:00:00+00:00",
            last_reminded_at=None,
            solved_at="2026-03-01T10:00:00+00:00",
            title="X",
            leetcode_slug="x",
            neetcode_slug="x",
            telegram_chat_id="chat-1",
            timezone="Europe/Berlin",
            reminder_daily_max=None,
            reminder_hour_local=None,
        )
        self.assertTrue(should_send_today(candidate, "2026-03-08T12:00:00+00:00"))

    def test_should_send_today_false_same_local_day(self) -> None:
        candidate = ReminderCandidate(
            review_id=1,
            user_problem_id=1,
            review_day=7,
            due_at="2026-03-08T10:00:00+00:00",
            buffer_until="2026-03-10T10:00:00+00:00",
            last_reminded_at="2026-03-08T08:00:00+00:00",
            solved_at="2026-03-01T10:00:00+00:00",
            title="X",
            leetcode_slug="x",
            neetcode_slug="x",
            telegram_chat_id="chat-1",
            timezone="Europe/Berlin",
            reminder_daily_max=None,
            reminder_hour_local=None,
        )
        self.assertFalse(should_send_today(candidate, "2026-03-08T20:00:00+00:00"))

    def test_build_reminder_message_contains_key_fields(self) -> None:
        candidate = ReminderCandidate(
            review_id=1,
            user_problem_id=1,
            review_day=21,
            due_at="2026-03-22T10:00:00+00:00",
            buffer_until="2026-03-24T10:00:00+00:00",
            last_reminded_at=None,
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
        self.assertIn("Day 21", text)
        self.assertIn("Use /due, then /done <token> 21st", text)

    def test_should_send_today_true_on_new_local_day_even_same_utc_day(self) -> None:
        candidate = ReminderCandidate(
            review_id=1,
            user_problem_id=1,
            review_day=7,
            due_at="2026-03-08T10:00:00+00:00",
            buffer_until="2026-03-10T10:00:00+00:00",
            last_reminded_at="2026-03-09T09:30:00+00:00",
            solved_at="2026-03-01T10:00:00+00:00",
            title="X",
            leetcode_slug="x",
            neetcode_slug="x",
            telegram_chat_id="chat-1",
            timezone="Pacific/Kiritimati",
            reminder_daily_max=None,
            reminder_hour_local=None,
        )
        self.assertTrue(should_send_today(candidate, "2026-03-09T10:15:00+00:00"))

    def test_was_group_reminded_today_true_when_any_candidate_was_sent_today(self) -> None:
        candidates = [
            ReminderCandidate(
                review_id=1,
                user_problem_id=10,
                review_day=7,
                due_at="2026-03-08T12:00:00+00:00",
                buffer_until="2026-03-10T12:00:00+00:00",
                last_reminded_at=None,
                solved_at="2026-03-01T10:00:00+00:00",
                title="A",
                leetcode_slug="a",
                neetcode_slug="a",
                telegram_chat_id="chat-1",
                timezone="UTC",
                reminder_daily_max=None,
                reminder_hour_local=None,
            ),
            ReminderCandidate(
                review_id=2,
                user_problem_id=11,
                review_day=7,
                due_at="2026-03-08T12:00:00+00:00",
                buffer_until="2026-03-10T12:00:00+00:00",
                last_reminded_at="2026-03-09T08:00:00+00:00",
                solved_at="2026-03-01T10:00:00+00:00",
                title="B",
                leetcode_slug="b",
                neetcode_slug="b",
                telegram_chat_id="chat-1",
                timezone="UTC",
                reminder_daily_max=None,
                reminder_hour_local=None,
            ),
        ]
        self.assertTrue(
            was_group_reminded_today(candidates, "2026-03-09T12:00:00+00:00", "UTC")
        )

    def test_select_candidates_for_batch_prefers_pending_then_overdue(self) -> None:
        selected = select_candidates_for_batch(
            [
                ReminderCandidate(
                    review_id=1,
                    user_problem_id=100,
                    review_day=7,
                    due_at="2026-03-08T09:00:00+00:00",
                    buffer_until="2026-03-10T09:00:00+00:00",
                    last_reminded_at=None,
                    solved_at="2026-03-01T10:00:00+00:00",
                    title="Pending",
                    leetcode_slug="pending",
                    neetcode_slug="pending",
                    telegram_chat_id="chat-1",
                    timezone="UTC",
                    reminder_daily_max=None,
                    reminder_hour_local=None,
                ),
                ReminderCandidate(
                    review_id=2,
                    user_problem_id=101,
                    review_day=7,
                    due_at="2026-03-01T09:00:00+00:00",
                    buffer_until="2026-03-03T09:00:00+00:00",
                    last_reminded_at=None,
                    solved_at="2026-02-20T10:00:00+00:00",
                    title="Overdue",
                    leetcode_slug="overdue",
                    neetcode_slug="overdue",
                    telegram_chat_id="chat-1",
                    timezone="UTC",
                    reminder_daily_max=None,
                    reminder_hour_local=None,
                ),
            ],
            now_iso="2026-03-09T09:00:00+00:00",
            daily_max=2,
        )
        self.assertEqual([candidate.title for candidate in selected], ["Pending", "Overdue"])

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
