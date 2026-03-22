from __future__ import annotations

import unittest

from leetcoach.app.application.ask.review_tools import (
    execute_get_due_reviews,
    get_due_reviews_tool_definition,
)


class ReviewToolsUnitTest(unittest.TestCase):
    def test_tool_definition_exposes_expected_shape(self) -> None:
        definition = get_due_reviews_tool_definition()
        self.assertEqual(definition["name"], "get_due_reviews")
        self.assertEqual(
            definition["parameters"]["properties"]["limit"]["maximum"],
            20,
        )

    def test_execute_get_due_reviews_rejects_invalid_limit(self) -> None:
        with self.assertRaisesRegex(ValueError, "limit must be between 1 and 20"):
            execute_get_due_reviews(
                db_path="ignored",
                telegram_user_id="u-1",
                arguments={"limit": 0},
            )


if __name__ == "__main__":
    unittest.main()
