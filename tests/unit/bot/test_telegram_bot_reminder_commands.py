from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from leetcoach.app.infrastructure.config.app_config import AppConfig
from leetcoach.app.infrastructure.config.db import get_connection
from leetcoach.app.misc.migrate import migrate_database
from leetcoach.app.application.problems.log_problem import LogProblemInput, log_problem
from leetcoach.app.interface.bot.handlers import remind_command


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
                )
            }
        ),
    )


def _update() -> SimpleNamespace:
    return SimpleNamespace(
        message=SimpleNamespace(reply_text=AsyncMock()),
        effective_user=SimpleNamespace(id="u-1"),
    )


def _insert_user(db_path: str, *, reminders_paused: int = 0) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO users (
                telegram_user_id, telegram_chat_id, timezone, reminders_paused,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "u-1",
                "chat-1",
                "UTC",
                reminders_paused,
                "2026-03-16T10:00:00+00:00",
                "2026-03-16T10:00:00+00:00",
            ),
        )
        conn.commit()


class TelegramBotReminderCommandsUnitTest(unittest.IsolatedAsyncioTestCase):
    async def test_remind_without_args_shows_effective_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "leetcoach-test.db")
            migrate_database(db_path)
            with get_connection(db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO users (
                        telegram_user_id, telegram_chat_id, timezone,
                        reminder_hour_local, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "u-1",
                        "chat-1",
                        "UTC",
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
            self.assertIn("<b>Reminder hour:</b> 11:00", text)

    async def test_remind_time_updates_setting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "leetcoach-test.db")
            migrate_database(db_path)
            _insert_user(db_path)

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

    async def test_remind_new_sends_top_of_queue_without_bumping_review_count(
        self,
    ) -> None:
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
            self.assertIn("ID: P1", text)
            self.assertIn("Two Sum", text)

            # The reminder body is plain text. Sending it as HTML made Telegram
            # reject the message ("unsupported start tag"), so no parse_mode here.
            self.assertIsNone(
                update.message.reply_text.await_args.kwargs.get("parse_mode")
            )

            # Manual /remind new is display-only: it stamps last_reminded_at for
            # daily de-dupe but leaves review_count alone. Only /reviewed <id>
            # advances the queue.
            with get_connection(db_path) as conn:
                up_row = conn.execute(
                    "SELECT review_count FROM user_problems"
                ).fetchone()
                self.assertEqual(int(up_row["review_count"]), 0)
                user_row = conn.execute(
                    "SELECT last_reminded_at FROM users WHERE telegram_user_id = ?",
                    ("u-1",),
                ).fetchone()
                self.assertIsNotNone(user_row["last_reminded_at"])

    async def test_remind_new_reports_empty_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "leetcoach-test.db")
            migrate_database(db_path)
            _insert_user(db_path)

            update = _update()
            context = _context(db_path=db_path, args=["new"])

            await remind_command(update, context)

            text = update.message.reply_text.await_args.args[0]
            self.assertIn("empty", text.lower())

    async def test_remind_stop_pauses_reminders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "leetcoach-test.db")
            migrate_database(db_path)
            _insert_user(db_path)

            update = _update()
            context = _context(db_path=db_path, args=["stop"])

            await remind_command(update, context)

            text = update.message.reply_text.await_args.args[0]
            self.assertIn("Stopped scheduled reminders", text)
            with get_connection(db_path) as conn:
                row = conn.execute(
                    "SELECT reminders_paused FROM users WHERE telegram_user_id = ?",
                    ("u-1",),
                ).fetchone()
                self.assertEqual(int(row["reminders_paused"]), 1)

    async def test_remind_start_resumes_reminders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "leetcoach-test.db")
            migrate_database(db_path)
            _insert_user(db_path, reminders_paused=1)

            update = _update()
            context = _context(db_path=db_path, args=["start"])

            await remind_command(update, context)

            text = update.message.reply_text.await_args.args[0]
            self.assertIn("Resumed scheduled reminders", text)
            with get_connection(db_path) as conn:
                row = conn.execute(
                    "SELECT reminders_paused FROM users WHERE telegram_user_id = ?",
                    ("u-1",),
                ).fetchone()
                self.assertEqual(int(row["reminders_paused"]), 0)

    async def test_remind_stop_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "leetcoach-test.db")
            migrate_database(db_path)
            _insert_user(db_path, reminders_paused=1)

            update = _update()
            context = _context(db_path=db_path, args=["stop"])

            await remind_command(update, context)

            text = update.message.reply_text.await_args.args[0]
            self.assertIn("already stopped", text)
            with get_connection(db_path) as conn:
                row = conn.execute(
                    "SELECT reminders_paused FROM users WHERE telegram_user_id = ?",
                    ("u-1",),
                ).fetchone()
                self.assertEqual(int(row["reminders_paused"]), 1)

    async def test_remind_settings_shows_paused_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "leetcoach-test.db")
            migrate_database(db_path)
            _insert_user(db_path, reminders_paused=1)

            update = _update()
            context = _context(db_path=db_path, args=[])

            await remind_command(update, context)

            text = update.message.reply_text.await_args.args[0]
            self.assertIn("paused", text)
            self.assertIn("/remind start", text)

    async def test_remind_new_still_works_while_paused(self) -> None:
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
                    "UPDATE users SET reminders_paused = 1 WHERE telegram_user_id = ?",
                    ("u-1",),
                )
                conn.commit()

            update = _update()
            context = _context(db_path=db_path, args=["new"])

            await remind_command(update, context)

            text = update.message.reply_text.await_args.args[0]
            self.assertIn("Manual Reminder", text)
            self.assertIn("Two Sum", text)


if __name__ == "__main__":
    unittest.main()
