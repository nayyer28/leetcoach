from __future__ import annotations

import unittest

from leetcoach.app.misc.notion_importer import (
    _extract_page_id,
    _parse_date_to_utc_iso,
    _parse_title_difficulty_date,
)


class NotionImporterUnitTest(unittest.TestCase):
    def test_extract_page_id_from_notion_url(self) -> None:
        page_id = _extract_page_id(
            "https://www.notion.so/NeetCode-150-2f25715dd0d080348fe1f65ac7c4cbae?source=copy_link"
        )
        self.assertEqual(page_id, "2f25715d-d0d0-8034-8fe1-f65ac7c4cbae")

    def test_parse_date_to_utc_iso_with_default_year(self) -> None:
        value = _parse_date_to_utc_iso(
            date_text="24.01", default_year=2026, timezone_name="Europe/Berlin"
        )
        self.assertTrue(value.startswith("2026-01-23T23:00:00+00:00"))

    def test_parse_title_difficulty_date(self) -> None:
        parsed = _parse_title_difficulty_date(
            "1. Invert a Binary Tree (Easy) (24.02.2026)",
            default_year=2026,
            timezone_name="UTC",
        )
        self.assertIsNotNone(parsed)
        title, difficulty, solved_at = parsed or ("", "", "")
        self.assertEqual(title, "Invert a Binary Tree")
        self.assertEqual(difficulty, "easy")
        self.assertTrue(solved_at.startswith("2026-02-24T00:00:00+00:00"))


if __name__ == "__main__":
    unittest.main()
