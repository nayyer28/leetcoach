"""LLM-related runtime configuration helpers."""

from leetcoach.app.infrastructure.config.app_config import AppConfig


def gemini_api_key(config: AppConfig) -> str | None:
    """Return the configured Gemini API key."""
    return config.gemini_api_key
