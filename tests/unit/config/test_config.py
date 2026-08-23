from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from leetcoach.app.infrastructure.config.app_config import load_config


class ConfigUnitTest(unittest.TestCase):
    def test_parse_allowed_user_ids_from_csv(self) -> None:
        with patch.dict(
            os.environ,
            {"LEETCOACH_ALLOWED_USER_IDS": "12345, 67890 ,,  "},
            clear=False,
        ):
            cfg = load_config()
        self.assertEqual(cfg.allowed_user_ids, frozenset({"12345", "67890"}))

    def test_parse_allowed_user_ids_defaults_to_open(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            cfg = load_config()
        self.assertEqual(cfg.allowed_user_ids, frozenset())

    def test_reminder_hour_is_clamped_to_valid_range(self) -> None:
        with patch.dict(
            os.environ,
            {"LEETCOACH_REMINDER_HOUR_LOCAL": "99"},
            clear=False,
        ):
            cfg = load_config()
        self.assertEqual(cfg.reminder_hour_local, 23)


if __name__ == "__main__":
    unittest.main()
