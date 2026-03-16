from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile
import unittest

from leetcoach.db.migrate import MIGRATIONS_DIR, migrate_database


class MigrateUnitTest(unittest.TestCase):
    def test_migrate_database_applies_all_migrations_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "leetcoach.db"

            first_result = migrate_database(str(db_path))
            second_result = migrate_database(str(db_path))

            self.assertEqual(first_result, 0)
            self.assertEqual(second_result, 0)

            with sqlite3.connect(db_path) as conn:
                versions = [
                    row[0]
                    for row in conn.execute(
                        "SELECT version FROM schema_migrations ORDER BY version"
                    ).fetchall()
                ]
                user_columns = [
                    row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()
                ]

            expected = [path.name for path in sorted(MIGRATIONS_DIR.glob("*.sql"))]
            self.assertEqual(versions, expected)
            self.assertIn("reminder_daily_max", user_columns)


if __name__ == "__main__":
    unittest.main()
