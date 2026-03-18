from __future__ import annotations

import unittest

from leetcoach.services.analytics_tools import (
    AggregateProblemFilters,
    AggregateUserProblemsRequest,
    aggregate_user_problems_tool_definition,
)


class AnalyticsToolsUnitTest(unittest.TestCase):
    def test_tool_definition_exposes_expected_enums(self) -> None:
        definition = aggregate_user_problems_tool_definition()
        params = definition["parameters"]["properties"]
        self.assertEqual(definition["name"], "aggregate_user_problems")
        self.assertEqual(
            params["group_by"]["enum"],
            ["none", "difficulty", "pattern", "solved_date"],
        )
        self.assertEqual(
            params["metric"]["enum"],
            ["problem_count", "review_count_sum", "strength_score"],
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


if __name__ == "__main__":
    unittest.main()
