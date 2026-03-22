from __future__ import annotations

from datetime import UTC, datetime
import sqlite3
from pathlib import Path
import tempfile
import unittest

from leetcoach.app.application.ask.review_tools import (
    execute_get_due_reviews,
    execute_get_last_reminder_batch,
    get_due_reviews_tool_definition,
    get_last_reminder_batch_tool_definition,
)
from leetcoach.app.application.problems.log_problem import LogProblemInput, log_problem
from leetcoach.app.misc.migrate import migrate_database


class ReviewToolsUnitTest(unittest.TestCase):
    def test_tool_definition_exposes_expected_shape(self) -> None:
        definition = get_due_reviews_tool_definition()
        self.assertEqual(definition["name"], "get_due_reviews")
        self.assertEqual(
            definition["parameters"]["properties"]["limit"]["maximum"],
            20,
        )
        last_definition = get_last_reminder_batch_tool_definition()
        self.assertEqual(last_definition["name"], "get_last_reminder_batch")

    def test_execute_get_due_reviews_rejects_invalid_limit(self) -> None:
        with self.assertRaisesRegex(ValueError, "limit must be between 1 and 20"):
            execute_get_due_reviews(
                db_path="ignored",
                telegram_user_id="u-1",
                arguments={"limit": 0},
            )

    def test_execute_get_last_reminder_batch_rejects_invalid_limit(self) -> None:
        with self.assertRaisesRegex(ValueError, "limit must be between 1 and 20"):
            execute_get_last_reminder_batch(
                db_path="ignored",
                telegram_user_id="u-1",
                arguments={"limit": 0},
            )

    def test_execute_get_last_reminder_batch_returns_empty_when_none_sent(self) -> None:
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

            result = execute_get_last_reminder_batch(
                db_path=db_path,
                telegram_user_id="u-1",
                arguments={"limit": 5},
            )

        self.assertIsNone(result["requested_at"])
        self.assertEqual(result["reviews"], [])


if __name__ == "__main__":
    unittest.main()
