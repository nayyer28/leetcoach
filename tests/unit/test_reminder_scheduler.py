from __future__ import annotations

import unittest

from leetcoach.reminder_scheduler import (
    ReminderCandidate,
    build_reminder_message,
    should_send_today,
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
        )
        self.assertTrue(should_send_today(candidate, "2026-03-09T10:15:00+00:00"))


if __name__ == "__main__":
    unittest.main()
