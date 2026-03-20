from __future__ import annotations

from leetcoach.app.infrastructure.config.db import get_connection
from leetcoach.app.infrastructure.dao.user_problems_dao import (
    get_user_problem_detail,
    list_recent_user_problems,
    list_user_problems,
    list_user_problems_by_pattern,
    search_user_problems,
)
from leetcoach.app.infrastructure.dao.users_dao import get_user_id_by_telegram_user_id


def _get_user_id(db_path: str, telegram_user_id: str) -> int | None:
    with get_connection(db_path) as conn:
        return get_user_id_by_telegram_user_id(conn, telegram_user_id=telegram_user_id)


def search_problems(db_path: str, telegram_user_id: str, query: str) -> list[dict[str, str]]:
    with get_connection(db_path) as conn:
        user_id = get_user_id_by_telegram_user_id(
            conn, telegram_user_id=telegram_user_id
        )
        if user_id is None:
            return []
        rows = search_user_problems(conn, user_id=user_id, query=query)
    return [
        {
            "user_problem_id": int(r["user_problem_id"]),
            "title": str(r["title"]),
            "difficulty": str(r["difficulty"]),
            "pattern": str(r["pattern"]),
            "solved_at": str(r["solved_at"]),
            "leetcode_slug": str(r["leetcode_slug"]) if r["leetcode_slug"] else "",
            "neetcode_slug": str(r["neetcode_slug"]) if r["neetcode_slug"] else "",
        }
        for r in rows
    ]


def list_by_pattern(
    db_path: str, telegram_user_id: str, pattern: str
) -> list[dict[str, str]]:
    with get_connection(db_path) as conn:
        user_id = get_user_id_by_telegram_user_id(
            conn, telegram_user_id=telegram_user_id
        )
        if user_id is None:
            return []
        rows = list_user_problems_by_pattern(conn, user_id=user_id, pattern=pattern)
    return [
        {
            "user_problem_id": int(r["user_problem_id"]),
            "title": str(r["title"]),
            "difficulty": str(r["difficulty"]),
            "pattern": str(r["pattern"]),
            "solved_at": str(r["solved_at"]),
            "leetcode_slug": str(r["leetcode_slug"]) if r["leetcode_slug"] else "",
            "neetcode_slug": str(r["neetcode_slug"]) if r["neetcode_slug"] else "",
        }
        for r in rows
    ]


def list_all_problems(db_path: str, telegram_user_id: str) -> list[dict[str, str]]:
    with get_connection(db_path) as conn:
        user_id = get_user_id_by_telegram_user_id(
            conn, telegram_user_id=telegram_user_id
        )
        if user_id is None:
            return []
        rows = list_user_problems(conn, user_id=user_id, limit=100)
    return [
        {
            "user_problem_id": int(r["user_problem_id"]),
            "title": str(r["title"]),
            "difficulty": str(r["difficulty"]),
            "pattern": str(r["pattern"]),
            "solved_at": str(r["solved_at"]),
            "leetcode_slug": str(r["leetcode_slug"]) if r["leetcode_slug"] else "",
            "neetcode_slug": str(r["neetcode_slug"]) if r["neetcode_slug"] else "",
        }
        for r in rows
    ]


def list_recent_problems(
    db_path: str, telegram_user_id: str, limit: int = 1
) -> list[dict[str, str]]:
    with get_connection(db_path) as conn:
        user_id = get_user_id_by_telegram_user_id(
            conn, telegram_user_id=telegram_user_id
        )
        if user_id is None:
            return []
        rows = list_recent_user_problems(conn, user_id=user_id, limit=limit)
    return [
        {
            "user_problem_id": int(r["user_problem_id"]),
            "title": str(r["title"]),
            "difficulty": str(r["difficulty"]),
            "pattern": str(r["pattern"]),
            "solved_at": str(r["solved_at"]),
            "leetcode_slug": str(r["leetcode_slug"]) if r["leetcode_slug"] else "",
            "neetcode_slug": str(r["neetcode_slug"]) if r["neetcode_slug"] else "",
        }
        for r in reversed(rows)
    ]


def get_problem_detail(
    db_path: str, telegram_user_id: str, user_problem_id: int
) -> dict[str, str] | None:
    with get_connection(db_path) as conn:
        user_id = get_user_id_by_telegram_user_id(
            conn, telegram_user_id=telegram_user_id
        )
        if user_id is None:
            return None
        row = get_user_problem_detail(
            conn, user_id=user_id, user_problem_id=user_problem_id
        )
    if row is None:
        return None
    return {
        "user_problem_id": str(row["user_problem_id"]),
        "title": str(row["title"]),
        "difficulty": str(row["difficulty"]),
        "pattern": str(row["pattern"]),
        "solved_at": str(row["solved_at"]),
        "leetcode_slug": str(row["leetcode_slug"]) if row["leetcode_slug"] else "",
        "neetcode_slug": str(row["neetcode_slug"]) if row["neetcode_slug"] else "",
        "concepts": str(row["concepts"]) if row["concepts"] else "",
        "time_complexity": (
            str(row["time_complexity"]) if row["time_complexity"] else ""
        ),
        "space_complexity": (
            str(row["space_complexity"]) if row["space_complexity"] else ""
        ),
        "notes": str(row["notes"]) if row["notes"] else "",
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
    }
