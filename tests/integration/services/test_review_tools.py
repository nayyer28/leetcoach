from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from leetcoach.app.application.ask.review_tools import execute_get_next_review
from leetcoach.app.application.problems.log_problem import LogProblemInput, log_problem
from leetcoach.app.misc.migrate import migrate_database


class ReviewToolsIntegrationTest(unittest.TestCase):
    def test_get_next_review_returns_top_of_queue(self) -> None:
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

            result = execute_get_next_review(
                db_path=db_path,
                telegram_user_id="u-1",
                arguments={},
            )

            next_review = result["next_review"]
            self.assertIsNotNone(next_review)
            # Tie broken by earlier entered_at (which mirrors solved_at on insert).
            self.assertEqual(next_review["problem_ref"], "P1")
            self.assertEqual(next_review["title"], "Maximum Depth of Binary Tree")
            self.assertEqual(next_review["review_count"], 0)

    def test_get_next_review_returns_none_when_queue_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "leetcoach-test.db")
            migrate_database(db_path)

            result = execute_get_next_review(
                db_path=db_path,
                telegram_user_id="never-registered",
                arguments={},
            )

            self.assertEqual(result, {"next_review": None})


if __name__ == "__main__":
    unittest.main()
