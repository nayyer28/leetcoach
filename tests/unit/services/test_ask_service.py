from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from leetcoach.app.application.ask.ask_service import ask_question
from leetcoach.app.application.problems.log_problem import LogProblemInput, log_problem
from leetcoach.app.infrastructure.llm.gemini_provider import GeminiProvider
from leetcoach.app.misc.migrate import migrate_database


class AskServiceUnitTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
