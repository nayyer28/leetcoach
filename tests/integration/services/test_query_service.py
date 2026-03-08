from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import tempfile
import unittest

from leetcoach.db.migrate import migrate_database
from leetcoach.services.log_problem_service import LogProblemInput, log_problem
from leetcoach.services.query_service import (
    complete_review,
    list_all_problems,
    list_by_pattern,
    list_due_reviews,
    search_problems,
)


class QueryServiceIntegrationTest(unittest.TestCase):
    def test_due_complete_search_pattern_and_list_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "leetcoach-test.db"
            migrate_database(str(db_path))

            old = datetime.now(UTC) - timedelta(days=30)
            recent = datetime.now(UTC) - timedelta(days=1)

            log_problem(
                str(db_path),
                LogProblemInput(
                    telegram_user_id="u-1",
                    telegram_chat_id="chat-1",
                    timezone="Europe/Berlin",
                    title="Maximum Depth of Binary Tree",
                    difficulty="easy",
                    leetcode_slug="maximum-depth-of-binary-tree",
                    neetcode_slug="max-depth-of-binary-tree",
                    pattern="trees",
                    solved_at=old.isoformat(),
                    concepts="dfs depth recursion",
                    time_complexity=None,
                    space_complexity=None,
                    notes="tree depth notes",
                ),
            )
            log_problem(
                str(db_path),
                LogProblemInput(
                    telegram_user_id="u-1",
                    telegram_chat_id="chat-1",
                    timezone="Europe/Berlin",
                    title="Sliding Window Maximum",
                    difficulty="hard",
                    leetcode_slug="sliding-window-maximum",
                    neetcode_slug="sliding-window-maximum-neet",
                    pattern="sliding-window",
                    solved_at=recent.isoformat(),
                    concepts="deque monotonic queue",
                    time_complexity=None,
                    space_complexity=None,
                    notes="deque notes",
                ),
            )

            all_rows = list_all_problems(str(db_path), "u-1")
            self.assertEqual(len(all_rows), 2)
            self.assertEqual(all_rows[0]["title"], "Sliding Window Maximum")
            self.assertEqual(all_rows[1]["title"], "Maximum Depth of Binary Tree")

            due = list_due_reviews(str(db_path), "u-1")
            self.assertEqual(len(due), 2)
            self.assertTrue(all(item.status in {"pending", "overdue"} for item in due))

            first = due[0]
            ok = complete_review(
                str(db_path), "u-1", first.user_problem_id, first.review_day
            )
            self.assertTrue(ok)

            second_try = complete_review(
                str(db_path), "u-1", first.user_problem_id, first.review_day
            )
            self.assertFalse(second_try)

            due_after = list_due_reviews(str(db_path), "u-1")
            self.assertEqual(len(due_after), 1)

            search_rows = search_problems(str(db_path), "u-1", "deque")
            self.assertEqual(len(search_rows), 1)
            self.assertEqual(search_rows[0]["title"], "Sliding Window Maximum")

            pattern_rows = list_by_pattern(str(db_path), "u-1", "tree")
            self.assertEqual(len(pattern_rows), 1)
            self.assertEqual(pattern_rows[0]["pattern"], "trees")

            unknown_user_due = list_due_reviews(str(db_path), "u-missing")
            self.assertEqual(unknown_user_due, [])


if __name__ == "__main__":
    unittest.main()
