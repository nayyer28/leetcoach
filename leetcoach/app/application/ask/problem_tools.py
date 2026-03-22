from __future__ import annotations

from typing import Any

from leetcoach.app.application.problems.browse_problems import (
    get_problem_detail_by_ref,
    list_all_problems,
    list_by_pattern,
    list_recent_problems,
    search_problems,
)
from leetcoach.app.application.problems.problem_refs import parse_problem_ref
from leetcoach.app.application.shared.patterns import ROADMAP_PATTERN_LEVELS, canonical_pattern_label


VALID_PATTERN_LABELS: tuple[str, ...] = tuple(
    label for _, label in ROADMAP_PATTERN_LEVELS.values()
)


def get_problem_detail_tool_definition() -> dict[str, Any]:
    return {
        "name": "get_problem_detail",
        "description": "Fetch one logged problem by stable problem ref like P1.",
        "parameters": {
            "type": "object",
            "properties": {
                "problem_ref": {
                    "type": "string",
                    "description": "Stable problem ref such as P1.",
                }
            },
            "required": ["problem_ref"],
        },
    }


def list_user_problems_tool_definition() -> dict[str, Any]:
    return {
        "name": "list_user_problems",
        "description": "List logged problems, optionally filtered by pattern or limited to recent results.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 20,
                    "description": "Maximum number of problems to return.",
                },
                "pattern": {
                    "type": "string",
                    "enum": list(VALID_PATTERN_LABELS),
                    "description": "Optional roadmap pattern filter.",
                },
                "recent_only": {
                    "type": "boolean",
                    "description": "If true, return the most recent problems first.",
                },
            },
            "required": [],
        },
    }


def search_user_problems_tool_definition() -> dict[str, Any]:
    return {
        "name": "search_user_problems",
        "description": "Search logged problems across title, pattern, concepts, notes, complexity, slugs, difficulty, and solved date text.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Free-text query to search across logged problem fields.",
                }
            },
            "required": ["query"],
        },
    }


def _parse_problem_ref_argument(arguments: dict[str, Any]) -> int:
    raw = arguments.get("problem_ref")
    if not isinstance(raw, str):
        raise ValueError("problem_ref must be a string like P1")
    display_id = parse_problem_ref(raw)
    if display_id is None:
        raise ValueError("problem_ref must look like P1")
    return display_id


def _parse_limit_argument(arguments: dict[str, Any]) -> int:
    limit = int(arguments.get("limit", 10))
    if limit < 1 or limit > 20:
        raise ValueError("limit must be between 1 and 20")
    return limit


def _parse_pattern_argument(arguments: dict[str, Any]) -> str | None:
    raw = arguments.get("pattern")
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ValueError("pattern must be a string")
    label = canonical_pattern_label(raw)
    if label is None:
        raise ValueError("pattern must resolve to a known roadmap pattern")
    return label


def _parse_recent_only_argument(arguments: dict[str, Any]) -> bool:
    value = arguments.get("recent_only", False)
    if isinstance(value, bool):
        return value
    raise ValueError("recent_only must be a boolean")


def _parse_query_argument(arguments: dict[str, Any]) -> str:
    raw = arguments.get("query")
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("query must be a non-empty string")
    return raw.strip()


def execute_get_problem_detail(
    *, db_path: str, telegram_user_id: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    display_id = _parse_problem_ref_argument(arguments)
    detail = get_problem_detail_by_ref(db_path, telegram_user_id, display_id)
    return {
        "problem": detail,
    }


def execute_list_user_problems(
    *, db_path: str, telegram_user_id: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    limit = _parse_limit_argument(arguments)
    pattern = _parse_pattern_argument(arguments)
    recent_only = _parse_recent_only_argument(arguments)

    if pattern is not None:
        problems = list_by_pattern(db_path, telegram_user_id, pattern)[:limit]
    elif recent_only:
        problems = list_recent_problems(db_path, telegram_user_id, limit=limit)
    else:
        problems = list_all_problems(db_path, telegram_user_id)[:limit]

    return {
        "problems": problems,
    }


def execute_search_user_problems(
    *, db_path: str, telegram_user_id: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    query = _parse_query_argument(arguments)
    return {
        "query": query,
        "problems": search_problems(db_path, telegram_user_id, query),
    }
