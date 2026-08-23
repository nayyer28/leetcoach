from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from leetcoach.app.application.ask.review_tools import (
    execute_get_next_review,
    get_next_review_tool_definition,
)
from leetcoach.app.application.problems.log_problem import LogProblemInput, log_problem
from leetcoach.app.misc.migrate import migrate_database


class ReviewToolsUnitTest(unittest.TestCase):
    def test_tool_definition_exposes_expected_shape(self) -> None:
        definition = get_next_review_tool_definition()
        self.assertEqual(definition["name"], "get_next_review")
        self.assertEqual(definition["parameters"]["properties"], {})
        self.assertEqual(definition["parameters"]["required"], [])

    def test_execute_get_next_review_returns_none_for_unknown_user(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "leetcoach-test.db")
            migrate_database(db_path)

            result = execute_get_next_review(
                db_path=db_path,
                telegram_user_id="never-seen",
                arguments={},
            )

        self.assertEqual(result, {"next_review": None})

    def test_execute_get_next_review_returns_none_when_queue_empty(self) -> None:
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

            # Another user has no problems, so their queue is empty.
            result = execute_get_next_review(
                db_path=db_path,
                telegram_user_id="u-other",
                arguments={},
            )

        self.assertEqual(result, {"next_review": None})


if __name__ == "__main__":
    unittest.main()
