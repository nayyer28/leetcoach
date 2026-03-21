from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile
import unittest

from leetcoach.app.misc.migrate import migrate_database
from leetcoach.app.application.problems.log_problem import LogProblemInput, log_problem


class LogProblemServiceIntegrationTest(unittest.TestCase):
    def test_log_problem_upserts_entities_and_initializes_queue_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "leetcoach-test.db"
            migrate_database(str(db_path))

            payload = LogProblemInput(
                telegram_user_id="u-1",
                telegram_chat_id="chat-1",
                timezone="Europe/Berlin",
                title="Maximum Depth of Binary Tree",
                difficulty="easy",
                leetcode_slug="maximum-depth-of-binary-tree",
                neetcode_slug="max-depth-of-binary-tree",
                pattern="tree-dfs",
                solved_at="2026-03-02T10:00:00+00:00",
                concepts="DFS recursive and iterative forms",
                time_complexity="O(n)",
                space_complexity="O(h)",
                notes="Revisit iterative stack variant",
            )

            first = log_problem(str(db_path), payload)
            second = log_problem(str(db_path), payload)

            self.assertEqual(first.user_id, second.user_id)
            self.assertEqual(first.problem_id, second.problem_id)
            self.assertEqual(first.user_problem_id, second.user_problem_id)
            self.assertEqual(first.display_id, second.display_id)
            self.assertEqual(first.problem_ref, second.problem_ref)
            self.assertEqual(first.problem_ref, "P1")

            with sqlite3.connect(db_path) as conn:
                users_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
                problems_count = conn.execute("SELECT COUNT(*) FROM problems").fetchone()[0]
                user_problems_count = conn.execute(
                    "SELECT COUNT(*) FROM user_problems"
                ).fetchone()[0]
                queue_state = conn.execute(
                    """
                    SELECT queue_position, review_count, last_review_requested_at, last_reviewed_at
                    FROM user_problems
                    """
                ).fetchone()

            self.assertEqual(users_count, 1)
            self.assertEqual(problems_count, 1)
            self.assertEqual(user_problems_count, 1)
            self.assertIsNotNone(queue_state)
            self.assertGreater(int(queue_state[0]), 0)
            self.assertEqual(int(queue_state[1]), 0)
            self.assertIsNone(queue_state[2])
            self.assertIsNone(queue_state[3])


if __name__ == "__main__":
    unittest.main()
