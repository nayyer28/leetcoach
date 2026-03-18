from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import sqlite3
import tempfile
import unittest

from leetcoach.db.migrate import migrate_database
from leetcoach.services.analytics_tools import (
    AggregateProblemFilters,
    AggregateUserProblemsRequest,
    aggregate_user_problems,
)
from leetcoach.services.log_problem_service import LogProblemInput, log_problem


class AnalyticsToolsIntegrationTest(unittest.TestCase):
    def test_problem_count_with_difficulty_and_pattern_filters(self) -> None:
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
                    pattern="tree dfs",
                    solved_at="2026-03-01T08:00:00+00:00",
                ),
            )
            log_problem(
                db_path,
                LogProblemInput(
                    telegram_user_id="u-1",
                    telegram_chat_id="chat-1",
                    timezone="Europe/Berlin",
                    title="Binary Tree Right Side View",
                    difficulty="medium",
                    leetcode_slug="binary-tree-right-side-view",
                    neetcode_slug="binary-tree-right-side-view",
                    pattern="trees",
                    solved_at="2026-03-02T08:00:00+00:00",
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
                    pattern="arrays",
                    solved_at="2026-03-03T08:00:00+00:00",
                ),
            )

            result = aggregate_user_problems(
                db_path,
                "u-1",
                AggregateUserProblemsRequest(
                    group_by="none",
                    metric="problem_count",
                    filters=AggregateProblemFilters(difficulty="easy", pattern="tree"),
                ),
            )

            self.assertEqual(result.rows[0].group, "all")
            self.assertEqual(result.rows[0].value, 1)
            self.assertEqual(result.filters_applied["difficulty"], "easy")
            self.assertEqual(result.filters_applied["pattern"], "Trees")

    def test_solved_date_aggregation_uses_user_timezone(self) -> None:
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
                    pattern="arrays",
                    solved_at="2026-03-01T23:30:00+00:00",
                ),
            )
            log_problem(
                db_path,
                LogProblemInput(
                    telegram_user_id="u-1",
                    telegram_chat_id="chat-1",
                    timezone="Europe/Berlin",
                    title="Two Sum",
                    difficulty="easy",
                    leetcode_slug="two-sum",
                    neetcode_slug="two-sum",
                    pattern="arrays",
                    solved_at="2026-03-01T23:45:00+00:00",
                ),
            )

            result = aggregate_user_problems(
                db_path,
                "u-1",
                AggregateUserProblemsRequest(
                    group_by="solved_date",
                    metric="problem_count",
                    sort="metric_desc",
                ),
            )

            self.assertEqual(result.rows[0].group, "2026-03-02")
            self.assertEqual(result.rows[0].value, 2)

    def test_strongest_pattern_uses_problem_count_plus_review_sum(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "leetcoach-test.db")
            migrate_database(db_path)

            first = log_problem(
                db_path,
                LogProblemInput(
                    telegram_user_id="u-1",
                    telegram_chat_id="chat-1",
                    timezone="UTC",
                    title="Maximum Depth of Binary Tree",
                    difficulty="easy",
                    leetcode_slug="maximum-depth-of-binary-tree",
                    neetcode_slug="max-depth-of-binary-tree",
                    pattern="trees",
                    solved_at="2026-03-01T10:00:00+00:00",
                ),
            )
            second = log_problem(
                db_path,
                LogProblemInput(
                    telegram_user_id="u-1",
                    telegram_chat_id="chat-1",
                    timezone="UTC",
                    title="Validate Binary Search Tree",
                    difficulty="medium",
                    leetcode_slug="validate-binary-search-tree",
                    neetcode_slug="valid-binary-search-tree",
                    pattern="tree",
                    solved_at="2026-03-02T10:00:00+00:00",
                ),
            )
            log_problem(
                db_path,
                LogProblemInput(
                    telegram_user_id="u-1",
                    telegram_chat_id="chat-1",
                    timezone="UTC",
                    title="Contains Duplicate",
                    difficulty="easy",
                    leetcode_slug="contains-duplicate",
                    neetcode_slug="contains-duplicate",
                    pattern="arrays",
                    solved_at="2026-03-03T10:00:00+00:00",
                ),
            )

            now_iso = datetime.now(UTC).isoformat()
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    "UPDATE user_problems SET review_count = ?, updated_at = ? WHERE id = ?",
                    (2, now_iso, first.user_problem_id),
                )
                conn.execute(
                    "UPDATE user_problems SET review_count = ?, updated_at = ? WHERE id = ?",
                    (1, now_iso, second.user_problem_id),
                )
                conn.commit()

            result = aggregate_user_problems(
                db_path,
                "u-1",
                AggregateUserProblemsRequest(
                    group_by="pattern",
                    metric="strength_score",
                    sort="metric_desc",
                    limit=3,
                ),
            )

            self.assertEqual(result.rows[0].group, "Trees")
            self.assertEqual(result.rows[0].value, 5)

    def test_invalid_pattern_filter_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "leetcoach-test.db")
            migrate_database(db_path)

            with self.assertRaises(ValueError):
                aggregate_user_problems(
                    db_path,
                    "u-1",
                    AggregateUserProblemsRequest(
                        group_by="none",
                        metric="problem_count",
                        filters=AggregateProblemFilters(pattern="not-a-real-pattern"),
                    ),
                )


if __name__ == "__main__":
    unittest.main()
