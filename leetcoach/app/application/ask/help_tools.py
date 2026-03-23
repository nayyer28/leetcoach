from __future__ import annotations

from typing import Any


_VALID_FOCUS = {"overview", "problems", "reviews", "analytics", "examples"}


def describe_ask_capabilities_tool_definition() -> dict[str, Any]:
    return {
        "name": "describe_ask_capabilities",
        "description": (
            "Return the current read-only capabilities of /ask, including supported question types, "
            "example prompts, and current limitations. Use this when the user asks what /ask can do, asks for examples, or asks how to use it."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "focus": {
                    "type": "string",
                    "description": "Optional area to emphasize.",
                    "enum": sorted(_VALID_FOCUS),
                }
            },
            "required": [],
            "additionalProperties": False,
        },
    }


def execute_describe_ask_capabilities(*, arguments: dict[str, Any]) -> dict[str, Any]:
    focus = str(arguments.get("focus", "overview")).strip().lower() or "overview"
    if focus not in _VALID_FOCUS:
        raise ValueError("focus must be one of overview, problems, reviews, analytics, examples")

    categories = [
        {
            "name": "problems",
            "description": "Look up, list, filter, and search your logged problems.",
            "examples": [
                "show problem P1",
                "show my latest 5 problems",
                "show my tree problems",
                "show me all problems I solved in Feb 2026",
                "search for binary search",
            ],
        },
        {
            "name": "reviews",
            "description": "See what is due and what was in your last reminder batch.",
            "examples": [
                "what is due right now?",
                "show my due reviews",
                "what did you remind me last?",
            ],
        },
        {
            "name": "analytics",
            "description": "Ask for counts, grouped breakdowns, and lightweight summaries.",
            "examples": [
                "how many easy problems have I solved in Trees?",
                "what is my strongest pattern?",
                "which day did I solve the most problems?",
            ],
        },
    ]

    payload: dict[str, Any] = {
        "summary": (
            "/ask is best for read-only questions about your logged problems, due reviews, reminder history, and analytics. "
            "Use /log and /edit for write flows."
        ),
        "categories": categories,
        "limitations": [
            "read-only for now",
            "write flows like logging, editing, or marking reviewed are better through explicit commands",
            "some niche reads may still need new tool support",
        ],
        "focus": focus,
    }

    if focus in {"problems", "reviews", "analytics"}:
        payload["categories"] = [category for category in categories if category["name"] == focus]
    elif focus == "examples":
        payload["examples"] = [
            example
            for category in categories
            for example in category["examples"]
        ]

    return payload
