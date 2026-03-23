from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from leetcoach.app.application.ask.problem_tools import (
    execute_get_problem_detail,
    execute_list_user_problems,
    execute_query_user_problems,
    execute_search_user_problems,
)
from leetcoach.app.application.problems.log_problem import LogProblemInput, log_problem
from leetcoach.app.misc.migrate import migrate_database


class ProblemToolsIntegrationTest(unittest.TestCase):
    def test_problem_tools_execute_against_real_db(self) -> None:
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
                    solved_at="2026-02-01T08:00:00+00:00",
                    concepts="dfs depth recursion",
                    time_complexity="O(n)",
                    space_complexity="O(h)",
                    notes="first tree note",
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
                    solved_at="2026-02-02T08:00:00+00:00",
                    concepts="hash set",
                    notes="duplicate lookup",
                ),
            )

            detail = execute_get_problem_detail(
                db_path=db_path,
                telegram_user_id="u-1",
                arguments={"problem_ref": "P1"},
            )
            self.assertEqual(detail["problem"]["problem_ref"], "P1")
            self.assertEqual(detail["problem"]["title"], "Maximum Depth of Binary Tree")

            recent = execute_list_user_problems(
                db_path=db_path,
                telegram_user_id="u-1",
                arguments={"limit": 1, "recent_only": True},
            )
            self.assertEqual(len(recent["problems"]), 1)
            self.assertEqual(recent["problems"][0]["problem_ref"], "P2")

            trees = execute_list_user_problems(
                db_path=db_path,
                telegram_user_id="u-1",
                arguments={"pattern": "Trees", "limit": 10},
            )
            self.assertEqual(len(trees["problems"]), 1)
            self.assertEqual(trees["problems"][0]["problem_ref"], "P1")

            search = execute_search_user_problems(
                db_path=db_path,
                telegram_user_id="u-1",
                arguments={"query": "O(n)"},
            )
            self.assertEqual(len(search["problems"]), 1)
            self.assertEqual(search["problems"][0]["problem_ref"], "P1")

            february = execute_query_user_problems(
                db_path=db_path,
                telegram_user_id="u-1",
                arguments={
                    "solved_date_from": "2026-02-01",
                    "solved_date_to": "2026-02-28",
                    "order_by": "solved_at_asc",
                    "limit": 10,
                },
            )
            self.assertEqual(len(february["problems"]), 2)
            self.assertEqual(
                [row["problem_ref"] for row in february["problems"]],
                ["P1", "P2"],
            )

            filtered = execute_query_user_problems(
                db_path=db_path,
                telegram_user_id="u-1",
                arguments={
                    "pattern": "Trees",
                    "difficulty": "easy",
                    "solved_date_from": "2026-02-01",
                    "solved_date_to": "2026-02-28",
                    "order_by": "solved_at_desc",
                    "limit": 10,
                },
            )
            self.assertEqual(len(filtered["problems"]), 1)
            self.assertEqual(filtered["problems"][0]["problem_ref"], "P1")


if __name__ == "__main__":
    unittest.main()
