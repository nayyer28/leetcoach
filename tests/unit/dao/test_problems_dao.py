from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from leetcoach.app.infrastructure.dao.problems_dao import upsert_problem
from leetcoach.app.infrastructure.config.db import get_connection
from leetcoach.app.misc.migrate import migrate_database


class ProblemsDaoUnitTest(unittest.TestCase):
    def test_upsert_problem_keeps_existing_leetcode_slug_when_new_value_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "leetcoach-test.db"
            migrate_database(str(db_path))

            with get_connection(str(db_path)) as conn:
                first_id = upsert_problem(
                    conn,
                    title="Validate Binary Search Tree",
                    difficulty="medium",
                    leetcode_slug="validate-binary-search-tree",
                    neetcode_slug="valid-binary-search-tree",
                    now_iso="2026-03-16T10:00:00+00:00",
                )
                second_id = upsert_problem(
                    conn,
                    title="Validate Binary Search Tree",
                    difficulty="hard",
                    leetcode_slug=None,
                    neetcode_slug="valid-binary-search-tree",
                    now_iso="2026-03-16T11:00:00+00:00",
                )
                conn.commit()

                self.assertEqual(first_id, second_id)
                row = conn.execute(
                    "SELECT difficulty, leetcode_slug FROM problems WHERE id = ?",
                    (first_id,),
                ).fetchone()
                self.assertEqual(row["difficulty"], "hard")
                self.assertEqual(row["leetcode_slug"], "validate-binary-search-tree")


if __name__ == "__main__":
    unittest.main()
