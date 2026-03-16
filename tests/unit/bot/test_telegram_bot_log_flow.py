from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from leetcoach.telegram_bot import (
    LOG_LEETCODE_SLUG,
    LOG_PATTERN,
    LOG_SOLVED_AT,
    _difficulty_inline_markup,
    _pattern_inline_markup,
    log_difficulty_callback,
    log_pattern,
    log_pattern_callback,
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
        message.reply_text.assert_awaited_once()
        self.assertIn("LeetCode URL or slug?", message.reply_text.await_args.args[0])

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
        message.reply_text.assert_awaited_once()
        self.assertIn("Solved time?", message.reply_text.await_args.args[0])

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


if __name__ == "__main__":
    unittest.main()
