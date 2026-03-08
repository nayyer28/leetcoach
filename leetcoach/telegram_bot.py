from __future__ import annotations

from datetime import UTC, datetime
import logging
from typing import Any

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from leetcoach.config import AppConfig
from leetcoach.dao.users_dao import upsert_user
from leetcoach.db.connection import get_connection
from leetcoach.services.due_tokens import DueTokenStore, ReviewToken
from leetcoach.services.log_problem_service import LogProblemInput, log_problem
from leetcoach.services.query_service import (
    DueReviewItem,
    complete_review,
    list_all_problems,
    list_by_pattern,
    list_due_reviews,
    search_problems,
)


LOGGER = logging.getLogger("leetcoach.telegram")

(
    LOG_TITLE,
    LOG_DIFFICULTY,
    LOG_LEETCODE_SLUG,
    LOG_NEETCODE_SLUG,
    LOG_PATTERN,
    LOG_SOLVED_AT,
    LOG_CONCEPTS,
    LOG_TIME_COMPLEXITY,
    LOG_SPACE_COMPLEXITY,
    LOG_NOTES,
) = range(10)


def _telegram_user_id(update: Update) -> str:
    if update.effective_user is None:
        raise RuntimeError("Missing effective user")
    return str(update.effective_user.id)


def _telegram_chat_id(update: Update) -> str:
    if update.effective_chat is None:
        raise RuntimeError("Missing effective chat")
    return str(update.effective_chat.id)


def _register_user(db_path: str, update: Update, timezone: str) -> None:
    now_iso = datetime.now(UTC).isoformat()
    with get_connection(db_path) as conn:
        upsert_user(
            conn,
            telegram_user_id=_telegram_user_id(update),
            telegram_chat_id=_telegram_chat_id(update),
            timezone=timezone,
            now_iso=now_iso,
        )
        conn.commit()


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg: AppConfig = context.application.bot_data["config"]
    _register_user(cfg.db_path, update, cfg.timezone)
    await update.message.reply_text(
        "Registered. Commands: /log, /due, /done <A#>, /search <query>, /pattern <name>, /list"
    )


async def log_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Log flow started. Enter problem title:")
    context.user_data["log_payload"] = {}
    return LOG_TITLE


async def log_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["log_payload"]["title"] = update.message.text.strip()
    await update.message.reply_text("Difficulty? (easy|medium|hard)")
    return LOG_DIFFICULTY


async def log_difficulty(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    difficulty = update.message.text.strip().lower()
    if difficulty not in {"easy", "medium", "hard"}:
        await update.message.reply_text("Invalid difficulty. Use easy, medium, or hard.")
        return LOG_DIFFICULTY
    context.user_data["log_payload"]["difficulty"] = difficulty
    await update.message.reply_text("LeetCode slug? (example: maximum-depth-of-binary-tree)")
    return LOG_LEETCODE_SLUG


async def log_leetcode_slug(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["log_payload"]["leetcode_slug"] = update.message.text.strip()
    await update.message.reply_text("NeetCode slug? (or '-' to skip)")
    return LOG_NEETCODE_SLUG


async def log_neetcode_slug(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    context.user_data["log_payload"]["neetcode_slug"] = None if text == "-" else text
    await update.message.reply_text("Pattern? (example: sliding-window)")
    return LOG_PATTERN


async def log_pattern(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["log_payload"]["pattern"] = update.message.text.strip()
    await update.message.reply_text(
        "Solved timestamp (ISO 8601) or 'now'. Example: 2026-03-08T12:00:00+00:00"
    )
    return LOG_SOLVED_AT


async def log_solved_at(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text.lower() == "now":
        solved_at = datetime.now(UTC).isoformat()
    else:
        try:
            datetime.fromisoformat(text)
        except ValueError:
            await update.message.reply_text("Invalid timestamp format. Provide ISO 8601 or 'now'.")
            return LOG_SOLVED_AT
        solved_at = text
    context.user_data["log_payload"]["solved_at"] = solved_at
    await update.message.reply_text("Concepts text? (or '-' to skip)")
    return LOG_CONCEPTS


async def log_concepts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    context.user_data["log_payload"]["concepts"] = None if text == "-" else text
    await update.message.reply_text("Time complexity text? (or '-' to skip)")
    return LOG_TIME_COMPLEXITY


async def log_time_complexity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    context.user_data["log_payload"]["time_complexity"] = None if text == "-" else text
    await update.message.reply_text("Space complexity text? (or '-' to skip)")
    return LOG_SPACE_COMPLEXITY


async def log_space_complexity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    context.user_data["log_payload"]["space_complexity"] = None if text == "-" else text
    await update.message.reply_text("Notes? (or '-' to skip)")
    return LOG_NOTES


async def log_notes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    cfg: AppConfig = context.application.bot_data["config"]
    payload_data: dict[str, Any] = context.user_data.get("log_payload", {})
    notes_text = update.message.text.strip()
    payload_data["notes"] = None if notes_text == "-" else notes_text

    log_input = LogProblemInput(
        telegram_user_id=_telegram_user_id(update),
        telegram_chat_id=_telegram_chat_id(update),
        timezone=cfg.timezone,
        title=payload_data["title"],
        difficulty=payload_data["difficulty"],
        leetcode_slug=payload_data["leetcode_slug"],
        neetcode_slug=payload_data["neetcode_slug"],
        pattern=payload_data["pattern"],
        solved_at=payload_data["solved_at"],
        concepts=payload_data.get("concepts"),
        time_complexity=payload_data.get("time_complexity"),
        space_complexity=payload_data.get("space_complexity"),
        notes=payload_data.get("notes"),
    )
    result = log_problem(cfg.db_path, log_input)
    await update.message.reply_text(
        f"Logged: {log_input.title}\nuser_problem_id={result.user_problem_id}"
    )
    context.user_data.pop("log_payload", None)
    return ConversationHandler.END


async def log_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("log_payload", None)
    await update.message.reply_text("Log flow cancelled.")
    return ConversationHandler.END


def _render_due(items: list[DueReviewItem], token_map: dict[str, ReviewToken]) -> str:
    lines = []
    rev_lookup = {(v.user_problem_id, v.review_day): k for k, v in token_map.items()}
    for item in items:
        token = rev_lookup[(item.user_problem_id, item.review_day)]
        lines.append(
            f"{token} | {item.title} | day {item.review_day} | {item.status} | due {item.due_at}"
        )
    return "\n".join(lines)


async def due_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg: AppConfig = context.application.bot_data["config"]
    token_store: DueTokenStore = context.application.bot_data["due_tokens"]
    telegram_user_id = _telegram_user_id(update)
    items = list_due_reviews(cfg.db_path, telegram_user_id)
    if not items:
        await update.message.reply_text("No pending/overdue reviews.")
        return
    token_map = token_store.put(telegram_user_id, items)
    await update.message.reply_text(_render_due(items, token_map))


async def done_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg: AppConfig = context.application.bot_data["config"]
    token_store: DueTokenStore = context.application.bot_data["due_tokens"]
    telegram_user_id = _telegram_user_id(update)
    if not context.args:
        await update.message.reply_text("Usage: /done <token> (example: /done A1)")
        return
    token = context.args[0].upper()
    ref = token_store.get(telegram_user_id, token)
    if ref is None:
        await update.message.reply_text("Unknown/expired token. Run /due again.")
        return
    ok = complete_review(cfg.db_path, telegram_user_id, ref.user_problem_id, ref.review_day)
    if not ok:
        await update.message.reply_text("Could not mark done. Run /due again.")
        return
    await update.message.reply_text(f"Marked complete: {token}")


def _render_problem_rows(rows: list[dict[str, str]]) -> str:
    lines = []
    for row in rows:
        lines.append(
            f"{row['title']} | {row['difficulty']} | {row['pattern']} | solved {row['solved_at']}"
        )
    return "\n".join(lines)


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg: AppConfig = context.application.bot_data["config"]
    telegram_user_id = _telegram_user_id(update)
    if not context.args:
        await update.message.reply_text("Usage: /search <query>")
        return
    query = " ".join(context.args)
    rows = search_problems(cfg.db_path, telegram_user_id, query)
    if not rows:
        await update.message.reply_text("No matching problems.")
        return
    await update.message.reply_text(_render_problem_rows(rows))


async def pattern_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg: AppConfig = context.application.bot_data["config"]
    telegram_user_id = _telegram_user_id(update)
    if not context.args:
        await update.message.reply_text("Usage: /pattern <pattern>")
        return
    pattern = " ".join(context.args)
    rows = list_by_pattern(cfg.db_path, telegram_user_id, pattern)
    if not rows:
        await update.message.reply_text("No problems for this pattern.")
        return
    await update.message.reply_text(_render_problem_rows(rows))


async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg: AppConfig = context.application.bot_data["config"]
    telegram_user_id = _telegram_user_id(update)
    rows = list_all_problems(cfg.db_path, telegram_user_id)
    if not rows:
        await update.message.reply_text("No logged problems yet.")
        return
    await update.message.reply_text(_render_problem_rows(rows))


def build_application(config: AppConfig) -> Application:
    if not config.telegram_bot_token:
        raise RuntimeError("LEETCOACH_TELEGRAM_BOT_TOKEN is not configured")

    app = Application.builder().token(config.telegram_bot_token).build()
    app.bot_data["config"] = config
    app.bot_data["due_tokens"] = DueTokenStore()

    log_flow = ConversationHandler(
        entry_points=[CommandHandler("log", log_command)],
        states={
            LOG_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, log_title)],
            LOG_DIFFICULTY: [MessageHandler(filters.TEXT & ~filters.COMMAND, log_difficulty)],
            LOG_LEETCODE_SLUG: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, log_leetcode_slug)
            ],
            LOG_NEETCODE_SLUG: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, log_neetcode_slug)
            ],
            LOG_PATTERN: [MessageHandler(filters.TEXT & ~filters.COMMAND, log_pattern)],
            LOG_SOLVED_AT: [MessageHandler(filters.TEXT & ~filters.COMMAND, log_solved_at)],
            LOG_CONCEPTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, log_concepts)],
            LOG_TIME_COMPLEXITY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, log_time_complexity)
            ],
            LOG_SPACE_COMPLEXITY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, log_space_complexity)
            ],
            LOG_NOTES: [MessageHandler(filters.TEXT & ~filters.COMMAND, log_notes)],
        },
        fallbacks=[CommandHandler("cancel", log_cancel)],
    )

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(log_flow)
    app.add_handler(CommandHandler("due", due_command))
    app.add_handler(CommandHandler("done", done_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("pattern", pattern_command))
    app.add_handler(CommandHandler("list", list_command))
    return app


def run_bot(config: AppConfig) -> int:
    application = build_application(config)
    LOGGER.info("Starting Telegram bot polling")
    application.run_polling(close_loop=False)
    return 0
