from __future__ import annotations

from pathlib import Path
from datetime import UTC, datetime
import sqlite3
import tempfile
import unittest

from leetcoach.app.application.ask.ask_service import AskServiceError, ask_question
from leetcoach.app.application.problems.log_problem import LogProblemInput, log_problem
from leetcoach.app.infrastructure.llm.gemini_provider import GeminiProvider
from leetcoach.app.misc.migrate import migrate_database


class AskServiceUnitTest(unittest.TestCase):
    def test_ask_question_rejects_duplicate_tool_call_early(self) -> None:
        responses = iter(
            [
                """{
                  "type": "tool_call",
                  "tool_name": "describe_ask_capabilities",
                  "arguments": {}
                }""",
                """{
                  "type": "tool_call",
                  "tool_name": "describe_ask_capabilities",
                  "arguments": {}
                }""",
            ]
        )

        def transport(model: str, prompt: str) -> str:
            return next(responses)

        provider = GeminiProvider(
            api_key="dummy",
            model_priority=("gemini-2.5-flash-lite",),
            transport=transport,
        )

        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "leetcoach-test.db")
            migrate_database(db_path)
            with self.assertRaisesRegex(
                AskServiceError,
                "repeated the same tool call",
            ) as exc_ctx:
                ask_question(
                    db_path=db_path,
                    telegram_user_id="u-1",
                    question="What can you do?",
                    provider=provider,
                    max_steps=5,
                )

        exc = exc_ctx.exception
        self.assertEqual(len(exc.tool_executions), 1)
        self.assertEqual(exc.tool_executions[0].tool_name, "describe_ask_capabilities")
        self.assertEqual(exc.trace_events[-1].event, "ask.fail")
        self.assertEqual(exc.trace_events[-1].payload["reason"], "duplicate_tool_call")

    def test_ask_question_records_failure_trace_when_steps_exhausted(self) -> None:
        responses = iter(
            [
                """{
                  "type": "tool_call",
                  "tool_name": "get_due_reviews",
                  "arguments": {
                    "limit": 1
                  }
                }""",
                """{
                  "type": "tool_call",
                  "tool_name": "get_last_reminder_batch",
                  "arguments": {
                    "limit": 1
                  }
                }""",
            ]
        )

        def transport(model: str, prompt: str) -> str:
            return next(responses)

        provider = GeminiProvider(
            api_key="dummy",
            model_priority=("gemini-2.5-flash-lite",),
            transport=transport,
        )

        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "leetcoach-test.db")
            migrate_database(db_path)
            with self.assertRaisesRegex(AskServiceError, "max_steps") as exc_ctx:
                ask_question(
                    db_path=db_path,
                    telegram_user_id="u-1",
                    question="What can /ask do?",
                    provider=provider,
                    max_steps=2,
                )
        exc = exc_ctx.exception
        self.assertTrue(exc.request_id)
        self.assertEqual(exc.trace_events[-1].event, "ask.fail")
        self.assertEqual(exc.trace_events[-1].payload["reason"], "max_steps_exhausted")

    def test_ask_question_can_describe_capabilities(self) -> None:
        responses = iter(
            [
                """{
                  "type": "tool_call",
                  "tool_name": "describe_ask_capabilities",
                  "arguments": {
                    "focus": "examples"
                  }
                }""",
                """{
                  "type": "final_answer",
                  "answer": "You can ask things like show problem P1, what is due right now, or what is my strongest pattern."
                }""",
            ]
        )

        def transport(model: str, prompt: str) -> str:
            return next(responses)

        provider = GeminiProvider(
            api_key="dummy",
            model_priority=("gemini-2.5-flash-lite",),
            transport=transport,
        )

        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "leetcoach-test.db")
            migrate_database(db_path)
            result = ask_question(
                db_path=db_path,
                telegram_user_id="u-1",
                question="What can /ask do?",
                provider=provider,
            )

        self.assertIn("show problem P1", result.answer)
        self.assertEqual(result.tool_executions[0].tool_name, "describe_ask_capabilities")
        self.assertIn("examples", result.tool_executions[0].result)
        self.assertTrue(result.request_id)
        self.assertEqual(result.trace_events[0].event, "ask.start")
        self.assertTrue(
            any(event.event == "ask.tool_call" for event in result.trace_events)
        )
        self.assertTrue(
            any(event.event == "ask.tool_result" for event in result.trace_events)
        )
        self.assertEqual(result.trace_events[-1].event, "ask.final_answer")

    def test_ask_question_runs_tool_loop_and_returns_final_answer(self) -> None:
        responses = iter(
            [
                """{
                  "type": "tool_call",
                  "tool_name": "aggregate_user_problems",
                  "arguments": {
                    "group_by": "none",
                    "metric": "problem_count",
                    "filters": {"difficulty": "easy", "pattern": "Trees"}
                  }
                }""",
                """{
                  "type": "final_answer",
                  "answer": "You have solved 1 easy tree problem."
                }""",
            ]
        )

        def transport(model: str, prompt: str) -> str:
            return next(responses)

        provider = GeminiProvider(
            api_key="dummy",
            model_priority=("gemini-2.5-flash-lite",),
            transport=transport,
        )

        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "leetcoach-test.db")
            migrate_database(db_path)
            log_problem(
                db_path,
                LogProblemInput(
                    telegram_user_id="u-1",
                    telegram_chat_id="chat-1",
                    timezone="Europe/Berlin",
                    title="Maximum Depth of Binary Tree",
                    difficulty="easy",
                    leetcode_slug="maximum-depth-of-binary-tree",
                    neetcode_slug="max-depth-of-binary-tree",
                    pattern="tree dfs",
                    solved_at="2026-03-01T08:00:00+00:00",
                ),
            )

            result = ask_question(
                db_path=db_path,
                telegram_user_id="u-1",
                question="How many easy problems have I solved in Trees?",
                provider=provider,
            )

        self.assertEqual(result.answer, "You have solved 1 easy tree problem.")
        self.assertEqual(len(result.tool_executions), 1)
        self.assertEqual(result.tool_executions[0].tool_name, "aggregate_user_problems")
        self.assertEqual(result.tool_executions[0].result["rows"][0]["value"], 1)

    def test_ask_question_can_fetch_problem_detail(self) -> None:
        responses = iter(
            [
                """{
                  "type": "tool_call",
                  "tool_name": "get_problem_detail",
                  "arguments": {
                    "problem_ref": "P1"
                  }
                }""",
                """{
                  "type": "final_answer",
                  "answer": "P1 is Maximum Depth of Binary Tree."
                }""",
            ]
        )

        def transport(model: str, prompt: str) -> str:
            return next(responses)

        provider = GeminiProvider(
            api_key="dummy",
            model_priority=("gemini-2.5-flash-lite",),
            transport=transport,
        )

        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "leetcoach-test.db")
            migrate_database(db_path)
            log_problem(
                db_path,
                LogProblemInput(
                    telegram_user_id="u-1",
                    telegram_chat_id="chat-1",
                    timezone="Europe/Berlin",
                    title="Maximum Depth of Binary Tree",
                    difficulty="easy",
                    leetcode_slug="maximum-depth-of-binary-tree",
                    neetcode_slug="max-depth-of-binary-tree",
                    pattern="tree dfs",
                    solved_at="2026-03-01T08:00:00+00:00",
                ),
            )

            result = ask_question(
                db_path=db_path,
                telegram_user_id="u-1",
                question="Show problem P1",
                provider=provider,
            )

        self.assertEqual(result.answer, "P1 is Maximum Depth of Binary Tree.")
        self.assertEqual(result.tool_executions[0].tool_name, "get_problem_detail")
        self.assertEqual(
            result.tool_executions[0].result["problem"]["title"],
            "Maximum Depth of Binary Tree",
        )

    def test_ask_question_can_search_problems(self) -> None:
        responses = iter(
            [
                """{
                  "type": "tool_call",
                  "tool_name": "search_user_problems",
                  "arguments": {
                    "query": "duplicate"
                  }
                }""",
                """{
                  "type": "final_answer",
                  "answer": "I found 1 matching problem: Contains Duplicate."
                }""",
            ]
        )

        def transport(model: str, prompt: str) -> str:
            return next(responses)

        provider = GeminiProvider(
            api_key="dummy",
            model_priority=("gemini-2.5-flash-lite",),
            transport=transport,
        )

        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "leetcoach-test.db")
            migrate_database(db_path)
            log_problem(
                db_path,
                LogProblemInput(
                    telegram_user_id="u-1",
                    telegram_chat_id="chat-1",
                    timezone="Europe/Berlin",
                    title="Contains Duplicate",
                    difficulty="easy",
                    leetcode_slug="contains-duplicate",
                    neetcode_slug="contains-duplicate",
                    pattern="arrays and hashing",
                    solved_at="2026-03-02T08:00:00+00:00",
                ),
            )

            result = ask_question(
                db_path=db_path,
                telegram_user_id="u-1",
                question="Search for duplicate",
                provider=provider,
            )

        self.assertEqual(
            result.answer, "I found 1 matching problem: Contains Duplicate."
        )
        self.assertEqual(result.tool_executions[0].tool_name, "search_user_problems")
        self.assertEqual(
            result.tool_executions[0].result["problems"][0]["title"],
            "Contains Duplicate",
        )

    def test_ask_question_can_query_problems_by_date_range(self) -> None:
        responses = iter(
            [
                """{
                  "type": "tool_call",
                  "tool_name": "query_user_problems",
                  "arguments": {
                    "solved_date_from": "2026-02-01",
                    "solved_date_to": "2026-02-28",
                    "order_by": "solved_at_asc",
                    "limit": 10
                  }
                }""",
                """{
                  "type": "final_answer",
                  "answer": "You solved 2 problems in February 2026."
                }""",
            ]
        )

        def transport(model: str, prompt: str) -> str:
            return next(responses)

        provider = GeminiProvider(
            api_key="dummy",
            model_priority=("gemini-2.5-flash-lite",),
            transport=transport,
        )

        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "leetcoach-test.db")
            migrate_database(db_path)
            log_problem(
                db_path,
                LogProblemInput(
                    telegram_user_id="u-1",
                    telegram_chat_id="chat-1",
                    timezone="Europe/Berlin",
                    title="Maximum Depth of Binary Tree",
                    difficulty="easy",
                    leetcode_slug="maximum-depth-of-binary-tree",
                    neetcode_slug="max-depth-of-binary-tree",
                    pattern="trees",
                    solved_at="2026-02-01T08:00:00+00:00",
                ),
            )
            log_problem(
                db_path,
                LogProblemInput(
                    telegram_user_id="u-1",
                    telegram_chat_id="chat-1",
                    timezone="Europe/Berlin",
                    title="Contains Duplicate",
                    difficulty="easy",
                    leetcode_slug="contains-duplicate",
                    neetcode_slug="contains-duplicate",
                    pattern="arrays and hashing",
                    solved_at="2026-02-02T08:00:00+00:00",
                ),
            )

            result = ask_question(
                db_path=db_path,
                telegram_user_id="u-1",
                question="Show me all problems I solved in Feb 2026",
                provider=provider,
            )

        self.assertEqual(result.answer, "You solved 2 problems in February 2026.")
        self.assertEqual(result.tool_executions[0].tool_name, "query_user_problems")
        self.assertEqual(len(result.tool_executions[0].result["problems"]), 2)

    def test_ask_question_can_fetch_due_reviews(self) -> None:
        responses = iter(
            [
                """{
                  "type": "tool_call",
                  "tool_name": "get_due_reviews",
                  "arguments": {
                    "limit": 5
                  }
                }""",
                """{
                  "type": "final_answer",
                  "answer": "You currently have 2 due reviews."
                }""",
            ]
        )

        def transport(model: str, prompt: str) -> str:
            return next(responses)

        provider = GeminiProvider(
            api_key="dummy",
            model_priority=("gemini-2.5-flash-lite",),
            transport=transport,
        )

        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "leetcoach-test.db")
            migrate_database(db_path)
            log_problem(
                db_path,
                LogProblemInput(
                    telegram_user_id="u-1",
                    telegram_chat_id="chat-1",
                    timezone="Europe/Berlin",
                    title="Maximum Depth of Binary Tree",
                    difficulty="easy",
                    leetcode_slug="maximum-depth-of-binary-tree",
                    neetcode_slug="max-depth-of-binary-tree",
                    pattern="tree dfs",
                    solved_at="2026-03-01T08:00:00+00:00",
                ),
            )
            log_problem(
                db_path,
                LogProblemInput(
                    telegram_user_id="u-1",
                    telegram_chat_id="chat-1",
                    timezone="Europe/Berlin",
                    title="Contains Duplicate",
                    difficulty="easy",
                    leetcode_slug="contains-duplicate",
                    neetcode_slug="contains-duplicate",
                    pattern="arrays and hashing",
                    solved_at="2026-03-02T08:00:00+00:00",
                ),
            )
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    """
                    UPDATE user_problems
                    SET last_review_requested_at = ?
                    WHERE user_id = (SELECT id FROM users WHERE telegram_user_id = ?)
                    """,
                    (datetime.now(UTC).isoformat(), "u-1"),
                )
                conn.commit()

            result = ask_question(
                db_path=db_path,
                telegram_user_id="u-1",
                question="What is due?",
                provider=provider,
            )

        self.assertEqual(result.answer, "You currently have 2 due reviews.")
        self.assertEqual(result.tool_executions[0].tool_name, "get_due_reviews")
        self.assertEqual(len(result.tool_executions[0].result["reviews"]), 2)

    def test_ask_question_can_fetch_last_reminder_batch(self) -> None:
        responses = iter(
            [
                """{
                  "type": "tool_call",
                  "tool_name": "get_last_reminder_batch",
                  "arguments": {
                    "limit": 5
                  }
                }""",
                """{
                  "type": "final_answer",
                  "answer": "Your last reminder batch had 2 problems."
                }""",
            ]
        )

        def transport(model: str, prompt: str) -> str:
            return next(responses)

        provider = GeminiProvider(
            api_key="dummy",
            model_priority=("gemini-2.5-flash-lite",),
            transport=transport,
        )

        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "leetcoach-test.db")
            migrate_database(db_path)
            log_problem(
                db_path,
                LogProblemInput(
                    telegram_user_id="u-1",
                    telegram_chat_id="chat-1",
                    timezone="Europe/Berlin",
                    title="Maximum Depth of Binary Tree",
                    difficulty="easy",
                    leetcode_slug="maximum-depth-of-binary-tree",
                    neetcode_slug="max-depth-of-binary-tree",
                    pattern="tree dfs",
                    solved_at="2026-03-01T08:00:00+00:00",
                ),
            )
            log_problem(
                db_path,
                LogProblemInput(
                    telegram_user_id="u-1",
                    telegram_chat_id="chat-1",
                    timezone="Europe/Berlin",
                    title="Contains Duplicate",
                    difficulty="easy",
                    leetcode_slug="contains-duplicate",
                    neetcode_slug="contains-duplicate",
                    pattern="arrays and hashing",
                    solved_at="2026-03-02T08:00:00+00:00",
                ),
            )
            requested_at = datetime.now(UTC).isoformat()
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    """
                    UPDATE user_problems
                    SET last_review_requested_at = ?
                    WHERE user_id = (SELECT id FROM users WHERE telegram_user_id = ?)
                    """,
                    (requested_at, "u-1"),
                )
                conn.commit()

            result = ask_question(
                db_path=db_path,
                telegram_user_id="u-1",
                question="What did you remind me last?",
                provider=provider,
            )

        self.assertEqual(result.answer, "Your last reminder batch had 2 problems.")
        self.assertEqual(result.tool_executions[0].tool_name, "get_last_reminder_batch")
        self.assertEqual(len(result.tool_executions[0].result["reviews"]), 2)


if __name__ == "__main__":
    unittest.main()
