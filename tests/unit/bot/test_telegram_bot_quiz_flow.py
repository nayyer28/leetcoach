from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from leetcoach.app.application.quiz.common import QuizQuestionPayload, StartQuizResult
from leetcoach.app.infrastructure.config.app_config import AppConfig
from leetcoach.app.interface.bot.handlers import quiz_command, unknown_command


class TelegramBotQuizFlowUnitTest(unittest.IsolatedAsyncioTestCase):
    async def test_quiz_command_shows_typing_before_generation(self) -> None:
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(
            message=message,
            effective_chat=SimpleNamespace(id=123),
            effective_user=SimpleNamespace(id=456),
        )
        context = SimpleNamespace(
            args=["arrays"],
            user_data={},
            application=SimpleNamespace(
                bot_data={
                    "config": AppConfig(
                        environment="development",
                        log_level="INFO",
                        timezone="UTC",
                        db_path=".local/leetcoach.db",
                        telegram_bot_token="token",
                        gemini_api_key="gemini-key",
                        allowed_user_ids=frozenset(),
                    ),
                    "quiz_provider": object(),
                }
            ),
            bot=SimpleNamespace(send_chat_action=AsyncMock()),
        )

        result = StartQuizResult(
            status="ok",
            question=QuizQuestionPayload(
                topic="arrays",
                question="Which structure gives O(1) average lookup?",
                options={"A": "Hash map", "B": "BST", "C": "List", "D": "Queue"},
                correct_option="A",
                why_correct="Hash map gives average O(1).",
                why_others_wrong={
                    "B": "BST is O(log n) average.",
                    "C": "List lookup is O(n).",
                    "D": "Queue is not for key lookup.",
                },
                concept_takeaway="Choose hash maps for fast average lookup.",
            ),
            model_used="gemini-2.5-flash",
        )

        with patch(
            "leetcoach.app.interface.bot.handlers.start_quiz", return_value=result
        ):
            await quiz_command(update, context)

        context.bot.send_chat_action.assert_awaited_once()
        message.reply_text.assert_awaited_once()
        self.assertIn("Quiz Time", message.reply_text.await_args.args[0])

    async def test_unknown_command_returns_helpful_feedback(self) -> None:
        message = SimpleNamespace(text="/quit", reply_text=AsyncMock())
        update = SimpleNamespace(
            message=message,
            effective_user=SimpleNamespace(id=456),
        )
        context = SimpleNamespace(
            application=SimpleNamespace(
                bot_data={
                    "config": AppConfig(
                        environment="development",
                        log_level="INFO",
                        timezone="UTC",
                        db_path=".local/leetcoach.db",
                        telegram_bot_token="token",
                        allowed_user_ids=frozenset(),
                    )
                }
            )
        )

        await unknown_command(update, context)

        message.reply_text.assert_awaited_once()
        self.assertIn("/quit", message.reply_text.await_args.args[0])
        self.assertIn("/help", message.reply_text.await_args.args[0])


if __name__ == "__main__":
    unittest.main()
