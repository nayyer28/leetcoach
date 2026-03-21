from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from leetcoach.app.infrastructure.config.db import get_connection


class ConnectionUnitTest(unittest.TestCase):
    def test_get_connection_creates_parent_directory_and_enables_foreign_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "nested" / "leetcoach.db"

            with get_connection(str(db_path)) as conn:
                row = conn.execute("PRAGMA foreign_keys;").fetchone()
                self.assertEqual(row[0], 1)
                self.assertEqual(conn.row_factory.__name__, "Row")

            self.assertTrue(db_path.parent.exists())


if __name__ == "__main__":
    unittest.main()
