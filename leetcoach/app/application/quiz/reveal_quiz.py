from __future__ import annotations

from datetime import UTC, datetime, timedelta

from leetcoach.app.application.quiz.common import QUIZ_TTL_HOURS, RevealQuizResult, parse_question_payload
from leetcoach.app.infrastructure.config.db import get_connection
from leetcoach.app.infrastructure.dao.active_quiz_sessions_dao import (
    close_quiz_session,
    get_active_quiz_session_by_user_id,
    mark_quiz_revealed,
)
from leetcoach.app.infrastructure.dao.users_dao import get_user_id_by_telegram_user_id


def _user_id_or_none(db_path: str, telegram_user_id: str) -> int | None:
    with get_connection(db_path) as conn:
        return get_user_id_by_telegram_user_id(conn, telegram_user_id=telegram_user_id)


def reveal_quiz(*, db_path: str, telegram_user_id: str, now_iso_fn) -> RevealQuizResult:
    user_id = _user_id_or_none(db_path, telegram_user_id)
    if user_id is None:
        return RevealQuizResult(status="user_not_registered")

    now_iso = now_iso_fn()
    expires_at = (
        datetime.fromisoformat(now_iso) + timedelta(hours=QUIZ_TTL_HOURS)
    ).isoformat()
    with get_connection(db_path) as conn:
        row = get_active_quiz_session_by_user_id(conn, user_id=user_id)
        if row is None or str(row["status"]) not in {"asked", "answered", "revealed"}:
            return RevealQuizResult(status="no_active_quiz")
        if str(row["expires_at"]) < now_iso:
            closed = close_quiz_session(
                conn,
                user_id=user_id,
                closed_at=now_iso,
                expires_at=now_iso,
                now_iso=now_iso,
            )
            if closed:
                conn.commit()
            return RevealQuizResult(status="expired_quiz")
        question = parse_question_payload(str(row["question_payload_json"]))
        marked = mark_quiz_revealed(
            conn,
            user_id=user_id,
            revealed_at=now_iso,
            expires_at=expires_at,
            now_iso=now_iso,
        )
        if marked:
            conn.commit()
    return RevealQuizResult(status="ok", question=question)


def default_now_iso() -> str:
    return datetime.now(UTC).isoformat()
