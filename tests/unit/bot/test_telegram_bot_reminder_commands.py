from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from leetcoach.config import AppConfig
from leetcoach.db.connection import get_connection
from leetcoach.db.migrate import migrate_database
from leetcoach.telegram_bot import reminder_command, reminder_count_command


class TelegramBotReminderCommandsUnitTest(unittest.IsolatedAsyncioTestCase):
    async def test_reminder_command_shows_effective_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "leetcoach-test.db")
            migrate_database(db_path)
            with get_connection(db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO users (
                        telegram_user_id, telegram_chat_id, timezone, reminder_daily_max, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "u-1",
                        "chat-1",
                        "UTC",
                        3,
                        "2026-03-16T10:00:00+00:00",
                        "2026-03-16T10:00:00+00:00",
                    ),
                )
                conn.commit()

            message = SimpleNamespace(reply_text=AsyncMock())
            update = SimpleNamespace(
                message=message,
                effective_user=SimpleNamespace(id="u-1"),
            )
            context = SimpleNamespace(
                user_data={},
                application=SimpleNamespace(
                    bot_data={
                        "config": AppConfig(
                            environment="development",
                            log_level="INFO",
                            timezone="UTC",
                            db_path=db_path,
                            telegram_bot_token="token",
                            allowed_user_ids=frozenset(),
                            reminder_hour_local=9,
                            reminder_daily_max=2,
                        )
                    }
                ),
            )

            await reminder_command(update, context)

            message.reply_text.assert_awaited_once()
            text = message.reply_text.await_args.args[0]
            self.assertIn("Daily reminder count: 3", text)
            self.assertIn("Reminder hour: 9:00", text)

    async def test_reminder_count_command_updates_setting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "leetcoach-test.db")
            migrate_database(db_path)
            with get_connection(db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO users (
                        telegram_user_id, telegram_chat_id, timezone, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        "u-1",
                        "chat-1",
                        "UTC",
                        "2026-03-16T10:00:00+00:00",
                        "2026-03-16T10:00:00+00:00",
                    ),
                )
                conn.commit()

            message = SimpleNamespace(reply_text=AsyncMock())
            update = SimpleNamespace(
                message=message,
                effective_user=SimpleNamespace(id="u-1"),
            )
            context = SimpleNamespace(
                args=["4"],
                user_data={},
                application=SimpleNamespace(
                    bot_data={
                        "config": AppConfig(
                            environment="development",
                            log_level="INFO",
                            timezone="UTC",
                            db_path=db_path,
                            telegram_bot_token="token",
                            allowed_user_ids=frozenset(),
                            reminder_hour_local=9,
                            reminder_daily_max=2,
                        )
                    }
                ),
            )

            await reminder_count_command(update, context)

            message.reply_text.assert_awaited_once()
            self.assertIn("Updated daily reminder count to 4", message.reply_text.await_args.args[0])
            with get_connection(db_path) as conn:
                row = conn.execute(
                    "SELECT reminder_daily_max FROM users WHERE telegram_user_id = ?",
                    ("u-1",),
                ).fetchone()
                self.assertEqual(int(row["reminder_daily_max"]), 4)


if __name__ == "__main__":
    unittest.main()
