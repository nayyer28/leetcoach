from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from leetcoach.app.infrastructure.dao.users_dao import (
    get_user_id_by_telegram_user_id,
    get_user_reminder_preferences,
    set_user_reminder_daily_max,
    set_user_reminder_hour_local,
    upsert_user,
)
from leetcoach.app.infrastructure.config.db import get_connection
from leetcoach.app.misc.migrate import migrate_database


class UsersDaoUnitTest(unittest.TestCase):
    def test_upsert_user_updates_existing_row_and_preserves_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "leetcoach-test.db"
            migrate_database(str(db_path))

            with get_connection(str(db_path)) as conn:
                first_id = upsert_user(
                    conn,
                    telegram_user_id="u-1",
                    telegram_chat_id="chat-1",
                    timezone="UTC",
                    now_iso="2026-03-16T10:00:00+00:00",
                )
                second_id = upsert_user(
                    conn,
                    telegram_user_id="u-1",
                    telegram_chat_id="chat-2",
                    timezone="Europe/Berlin",
                    now_iso="2026-03-16T11:00:00+00:00",
                )
                conn.commit()

                self.assertEqual(first_id, second_id)
                self.assertEqual(
                    get_user_id_by_telegram_user_id(
                        conn, telegram_user_id="u-1"
                    ),
                    first_id,
                )
                row = conn.execute(
                    "SELECT telegram_chat_id, timezone FROM users WHERE id = ?",
                    (first_id,),
                ).fetchone()
                self.assertEqual(row["telegram_chat_id"], "chat-2")
                self.assertEqual(row["timezone"], "Europe/Berlin")

    def test_set_and_get_user_reminder_daily_max(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "leetcoach-test.db"
            migrate_database(str(db_path))

            with get_connection(str(db_path)) as conn:
                upsert_user(
                    conn,
                    telegram_user_id="u-1",
                    telegram_chat_id="chat-1",
                    timezone="UTC",
                    now_iso="2026-03-16T10:00:00+00:00",
                )
                updated = set_user_reminder_daily_max(
                    conn,
                    telegram_user_id="u-1",
                    reminder_daily_max=3,
                    now_iso="2026-03-16T10:05:00+00:00",
                )
                conn.commit()
                self.assertTrue(updated)
                row = get_user_reminder_preferences(conn, telegram_user_id="u-1")
                self.assertIsNotNone(row)
                self.assertEqual(int(row["reminder_daily_max"]), 3)

    def test_set_and_get_user_reminder_hour_local(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "leetcoach-test.db"
            migrate_database(str(db_path))

            with get_connection(str(db_path)) as conn:
                upsert_user(
                    conn,
                    telegram_user_id="u-1",
                    telegram_chat_id="chat-1",
                    timezone="UTC",
                    now_iso="2026-03-16T10:00:00+00:00",
                )
                updated = set_user_reminder_hour_local(
                    conn,
                    telegram_user_id="u-1",
                    reminder_hour_local=14,
                    now_iso="2026-03-16T10:05:00+00:00",
                )
                conn.commit()
                self.assertTrue(updated)
                row = get_user_reminder_preferences(conn, telegram_user_id="u-1")
                self.assertIsNotNone(row)
                self.assertEqual(int(row["reminder_hour_local"]), 14)


if __name__ == "__main__":
    unittest.main()
