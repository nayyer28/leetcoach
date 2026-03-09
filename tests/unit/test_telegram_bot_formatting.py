from __future__ import annotations

import unittest

from leetcoach.config import AppConfig
from leetcoach.services.due_tokens import ReviewToken
from leetcoach.services.query_service import DueReviewItem
from leetcoach.telegram_bot import (
    _chunk_text,
    _format_timestamp,
    _is_user_allowed,
    _leetcode_url,
    _neetcode_url,
    _normalize_solved_at,
    _render_due,
    _render_problem_rows,
)


class TelegramBotFormattingUnitTest(unittest.TestCase):
    def test_chunk_text_splits_long_message(self) -> None:
        text = ("line-1234567890\n" * 1000).strip()
        chunks = _chunk_text(text, chunk_size=500)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 500 for chunk in chunks))

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

    def test_problem_url_builders_from_slug(self) -> None:
        self.assertEqual(
            _leetcode_url("validate-binary-search-tree"),
            "https://leetcode.com/problems/validate-binary-search-tree/description/",
        )
        self.assertEqual(
            _neetcode_url("valid-binary-search-tree"),
            "https://neetcode.io/problems/valid-binary-search-tree/question",
        )
        self.assertIsNone(_neetcode_url(None))

    def test_user_allowlist_behavior(self) -> None:
        open_cfg = AppConfig(
            environment="development",
            log_level="INFO",
            timezone="UTC",
            db_path=".local/leetcoach.db",
            telegram_bot_token="token",
            allowed_user_ids=frozenset(),
        )
        locked_cfg = AppConfig(
            environment="development",
            log_level="INFO",
            timezone="UTC",
            db_path=".local/leetcoach.db",
            telegram_bot_token="token",
            allowed_user_ids=frozenset({"12345"}),
        )
        self.assertTrue(_is_user_allowed("999", open_cfg))
        self.assertTrue(_is_user_allowed("12345", locked_cfg))
        self.assertFalse(_is_user_allowed("999", locked_cfg))

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
        self.assertNotIn("<pre>", text)
        self.assertIn("Validate Binary Search Tree", text)
        self.assertIn("Medium", text)
        self.assertIn("Trees", text)
        self.assertIn("08 Mar 14:28 CET", text)
        self.assertIn(
            "https://leetcode.com/problems/validate-binary-search-tree/description/",
            text,
        )
        self.assertIn(
            "https://neetcode.io/problems/valid-binary-search-tree/question",
            text,
        )

    def test_render_problem_rows_groups_patterns_in_roadmap_order(self) -> None:
        rows = [
            {
                "title": "Graph Valid Tree",
                "difficulty": "medium",
                "pattern": "Graphs",
                "solved_at": "2026-03-08T13:28:44+00:00",
                "leetcode_slug": "graph-valid-tree",
                "neetcode_slug": "graph-valid-tree",
            },
            {
                "title": "Contains Duplicate",
                "difficulty": "easy",
                "pattern": "Arrays and Hashing",
                "solved_at": "2026-03-08T13:28:44+00:00",
                "leetcode_slug": "contains-duplicate",
                "neetcode_slug": "contains-duplicate",
            },
            {
                "title": "Binary Tree Right Side View",
                "difficulty": "medium",
                "pattern": "Tree DFS",
                "solved_at": "2026-03-08T13:28:44+00:00",
                "leetcode_slug": "binary-tree-right-side-view",
                "neetcode_slug": "binary-tree-right-side-view",
            },
        ]
        text = _render_problem_rows(rows, "Europe/Berlin")
        self.assertLess(text.find("🧩 Arrays & Hashing"), text.find("🧩 Trees"))
        self.assertLess(text.find("🧩 Trees"), text.find("🧩 Graphs"))

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
        self.assertNotIn("<pre>", text)
        self.assertIn("[A1]", text)
        self.assertIn("PENDING", text)
        self.assertIn("15 Mar 14:28 CET", text)
        self.assertIn(
            "https://leetcode.com/problems/validate-binary-search-tree/description/",
            text,
        )
        self.assertIn(
            "https://neetcode.io/problems/valid-binary-search-tree/question",
            text,
        )

    def test_render_due_sorts_overdue_first_then_due_date(self) -> None:
        items = [
            DueReviewItem(
                user_problem_id=30,
                review_day=21,
                title="Pending Later",
                leetcode_slug="l3",
                neetcode_slug="n3",
                due_at="2026-03-12T10:00:00+00:00",
                buffer_until="2026-03-14T10:00:00+00:00",
                status="pending",
            ),
            DueReviewItem(
                user_problem_id=20,
                review_day=7,
                title="Overdue Newer",
                leetcode_slug="l2",
                neetcode_slug="n2",
                due_at="2026-03-08T10:00:00+00:00",
                buffer_until="2026-03-10T10:00:00+00:00",
                status="overdue",
            ),
            DueReviewItem(
                user_problem_id=10,
                review_day=7,
                title="Overdue Older",
                leetcode_slug="l1",
                neetcode_slug="n1",
                due_at="2026-03-06T10:00:00+00:00",
                buffer_until="2026-03-08T10:00:00+00:00",
                status="overdue",
            ),
        ]
        token_map = {
            "A1": ReviewToken(user_problem_id=10, review_day=7),
            "A2": ReviewToken(user_problem_id=20, review_day=7),
            "A3": ReviewToken(user_problem_id=30, review_day=21),
        }
        text = _render_due(items, token_map, "UTC")
        self.assertLess(text.find("Overdue Older"), text.find("Overdue Newer"))
        self.assertLess(text.find("Overdue Newer"), text.find("Pending Later"))


if __name__ == "__main__":
    unittest.main()
