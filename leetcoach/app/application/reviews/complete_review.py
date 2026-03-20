from __future__ import annotations

from datetime import UTC, datetime

from leetcoach.app.infrastructure.config.db import get_connection
from leetcoach.app.infrastructure.dao.review_queue_dao import mark_reviewed
from leetcoach.app.infrastructure.dao.users_dao import get_user_id_by_telegram_user_id


def complete_review(db_path: str, telegram_user_id: str, user_problem_id: int) -> bool:
    now_iso = datetime.now(UTC).isoformat()
    with get_connection(db_path) as conn:
        user_id = get_user_id_by_telegram_user_id(
            conn, telegram_user_id=telegram_user_id
        )
        if user_id is None:
            return False
        ok = mark_reviewed(
            conn,
            user_id=user_id,
            user_problem_id=user_problem_id,
            reviewed_at=now_iso,
        )
        if ok:
            conn.commit()
        return ok
