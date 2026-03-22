from __future__ import annotations

from typing import Any

from leetcoach.app.application.reviews.due_reviews import list_due_reviews


def get_due_reviews_tool_definition() -> dict[str, Any]:
    return {
        "name": "get_due_reviews",
        "description": "Fetch currently outstanding due reviews for the user.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 20,
                    "description": "Maximum number of due reviews to return.",
                }
            },
            "required": [],
        },
    }


def execute_get_due_reviews(
    *, db_path: str, telegram_user_id: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    limit = int(arguments.get("limit", 10))
    if limit < 1 or limit > 20:
        raise ValueError("limit must be between 1 and 20")
    items = list_due_reviews(db_path, telegram_user_id)
    return {
        "reviews": [
            {
                "problem_ref": item.problem_ref,
                "title": item.title,
                "leetcode_slug": item.leetcode_slug,
                "neetcode_slug": item.neetcode_slug,
                "solved_at": item.solved_at,
                "review_count": item.review_count,
                "requested_at": item.requested_at,
                "last_reviewed_at": item.last_reviewed_at,
                "status": item.status,
            }
            for item in items[:limit]
        ]
    }
