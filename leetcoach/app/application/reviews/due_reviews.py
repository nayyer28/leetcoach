from __future__ import annotations

from dataclasses import dataclass

from leetcoach.app.infrastructure.config.db import get_connection
from leetcoach.app.infrastructure.dao.review_queue_dao import (
    list_outstanding_reviews_for_user,
)
from leetcoach.app.infrastructure.dao.users_dao import get_user_id_by_telegram_user_id


@dataclass(frozen=True)
class DueReviewItem:
    user_problem_id: int
    title: str
    leetcode_slug: str | None
    neetcode_slug: str | None
    solved_at: str
    review_count: int
    requested_at: str
    last_reviewed_at: str | None
    status: str


def _status_for(*, requested_at: str, last_reviewed_at: str | None) -> str:
    if last_reviewed_at is None:
        return "pending"
    return "pending" if requested_at > last_reviewed_at else "reviewed"


def list_due_reviews(db_path: str, telegram_user_id: str) -> list[DueReviewItem]:
    with get_connection(db_path) as conn:
        user_id = get_user_id_by_telegram_user_id(
            conn, telegram_user_id=telegram_user_id
        )
        if user_id is None:
            return []
        rows = list_outstanding_reviews_for_user(conn, user_id=user_id)
    items: list[DueReviewItem] = []
    for row in rows:
        items.append(
            DueReviewItem(
                user_problem_id=int(row["user_problem_id"]),
                title=str(row["title"]),
                leetcode_slug=(
                    str(row["leetcode_slug"]) if row["leetcode_slug"] else None
                ),
                neetcode_slug=(
                    str(row["neetcode_slug"]) if row["neetcode_slug"] else None
                ),
                solved_at=str(row["solved_at"]),
                review_count=int(row["review_count"]),
                requested_at=str(row["last_review_requested_at"]),
                last_reviewed_at=(
                    str(row["last_reviewed_at"]) if row["last_reviewed_at"] else None
                ),
                status=_status_for(
                    requested_at=str(row["last_review_requested_at"]),
                    last_reviewed_at=(
                        str(row["last_reviewed_at"]) if row["last_reviewed_at"] else None
                    ),
                ),
            )
        )
    return items
