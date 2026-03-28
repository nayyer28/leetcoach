from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from leetcoach.app.application.ask.ask_service import AskServiceError, AskServiceResult
from leetcoach.app.application.quiz.common import QuizQuestionPayload, StartQuizResult
from leetcoach.app.infrastructure.config.app_config import AppConfig
from leetcoach.app.interface.bot.handlers import ask_command, quiz_command, unknown_command


class TelegramBotQuizFlowUnitTest(unittest.IsolatedAsyncioTestCase):
    async def test_ask_command_calls_service_and_replies_with_answer(self) -> None:
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(
            message=message,
            effective_chat=SimpleNamespace(id=123),
            effective_user=SimpleNamespace(id=456),
        )
        context = SimpleNamespace(
            args=["How", "many", "easy", "problems?"],
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
                    "ask_provider": object(),
                }
            ),
            bot=SimpleNamespace(send_chat_action=AsyncMock()),
        )

        with (
            patch("leetcoach.app.interface.bot.handlers._interrupt_quiz_if_needed"),
            patch(
                "leetcoach.app.interface.bot.handlers.ask_question",
                return_value=AskServiceResult(
                    response_type="final_answer",
                    model="gemini-2.5-flash-lite",
                    tool_executions=[],
                    answer="You have solved 3 easy problems.",
                    confidence="high",
                    tool_fit="exact",
                    answer_basis="direct_tool_result",
                    comments="I used the aggregate tool result directly.",
                ),
            ) as ask_mock,
        ):
            await ask_command(update, context)

        context.bot.send_chat_action.assert_awaited_once()
        ask_mock.assert_called_once()
        message.reply_text.assert_awaited_once_with(
            "You have solved 3 easy problems.\n\n"
            "<b>Confidence:</b> high\n\n"
            "<b>Tool fit:</b> exact\n\n"
            "<b>Answer basis:</b> direct_tool_result\n\n"
            "<b>Comments:</b> I used the aggregate tool result directly.",
            parse_mode="HTML",
        )

    async def test_ask_command_requires_question(self) -> None:
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
                    "config": AppConfig(
                        environment="development",
                        log_level="INFO",
                        timezone="UTC",
                        db_path=".local/leetcoach.db",
                        telegram_bot_token="token",
                        allowed_user_ids=frozenset(),
                    )
                }
            ),
        )

        with patch("leetcoach.app.interface.bot.handlers._interrupt_quiz_if_needed"):
            await ask_command(update, context)

        message.reply_text.assert_awaited_once_with("Usage: /ask <question>")

    async def test_ask_command_includes_request_id_on_shared_failure(self) -> None:
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(
            message=message,
            effective_chat=SimpleNamespace(id=123),
            effective_user=SimpleNamespace(id=456),
        )
        context = SimpleNamespace(
            args=["what", "can", "you", "do?"],
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
                    "ask_provider": object(),
                }
            ),
            bot=SimpleNamespace(send_chat_action=AsyncMock()),
        )

        with (
            patch("leetcoach.app.interface.bot.handlers._interrupt_quiz_if_needed"),
            patch(
                "leetcoach.app.interface.bot.handlers.ask_question",
                side_effect=AskServiceError(
                    message="LLM did not finish within max_steps",
                    request_id="req-ask-1",
                    model="gemini-2.5-flash-lite",
                ),
            ),
        ):
            await ask_command(update, context)

        context.bot.send_chat_action.assert_awaited_once()
        message.reply_text.assert_awaited_once_with(
            "⚠️ Could not answer that right now: LLM did not finish within max_steps\n"
            "Request ID: req-ask-1\n"
            "Try again shortly."
        )

    async def test_ask_command_can_render_cannot_answer_confidently(self) -> None:
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(
            message=message,
            effective_chat=SimpleNamespace(id=123),
            effective_user=SimpleNamespace(id=456),
        )
        context = SimpleNamespace(
            args=["which", "month", "was", "best?"],
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
                    "ask_provider": object(),
                }
            ),
            bot=SimpleNamespace(send_chat_action=AsyncMock()),
        )

        with (
            patch("leetcoach.app.interface.bot.handlers._interrupt_quiz_if_needed"),
            patch(
                "leetcoach.app.interface.bot.handlers.ask_question",
                return_value=AskServiceResult(
                    response_type="cannot_answer_confidently",
                    model="gemini-2.5-flash-lite",
                    tool_executions=[],
                    comments="The current tools do not support month-level grouping.",
                ),
            ),
        ):
            await ask_command(update, context)

        message.reply_text.assert_awaited_once_with(
            "I cannot answer this confidently right now.\n\n"
            "<b>Comments:</b> The current tools do not support month-level grouping.",
            parse_mode="HTML",
        )

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
        self.assertIn("/hi", message.reply_text.await_args.args[0])
        self.assertNotIn("/help", message.reply_text.await_args.args[0])


if __name__ == "__main__":
    unittest.main()
