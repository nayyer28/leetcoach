from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from leetcoach.services.query_service import DueReviewItem


@dataclass(frozen=True)
class ReviewToken:
    user_problem_id: int
    review_day: int


class DueTokenStore:
    def __init__(self) -> None:
        self._store: dict[str, tuple[datetime, dict[str, ReviewToken]]] = {}

    def put(
        self, telegram_user_id: str, items: list[DueReviewItem]
    ) -> dict[str, ReviewToken]:
        expires = datetime.now(UTC) + timedelta(hours=4)
        mapping: dict[str, ReviewToken] = {}
        for idx, item in enumerate(items, start=1):
            token = f"A{idx}"
            mapping[token] = ReviewToken(
                user_problem_id=item.user_problem_id,
                review_day=item.review_day,
            )
        self._store[telegram_user_id] = (expires, mapping)
        return mapping

    def get(self, telegram_user_id: str, token: str) -> ReviewToken | None:
        value = self._store.get(telegram_user_id)
        if value is None:
            return None
        expires, mapping = value
        if datetime.now(UTC) > expires:
            del self._store[telegram_user_id]
            return None
        return mapping.get(token.upper())

