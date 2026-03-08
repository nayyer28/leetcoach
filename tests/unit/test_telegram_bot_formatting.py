from __future__ import annotations

import unittest

from leetcoach.services.due_tokens import ReviewToken
from leetcoach.services.query_service import DueReviewItem
from leetcoach.telegram_bot import (
    _format_timestamp,
    _normalize_solved_at,
    _render_due,
    _render_problem_rows,
)


class TelegramBotFormattingUnitTest(unittest.TestCase):
    def test_format_timestamp_uses_timezone(self) -> None:
        value = _format_timestamp("2026-03-08T13:28:44+00:00", "Europe/Berlin")
        self.assertIn("08 Mar 2026, 14:28", value)
        self.assertIn("CET", value)

    def test_normalize_solved_at_accepts_local_datetime(self) -> None:
        value = _normalize_solved_at("2026-03-08 14:30", "Europe/Berlin")
        self.assertEqual(value, "2026-03-08T13:30:00+00:00")

    def test_normalize_solved_at_rejects_invalid(self) -> None:
        value = _normalize_solved_at("not-a-date", "Europe/Berlin")
        self.assertIsNone(value)

    def test_render_problem_rows_includes_header_and_human_time(self) -> None:
        rows = [
            {
                "title": "Validate Binary Search Tree",
                "difficulty": "medium",
                "pattern": "Trees",
                "solved_at": "2026-03-08T13:28:44+00:00",
                "leetcode_slug": "validate-binary-search-tree",
                "neetcode_slug": "valid-binary-search-tree",
            }
        ]
        text = _render_problem_rows(rows, "Europe/Berlin")
        self.assertIn("Your Problems", text)
        self.assertIn("Difficulty: Medium", text)
        self.assertIn("Solved: 08 Mar 2026, 14:28 CET", text)

    def test_render_due_includes_header_token_and_human_time(self) -> None:
        items = [
            DueReviewItem(
                user_problem_id=10,
                review_day=7,
                title="Validate Binary Search Tree",
                leetcode_slug="validate-binary-search-tree",
                neetcode_slug="valid-binary-search-tree",
                due_at="2026-03-15T13:28:44+00:00",
                buffer_until="2026-03-17T13:28:44+00:00",
                status="pending",
            )
        ]
        token_map = {"A1": ReviewToken(user_problem_id=10, review_day=7)}
        text = _render_due(items, token_map, "Europe/Berlin")
        self.assertIn("Due Reviews", text)
        self.assertIn("[A1]", text)
        self.assertIn("Status: PENDING", text)
        self.assertIn("Due: 15 Mar 2026, 14:28 CET", text)


if __name__ == "__main__":
    unittest.main()
