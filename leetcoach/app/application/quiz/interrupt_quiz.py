from __future__ import annotations

from datetime import UTC, datetime

from leetcoach.app.infrastructure.config.db import get_connection
from leetcoach.app.infrastructure.dao.active_quiz_sessions_dao import (
    close_quiz_session,
    get_active_quiz_session_by_user_id,
)
from leetcoach.app.infrastructure.dao.users_dao import get_user_id_by_telegram_user_id


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _user_id_or_none(db_path: str, telegram_user_id: str) -> int | None:
    with get_connection(db_path) as conn:
        return get_user_id_by_telegram_user_id(conn, telegram_user_id=telegram_user_id)


def interrupt_active_quiz(*, db_path: str, telegram_user_id: str) -> bool:
    user_id = _user_id_or_none(db_path, telegram_user_id)
    if user_id is None:
        return False

    now_iso = _now_iso()
    with get_connection(db_path) as conn:
        row = get_active_quiz_session_by_user_id(conn, user_id=user_id)
        if row is None or str(row["status"]) not in {"asked", "answered", "revealed"}:
            return False
        closed = close_quiz_session(
            conn,
            user_id=user_id,
            closed_at=now_iso,
            expires_at=now_iso,
            now_iso=now_iso,
        )
        if closed:
            conn.commit()
        return closed
