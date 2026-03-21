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


if __name__ == "__main__":
    unittest.main()
