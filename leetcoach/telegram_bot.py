from __future__ import annotations

from datetime import UTC, datetime
from html import escape
import logging
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from telegram import LinkPreviewOptions, Update
from telegram.constants import ParseMode
from telegram.error import Conflict
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    Defaults,
    MessageHandler,
    filters,
)

from leetcoach.config import AppConfig
from leetcoach.dao.users_dao import get_user_id_by_telegram_user_id, upsert_user
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


def _resolve_timezone(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _format_timestamp(iso_ts: str, timezone_name: str) -> str:
    dt = datetime.fromisoformat(iso_ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    local_dt = dt.astimezone(_resolve_timezone(timezone_name))
    return local_dt.strftime("%d %b %Y, %H:%M %Z")


def _format_timestamp_compact(iso_ts: str, timezone_name: str) -> str:
    dt = datetime.fromisoformat(iso_ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    local_dt = dt.astimezone(_resolve_timezone(timezone_name))
    return local_dt.strftime("%d %b %H:%M %Z")


def _leetcode_url(leetcode_slug: str) -> str:
    return f"https://leetcode.com/problems/{leetcode_slug}/description/"


def _neetcode_url(neetcode_slug: str | None) -> str | None:
    if not neetcode_slug:
        return None
    return f"https://neetcode.io/problems/{neetcode_slug}/question"


def _normalize_solved_at(raw_value: str, timezone_name: str) -> str | None:
    value = raw_value.strip()
    if value.lower() == "now":
        return datetime.now(UTC).isoformat()

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d %H:%M")
        except ValueError:
            return None
        parsed = parsed.replace(tzinfo=_resolve_timezone(timezone_name))
    else:
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=_resolve_timezone(timezone_name))

    return parsed.astimezone(UTC).isoformat()


def _commands_help_text() -> str:
    return (
        "🤖 <b>LeetCoach Command Menu</b>\n\n"
        "📝 <b>Log</b>\n"
        "• /log\n\n"
        "⏰ <b>Review</b>\n"
        "• /due\n"
        "• /done A1\n\n"
        "📚 <b>Browse</b>\n"
        "• /list\n"
        "• /pattern &lt;text&gt;\n"
        "• /search &lt;text&gt;\n\n"
        "👤 <b>Registration</b>\n"
        "• /register\n\n"
        "ℹ️ <b>Help</b>\n"
        "• /help"
    )


def _log_prompt(step: int, total: int, text: str) -> str:
    return f"🧩 [{step}/{total}] {text}\nSend /cancel to stop."


def _telegram_user_id(update: Update) -> str:
    if update.effective_user is None:
        raise RuntimeError("Missing effective user")
    return str(update.effective_user.id)


def _telegram_chat_id(update: Update) -> str:
    if update.effective_chat is None:
        raise RuntimeError("Missing effective chat")
    return str(update.effective_chat.id)


def _register_user(db_path: str, update: Update, timezone: str) -> bool:
    now_iso = datetime.now(UTC).isoformat()
    is_new = False
    with get_connection(db_path) as conn:
        existing = get_user_id_by_telegram_user_id(
            conn, telegram_user_id=_telegram_user_id(update)
        )
        is_new = existing is None
        upsert_user(
            conn,
            telegram_user_id=_telegram_user_id(update),
            telegram_chat_id=_telegram_chat_id(update),
            timezone=timezone,
            now_iso=now_iso,
        )
        conn.commit()
    return is_new


def _display_name(update: Update) -> str:
    if update.effective_user and update.effective_user.first_name:
        return update.effective_user.first_name
    return "there"


def _is_user_allowed(telegram_user_id: str, config: AppConfig) -> bool:
    if not config.allowed_user_ids:
        return True
    return telegram_user_id in config.allowed_user_ids


async def _ensure_authorized(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> AppConfig | None:
    cfg: AppConfig = context.application.bot_data["config"]
    telegram_user_id = _telegram_user_id(update)
    if _is_user_allowed(telegram_user_id, cfg):
        return cfg
    LOGGER.warning("Unauthorized Telegram user blocked: %s", telegram_user_id)
    await update.message.reply_text("⛔ Access denied for this bot.")
    return None


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = await _ensure_authorized(update, context)
    if cfg is None:
        return
    is_new = _register_user(cfg.db_path, update, cfg.timezone)
    name = _display_name(update)
    if is_new:
        message = f"✅ You’re registered, {escape(name)}. Let’s train."
    else:
        message = f"👋 Welcome back, {escape(name)}. Ready for another round?"
    await update.message.reply_text(message, parse_mode=ParseMode.HTML)
    await update.message.reply_text(
        _commands_help_text(),
        parse_mode=ParseMode.HTML,
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = await _ensure_authorized(update, context)
    if cfg is None:
        return
    await update.message.reply_text(_commands_help_text(), parse_mode=ParseMode.HTML)


async def register_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start_command(update, context)


async def log_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    cfg = await _ensure_authorized(update, context)
    if cfg is None:
        return ConversationHandler.END
    await update.message.reply_text(_log_prompt(1, 10, "Enter problem title:"))
    context.user_data["log_payload"] = {}
    return LOG_TITLE


async def log_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["log_payload"]["title"] = update.message.text.strip()
    await update.message.reply_text(_log_prompt(2, 10, "Difficulty? (easy|medium|hard)"))
    return LOG_DIFFICULTY


async def log_difficulty(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    difficulty = update.message.text.strip().lower()
    if difficulty not in {"easy", "medium", "hard"}:
        await update.message.reply_text(
            "⚠️ Invalid difficulty. Use: easy, medium, or hard."
        )
        return LOG_DIFFICULTY
    context.user_data["log_payload"]["difficulty"] = difficulty
    await update.message.reply_text(
        _log_prompt(3, 10, "LeetCode slug? (example: maximum-depth-of-binary-tree)")
    )
    return LOG_LEETCODE_SLUG


async def log_leetcode_slug(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["log_payload"]["leetcode_slug"] = update.message.text.strip()
    await update.message.reply_text(_log_prompt(4, 10, "NeetCode slug? (or '-' to skip)"))
    return LOG_NEETCODE_SLUG


async def log_neetcode_slug(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    context.user_data["log_payload"]["neetcode_slug"] = None if text == "-" else text
    await update.message.reply_text(_log_prompt(5, 10, "Pattern? (example: sliding-window)"))
    return LOG_PATTERN


async def log_pattern(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["log_payload"]["pattern"] = update.message.text.strip()
    await update.message.reply_text(
        _log_prompt(
            6,
            10,
            "Solved time? Use 'now', ISO 8601, or YYYY-MM-DD HH:MM (local time).",
        )
    )
    return LOG_SOLVED_AT


async def log_solved_at(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    cfg: AppConfig = context.application.bot_data["config"]
    solved_at = _normalize_solved_at(update.message.text, cfg.timezone)
    if solved_at is None:
        await update.message.reply_text(
            "⚠️ Invalid timestamp. Use 'now', ISO 8601, or YYYY-MM-DD HH:MM."
        )
        return LOG_SOLVED_AT
    context.user_data["log_payload"]["solved_at"] = solved_at
    await update.message.reply_text(_log_prompt(7, 10, "Concepts text? (or '-' to skip)"))
    return LOG_CONCEPTS


async def log_concepts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    context.user_data["log_payload"]["concepts"] = None if text == "-" else text
    await update.message.reply_text(_log_prompt(8, 10, "Time complexity text? (or '-' to skip)"))
    return LOG_TIME_COMPLEXITY


async def log_time_complexity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    context.user_data["log_payload"]["time_complexity"] = None if text == "-" else text
    await update.message.reply_text(
        _log_prompt(9, 10, "Space complexity text? (or '-' to skip)")
    )
    return LOG_SPACE_COMPLEXITY


async def log_space_complexity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    context.user_data["log_payload"]["space_complexity"] = None if text == "-" else text
    await update.message.reply_text(_log_prompt(10, 10, "Notes? (or '-' to skip)"))
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
    solved_label = _format_timestamp(payload_data["solved_at"], cfg.timezone)
    await update.message.reply_text(
        (
            "✅ Problem logged\n"
            f"Title: {log_input.title}\n"
            f"Difficulty: {log_input.difficulty.title()}\n"
            f"Pattern: {log_input.pattern}\n"
            f"Solved: {solved_label}\n"
            f"ID: {result.user_problem_id}"
        )
    )
    context.user_data.pop("log_payload", None)
    return ConversationHandler.END


async def log_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("log_payload", None)
    await update.message.reply_text("🛑 Log flow cancelled.")
    return ConversationHandler.END


def _render_due(
    items: list[DueReviewItem], token_map: dict[str, ReviewToken], timezone_name: str
) -> str:
    rev_lookup = {(v.user_problem_id, v.review_day): k for k, v in token_map.items()}
    lines: list[str] = ["⏰ Due Reviews", ""]
    for idx, item in enumerate(items, start=1):
        token = rev_lookup[(item.user_problem_id, item.review_day)]
        lines.append(
            f"{idx}. [{token}] {item.title}"
        )
        lines.append(
            (
                f"   Day {item.review_day} • {item.status.upper()} • "
                f"{_format_timestamp_compact(item.due_at, timezone_name)}"
            )
        )
        lines.append(f"   🔗 LC: {_leetcode_url(item.leetcode_slug)}")
        neetcode = _neetcode_url(item.neetcode_slug)
        if neetcode:
            lines.append(f"   🔗 NC: {neetcode}")
    lines.append("")
    lines.append("Use /done A1")
    return "\n".join(lines)


async def due_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = await _ensure_authorized(update, context)
    if cfg is None:
        return
    token_store: DueTokenStore = context.application.bot_data["due_tokens"]
    telegram_user_id = _telegram_user_id(update)
    items = list_due_reviews(cfg.db_path, telegram_user_id)
    if not items:
        await update.message.reply_text(
            "✅ No pending/overdue reviews right now.\nUse /list to see your logged problems."
        )
        return
    token_map = token_store.put(telegram_user_id, items)
    await update.message.reply_text(_render_due(items, token_map, cfg.timezone))


async def done_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = await _ensure_authorized(update, context)
    if cfg is None:
        return
    token_store: DueTokenStore = context.application.bot_data["due_tokens"]
    telegram_user_id = _telegram_user_id(update)
    if not context.args:
        await update.message.reply_text("Usage: /done <token> (example: /done A1)")
        return
    token = context.args[0].upper()
    ref = token_store.get(telegram_user_id, token)
    if ref is None:
        await update.message.reply_text("⚠️ Unknown/expired token. Run /due again.")
        return
    ok = complete_review(cfg.db_path, telegram_user_id, ref.user_problem_id, ref.review_day)
    if not ok:
        await update.message.reply_text("⚠️ Could not mark done. Run /due again.")
        return
    await update.message.reply_text(f"✅ Marked complete: {token}")


def _render_problem_rows(rows: list[dict[str, str]], timezone_name: str) -> str:
    lines: list[str] = ["📚 Your Problems", ""]
    for idx, row in enumerate(rows, start=1):
        leetcode_url = _leetcode_url(row["leetcode_slug"])
        neetcode_url = _neetcode_url(row["neetcode_slug"] or None)
        lines.append(f"{idx}. {row['title']}")
        lines.append(
            (
                f"   {row['difficulty'].title()} • {row['pattern']} • "
                f"{_format_timestamp_compact(row['solved_at'], timezone_name)}"
            )
        )
        lines.append(f"   🔗 LC: {leetcode_url}")
        if neetcode_url:
            lines.append(f"   🔗 NC: {neetcode_url}")
    return "\n".join(lines)


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = await _ensure_authorized(update, context)
    if cfg is None:
        return
    telegram_user_id = _telegram_user_id(update)
    if not context.args:
        await update.message.reply_text("Usage: /search <query>")
        return
    query = " ".join(context.args)
    rows = search_problems(cfg.db_path, telegram_user_id, query)
    if not rows:
        await update.message.reply_text("🔎 No matching problems.")
        return
    await update.message.reply_text(_render_problem_rows(rows, cfg.timezone))


async def pattern_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = await _ensure_authorized(update, context)
    if cfg is None:
        return
    telegram_user_id = _telegram_user_id(update)
    if not context.args:
        await update.message.reply_text("Usage: /pattern <pattern>")
        return
    pattern = " ".join(context.args)
    rows = list_by_pattern(cfg.db_path, telegram_user_id, pattern)
    if not rows:
        await update.message.reply_text("🧠 No problems for this pattern.")
        return
    await update.message.reply_text(_render_problem_rows(rows, cfg.timezone))


async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = await _ensure_authorized(update, context)
    if cfg is None:
        return
    telegram_user_id = _telegram_user_id(update)
    rows = list_all_problems(cfg.db_path, telegram_user_id)
    if not rows:
        await update.message.reply_text("🗂️ No logged problems yet.")
        return
    await update.message.reply_text(_render_problem_rows(rows, cfg.timezone))


async def default_text_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = await _ensure_authorized(update, context)
    if cfg is None:
        return
    await update.message.reply_text(
        "👋 I’m here. Try /help to see available commands."
    )


async def app_error_handler(_: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    error = context.error
    if isinstance(error, Conflict):
        LOGGER.error(
            "Telegram polling conflict: another bot instance is already running "
            "for this token. Stopping this instance."
        )
        context.application.stop_running()
        return
    if error is not None:
        LOGGER.exception("Unhandled Telegram error", exc_info=error)


def build_application(config: AppConfig) -> Application:
    if not config.telegram_bot_token:
        raise RuntimeError("LEETCOACH_TELEGRAM_BOT_TOKEN is not configured")

    app = (
        Application.builder()
        .token(config.telegram_bot_token)
        .defaults(Defaults(link_preview_options=LinkPreviewOptions(is_disabled=True)))
        .build()
    )
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
    app.add_handler(CommandHandler("register", register_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(log_flow)
    app.add_handler(CommandHandler("due", due_command))
    app.add_handler(CommandHandler("done", done_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("pattern", pattern_command))
    app.add_handler(CommandHandler("list", list_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, default_text_command))
    app.add_error_handler(app_error_handler)
    return app


def run_bot(config: AppConfig) -> int:
    application = build_application(config)
    LOGGER.info("Starting Telegram bot polling")
    try:
        application.run_polling(close_loop=False, bootstrap_retries=0)
    except Conflict:
        LOGGER.error(
            "Telegram polling conflict at startup. Ensure only one bot process "
            "is running for this token."
        )
        return 1
    return 0
