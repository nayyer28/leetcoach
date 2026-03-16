from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from leetcoach.config import AppConfig
from leetcoach.db.connection import get_connection
from leetcoach.db.migrate import migrate_database
from leetcoach.services.log_problem_service import LogProblemInput, log_problem
from leetcoach.telegram_bot import remind_command


def _context(*, db_path: str, args: list[str]) -> SimpleNamespace:
    return SimpleNamespace(
        args=args,
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


def _update() -> SimpleNamespace:
    return SimpleNamespace(
        message=SimpleNamespace(reply_text=AsyncMock()),
        effective_user=SimpleNamespace(id="u-1"),
    )


class TelegramBotReminderCommandsUnitTest(unittest.IsolatedAsyncioTestCase):
    async def test_remind_without_args_shows_effective_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "leetcoach-test.db")
            migrate_database(db_path)
            with get_connection(db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO users (
                        telegram_user_id, telegram_chat_id, timezone, reminder_daily_max,
                        reminder_hour_local, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "u-1",
                        "chat-1",
                        "UTC",
                        3,
                        11,
                        "2026-03-16T10:00:00+00:00",
                        "2026-03-16T10:00:00+00:00",
                    ),
                )
                conn.commit()

            update = _update()
            context = _context(db_path=db_path, args=[])

            await remind_command(update, context)

            update.message.reply_text.assert_awaited_once()
            text = update.message.reply_text.await_args.args[0]
            self.assertIn("Daily reminder count: 3", text)
            self.assertIn("Reminder hour: 11:00", text)

    async def test_remind_count_updates_setting(self) -> None:
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

            update = _update()
            context = _context(db_path=db_path, args=["count", "4"])

            await remind_command(update, context)

            self.assertIn(
                "Updated daily reminder count to 4",
                update.message.reply_text.await_args.args[0],
            )
            with get_connection(db_path) as conn:
                row = conn.execute(
                    "SELECT reminder_daily_max FROM users WHERE telegram_user_id = ?",
                    ("u-1",),
                ).fetchone()
                self.assertEqual(int(row["reminder_daily_max"]), 4)

    async def test_remind_time_updates_setting(self) -> None:
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

            update = _update()
            context = _context(db_path=db_path, args=["time", "13"])

            await remind_command(update, context)

            self.assertIn(
                "Updated reminder hour to 13:00",
                update.message.reply_text.await_args.args[0],
            )
            with get_connection(db_path) as conn:
                row = conn.execute(
                    "SELECT reminder_hour_local FROM users WHERE telegram_user_id = ?",
                    ("u-1",),
                ).fetchone()
                self.assertEqual(int(row["reminder_hour_local"]), 13)

    async def test_remind_last_shows_latest_batch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "leetcoach-test.db")
            migrate_database(db_path)
            log_problem(
                db_path,
                LogProblemInput(
                    telegram_user_id="u-1",
                    telegram_chat_id="chat-1",
                    timezone="UTC",
                    title="Two Sum",
                    difficulty="easy",
                    leetcode_slug="two-sum",
                    neetcode_slug="two-sum",
                    pattern="arrays",
                    solved_at="2026-03-01T10:00:00+00:00",
                    notes="",
                ),
            )
            with get_connection(db_path) as conn:
                conn.execute(
                    "UPDATE problem_reviews SET last_reminded_at = ?, updated_at = ?",
                    ("2026-03-16T09:00:00+00:00", "2026-03-16T09:00:00+00:00"),
                )
                conn.commit()

            update = _update()
            context = _context(db_path=db_path, args=["last"])

            await remind_command(update, context)

            text = update.message.reply_text.await_args.args[0]
            self.assertIn("Last Reminder Batch", text)
            self.assertIn("Two Sum", text)

    async def test_remind_new_sends_one_extra_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "leetcoach-test.db")
            migrate_database(db_path)
            log_problem(
                db_path,
                LogProblemInput(
                    telegram_user_id="u-1",
                    telegram_chat_id="chat-1",
                    timezone="UTC",
                    title="Two Sum",
                    difficulty="easy",
                    leetcode_slug="two-sum",
                    neetcode_slug="two-sum",
                    pattern="arrays",
                    solved_at="2026-03-01T10:00:00+00:00",
                    notes="",
                ),
            )

            update = _update()
            context = _context(db_path=db_path, args=["new"])

            await remind_command(update, context)

            text = update.message.reply_text.await_args.args[0]
            self.assertIn("Manual Reminder", text)
            self.assertIn("Two Sum", text)
            with get_connection(db_path) as conn:
                row = conn.execute(
                    "SELECT last_reminded_at FROM problem_reviews WHERE review_day = 7"
                ).fetchone()
                self.assertIsNotNone(row["last_reminded_at"])


if __name__ == "__main__":
    unittest.main()
