from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

@dataclass(frozen=True)
class ProblemToken:
    user_problem_id: int


class DueTokenStore:
    def __init__(self) -> None:
        self._store: dict[str, tuple[datetime, dict[str, ProblemToken]]] = {}

    def put(self, telegram_user_id: str, user_problem_ids: list[int]) -> dict[str, ProblemToken]:
        expires = datetime.now(UTC) + timedelta(hours=4)
        mapping: dict[str, ProblemToken] = {}
        for idx, user_problem_id in enumerate(user_problem_ids, start=1):
            token = f"A{idx}"
            mapping[token] = ProblemToken(user_problem_id=user_problem_id)
        self._store[telegram_user_id] = (expires, mapping)
        return mapping

    def get(self, telegram_user_id: str, token: str) -> ProblemToken | None:
        value = self._store.get(telegram_user_id)
        if value is None:
            return None
        expires, mapping = value
        if datetime.now(UTC) > expires:
            del self._store[telegram_user_id]
            return None
        return mapping.get(token.upper())
