from __future__ import annotations

from typing import Any

from leetcoach.app.application.reviews.due_reviews import list_due_reviews
from leetcoach.app.application.reviews.reminder_engine import row_to_candidate
from leetcoach.app.infrastructure.config.db import get_connection
from leetcoach.app.infrastructure.dao.review_queue_dao import (
    list_last_requested_batch_for_user,
)
from leetcoach.app.infrastructure.dao.users_dao import get_user_id_by_telegram_user_id


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


def get_last_reminder_batch_tool_definition() -> dict[str, Any]:
    return {
        "name": "get_last_reminder_batch",
        "description": "Fetch the most recent reminder batch that was sent to the user.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 20,
                    "description": "Maximum number of reminder items to return.",
                }
            },
            "required": [],
        },
    }


def _parse_limit(arguments: dict[str, Any]) -> int:
    limit = int(arguments.get("limit", 10))
    if limit < 1 or limit > 20:
        raise ValueError("limit must be between 1 and 20")
    return limit


def execute_get_due_reviews(
    *, db_path: str, telegram_user_id: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    limit = _parse_limit(arguments)
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


def execute_get_last_reminder_batch(
    *, db_path: str, telegram_user_id: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    limit = _parse_limit(arguments)
    with get_connection(db_path) as conn:
        user_id = get_user_id_by_telegram_user_id(
            conn, telegram_user_id=telegram_user_id
        )
        if user_id is None:
            return {"requested_at": None, "reviews": []}
        rows = list_last_requested_batch_for_user(conn, user_id=user_id)

    if not rows:
        return {"requested_at": None, "reviews": []}

    candidates = [row_to_candidate(row) for row in rows[:limit]]
    requested_at = candidates[0].last_review_requested_at
    return {
        "requested_at": requested_at,
        "reviews": [
            {
                "problem_ref": candidate.problem_ref,
                "title": candidate.title,
                "leetcode_slug": candidate.leetcode_slug,
                "neetcode_slug": candidate.neetcode_slug,
                "solved_at": candidate.solved_at,
                "review_count": candidate.review_count,
                "requested_at": candidate.last_review_requested_at,
                "last_reviewed_at": candidate.last_reviewed_at,
            }
            for candidate in candidates
        ],
    }
