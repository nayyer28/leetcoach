from __future__ import annotations

from datetime import date

from leetcoach.app.application.problems.problem_refs import format_problem_ref
from leetcoach.app.infrastructure.config.db import get_connection
from leetcoach.app.infrastructure.dao.user_problems_dao import (
    get_user_problem_detail_by_display_id,
    get_user_problem_detail,
    list_recent_user_problems,
    list_user_problems,
    list_user_problems_by_pattern,
    query_user_problems as query_user_problems_rows,
    resolve_user_problem_id_by_display_id,
    search_user_problems,
)
from leetcoach.app.infrastructure.dao.users_dao import get_user_id_by_telegram_user_id


def _get_user_id(db_path: str, telegram_user_id: str) -> int | None:
    with get_connection(db_path) as conn:
        return get_user_id_by_telegram_user_id(conn, telegram_user_id=telegram_user_id)


def _serialize_problem_row(row) -> dict[str, str]:
    keys = set(row.keys())

    def _optional(key: str) -> str:
        if key not in keys or row[key] is None:
            return ""
        return str(row[key])

    return {
        "user_problem_id": int(row["user_problem_id"]),
        "display_id": int(row["display_id"]),
        "problem_ref": format_problem_ref(int(row["display_id"])),
        "title": str(row["title"]),
        "difficulty": str(row["difficulty"]),
        "pattern": str(row["pattern"]),
        "solved_at": str(row["solved_at"]),
        "leetcode_slug": _optional("leetcode_slug"),
        "neetcode_slug": _optional("neetcode_slug"),
        "concepts": _optional("concepts"),
        "time_complexity": _optional("time_complexity"),
        "space_complexity": _optional("space_complexity"),
        "notes": _optional("notes"),
        "created_at": _optional("created_at"),
        "updated_at": _optional("updated_at"),
    }


def search_problems(db_path: str, telegram_user_id: str, query: str) -> list[dict[str, str]]:
    with get_connection(db_path) as conn:
        user_id = get_user_id_by_telegram_user_id(
            conn, telegram_user_id=telegram_user_id
        )
        if user_id is None:
            return []
        rows = search_user_problems(conn, user_id=user_id, query=query)
    return [_serialize_problem_row(r) for r in rows]


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
    return [_serialize_problem_row(r) for r in rows]


def list_all_problems(db_path: str, telegram_user_id: str) -> list[dict[str, str]]:
    with get_connection(db_path) as conn:
        user_id = get_user_id_by_telegram_user_id(
            conn, telegram_user_id=telegram_user_id
        )
        if user_id is None:
            return []
        rows = list_user_problems(conn, user_id=user_id, limit=100)
    return [_serialize_problem_row(r) for r in rows]


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
    return [_serialize_problem_row(r) for r in reversed(rows)]


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
        **_serialize_problem_row(row),
    }


def get_problem_detail_by_ref(
    db_path: str, telegram_user_id: str, display_id: int
) -> dict[str, str] | None:
    with get_connection(db_path) as conn:
        user_id = get_user_id_by_telegram_user_id(
            conn, telegram_user_id=telegram_user_id
        )
        if user_id is None:
            return None
        row = get_user_problem_detail_by_display_id(
            conn, user_id=user_id, display_id=display_id
        )
    if row is None:
        return None
    return {
        **_serialize_problem_row(row),
        "problem_id": int(row["problem_id"]),
    }


def resolve_problem_id_by_ref(
    db_path: str, telegram_user_id: str, display_id: int
) -> int | None:
    with get_connection(db_path) as conn:
        user_id = get_user_id_by_telegram_user_id(
            conn, telegram_user_id=telegram_user_id
        )
        if user_id is None:
            return None
        return resolve_user_problem_id_by_display_id(
            conn, user_id=user_id, display_id=display_id
        )


def query_problems(
    db_path: str,
    telegram_user_id: str,
    *,
    display_id: int | None = None,
    difficulty: str | None = None,
    pattern: str | None = None,
    text_query: str | None = None,
    solved_date_from: date | None = None,
    solved_date_to: date | None = None,
    order_by: str = "solved_at_desc",
    limit: int = 10,
) -> list[dict[str, str]]:
    with get_connection(db_path) as conn:
        user_id = get_user_id_by_telegram_user_id(
            conn, telegram_user_id=telegram_user_id
        )
        if user_id is None:
            return []
        rows = query_user_problems_rows(
            conn,
            user_id=user_id,
            display_id=display_id,
            difficulty=difficulty,
            pattern=pattern,
            text_query=text_query,
            solved_date_from=solved_date_from.isoformat() if solved_date_from else None,
            solved_date_to=solved_date_to.isoformat() if solved_date_to else None,
            order_by=order_by,
            limit=limit,
        )
    return [_serialize_problem_row(r) for r in rows]
