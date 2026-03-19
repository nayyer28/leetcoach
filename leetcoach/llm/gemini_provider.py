"""Backward-compatible Gemini provider import path."""

from leetcoach.app.infrastructure.llm import gemini_provider as _provider

DEFAULT_GEMINI_MODEL_PRIORITY = _provider.DEFAULT_GEMINI_MODEL_PRIORITY
GeminiAllModelsFailed = _provider.GeminiAllModelsFailed
GeminiApiError = _provider.GeminiApiError
GeminiGenerateResult = _provider.GeminiGenerateResult
GeminiProvider = _provider.GeminiProvider
_classify_http_error = _provider._classify_http_error
_extract_text = _provider._extract_text
