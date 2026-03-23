from __future__ import annotations

import unittest

from leetcoach.app.application.ask.problem_tools import (
    VALID_PATTERN_LABELS,
    VALID_ORDER_BY,
    execute_query_user_problems,
    get_problem_detail_tool_definition,
    list_user_problems_tool_definition,
    query_user_problems_tool_definition,
    search_user_problems_tool_definition,
    execute_get_problem_detail,
    execute_list_user_problems,
    execute_search_user_problems,
)


class ProblemToolsUnitTest(unittest.TestCase):
    def test_tool_definitions_expose_expected_shapes(self) -> None:
        detail = get_problem_detail_tool_definition()
        listing = list_user_problems_tool_definition()
        search = search_user_problems_tool_definition()
        query = query_user_problems_tool_definition()

        self.assertEqual(detail["name"], "get_problem_detail")
        self.assertEqual(listing["name"], "list_user_problems")
        self.assertEqual(search["name"], "search_user_problems")
        self.assertEqual(query["name"], "query_user_problems")
        self.assertEqual(
            listing["parameters"]["properties"]["pattern"]["enum"],
            list(VALID_PATTERN_LABELS),
        )
        self.assertEqual(
            query["parameters"]["properties"]["order_by"]["enum"],
            list(VALID_ORDER_BY),
        )

    def test_get_problem_detail_rejects_invalid_problem_ref(self) -> None:
        with self.assertRaisesRegex(ValueError, "problem_ref must look like P1"):
            execute_get_problem_detail(
                db_path="ignored",
                telegram_user_id="u-1",
                arguments={"problem_ref": "abc"},
            )

    def test_list_user_problems_rejects_invalid_limit(self) -> None:
        with self.assertRaisesRegex(ValueError, "limit must be between 1 and 20"):
            execute_list_user_problems(
                db_path="ignored",
                telegram_user_id="u-1",
                arguments={"limit": 0},
            )

    def test_list_user_problems_rejects_unknown_pattern(self) -> None:
        with self.assertRaisesRegex(ValueError, "pattern must resolve"):
            execute_list_user_problems(
                db_path="ignored",
                telegram_user_id="u-1",
                arguments={"pattern": "not-a-real-pattern"},
            )

    def test_search_user_problems_rejects_blank_query(self) -> None:
        with self.assertRaisesRegex(ValueError, "query must be a non-empty string"):
            execute_search_user_problems(
                db_path="ignored",
                telegram_user_id="u-1",
                arguments={"query": "   "},
            )

    def test_query_user_problems_rejects_invalid_dates(self) -> None:
        with self.assertRaisesRegex(ValueError, "solved_date_from must be a YYYY-MM-DD string"):
            execute_query_user_problems(
                db_path="ignored",
                telegram_user_id="u-1",
                arguments={"solved_date_from": "2026/02/01"},
            )

    def test_query_user_problems_rejects_inverted_date_range(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot be after"):
            execute_query_user_problems(
                db_path="ignored",
                telegram_user_id="u-1",
                arguments={
                    "solved_date_from": "2026-03-01",
                    "solved_date_to": "2026-02-01",
                },
            )

    def test_query_user_problems_rejects_invalid_order_by(self) -> None:
        with self.assertRaisesRegex(ValueError, "order_by must be a supported ordering"):
            execute_query_user_problems(
                db_path="ignored",
                telegram_user_id="u-1",
                arguments={"order_by": "title_asc"},
            )


if __name__ == "__main__":
    unittest.main()
