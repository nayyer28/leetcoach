from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from leetcoach.app.application.problems.problem_refs import format_problem_ref
from leetcoach.app.infrastructure.config.db import get_connection
from leetcoach.app.infrastructure.dao.problems_dao import update_problem_metadata
from leetcoach.app.infrastructure.dao.user_problems_dao import (
    get_user_problem_detail_by_display_id,
    update_user_problem_metadata,
)
from leetcoach.app.infrastructure.dao.users_dao import get_user_id_by_telegram_user_id


@dataclass(frozen=True)
class EditProblemResult:
    status: str  # ok | user_not_registered | not_found | invalid_field
    problem_ref: str | None = None


def edit_problem_field(
    *,
    db_path: str,
    telegram_user_id: str,
    display_id: int,
    field: str,
    value: str | None,
) -> EditProblemResult:
    now_iso = datetime.now(UTC).isoformat()
    with get_connection(db_path) as conn:
        user_id = get_user_id_by_telegram_user_id(
            conn, telegram_user_id=telegram_user_id
        )
        if user_id is None:
            return EditProblemResult(status="user_not_registered")

        detail = get_user_problem_detail_by_display_id(
            conn, user_id=user_id, display_id=display_id
        )
        if detail is None:
            return EditProblemResult(status="not_found")

        user_problem_id = int(detail["user_problem_id"])
        problem_id = int(detail["problem_id"])
        ok = False

        if field == "title":
            ok = update_problem_metadata(
                conn, problem_id=problem_id, title=value, now_iso=now_iso
            )
        elif field == "difficulty":
            ok = update_problem_metadata(
                conn, problem_id=problem_id, difficulty=value, now_iso=now_iso
            )
        elif field == "leetcode_slug":
            ok = update_problem_metadata(
                conn, problem_id=problem_id, leetcode_slug=value, now_iso=now_iso
            )
        elif field == "neetcode_slug":
            ok = update_problem_metadata(
                conn, problem_id=problem_id, neetcode_slug=value, now_iso=now_iso
            )
        elif field == "pattern":
            ok = update_user_problem_metadata(
                conn,
                user_id=user_id,
                user_problem_id=user_problem_id,
                pattern=value,
                now_iso=now_iso,
            )
        elif field == "concepts":
            ok = update_user_problem_metadata(
                conn,
                user_id=user_id,
                user_problem_id=user_problem_id,
                concepts=value,
                now_iso=now_iso,
            )
        elif field == "time_complexity":
            ok = update_user_problem_metadata(
                conn,
                user_id=user_id,
                user_problem_id=user_problem_id,
                time_complexity=value,
                now_iso=now_iso,
            )
        elif field == "space_complexity":
            ok = update_user_problem_metadata(
                conn,
                user_id=user_id,
                user_problem_id=user_problem_id,
                space_complexity=value,
                now_iso=now_iso,
            )
        elif field == "notes":
            ok = update_user_problem_metadata(
                conn,
                user_id=user_id,
                user_problem_id=user_problem_id,
                notes=value,
                now_iso=now_iso,
            )
        else:
            return EditProblemResult(status="invalid_field")

        if ok:
            conn.commit()
            return EditProblemResult(
                status="ok", problem_ref=format_problem_ref(display_id)
            )
        return EditProblemResult(status="not_found")
