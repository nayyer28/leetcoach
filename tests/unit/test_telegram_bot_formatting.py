from __future__ import annotations

import unittest

from leetcoach.config import AppConfig
from leetcoach.services.due_tokens import ProblemToken
from leetcoach.services.query_service import DueReviewItem
from leetcoach.telegram_bot import (
    DueProblemEntry,
    _chunk_text,
    _format_timestamp,
    _group_due_entries,
    _is_user_allowed,
    _leetcode_url,
    _neetcode_url,
    _parse_review_day,
    _normalize_solved_at,
    _render_problem_detail,
    _render_due,
    _render_quiz_question,
    _render_quiz_reveal,
    _render_problem_rows,
)
from leetcoach.services.quiz_service import QuizQuestionPayload, is_known_quiz_topic


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
                "user_problem_id": 10,
                "title": "Validate Binary Search Tree",
                "difficulty": "medium",
                "pattern": "Trees",
                "solved_at": "2026-03-08T13:28:44+00:00",
                "leetcode_slug": "validate-binary-search-tree",
                "neetcode_slug": "valid-binary-search-tree",
            }
        ]
        token_map = {"A1": ProblemToken(user_problem_id=10)}
        text = _render_problem_rows(rows, token_map, "Europe/Berlin")
        self.assertIn("Your Problems", text)
        self.assertNotIn("<pre>", text)
        self.assertIn("[A1]", text)
        self.assertIn("Use /show A1", text)
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
                "user_problem_id": 30,
                "title": "Graph Valid Tree",
                "difficulty": "medium",
                "pattern": "Graphs",
                "solved_at": "2026-03-08T13:28:44+00:00",
                "leetcode_slug": "graph-valid-tree",
                "neetcode_slug": "graph-valid-tree",
            },
            {
                "user_problem_id": 10,
                "title": "Contains Duplicate",
                "difficulty": "easy",
                "pattern": "Arrays and Hashing",
                "solved_at": "2026-03-08T13:28:44+00:00",
                "leetcode_slug": "contains-duplicate",
                "neetcode_slug": "contains-duplicate",
            },
            {
                "user_problem_id": 20,
                "title": "Binary Tree Right Side View",
                "difficulty": "medium",
                "pattern": "Tree DFS",
                "solved_at": "2026-03-08T13:28:44+00:00",
                "leetcode_slug": "binary-tree-right-side-view",
                "neetcode_slug": "binary-tree-right-side-view",
            },
        ]
        token_map = {
            "A1": ProblemToken(user_problem_id=10),
            "A2": ProblemToken(user_problem_id=20),
            "A3": ProblemToken(user_problem_id=30),
        }
        text = _render_problem_rows(rows, token_map, "Europe/Berlin")
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
                solved_at="2026-03-08T13:28:44+00:00",
                due_at="2026-03-15T13:28:44+00:00",
                buffer_until="2026-03-17T13:28:44+00:00",
                status="pending",
            )
        ]
        entries = _group_due_entries(items)
        token_map = {"A1": ProblemToken(user_problem_id=10)}
        text = _render_due(entries, token_map, "Europe/Berlin")
        self.assertIn("Due Reviews", text)
        self.assertNotIn("<pre>", text)
        self.assertIn("[A1]", text)
        self.assertIn("First attempt", text)
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
                solved_at="2026-03-01T10:00:00+00:00",
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
                solved_at="2026-03-01T10:00:00+00:00",
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
                solved_at="2026-03-01T10:00:00+00:00",
                due_at="2026-03-06T10:00:00+00:00",
                buffer_until="2026-03-08T10:00:00+00:00",
                status="overdue",
            ),
        ]
        entries = _group_due_entries(items)
        token_map = {
            "A1": ProblemToken(user_problem_id=10),
            "A2": ProblemToken(user_problem_id=20),
            "A3": ProblemToken(user_problem_id=30),
        }
        text = _render_due(entries, token_map, "UTC")
        self.assertLess(text.find("[A1] Overdue Older"), text.find("[A2] Overdue Newer"))
        self.assertLess(text.find("[A2] Overdue Newer"), text.find("[A3] Pending Later"))

    def test_group_due_entries_merges_day7_and_day21(self) -> None:
        items = [
            DueReviewItem(
                user_problem_id=10,
                review_day=7,
                title="X",
                leetcode_slug="x",
                neetcode_slug="x",
                solved_at="2026-03-01T10:00:00+00:00",
                due_at="2026-03-08T10:00:00+00:00",
                buffer_until="2026-03-10T10:00:00+00:00",
                status="overdue",
            ),
            DueReviewItem(
                user_problem_id=10,
                review_day=21,
                title="X",
                leetcode_slug="x",
                neetcode_slug="x",
                solved_at="2026-03-01T10:00:00+00:00",
                due_at="2026-03-22T10:00:00+00:00",
                buffer_until="2026-03-24T10:00:00+00:00",
                status="pending",
            ),
        ]
        entries = _group_due_entries(items)
        self.assertEqual(len(entries), 1)
        self.assertEqual(set(entries[0].checkpoints.keys()), {7, 21})

    def test_parse_review_day(self) -> None:
        self.assertEqual(_parse_review_day("7"), 7)
        self.assertEqual(_parse_review_day("7th"), 7)
        self.assertEqual(_parse_review_day("21"), 21)
        self.assertEqual(_parse_review_day("21st"), 21)
        self.assertIsNone(_parse_review_day("14"))

    def test_quiz_topic_recognition(self) -> None:
        self.assertTrue(is_known_quiz_topic("dp"))
        self.assertTrue(is_known_quiz_topic("Binary Search"))
        self.assertFalse(is_known_quiz_topic("made-up-topic-xyz"))

    def test_render_quiz_question_and_reveal(self) -> None:
        question = QuizQuestionPayload(
            topic="arrays",
            question="Which structure gives O(1) average lookup?",
            options={
                "A": "Hash map",
                "B": "Binary search tree",
                "C": "Linked list",
                "D": "Queue",
            },
            correct_option="A",
            why_correct="Hash map gives average O(1).",
            why_others_wrong={
                "B": "BST is O(log n) average.",
                "C": "Linked list search is O(n).",
                "D": "Queue is not for key lookup.",
            },
            concept_takeaway="Choose hash map for fast key-value lookup.",
        )
        question_text = _render_quiz_question(question, "gemini-2.5-flash-lite")
        reveal_text = _render_quiz_reveal(question)
        self.assertIn("Quiz Time", question_text)
        self.assertIn("A) Hash map", question_text)
        self.assertIn("Model: gemini-2.5-flash-lite", question_text)
        self.assertIn("Correct option: A", reveal_text)
        self.assertIn("Takeaway", reveal_text)

    def test_render_problem_detail_includes_all_optional_fields(self) -> None:
        row = {
            "user_problem_id": "10",
            "title": "Validate Binary Search Tree",
            "difficulty": "medium",
            "pattern": "Trees",
            "solved_at": "2026-03-08T13:28:44+00:00",
            "leetcode_slug": "validate-binary-search-tree",
            "neetcode_slug": "valid-binary-search-tree",
            "concepts": "Track lower and upper bounds recursively.",
            "time_complexity": "O(n)",
            "space_complexity": "O(h)",
            "notes": "Careful with duplicates.",
            "created_at": "2026-03-08T13:28:44+00:00",
            "updated_at": "2026-03-08T13:28:44+00:00",
        }
        text = _render_problem_detail(row, "Europe/Berlin")
        self.assertIn("Validate Binary Search Tree", text)
        self.assertIn("Concepts:", text)
        self.assertIn("Track lower and upper bounds recursively.", text)
        self.assertIn("Time complexity:", text)
        self.assertIn("O(n)", text)
        self.assertIn("Space complexity:", text)
        self.assertIn("O(h)", text)
        self.assertIn("Notes:", text)
        self.assertIn("Careful with duplicates.", text)


if __name__ == "__main__":
    unittest.main()
