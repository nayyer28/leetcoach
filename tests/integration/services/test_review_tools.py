from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import sqlite3
import tempfile
import unittest

from leetcoach.app.application.ask.review_tools import execute_get_due_reviews
from leetcoach.app.application.problems.log_problem import LogProblemInput, log_problem
from leetcoach.app.misc.migrate import migrate_database
from leetcoach.app.application.ask.review_tools import execute_get_last_reminder_batch


class ReviewToolsIntegrationTest(unittest.TestCase):
    def test_due_review_tool_executes_against_real_db(self) -> None:
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

            result = execute_get_due_reviews(
                db_path=db_path,
                telegram_user_id="u-1",
                arguments={"limit": 1},
            )

            self.assertEqual(len(result["reviews"]), 1)
            self.assertEqual(result["reviews"][0]["problem_ref"], "P1")
            self.assertEqual(result["reviews"][0]["status"], "pending")

    def test_last_reminder_batch_tool_executes_against_real_db(self) -> None:
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

            result = execute_get_last_reminder_batch(
                db_path=db_path,
                telegram_user_id="u-1",
                arguments={"limit": 5},
            )

            self.assertEqual(result["requested_at"], requested_at)
            self.assertEqual(len(result["reviews"]), 2)
            self.assertEqual(result["reviews"][0]["problem_ref"], "P1")
            self.assertEqual(result["reviews"][1]["problem_ref"], "P2")


if __name__ == "__main__":
    unittest.main()
