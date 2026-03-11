from __future__ import annotations

import json
import os
import unittest

from leetcoach.llm.gemini_provider import GeminiProvider


def _extract_json_payload(text: str) -> dict[str, object]:
    body = text.strip()
    if body.startswith("```"):
        lines = body.splitlines()
        if len(lines) >= 3:
            body = "\n".join(lines[1:-1]).strip()
    return json.loads(body)


@unittest.skipUnless(
    os.getenv("LEETCOACH_RUN_LIVE_TESTS") == "1",
    "Set LEETCOACH_RUN_LIVE_TESTS=1 to run live Gemini integration tests.",
)
class GeminiProviderLiveIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            self.skipTest("GEMINI_API_KEY is required for live Gemini tests")
        self.api_key = api_key

    def test_live_generation_returns_expected_json_shape(self) -> None:
        provider = GeminiProvider(
            api_key=self.api_key,
            model_priority=("gemini-2.5-flash-lite",),
            max_transient_retries=1,
        )
        prompt = (
            "Return only valid JSON with keys: "
            "topic, question, options, correct_option, why_correct, why_others_wrong, concept_takeaway. "
            "options must be an object with A,B,C,D keys. "
            "why_others_wrong must be an object with A,B,C,D keys. "
            "No markdown fences. Topic should be arrays."
        )
        result = provider.generate_text(prompt)
        payload = _extract_json_payload(result.text)

        self.assertEqual(result.model, "gemini-2.5-flash-lite")
        self.assertIn("question", payload)
        self.assertIn("options", payload)
        self.assertIn("correct_option", payload)
        self.assertIn("why_correct", payload)
        self.assertIn("why_others_wrong", payload)
        self.assertIn("concept_takeaway", payload)

        options = payload.get("options")
        self.assertIsInstance(options, dict)
        for key in ("A", "B", "C", "D"):
            self.assertIn(key, options)

        why_others_wrong = payload.get("why_others_wrong")
        self.assertIsInstance(why_others_wrong, dict)
        for key in ("A", "B", "C", "D"):
            self.assertIn(key, why_others_wrong)

    def test_live_fallback_from_invalid_model_to_valid_model(self) -> None:
        provider = GeminiProvider(
            api_key=self.api_key,
            model_priority=("gemini-invalid-model", "gemini-2.5-flash-lite"),
            max_transient_retries=0,
        )
        prompt = "Reply with one sentence about binary search trees."
        result = provider.generate_text(prompt)
        self.assertEqual(result.model, "gemini-2.5-flash-lite")
        self.assertTrue(len(result.text.strip()) > 0)


if __name__ == "__main__":
    unittest.main()

