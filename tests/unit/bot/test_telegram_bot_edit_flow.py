from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from leetcoach.app.interface.bot.handlers import (
    EDIT_DIFFICULTY,
    EDIT_FIELD,
    EDIT_TEXT,
    _edit_difficulty_inline_markup,
    _edit_field_markup,
    edit_command,
    edit_field_callback,
    edit_text,
)


class TelegramBotEditFlowUnitTest(unittest.IsolatedAsyncioTestCase):
    async def test_edit_command_shows_field_picker(self) -> None:
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(
            message=message,
            effective_user=SimpleNamespace(id=456),
        )
        context = SimpleNamespace(
            args=["P1"],
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
        row = {
            "display_id": 1,
            "problem_ref": "P1",
            "title": "Two Sum",
            "difficulty": "easy",
            "leetcode_slug": "two-sum",
            "neetcode_slug": "two-sum",
            "pattern": "Arrays & Hashing",
            "concepts": "hash map",
            "time_complexity": "O(n)",
            "space_complexity": "O(n)",
            "notes": "notes",
        }

        with (
            patch("leetcoach.app.interface.bot.handlers._interrupt_quiz_if_needed"),
            patch(
                "leetcoach.app.interface.bot.handlers.get_problem_detail_by_ref",
                return_value=row,
            ),
        ):
            next_state = await edit_command(update, context)

        self.assertEqual(next_state, EDIT_FIELD)
        self.assertEqual(context.user_data["edit_problem_detail"]["problem_ref"], "P1")
        message.reply_text.assert_awaited_once()
        self.assertEqual(
            message.reply_text.await_args.kwargs["reply_markup"].to_dict(),
            _edit_field_markup().to_dict(),
        )

    async def test_edit_field_callback_for_concepts_prompts_with_current_value(self) -> None:
        message = SimpleNamespace(reply_text=AsyncMock())
        query = SimpleNamespace(
            data="edit:field:concepts",
            answer=AsyncMock(),
            edit_message_reply_markup=AsyncMock(),
            message=message,
        )
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(
            user_data={
                "edit_problem_detail": {
                    "display_id": 1,
                    "problem_ref": "P1",
                    "concepts": "hash map and complements",
                }
            }
        )

        next_state = await edit_field_callback(update, context)

        self.assertEqual(next_state, EDIT_TEXT)
        self.assertEqual(context.user_data["edit_problem_field"], "concepts")
        query.answer.assert_awaited_once()
        query.edit_message_reply_markup.assert_awaited_once_with(reply_markup=None)
        self.assertIn("Current value:", message.reply_text.await_args.args[0])
        self.assertIn("hash map and complements", message.reply_text.await_args.args[0])

    async def test_edit_field_callback_for_difficulty_reuses_selectable_options(self) -> None:
        message = SimpleNamespace(reply_text=AsyncMock())
        query = SimpleNamespace(
            data="edit:field:difficulty",
            answer=AsyncMock(),
            edit_message_reply_markup=AsyncMock(),
            message=message,
        )
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(
            user_data={
                "edit_problem_detail": {
                    "display_id": 1,
                    "problem_ref": "P1",
                    "difficulty": "easy",
                }
            }
        )

        next_state = await edit_field_callback(update, context)

        self.assertEqual(next_state, EDIT_DIFFICULTY)
        self.assertEqual(
            message.reply_text.await_args.kwargs["reply_markup"].to_dict(),
            _edit_difficulty_inline_markup().to_dict(),
        )

    async def test_edit_text_normalizes_leetcode_url_before_apply(self) -> None:
        message = SimpleNamespace(
            text="https://leetcode.com/problems/two-sum/description/",
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            message=message,
            effective_message=message,
            effective_user=SimpleNamespace(id=456),
        )
        context = SimpleNamespace(
            user_data={
                "edit_problem_detail": {
                    "display_id": 1,
                    "problem_ref": "P1",
                },
                "edit_problem_field": "leetcode_slug",
            },
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

        with patch(
            "leetcoach.app.interface.bot.handlers._apply_problem_edit",
            new=AsyncMock(return_value=-1),
        ) as apply_mock:
            next_state = await edit_text(update, context)

        self.assertEqual(next_state, -1)
        apply_mock.assert_awaited_once()
        self.assertEqual(apply_mock.await_args.kwargs["field"], "leetcode_slug")
        self.assertEqual(apply_mock.await_args.kwargs["value"], "two-sum")


if __name__ == "__main__":
    unittest.main()
