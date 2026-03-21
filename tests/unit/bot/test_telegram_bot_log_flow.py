from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from leetcoach.app.interface.bot.handlers import (
    LOG_EDIT_DIFFICULTY,
    LOG_EDIT_FIELD,
    LOG_EDIT_TEXT,
    LOG_REVIEW,
    LOG_TITLE,
    LOG_LEETCODE_SLUG,
    LOG_PATTERN,
    LOG_SOLVED_AT,
    _difficulty_inline_markup,
    _pattern_inline_markup,
    log_edit_field_callback,
    log_edit_text,
    log_command,
    log_difficulty_callback,
    log_notes,
    log_pattern,
    log_pattern_callback,
    log_review_callback,
)


class TelegramBotLogFlowUnitTest(unittest.IsolatedAsyncioTestCase):
    async def test_log_difficulty_callback_advances_to_slug_prompt(self) -> None:
        message = SimpleNamespace(reply_text=AsyncMock())
        query = SimpleNamespace(
            data="log:difficulty:medium",
            answer=AsyncMock(),
            edit_message_reply_markup=AsyncMock(),
            message=message,
        )
        update = SimpleNamespace(callback_query=query, message=None)
        context = SimpleNamespace(user_data={"log_payload": {}})

        next_state = await log_difficulty_callback(update, context)

        self.assertEqual(next_state, LOG_LEETCODE_SLUG)
        self.assertEqual(context.user_data["log_payload"]["difficulty"], "medium")
        query.answer.assert_awaited_once()
        query.edit_message_reply_markup.assert_awaited_once_with(reply_markup=None)
        self.assertEqual(message.reply_text.await_count, 2)
        self.assertEqual(message.reply_text.await_args_list[0].args[0], "✓ Selected: Medium")
        self.assertIn(
            "LeetCode URL or slug?",
            message.reply_text.await_args_list[1].args[0],
        )

    async def test_log_pattern_callback_advances_to_solved_at_prompt(self) -> None:
        message = SimpleNamespace(reply_text=AsyncMock())
        query = SimpleNamespace(
            data="log:pattern:trees",
            answer=AsyncMock(),
            edit_message_reply_markup=AsyncMock(),
            message=message,
        )
        update = SimpleNamespace(callback_query=query, message=None)
        context = SimpleNamespace(user_data={"log_payload": {}})

        next_state = await log_pattern_callback(update, context)

        self.assertEqual(next_state, LOG_SOLVED_AT)
        self.assertEqual(context.user_data["log_payload"]["pattern"], "Trees")
        query.answer.assert_awaited_once()
        query.edit_message_reply_markup.assert_awaited_once_with(reply_markup=None)
        self.assertEqual(message.reply_text.await_count, 2)
        self.assertEqual(message.reply_text.await_args_list[0].args[0], "✓ Selected: Trees")
        self.assertIn("Solved time?", message.reply_text.await_args_list[1].args[0])

    async def test_log_pattern_message_reprompts_on_unknown_pattern(self) -> None:
        message = SimpleNamespace(text="unknown pattern", reply_text=AsyncMock())
        update = SimpleNamespace(message=message, callback_query=None)
        context = SimpleNamespace(user_data={"log_payload": {}})

        next_state = await log_pattern(update, context)

        self.assertEqual(next_state, LOG_PATTERN)
        message.reply_text.assert_awaited_once()
        self.assertIn("Unknown pattern", message.reply_text.await_args.args[0])
        self.assertEqual(
            message.reply_text.await_args.kwargs["reply_markup"].to_dict(),
            _pattern_inline_markup().to_dict(),
        )

    async def test_log_pattern_message_accepts_alias(self) -> None:
        message = SimpleNamespace(text="tree", reply_text=AsyncMock())
        update = SimpleNamespace(message=message, callback_query=None)
        context = SimpleNamespace(user_data={"log_payload": {}})

        next_state = await log_pattern(update, context)

        self.assertEqual(next_state, LOG_SOLVED_AT)
        self.assertEqual(context.user_data["log_payload"]["pattern"], "Trees")

    async def test_inline_markups_are_stable_for_log_flow(self) -> None:
        self.assertEqual(_difficulty_inline_markup().inline_keyboard[0][0].text, "Easy")
        self.assertEqual(_pattern_inline_markup().inline_keyboard[0][0].text, "Arrays & Hashing")

    async def test_log_command_without_show_starts_conversation(self) -> None:
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(
            message=message,
            effective_user=SimpleNamespace(id=456),
        )
        context = SimpleNamespace(
            args=[],
            user_data={},
            application=SimpleNamespace(
                bot_data={
                    "config": SimpleNamespace(
                        allowed_user_ids=frozenset(),
                        timezone="UTC",
                        db_path=".local/leetcoach.db",
                    )
                }
            ),
        )

        with patch("leetcoach.app.interface.bot.handlers._interrupt_quiz_if_needed"):
            next_state = await log_command(update, context)

        self.assertEqual(next_state, LOG_TITLE)
        message.reply_text.assert_awaited_once()
        self.assertEqual(context.user_data["log_payload"], {})

    async def test_log_command_show_defaults_to_one(self) -> None:
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(
            message=message,
            effective_user=SimpleNamespace(id=456),
        )
        context = SimpleNamespace(
            args=["show"],
            user_data={},
            application=SimpleNamespace(
                bot_data={
                    "config": SimpleNamespace(
                        allowed_user_ids=frozenset(),
                        timezone="UTC",
                        db_path=".local/leetcoach.db",
                    ),
                }
            ),
        )
        rows = [
            {
                "user_problem_id": 10,
                "display_id": 1,
                "problem_ref": "P1",
                "title": "Contains Duplicate",
                "difficulty": "easy",
                "pattern": "Arrays & Hashing",
                "solved_at": "2026-03-08T13:28:44+00:00",
                "leetcode_slug": "contains-duplicate",
                "neetcode_slug": "contains-duplicate",
            }
        ]

        with (
            patch("leetcoach.app.interface.bot.handlers._interrupt_quiz_if_needed"),
            patch(
                "leetcoach.app.interface.bot.handlers.list_recent_problems",
                return_value=rows,
            ) as recent_mock,
            patch(
                "leetcoach.app.interface.bot.handlers._reply_long_text",
                new=AsyncMock(),
            ) as reply_mock,
        ):
            next_state = await log_command(update, context)

        self.assertEqual(next_state, -1)
        recent_mock.assert_called_once_with(".local/leetcoach.db", "456", limit=1)
        reply_mock.assert_awaited_once()

    async def test_log_command_show_rejects_invalid_limit(self) -> None:
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(
            message=message,
            effective_user=SimpleNamespace(id=456),
        )
        context = SimpleNamespace(
            args=["show", "zero"],
            user_data={},
            application=SimpleNamespace(
                bot_data={
                    "config": SimpleNamespace(
                        allowed_user_ids=frozenset(),
                        timezone="UTC",
                        db_path=".local/leetcoach.db",
                    )
                }
            ),
        )

        with patch("leetcoach.app.interface.bot.handlers._interrupt_quiz_if_needed"):
            next_state = await log_command(update, context)

        self.assertEqual(next_state, -1)
        message.reply_text.assert_awaited_once()
        self.assertIn("Usage: /log show [n]", message.reply_text.await_args.args[0])

    async def test_log_notes_shows_review_summary_instead_of_saving(self) -> None:
        message = SimpleNamespace(text="important notes", reply_text=AsyncMock())
        update = SimpleNamespace(message=message)
        context = SimpleNamespace(
            user_data={
                "log_payload": {
                    "title": "Two Sum",
                    "difficulty": "easy",
                    "leetcode_slug": "two-sum",
                    "neetcode_slug": "two-sum",
                    "pattern": "Arrays & Hashing",
                    "solved_at": "2026-03-08T13:30:00+00:00",
                    "concepts": "hash map",
                    "time_complexity": "O(n)",
                    "space_complexity": "O(n)",
                }
            },
            application=SimpleNamespace(
                bot_data={"config": SimpleNamespace(timezone="UTC")}
            ),
        )

        next_state = await log_notes(update, context)

        self.assertEqual(next_state, LOG_REVIEW)
        self.assertEqual(context.user_data["log_payload"]["notes"], "important notes")
        message.reply_text.assert_awaited_once()
        self.assertIn("Review Problem Log", message.reply_text.await_args.args[0])
        self.assertIsNotNone(message.reply_text.await_args.kwargs["reply_markup"])

    async def test_log_review_edit_shows_field_picker(self) -> None:
        message = SimpleNamespace(reply_text=AsyncMock())
        query = SimpleNamespace(
            data="log:review:edit",
            answer=AsyncMock(),
            edit_message_reply_markup=AsyncMock(),
            message=message,
        )
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(
            user_data={"log_payload": {"title": "Two Sum"}},
            application=SimpleNamespace(
                bot_data={"config": SimpleNamespace(timezone="UTC")}
            ),
        )

        next_state = await log_review_callback(update, context)

        self.assertEqual(next_state, LOG_EDIT_FIELD)
        message.reply_text.assert_awaited_once()
        self.assertIn("What do you want to change?", message.reply_text.await_args.args[0])

    async def test_log_edit_field_concepts_prompts_with_current_value(self) -> None:
        message = SimpleNamespace(reply_text=AsyncMock())
        query = SimpleNamespace(
            data="log:editfield:concepts",
            answer=AsyncMock(),
            edit_message_reply_markup=AsyncMock(),
            message=message,
        )
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(
            user_data={"log_payload": {"concepts": "hash map complement"}},
        )

        next_state = await log_edit_field_callback(update, context)

        self.assertEqual(next_state, LOG_EDIT_TEXT)
        self.assertEqual(context.user_data["log_edit_field"], "concepts")
        self.assertIn("Current value:", message.reply_text.await_args.args[0])
        self.assertIn("hash map complement", message.reply_text.await_args.args[0])

    async def test_log_edit_field_difficulty_reuses_selectable_options(self) -> None:
        message = SimpleNamespace(reply_text=AsyncMock())
        query = SimpleNamespace(
            data="log:editfield:difficulty",
            answer=AsyncMock(),
            edit_message_reply_markup=AsyncMock(),
            message=message,
        )
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(user_data={"log_payload": {"difficulty": "easy"}})

        next_state = await log_edit_field_callback(update, context)

        self.assertEqual(next_state, LOG_EDIT_DIFFICULTY)
        markup = message.reply_text.await_args.kwargs["reply_markup"]
        self.assertEqual(
            [button.text for button in markup.inline_keyboard[0]],
            [button.text for button in _difficulty_inline_markup().inline_keyboard[0]],
        )

    async def test_log_edit_text_updates_value_and_returns_to_review(self) -> None:
        message = SimpleNamespace(text="updated concepts", reply_text=AsyncMock())
        update = SimpleNamespace(message=message)
        context = SimpleNamespace(
            user_data={
                "log_payload": {
                    "title": "Two Sum",
                    "difficulty": "easy",
                    "leetcode_slug": "two-sum",
                    "neetcode_slug": "two-sum",
                    "pattern": "Arrays & Hashing",
                    "solved_at": "2026-03-08T13:30:00+00:00",
                    "concepts": "old concepts",
                    "time_complexity": None,
                    "space_complexity": None,
                    "notes": None,
                },
                "log_edit_field": "concepts",
            },
            application=SimpleNamespace(
                bot_data={"config": SimpleNamespace(timezone="UTC")}
            ),
        )

        next_state = await log_edit_text(update, context)

        self.assertEqual(next_state, LOG_REVIEW)
        self.assertEqual(context.user_data["log_payload"]["concepts"], "updated concepts")
        self.assertNotIn("log_edit_field", context.user_data)
        self.assertIn("Review Problem Log", message.reply_text.await_args.args[0])


if __name__ == "__main__":
    unittest.main()
