from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
import tempfile
import unittest

from leetcoach.db.migrate import migrate_database
from leetcoach.services.log_problem_service import LogProblemInput, log_problem


class LogProblemServiceIntegrationTest(unittest.TestCase):
    def test_log_problem_upserts_entities_and_creates_review_rows(self) -> None:
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

            with sqlite3.connect(db_path) as conn:
                users_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
                problems_count = conn.execute("SELECT COUNT(*) FROM problems").fetchone()[0]
                user_problems_count = conn.execute(
                    "SELECT COUNT(*) FROM user_problems"
                ).fetchone()[0]
                reviews = conn.execute(
                    """
                    SELECT review_day, due_at, buffer_until
                    FROM problem_reviews
                    ORDER BY review_day
                    """
                ).fetchall()

            self.assertEqual(users_count, 1)
            self.assertEqual(problems_count, 1)
            self.assertEqual(user_problems_count, 1)
            self.assertEqual(len(reviews), 2)

            solved_at = datetime.fromisoformat(payload.solved_at)
            expected = {
                7: (solved_at + timedelta(days=7), solved_at + timedelta(days=7, hours=48)),
                21: (
                    solved_at + timedelta(days=21),
                    solved_at + timedelta(days=21, hours=48),
                ),
            }
            for review_day, due_at, buffer_until in reviews:
                exp_due, exp_buffer = expected[int(review_day)]
                self.assertEqual(datetime.fromisoformat(due_at), exp_due)
                self.assertEqual(datetime.fromisoformat(buffer_until), exp_buffer)


if __name__ == "__main__":
    unittest.main()

