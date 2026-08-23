from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from telegram.ext import ConversationHandler

from leetcoach.app.infrastructure.config.app_config import AppConfig
from leetcoach.app.infrastructure.config.db import get_connection
from leetcoach.app.misc.migrate import migrate_database
from leetcoach.app.application.problems.log_problem import LogProblemInput, log_problem
from leetcoach.app.interface.bot.handlers import (
    REMIND_SCHEDULE_MODE,
    REMIND_SCHEDULE_REVIEW,
    REMIND_SCHEDULE_TIME,
    remind_command,
    remind_schedule_mode_callback,
    remind_schedule_review_callback,
    remind_schedule_time,
)


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
        callback_query=None,
    )


def _callback_update(data: str) -> SimpleNamespace:
    """An update carrying an inline-button press, as the schedule flow sees it."""
    return SimpleNamespace(
        message=None,
        effective_user=SimpleNamespace(id="u-1"),
        callback_query=SimpleNamespace(
            data=data,
            answer=AsyncMock(),
            edit_message_reply_markup=AsyncMock(),
            message=SimpleNamespace(reply_text=AsyncMock()),
        ),
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

    async def test_remind_schedule_start_flow_saves_hour_and_resumes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "leetcoach-test.db")
            migrate_database(db_path)
            _insert_user(db_path, reminders_paused=1)

            context = _context(db_path=db_path, args=["schedule"])

            entry = _update()
            state = await remind_command(entry, context)
            self.assertEqual(state, REMIND_SCHEDULE_MODE)

            mode = _callback_update("remind:mode:start")
            state = await remind_schedule_mode_callback(mode, context)
            self.assertEqual(state, REMIND_SCHEDULE_TIME)

            time_update = _update()
            time_update.message.text = "13"
            state = await remind_schedule_time(time_update, context)
            self.assertEqual(state, REMIND_SCHEDULE_REVIEW)

            # The draft is shown before anything is written.
            draft_text = time_update.message.reply_text.await_args.args[0]
            self.assertIn("Review Reminder Schedule", draft_text)
            self.assertIn("stopped", draft_text)
            self.assertIn("13:00", draft_text)
            with get_connection(db_path) as conn:
                row = conn.execute(
                    "SELECT reminders_paused FROM users WHERE telegram_user_id = ?",
                    ("u-1",),
                ).fetchone()
                self.assertEqual(int(row["reminders_paused"]), 1)

            save = _callback_update("remind:review:save")
            await remind_schedule_review_callback(save, context)

            with get_connection(db_path) as conn:
                row = conn.execute(
                    """
                    SELECT reminders_paused, reminder_hour_local
                    FROM users WHERE telegram_user_id = ?
                    """,
                    ("u-1",),
                ).fetchone()
                self.assertEqual(int(row["reminders_paused"]), 0)
                self.assertEqual(int(row["reminder_hour_local"]), 13)

    async def test_remind_schedule_stop_flow_pauses_without_asking_time(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "leetcoach-test.db")
            migrate_database(db_path)
            _insert_user(db_path)

            context = _context(db_path=db_path, args=["schedule"])
            await remind_command(_update(), context)

            mode = _callback_update("remind:mode:stop")
            state = await remind_schedule_mode_callback(mode, context)
            # Stopping skips the time question and goes straight to the draft.
            self.assertEqual(state, REMIND_SCHEDULE_REVIEW)

            save = _callback_update("remind:review:save")
            await remind_schedule_review_callback(save, context)

            with get_connection(db_path) as conn:
                row = conn.execute(
                    "SELECT reminders_paused FROM users WHERE telegram_user_id = ?",
                    ("u-1",),
                ).fetchone()
                self.assertEqual(int(row["reminders_paused"]), 1)

    async def test_remind_schedule_stop_keeps_inherited_hour_null(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "leetcoach-test.db")
            migrate_database(db_path)
            _insert_user(db_path)  # reminder_hour_local stays NULL

            context = _context(db_path=db_path, args=["schedule"])
            await remind_command(_update(), context)
            await remind_schedule_mode_callback(
                _callback_update("remind:mode:stop"), context
            )
            await remind_schedule_review_callback(
                _callback_update("remind:review:save"), context
            )

            # Stopping says nothing about the hour. Writing the effective hour here
            # would freeze the app default into a per-user override.
            with get_connection(db_path) as conn:
                row = conn.execute(
                    """
                    SELECT reminders_paused, reminder_hour_local
                    FROM users WHERE telegram_user_id = ?
                    """,
                    ("u-1",),
                ).fetchone()
                self.assertEqual(int(row["reminders_paused"]), 1)
                self.assertIsNone(row["reminder_hour_local"])

    async def test_remind_schedule_refuses_to_open_during_log_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "leetcoach-test.db")
            migrate_database(db_path)
            _insert_user(db_path)

            update = _update()
            context = _context(db_path=db_path, args=["schedule"])
            # A /log form is mid-flight, waiting on a text answer.
            context.user_data["log_payload"] = {}

            state = await remind_command(update, context)

            # Otherwise the hour typed here would be eaten by log_flow as a title.
            self.assertEqual(state, ConversationHandler.END)
            self.assertNotIn("remind_schedule", context.user_data)
            text = update.message.reply_text.await_args.args[0]
            self.assertIn("/log", text)
            self.assertIn("/cancel", text)

    async def test_remind_schedule_cancel_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "leetcoach-test.db")
            migrate_database(db_path)
            _insert_user(db_path)

            context = _context(db_path=db_path, args=["schedule"])
            await remind_command(_update(), context)

            mode = _callback_update("remind:mode:stop")
            await remind_schedule_mode_callback(mode, context)

            cancel = _callback_update("remind:review:cancel")
            await remind_schedule_review_callback(cancel, context)

            self.assertIn(
                "unchanged",
                cancel.callback_query.message.reply_text.await_args.args[0],
            )
            with get_connection(db_path) as conn:
                row = conn.execute(
                    "SELECT reminders_paused FROM users WHERE telegram_user_id = ?",
                    ("u-1",),
                ).fetchone()
                self.assertEqual(int(row["reminders_paused"]), 0)

    async def test_remind_schedule_rejects_out_of_range_hour(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "leetcoach-test.db")
            migrate_database(db_path)
            _insert_user(db_path)

            context = _context(db_path=db_path, args=["schedule"])
            await remind_command(_update(), context)
            await remind_schedule_mode_callback(
                _callback_update("remind:mode:start"), context
            )

            for bad in ("99", "not-a-number"):
                update = _update()
                update.message.text = bad
                state = await remind_schedule_time(update, context)
                # Stays on the question rather than advancing to the draft.
                self.assertEqual(state, REMIND_SCHEDULE_TIME)
                self.assertIn("⚠️", update.message.reply_text.await_args.args[0])

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

    async def test_remind_unknown_action_shows_usage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "leetcoach-test.db")
            migrate_database(db_path)
            _insert_user(db_path)

            update = _update()
            # "stop" was a top-level action before; it now lives inside
            # /remind schedule, so it should fall through to usage help.
            context = _context(db_path=db_path, args=["stop"])

            await remind_command(update, context)

            text = update.message.reply_text.await_args.args[0]
            self.assertIn("/remind now", text)
            self.assertIn("/remind schedule", text)
            with get_connection(db_path) as conn:
                row = conn.execute(
                    "SELECT reminders_paused FROM users WHERE telegram_user_id = ?",
                    ("u-1",),
                ).fetchone()
                self.assertEqual(int(row["reminders_paused"]), 0)

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
            self.assertIn("/remind schedule", text)

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
