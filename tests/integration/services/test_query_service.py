from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import tempfile
import unittest

from leetcoach.app.application.problems.browse_problems import (
    get_problem_detail,
    get_problem_detail_by_ref,
    list_all_problems,
    list_by_pattern,
    resolve_problem_id_by_ref,
    search_problems,
)
from leetcoach.app.misc.migrate import migrate_database
from leetcoach.app.application.problems.log_problem import LogProblemInput, log_problem
from leetcoach.app.application.problems.edit_problem import edit_problem_field
from leetcoach.app.application.reviews.complete_review import complete_review


class QueryServiceIntegrationTest(unittest.TestCase):
    def test_search_pattern_and_list_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "leetcoach-test.db"
            migrate_database(str(db_path))

            old = datetime(2026, 2, 1, 8, 0, tzinfo=UTC)
            recent = datetime(2026, 2, 28, 8, 0, tzinfo=UTC)

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
                    time_complexity="O(n)",
                    space_complexity="O(k)",
                    notes="deque notes",
                ),
            )

            all_rows = list_all_problems(str(db_path), "u-1")
            self.assertEqual(len(all_rows), 2)
            self.assertEqual(all_rows[0]["title"], "Maximum Depth of Binary Tree")
            self.assertEqual(all_rows[1]["title"], "Sliding Window Maximum")
            detail = get_problem_detail(
                str(db_path), "u-1", int(all_rows[1]["user_problem_id"])
            )
            self.assertIsNotNone(detail)
            self.assertEqual(detail["title"], "Sliding Window Maximum")
            self.assertEqual(detail["concepts"], "deque monotonic queue")
            self.assertEqual(detail["notes"], "deque notes")

            # `complete_review` still exists as the shared "mark reviewed" path.
            # First call bumps review_count, second call is idempotent-ish
            # (both return True — the row exists and belongs to the user).
            self.assertTrue(
                complete_review(str(db_path), "u-1", int(all_rows[0]["user_problem_id"]))
            )
            self.assertTrue(
                complete_review(str(db_path), "u-1", int(all_rows[0]["user_problem_id"]))
            )

            search_rows = search_problems(str(db_path), "u-1", "deque")
            self.assertEqual(search_rows, [])

            complexity_rows = search_problems(str(db_path), "u-1", "o(n)")
            self.assertEqual(complexity_rows, [])

            difficulty_rows = search_problems(str(db_path), "u-1", "hard")
            self.assertEqual(len(difficulty_rows), 1)
            self.assertEqual(difficulty_rows[0]["title"], "Sliding Window Maximum")

            year_rows = search_problems(str(db_path), "u-1", str(recent.year))
            self.assertEqual(len(year_rows), 2)

            month_rows = search_problems(str(db_path), "u-1", recent.strftime("%B"))
            self.assertEqual(len(month_rows), 2)

            slug_rows = search_problems(str(db_path), "u-1", "sliding-window-maximum")
            self.assertEqual(slug_rows, [])

            pattern_rows = list_by_pattern(str(db_path), "u-1", "tree")
            self.assertEqual(len(pattern_rows), 1)
            self.assertEqual(pattern_rows[0]["pattern"], "trees")

    def test_stable_problem_ref_can_show_review_and_edit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "leetcoach-test.db"
            migrate_database(str(db_path))

            result = log_problem(
                str(db_path),
                LogProblemInput(
                    telegram_user_id="u-1",
                    telegram_chat_id="chat-1",
                    timezone="Europe/Berlin",
                    title="Maximum Depth of Binary Tree",
                    difficulty="easy",
                    leetcode_slug=None,
                    neetcode_slug="max-depth-of-binary-tree",
                    pattern="trees",
                    solved_at="2026-03-01T10:00:00+00:00",
                    notes="tree depth notes",
                ),
            )

            self.assertEqual(result.problem_ref, "P1")

            resolved_id = resolve_problem_id_by_ref(str(db_path), "u-1", 1)
            self.assertEqual(resolved_id, result.user_problem_id)

            detail = get_problem_detail_by_ref(str(db_path), "u-1", 1)
            self.assertIsNotNone(detail)
            self.assertEqual(detail["problem_ref"], "P1")
            self.assertEqual(detail["leetcode_slug"], "")

            edited = edit_problem_field(
                db_path=str(db_path),
                telegram_user_id="u-1",
                display_id=1,
                field="leetcode_slug",
                value="maximum-depth-of-binary-tree",
            )
            self.assertEqual(edited.status, "ok")

            detail_after = get_problem_detail_by_ref(str(db_path), "u-1", 1)
            self.assertIsNotNone(detail_after)
            self.assertEqual(
                detail_after["leetcode_slug"], "maximum-depth-of-binary-tree"
            )


if __name__ == "__main__":
    unittest.main()
