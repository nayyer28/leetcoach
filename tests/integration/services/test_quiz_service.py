from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from leetcoach.app.application.quiz.answer_quiz import answer_quiz
from leetcoach.app.application.quiz.interrupt_quiz import interrupt_active_quiz
from leetcoach.app.application.quiz.reveal_quiz import reveal_quiz
from leetcoach.app.application.quiz.start_quiz import start_quiz
from leetcoach.app.infrastructure.config.db import get_connection
from leetcoach.app.misc.migrate import migrate_database


QUESTION_JSON = """{
  "topic": "arrays",
  "question": "What is the average lookup complexity of a hash map?",
  "options": {"A": "O(1)", "B": "O(log n)", "C": "O(n)", "D": "O(n log n)"},
  "correct_option": "A",
  "why_correct": "With good hashing and load factor, average lookup is constant.",
  "why_others_wrong": {
    "B": "This applies to balanced trees.",
    "C": "Worst-case can degrade but not average.",
    "D": "Sorting complexity, not hash lookup."
  },
  "concept_takeaway": "Hash maps are usually O(1) average, O(n) worst-case."
}"""

ANSWER_JSON = """{
  "user_answer_normalized": "A",
  "is_correct": true,
  "verdict_summary": "Correct.",
  "formal_feedback": "Hash map average lookup is constant under good hashing.",
  "concept_takeaway": "Always separate average from worst-case complexity."
}"""


class _StubProvider:
    def __init__(self, responses: list[tuple[str, str]]) -> None:
        self._responses = responses
        self.calls: list[str] = []

    def generate_text(self, prompt: str):
        self.calls.append(prompt)
        model, text = self._responses.pop(0)
        return type("Resp", (), {"model": model, "text": text})()


class QuizServiceIntegrationTest(unittest.TestCase):
    def _seed_user(self, db_path: str) -> str:
        telegram_user_id = "8719696311"
        with get_connection(db_path) as conn:
            conn.execute(
                """
                INSERT INTO users (telegram_user_id, telegram_chat_id, timezone, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    telegram_user_id,
                    "chat-1",
                    "UTC",
                    "2026-03-11T10:00:00+00:00",
                    "2026-03-11T10:00:00+00:00",
                ),
            )
            conn.commit()
        return telegram_user_id

    def test_start_answer_reveal_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "leetcoach-test.db")
            migrate_database(db_path)
            telegram_user_id = self._seed_user(db_path)

            provider = _StubProvider(
                responses=[
                    ("gemini-2.5-flash-lite", QUESTION_JSON),
                    ("gemini-2.5-flash-lite", ANSWER_JSON),
                ]
            )

            start = start_quiz(
                db_path=db_path,
                telegram_user_id=telegram_user_id,
                topic="arrays",
                provider=provider,
            )
            self.assertEqual(start.status, "ok")
            self.assertIsNotNone(start.question)
            self.assertEqual(start.model_used, "gemini-2.5-flash-lite")

            answered = answer_quiz(
                db_path=db_path,
                telegram_user_id=telegram_user_id,
                user_answer_text="A because hash maps are fast",
                provider=provider,
            )
            self.assertEqual(answered.status, "ok")
            self.assertIsNotNone(answered.feedback)
            self.assertTrue(answered.feedback.is_correct)

            revealed = reveal_quiz(
                db_path=db_path,
                telegram_user_id=telegram_user_id,
            )
            self.assertEqual(revealed.status, "ok")
            self.assertIsNotNone(revealed.question)
            self.assertEqual(revealed.question.correct_option, "A")

    def test_unknown_topic_short_circuit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "leetcoach-test.db")
            migrate_database(db_path)
            telegram_user_id = self._seed_user(db_path)
            provider = _StubProvider(responses=[("gemini-2.5-flash-lite", QUESTION_JSON)])
            result = start_quiz(
                db_path=db_path,
                telegram_user_id=telegram_user_id,
                topic="totally-unknown-topic",
                provider=provider,
            )
            self.assertEqual(result.status, "unknown_topic")
            self.assertEqual(len(provider.calls), 0)

    def test_invalid_answer_short_circuits_before_llm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "leetcoach-test.db")
            migrate_database(db_path)
            telegram_user_id = self._seed_user(db_path)

            provider = _StubProvider(
                responses=[
                    ("gemini-2.5-flash-lite", QUESTION_JSON),
                    ("gemini-2.5-flash-lite", ANSWER_JSON),
                ]
            )

            start = start_quiz(
                db_path=db_path,
                telegram_user_id=telegram_user_id,
                topic="arrays",
                provider=provider,
            )
            self.assertEqual(start.status, "ok")

            answered = answer_quiz(
                db_path=db_path,
                telegram_user_id=telegram_user_id,
                user_answer_text="kjfnaekfnaejkfnaekfjnefan",
                provider=provider,
            )
            self.assertEqual(answered.status, "invalid_answer")
            self.assertIsNotNone(answered.question)
            self.assertEqual(len(provider.calls), 1)

    def test_interrupt_active_quiz_closes_existing_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "leetcoach-test.db")
            migrate_database(db_path)
            telegram_user_id = self._seed_user(db_path)

            provider = _StubProvider(
                responses=[("gemini-2.5-flash-lite", QUESTION_JSON)]
            )
            start = start_quiz(
                db_path=db_path,
                telegram_user_id=telegram_user_id,
                topic="arrays",
                provider=provider,
            )
            self.assertEqual(start.status, "ok")

            interrupted = interrupt_active_quiz(
                db_path=db_path,
                telegram_user_id=telegram_user_id,
            )
            self.assertTrue(interrupted)

            reveal = reveal_quiz(
                db_path=db_path,
                telegram_user_id=telegram_user_id,
            )
            self.assertEqual(reveal.status, "no_active_quiz")

    def test_expired_quiz_cannot_be_answered_or_revealed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "leetcoach-test.db")
            migrate_database(db_path)
            telegram_user_id = self._seed_user(db_path)

            provider = _StubProvider(
                responses=[("gemini-2.5-flash-lite", QUESTION_JSON)]
            )
            with patch(
                "leetcoach.app.application.quiz.start_quiz.default_now_iso",
                return_value="2026-03-11T10:00:00+00:00",
            ):
                start = start_quiz(
                    db_path=db_path,
                    telegram_user_id=telegram_user_id,
                    topic="arrays",
                    provider=provider,
                )
            self.assertEqual(start.status, "ok")

            with patch(
                "leetcoach.app.application.quiz.answer_quiz.default_now_iso",
                return_value="2026-03-11T10:31:00+00:00",
            ):
                answered = answer_quiz(
                    db_path=db_path,
                    telegram_user_id=telegram_user_id,
                    user_answer_text="A because hash maps are fast",
                    provider=provider,
                )
            self.assertEqual(answered.status, "expired_quiz")
            self.assertEqual(len(provider.calls), 1)

            with patch(
                "leetcoach.app.application.quiz.reveal_quiz.default_now_iso",
                return_value="2026-03-11T10:31:30+00:00",
            ):
                revealed = reveal_quiz(
                    db_path=db_path,
                    telegram_user_id=telegram_user_id,
                )
            self.assertEqual(revealed.status, "no_active_quiz")


if __name__ == "__main__":
    unittest.main()
