from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from leetcoach.app.application.problems.problem_refs import format_problem_ref
from leetcoach.app.infrastructure.config.db import get_connection
from leetcoach.app.infrastructure.dao.problems_dao import upsert_problem
from leetcoach.app.infrastructure.dao.review_queue_dao import ensure_review_queue_state
from leetcoach.app.infrastructure.dao.user_problems_dao import (
    get_user_problem_detail,
    upsert_user_problem,
)
from leetcoach.app.infrastructure.dao.users_dao import upsert_user


@dataclass(frozen=True)
class LogProblemInput:
    telegram_user_id: str
    telegram_chat_id: str
    timezone: str
    title: str
    difficulty: str
    leetcode_slug: str | None
    neetcode_slug: str
    pattern: str
    solved_at: str
    concepts: str | None = None
    time_complexity: str | None = None
    space_complexity: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class LogProblemResult:
    user_id: int
    problem_id: int
    user_problem_id: int
    display_id: int
    problem_ref: str


def log_problem(db_path: str, payload: LogProblemInput) -> LogProblemResult:
    now_iso = datetime.now(UTC).isoformat()
    with get_connection(db_path) as conn:
        user_id = upsert_user(
            conn,
            telegram_user_id=payload.telegram_user_id,
            telegram_chat_id=payload.telegram_chat_id,
            timezone=payload.timezone,
            now_iso=now_iso,
        )
        problem_id = upsert_problem(
            conn,
            title=payload.title,
            difficulty=payload.difficulty,
            leetcode_slug=payload.leetcode_slug,
            neetcode_slug=payload.neetcode_slug,
            now_iso=now_iso,
        )
        user_problem_id = upsert_user_problem(
            conn,
            user_id=user_id,
            problem_id=problem_id,
            pattern=payload.pattern,
            solved_at=payload.solved_at,
            concepts=payload.concepts,
            time_complexity=payload.time_complexity,
            space_complexity=payload.space_complexity,
            notes=payload.notes,
            now_iso=now_iso,
        )
        ensure_review_queue_state(
            conn,
            user_id=user_id,
            user_problem_id=user_problem_id,
            now_iso=now_iso,
        )
        conn.commit()
        detail = get_user_problem_detail(
            conn, user_id=user_id, user_problem_id=user_problem_id
        )
        if detail is None:
            raise RuntimeError("Failed to load user problem detail after log")
        display_id = int(detail["display_id"])
    return LogProblemResult(
        user_id=user_id,
        problem_id=problem_id,
        user_problem_id=user_problem_id,
        display_id=display_id,
        problem_ref=format_problem_ref(display_id),
    )
