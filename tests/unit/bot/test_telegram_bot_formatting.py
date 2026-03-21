from __future__ import annotations

import unittest

from telegram import InlineKeyboardMarkup

from leetcoach.app.infrastructure.config.app_config import AppConfig
from leetcoach.app.application.quiz.common import (
    QuizQuestionPayload,
    extract_quiz_answer_option,
    is_known_quiz_topic,
)
from leetcoach.app.application.reviews.due_reviews import DueReviewItem
from leetcoach.app.interface.bot.handlers import (
    _canonical_pattern_label,
    _chunk_text,
    _commands_help_text,
    _difficulty_inline_markup,
    _extract_problem_slug,
    _format_timestamp,
    _is_user_allowed,
    _leetcode_url,
    _neetcode_url,
    _normalize_difficulty_input,
    _parse_log_show_limit,
    _normalize_solved_at,
    _unknown_command_help_text,
    _pattern_inline_markup,
    _unknown_text_help_text,
    _render_problem_detail,
    _render_due,
    _render_quiz_question,
    _render_quiz_reveal,
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

    def test_normalize_difficulty_input(self) -> None:
        self.assertEqual(_normalize_difficulty_input("Easy"), "easy")
        self.assertEqual(_normalize_difficulty_input("MEDIUM"), "medium")
        self.assertEqual(_normalize_difficulty_input("hard"), "hard")
        self.assertIsNone(_normalize_difficulty_input("med"))

    def test_difficulty_inline_markup_has_expected_buttons(self) -> None:
        markup = _difficulty_inline_markup()
        self.assertIsInstance(markup, InlineKeyboardMarkup)
        self.assertEqual(
            [button.text for button in markup.inline_keyboard[0]],
            ["Easy", "Medium", "Hard"],
        )
        self.assertEqual(
            [button.callback_data for button in markup.inline_keyboard[0]],
            ["log:difficulty:easy", "log:difficulty:medium", "log:difficulty:hard"],
        )

    def test_canonical_pattern_label(self) -> None:
        self.assertEqual(_canonical_pattern_label("Trees"), "Trees")
        self.assertEqual(_canonical_pattern_label("tree"), "Trees")
        self.assertEqual(_canonical_pattern_label("tree dfs"), "Trees")
        self.assertEqual(_canonical_pattern_label("Heap"), "Heap / Priority Queue")
        self.assertIsNone(_canonical_pattern_label("totally unknown"))

    def test_pattern_inline_markup_has_known_pattern_buttons(self) -> None:
        markup = _pattern_inline_markup()
        self.assertIsInstance(markup, InlineKeyboardMarkup)
        self.assertEqual(markup.inline_keyboard[0][0].text, "Arrays & Hashing")
        self.assertEqual(
            markup.inline_keyboard[0][0].callback_data,
            "log:pattern:arrays hashing",
        )
        self.assertEqual(markup.inline_keyboard[-1][-1].text, "Math & Geometry")
        self.assertEqual(
            markup.inline_keyboard[-1][-1].callback_data,
            "log:pattern:math geometry",
        )

    def test_extract_problem_slug_from_url_or_slug(self) -> None:
        self.assertEqual(
            _extract_problem_slug(
                "https://leetcode.com/problems/validate-binary-search-tree/description/",
                provider="leetcode",
            ),
            "validate-binary-search-tree",
        )
        self.assertEqual(
            _extract_problem_slug(
                "https://neetcode.io/problems/valid-binary-search-tree/question",
                provider="neetcode",
            ),
            "valid-binary-search-tree",
        )
        self.assertEqual(
            _extract_problem_slug(
                "https://leetcode.com/problems/validate-binary-search-tree/editorial",
                provider="leetcode",
            ),
            "validate-binary-search-tree",
        )
        self.assertEqual(
            _extract_problem_slug(
                "https://neetcode.io/problems/valid-binary-search-tree/anything",
                provider="neetcode",
            ),
            "valid-binary-search-tree",
        )
        self.assertEqual(
            _extract_problem_slug("validate-binary-search-tree", provider="leetcode"),
            "validate-binary-search-tree",
        )
        self.assertEqual(
            _extract_problem_slug("valid-binary-search-tree", provider="neetcode"),
            "valid-binary-search-tree",
        )
        self.assertIsNone(_extract_problem_slug("not a slug", provider="leetcode"))

    def test_commands_help_text_uses_guided_edit_syntax(self) -> None:
        help_text = _commands_help_text()
        self.assertIn("• /edit P1", help_text)
        self.assertNotIn("/edit P1 lc", help_text)
        self.assertIn("• /ask &lt;question&gt;", help_text)

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
                "display_id": 1,
                "problem_ref": "P1",
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
        self.assertIn("[P1]", text)
        self.assertIn("Use /show P1", text)
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
                "display_id": 3,
                "problem_ref": "P3",
                "title": "Graph Valid Tree",
                "difficulty": "medium",
                "pattern": "Graphs",
                "solved_at": "2026-03-08T13:28:44+00:00",
                "leetcode_slug": "graph-valid-tree",
                "neetcode_slug": "graph-valid-tree",
            },
            {
                "user_problem_id": 10,
                "display_id": 1,
                "problem_ref": "P1",
                "title": "Contains Duplicate",
                "difficulty": "easy",
                "pattern": "Arrays and Hashing",
                "solved_at": "2026-03-08T13:28:44+00:00",
                "leetcode_slug": "contains-duplicate",
                "neetcode_slug": "contains-duplicate",
            },
            {
                "user_problem_id": 20,
                "display_id": 2,
                "problem_ref": "P2",
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

    def test_render_problem_rows_orders_oldest_first_within_pattern(self) -> None:
        rows = [
            {
                "user_problem_id": 10,
                "display_id": 2,
                "problem_ref": "P2",
                "title": "Later Problem",
                "difficulty": "medium",
                "pattern": "Trees",
                "solved_at": "2026-03-10T13:28:44+00:00",
                "leetcode_slug": "later-problem",
                "neetcode_slug": "later-problem",
            },
            {
                "user_problem_id": 20,
                "display_id": 1,
                "problem_ref": "P1",
                "title": "Earlier Problem",
                "difficulty": "easy",
                "pattern": "Trees",
                "solved_at": "2026-03-08T13:28:44+00:00",
                "leetcode_slug": "earlier-problem",
                "neetcode_slug": "earlier-problem",
            },
        ]
        text = _render_problem_rows(rows, "Europe/Berlin")
        self.assertLess(text.find("Earlier Problem"), text.find("Later Problem"))

    def test_render_due_includes_header_token_and_human_time(self) -> None:
        items = [
            DueReviewItem(
                user_problem_id=10,
                display_id=1,
                problem_ref="P1",
                title="Validate Binary Search Tree",
                leetcode_slug="validate-binary-search-tree",
                neetcode_slug="valid-binary-search-tree",
                solved_at="2026-03-08T13:28:44+00:00",
                review_count=2,
                requested_at="2026-03-15T13:28:44+00:00",
                last_reviewed_at="2026-03-10T13:28:44+00:00",
                status="pending",
            )
        ]
        text = _render_due(items, "Europe/Berlin")
        self.assertIn("Due Reviews", text)
        self.assertNotIn("<pre>", text)
        self.assertIn("[P1]", text)
        self.assertIn("First attempt", text)
        self.assertIn("Reviews completed", text)
        self.assertIn("15 Mar 14:28 CET", text)
        self.assertIn(
            "https://leetcode.com/problems/validate-binary-search-tree/description/",
            text,
        )
        self.assertIn(
            "https://neetcode.io/problems/valid-binary-search-tree/question",
            text,
        )

    def test_render_due_preserves_due_item_order(self) -> None:
        items = [
            DueReviewItem(
                user_problem_id=30,
                display_id=3,
                problem_ref="P3",
                title="Pending Later",
                leetcode_slug="l3",
                neetcode_slug="n3",
                solved_at="2026-03-01T10:00:00+00:00",
                review_count=1,
                requested_at="2026-03-12T10:00:00+00:00",
                last_reviewed_at=None,
                status="pending",
            ),
            DueReviewItem(
                user_problem_id=20,
                display_id=2,
                problem_ref="P2",
                title="Overdue Newer",
                leetcode_slug="l2",
                neetcode_slug="n2",
                solved_at="2026-03-01T10:00:00+00:00",
                review_count=0,
                requested_at="2026-03-08T10:00:00+00:00",
                last_reviewed_at=None,
                status="pending",
            ),
            DueReviewItem(
                user_problem_id=10,
                display_id=1,
                problem_ref="P1",
                title="Overdue Older",
                leetcode_slug="l1",
                neetcode_slug="n1",
                solved_at="2026-03-01T10:00:00+00:00",
                review_count=0,
                requested_at="2026-03-06T10:00:00+00:00",
                last_reviewed_at=None,
                status="pending",
            ),
        ]
        text = _render_due(items, "UTC")
        self.assertLess(text.find("[P3] Pending Later"), text.find("[P2] Overdue Newer"))
        self.assertLess(text.find("[P2] Overdue Newer"), text.find("[P1] Overdue Older"))

    def test_quiz_topic_recognition(self) -> None:
        self.assertTrue(is_known_quiz_topic("dp"))
        self.assertTrue(is_known_quiz_topic("Binary Search"))
        self.assertFalse(is_known_quiz_topic("made-up-topic-xyz"))

    def test_extract_quiz_answer_option(self) -> None:
        self.assertEqual(extract_quiz_answer_option("A"), "A")
        self.assertEqual(extract_quiz_answer_option("b because hash map"), "B")
        self.assertEqual(extract_quiz_answer_option("option c"), "C")
        self.assertIsNone(extract_quiz_answer_option("kjfnaekfnaejkfnaekfjnefan"))

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
            "display_id": 1,
            "problem_ref": "P1",
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
        self.assertIn("ID: P1", text)
        self.assertIn("Concepts:", text)
        self.assertIn("Track lower and upper bounds recursively.", text)
        self.assertIn("Time complexity:", text)
        self.assertIn("O(n)", text)
        self.assertIn("Space complexity:", text)
        self.assertIn("O(h)", text)
        self.assertIn("Notes:", text)
        self.assertIn("Careful with duplicates.", text)

    def test_unknown_text_help_lists_primary_commands(self) -> None:
        text = _unknown_text_help_text()
        self.assertIn("I didn’t understand that", text)
        self.assertIn("/hi", text)
        self.assertNotIn("/help", text)
        self.assertIn("/ask <question>", text)
        self.assertIn("/log", text)
        self.assertIn("/quiz [topic]", text)

    def test_unknown_command_help_mentions_command_and_options(self) -> None:
        text = _unknown_command_help_text("/quit")
        self.assertIn("I don’t recognize `/quit`", text)
        self.assertIn("/hi", text)
        self.assertNotIn("/help", text)
        self.assertIn("/ask <question>", text)
        self.assertIn("/log", text)

    def test_commands_help_text_escapes_html_placeholders(self) -> None:
        text = _commands_help_text()
        self.assertIn("&lt;topic&gt;", text)
        self.assertIn("&lt;text&gt;", text)

    def test_commands_help_text_uses_hi_only_for_help(self) -> None:
        text = _commands_help_text()
        self.assertIn("• /hi", text)
        self.assertNotIn("• /help", text)

    def test_parse_log_show_limit(self) -> None:
        self.assertIsNone(_parse_log_show_limit([]))
        self.assertIsNone(_parse_log_show_limit(["foo"]))
        self.assertEqual(_parse_log_show_limit(["show"]), 1)
        self.assertEqual(_parse_log_show_limit(["show", "3"]), 3)
        self.assertEqual(_parse_log_show_limit(["show", "0"]), -1)
        self.assertEqual(_parse_log_show_limit(["show", "abc"]), -1)
        self.assertEqual(_parse_log_show_limit(["show", "2", "extra"]), -1)


if __name__ == "__main__":
    unittest.main()
