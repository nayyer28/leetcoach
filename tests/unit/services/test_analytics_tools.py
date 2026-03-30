from __future__ import annotations

import unittest

from leetcoach.app.application.analytics.aggregate_user_problems import (
    AggregateProblemFilters,
    AggregateUserProblemsRequest,
    VALID_PATTERN_LABELS,
    aggregate_user_problems_tool_definition,
    validate_aggregate_user_problems_request,
)


class AnalyticsToolsUnitTest(unittest.TestCase):
    def test_tool_definition_exposes_expected_enums(self) -> None:
        definition = aggregate_user_problems_tool_definition()
        params = definition["parameters"]["properties"]
        self.assertEqual(definition["name"], "aggregate_user_problems")
        self.assertEqual(
            params["group_by"]["enum"],
            ["none", "difficulty", "pattern", "solved_date", "solved_month"],
        )
        self.assertEqual(
            params["metric"]["enum"],
            ["problem_count", "review_count_sum", "strength_score"],
        )
        self.assertEqual(
            params["filters"]["properties"]["pattern"]["enum"],
            list(VALID_PATTERN_LABELS),
        )

    def test_request_dataclass_can_hold_filters(self) -> None:
        request = AggregateUserProblemsRequest(
            group_by="pattern",
            metric="strength_score",
            sort="metric_desc",
            limit=5,
            filters=AggregateProblemFilters(
                difficulty="easy",
                pattern="tree",
                solved_date_from="2026-03-01",
                solved_date_to="2026-03-31",
            ),
        )
        self.assertEqual(request.group_by, "pattern")
        self.assertEqual(request.metric, "strength_score")
        self.assertEqual(request.filters.pattern, "tree")

    def test_validate_request_normalizes_filters(self) -> None:
        validated = validate_aggregate_user_problems_request(
            AggregateUserProblemsRequest(
                group_by="pattern",
                metric="strength_score",
                sort="metric_desc",
                limit=5,
                filters=AggregateProblemFilters(
                    difficulty="Easy",
                    pattern="tree",
                    solved_date_from="2026-03-01",
                    solved_date_to="2026-03-31",
                ),
            )
        )
        self.assertEqual(validated.difficulty, "easy")
        self.assertEqual(validated.pattern, "Trees")
        self.assertEqual(validated.solved_date_from.isoformat(), "2026-03-01")
        self.assertEqual(validated.solved_date_to.isoformat(), "2026-03-31")

    def test_validate_request_rejects_unknown_pattern(self) -> None:
        with self.assertRaisesRegex(ValueError, "pattern must resolve"):
            validate_aggregate_user_problems_request(
                AggregateUserProblemsRequest(
                    group_by="none",
                    metric="problem_count",
                    filters=AggregateProblemFilters(pattern="not-a-real-pattern"),
                )
            )

    def test_validate_request_rejects_invalid_limit(self) -> None:
        with self.assertRaisesRegex(ValueError, "limit must be between 1 and 20"):
            validate_aggregate_user_problems_request(
                AggregateUserProblemsRequest(
                    group_by="none",
                    metric="problem_count",
                    limit=21,
                )
            )

    def test_validate_request_rejects_date_range_inversion(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot be after"):
            validate_aggregate_user_problems_request(
                AggregateUserProblemsRequest(
                    group_by="none",
                    metric="problem_count",
                    filters=AggregateProblemFilters(
                        solved_date_from="2026-03-31",
                        solved_date_to="2026-03-01",
                    ),
                )
            )


if __name__ == "__main__":
    unittest.main()
