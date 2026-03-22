from __future__ import annotations

import unittest

from leetcoach.app.application.ask.problem_tools import (
    VALID_PATTERN_LABELS,
    get_problem_detail_tool_definition,
    list_user_problems_tool_definition,
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

        self.assertEqual(detail["name"], "get_problem_detail")
        self.assertEqual(listing["name"], "list_user_problems")
        self.assertEqual(search["name"], "search_user_problems")
        self.assertEqual(
            listing["parameters"]["properties"]["pattern"]["enum"],
            list(VALID_PATTERN_LABELS),
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


if __name__ == "__main__":
    unittest.main()
