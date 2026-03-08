from __future__ import annotations

from datetime import UTC, datetime, timedelta
import unittest

from leetcoach.services.due_tokens import DueTokenStore
from leetcoach.services.query_service import DueReviewItem


class DueTokenStoreTest(unittest.TestCase):
    def test_put_and_get_case_insensitive_tokens(self) -> None:
        store = DueTokenStore()
        items = [
            DueReviewItem(
                user_problem_id=10,
                review_day=7,
                title="A",
                leetcode_slug="a",
                neetcode_slug=None,
                due_at="2026-01-01T00:00:00+00:00",
                buffer_until="2026-01-03T00:00:00+00:00",
                status="pending",
            ),
            DueReviewItem(
                user_problem_id=11,
                review_day=21,
                title="B",
                leetcode_slug="b",
                neetcode_slug=None,
                due_at="2026-01-01T00:00:00+00:00",
                buffer_until="2026-01-03T00:00:00+00:00",
                status="pending",
            ),
        ]

        mapping = store.put("u-1", items)
        self.assertEqual(set(mapping.keys()), {"A1", "A2"})
        self.assertIsNotNone(store.get("u-1", "A1"))
        self.assertIsNotNone(store.get("u-1", "a2"))

    def test_expired_token_set_returns_none(self) -> None:
        store = DueTokenStore()
        items = [
            DueReviewItem(
                user_problem_id=10,
                review_day=7,
                title="A",
                leetcode_slug="a",
                neetcode_slug=None,
                due_at="2026-01-01T00:00:00+00:00",
                buffer_until="2026-01-03T00:00:00+00:00",
                status="pending",
            )
        ]
        store.put("u-1", items)

        # Simulate expiration by overriding internal expiry timestamp.
        mapping = store._store["u-1"][1]  # noqa: SLF001 - intentional white-box test
        store._store["u-1"] = (datetime.now(UTC) - timedelta(seconds=1), mapping)  # noqa: SLF001

        self.assertIsNone(store.get("u-1", "A1"))


if __name__ == "__main__":
    unittest.main()

