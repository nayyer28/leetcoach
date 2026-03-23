from __future__ import annotations

import unittest

from leetcoach.app.application.ask.help_tools import (
    describe_ask_capabilities_tool_definition,
    execute_describe_ask_capabilities,
)


class HelpToolsUnitTest(unittest.TestCase):
    def test_tool_definition_exposes_focus_enum(self) -> None:
        tool = describe_ask_capabilities_tool_definition()
        self.assertEqual(tool["name"], "describe_ask_capabilities")
        self.assertIn("focus", tool["parameters"]["properties"])
        self.assertIn("examples", tool["parameters"]["properties"]["focus"]["enum"])

    def test_execute_describe_ask_capabilities_returns_examples(self) -> None:
        result = execute_describe_ask_capabilities(arguments={"focus": "examples"})
        self.assertEqual(result["focus"], "examples")
        self.assertIn("examples", result)
        self.assertIn("show problem P1", result["examples"])
        self.assertIn("what is due right now?", result["examples"])

    def test_execute_describe_ask_capabilities_can_focus_on_reviews(self) -> None:
        result = execute_describe_ask_capabilities(arguments={"focus": "reviews"})
        self.assertEqual(result["focus"], "reviews")
        self.assertEqual(len(result["categories"]), 1)
        self.assertEqual(result["categories"][0]["name"], "reviews")

