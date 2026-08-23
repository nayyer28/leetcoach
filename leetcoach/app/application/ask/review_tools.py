from __future__ import annotations

from typing import Any

from leetcoach.app.application.problems.problem_refs import format_problem_ref
from leetcoach.app.infrastructure.config.db import get_connection
from leetcoach.app.infrastructure.dao.review_queue_dao import (
    peek_next_review_candidate_for_user,
)
from leetcoach.app.infrastructure.dao.users_dao import get_user_id_by_telegram_user_id


def get_next_review_tool_definition() -> dict[str, Any]:
    return {
        "name": "get_next_review",
        "description": (
            "Peek the top of the user's review queue — the least-reviewed problem, "
            "ties broken by oldest bucket entry. Returns null if the queue is empty."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    }


def execute_get_next_review(
    *, db_path: str, telegram_user_id: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    del arguments  # no arguments — tool is a pure peek
    with get_connection(db_path) as conn:
        user_id = get_user_id_by_telegram_user_id(
            conn, telegram_user_id=telegram_user_id
        )
        if user_id is None:
            return {"next_review": None}
        row = peek_next_review_candidate_for_user(conn, user_id=user_id)

    if row is None:
        return {"next_review": None}

    return {
        "next_review": {
            "problem_ref": format_problem_ref(int(row["display_id"])),
            "title": str(row["title"]),
            "leetcode_slug": str(row["leetcode_slug"]) if row["leetcode_slug"] else None,
            "neetcode_slug": str(row["neetcode_slug"]) if row["neetcode_slug"] else None,
            "solved_at": str(row["solved_at"]),
            "review_count": int(row["review_count"]),
            "entered_at": str(row["entered_at"]),
        }
    }
