from __future__ import annotations

from datetime import UTC, datetime, timedelta
import unittest

from leetcoach.services.due_tokens import DueTokenStore


class DueTokenStoreTest(unittest.TestCase):
    def test_put_and_get_case_insensitive_tokens(self) -> None:
        store = DueTokenStore()
        mapping = store.put("u-1", [10, 11])
        self.assertEqual(set(mapping.keys()), {"A1", "A2"})
        self.assertIsNotNone(store.get("u-1", "A1"))
        self.assertIsNotNone(store.get("u-1", "a2"))

    def test_expired_token_set_returns_none(self) -> None:
        store = DueTokenStore()
        store.put("u-1", [10])

        # Simulate expiration by overriding internal expiry timestamp.
        mapping = store._store["u-1"][1]  # noqa: SLF001 - intentional white-box test
        store._store["u-1"] = (datetime.now(UTC) - timedelta(seconds=1), mapping)  # noqa: SLF001

        self.assertIsNone(store.get("u-1", "A1"))


if __name__ == "__main__":
    unittest.main()
