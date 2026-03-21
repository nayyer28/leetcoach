from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from leetcoach.app.infrastructure.dao.problems_dao import upsert_problem
from leetcoach.app.infrastructure.dao.user_problems_dao import get_user_problem_detail, upsert_user_problem
from leetcoach.app.infrastructure.dao.users_dao import upsert_user
from leetcoach.app.infrastructure.config.db import get_connection
from leetcoach.app.misc.migrate import migrate_database


class UserProblemsDaoUnitTest(unittest.TestCase):
    def test_upsert_user_problem_updates_existing_detail_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "leetcoach-test.db"
            migrate_database(str(db_path))

            with get_connection(str(db_path)) as conn:
                user_id = upsert_user(
                    conn,
                    telegram_user_id="u-1",
                    telegram_chat_id="chat-1",
                    timezone="UTC",
                    now_iso="2026-03-16T10:00:00+00:00",
                )
                problem_id = upsert_problem(
                    conn,
                    title="Validate Binary Search Tree",
                    difficulty="medium",
                    leetcode_slug="validate-binary-search-tree",
                    neetcode_slug="valid-binary-search-tree",
                    now_iso="2026-03-16T10:00:00+00:00",
                )
                first_id = upsert_user_problem(
                    conn,
                    user_id=user_id,
                    problem_id=problem_id,
                    pattern="Trees",
                    solved_at="2026-03-16T10:00:00+00:00",
                    concepts="bounds",
                    time_complexity="O(n)",
                    space_complexity="O(h)",
                    notes="first",
                    now_iso="2026-03-16T10:00:00+00:00",
                )
                second_id = upsert_user_problem(
                    conn,
                    user_id=user_id,
                    problem_id=problem_id,
                    pattern="Trees",
                    solved_at="2026-03-16T11:00:00+00:00",
                    concepts="recursive bounds",
                    time_complexity="O(n)",
                    space_complexity="O(h)",
                    notes="updated",
                    now_iso="2026-03-16T11:00:00+00:00",
                )
                conn.commit()

                self.assertEqual(first_id, second_id)
                row = get_user_problem_detail(
                    conn, user_id=user_id, user_problem_id=first_id
                )
                self.assertIsNotNone(row)
                self.assertEqual(row["concepts"], "recursive bounds")
                self.assertEqual(row["notes"], "updated")
                self.assertEqual(row["solved_at"], "2026-03-16T11:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
