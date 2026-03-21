from __future__ import annotations

import unittest

from leetcoach.app.infrastructure.llm.gemini_provider import (
    DEFAULT_GEMINI_MODEL_PRIORITY,
    GeminiAllModelsFailed,
    GeminiApiError,
    GeminiProvider,
    _classify_http_error,
    _extract_text,
)


class GeminiProviderUnitTest(unittest.TestCase):
    def test_fallback_on_quota_exhausted(self) -> None:
        calls: list[str] = []

        def transport(model: str, prompt: str) -> str:
            calls.append(model)
            if model == "gemini-2.5-pro":
                raise GeminiApiError(
                    message="quota exceeded",
                    status_code=429,
                    retryable=True,
                    quota_exhausted=True,
                )
            return f"ok from {model}: {prompt}"

        provider = GeminiProvider(
            api_key="dummy",
            model_priority=("gemini-2.5-pro", "gemini-2.5-flash"),
            transport=transport,
        )
        result = provider.generate_text("hello")
        self.assertEqual(result.model, "gemini-2.5-flash")
        self.assertIn("hello", result.text)
        self.assertEqual(calls, ["gemini-2.5-pro", "gemini-2.5-flash"])

    def test_retry_transient_then_success_same_model(self) -> None:
        calls = {"count": 0}

        def transport(model: str, prompt: str) -> str:
            calls["count"] += 1
            if calls["count"] == 1:
                raise GeminiApiError(message="network timeout", retryable=True)
            return "success"

        provider = GeminiProvider(
            api_key="dummy",
            model_priority=("gemini-2.5-flash",),
            max_transient_retries=1,
            transport=transport,
            sleep_fn=lambda _: None,
        )
        result = provider.generate_text("x")
        self.assertEqual(result.model, "gemini-2.5-flash")
        self.assertEqual(result.text, "success")
        self.assertEqual(calls["count"], 2)

    def test_all_models_failed_raises(self) -> None:
        def transport(model: str, prompt: str) -> str:
            raise GeminiApiError(message=f"{model} down", retryable=False)

        provider = GeminiProvider(
            api_key="dummy",
            model_priority=("gemini-2.5-pro", "gemini-2.5-flash"),
            transport=transport,
        )
        with self.assertRaises(GeminiAllModelsFailed) as ctx:
            provider.generate_text("x")
        msg = str(ctx.exception)
        self.assertIn("gemini-2.5-pro", msg)
        self.assertIn("gemini-2.5-flash", msg)

    def test_extract_text(self) -> None:
        payload = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "line1"},
                            {"text": "line2"},
                        ]
                    }
                }
            ]
        }
        self.assertEqual(_extract_text(payload), "line1\nline2")

    def test_classify_http_error_quota(self) -> None:
        err = _classify_http_error(429, '{"error":{"status":"RESOURCE_EXHAUSTED"}}')
        self.assertTrue(err.quota_exhausted)
        self.assertTrue(err.retryable)

    def test_default_model_priority_order(self) -> None:
        self.assertEqual(
            DEFAULT_GEMINI_MODEL_PRIORITY,
            (
                "gemini-2.5-pro",
                "gemini-2.5-flash",
                "gemini-2.5-flash-lite",
                "gemini-2.0-flash",
                "gemini-2.0-flash-lite",
            ),
        )


if __name__ == "__main__":
    unittest.main()

