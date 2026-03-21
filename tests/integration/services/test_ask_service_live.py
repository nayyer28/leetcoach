from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from leetcoach.app.application.ask.ask_service import ask_question
from leetcoach.app.application.problems.log_problem import LogProblemInput, log_problem
from leetcoach.app.infrastructure.llm.gemini_provider import (
    GeminiAllModelsFailed,
    GeminiProvider,
)
from leetcoach.app.misc.migrate import migrate_database


@unittest.skipUnless(
    os.getenv("LEETCOACH_RUN_LIVE_TESTS") == "1",
    "Set LEETCOACH_RUN_LIVE_TESTS=1 to run live Gemini integration tests.",
)
class AskServiceLiveIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            self.skipTest("GEMINI_API_KEY is required for live Gemini tests")
        self.provider = GeminiProvider(
            api_key=api_key,
            model_priority=("gemini-2.5-flash-lite",),
            max_transient_retries=1,
        )

    def test_live_ask_uses_aggregate_tool_for_filtered_count(self) -> None:
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

            try:
                result = ask_question(
                    db_path=db_path,
                    telegram_user_id="u-1",
                    question="How many easy problems have I solved in Trees?",
                    provider=self.provider,
                )
            except GeminiAllModelsFailed as exc:
                if "network error" in str(exc).lower():
                    self.skipTest(f"Live ask test skipped due to network issue: {exc}")
                raise

            self.assertTrue(result.answer.strip())
            self.assertGreaterEqual(len(result.tool_executions), 1)
            self.assertEqual(result.tool_executions[0].tool_name, "aggregate_user_problems")
            self.assertEqual(result.tool_executions[0].result["rows"][0]["value"], 1)
            self.assertIn("1", result.answer)


if __name__ == "__main__":
    unittest.main()
