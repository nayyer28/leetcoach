from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from html import escape
import logging
from typing import Any

from telegram import (
    LinkPreviewOptions,
    ReplyKeyboardRemove,
    Update,
)
from telegram.constants import ChatAction, ParseMode
from telegram.error import Conflict, NetworkError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    Defaults,
    MessageHandler,
    filters,
)

from leetcoach.app.application.problems.browse_problems import (
    get_problem_detail,
    list_all_problems,
    list_by_pattern,
    list_recent_problems,
    search_problems,
)
from leetcoach.app.application.problems.log_problem import LogProblemInput, log_problem
from leetcoach.app.application.quiz.answer_quiz import answer_quiz
from leetcoach.app.application.quiz.common import (
    AnswerQuizResult,
    QuizQuestionPayload,
    is_known_quiz_topic,
)
from leetcoach.app.application.quiz.interrupt_quiz import interrupt_active_quiz
from leetcoach.app.application.quiz.reveal_quiz import reveal_quiz
from leetcoach.app.application.quiz.start_quiz import start_quiz
from leetcoach.app.application.reviews.complete_review import complete_review
from leetcoach.app.application.reviews.due_reviews import (
    DueReviewItem,
    list_due_reviews,
)
from leetcoach.app.application.reviews.reminder_engine import (
    build_reminder_message,
    row_to_candidate,
    select_candidates_for_batch,
)
from leetcoach.app.infrastructure.config.app_config import AppConfig
from leetcoach.app.infrastructure.config.db import get_connection
from leetcoach.app.infrastructure.dao.review_queue_dao import (
    list_last_requested_batch_for_user,
    list_next_review_candidates_for_user,
    mark_review_requested,
)
from leetcoach.app.infrastructure.dao.users_dao import (
    get_user_id_by_telegram_user_id,
    get_user_reminder_preferences,
    set_user_reminder_daily_max,
    set_user_reminder_hour_local,
    upsert_user,
)
from leetcoach.app.infrastructure.llm.gemini_provider import (
    DEFAULT_GEMINI_MODEL_PRIORITY,
    GeminiAllModelsFailed,
    GeminiProvider,
)
from leetcoach.patterns import (
    ROADMAP_PATTERN_LEVELS,
    canonical_pattern_label as _canonical_pattern_label,
    normalize_pattern_key as _normalize_pattern_key,
)
from leetcoach.app.interface.bot.keyboards import (
    difficulty_inline_markup as _difficulty_inline_markup_impl,
    pattern_inline_markup as _pattern_inline_markup_impl,
)
from leetcoach.app.interface.bot.views import (
    chunk_text as _chunk_text,
    commands_help_text as _commands_help_text,
    extract_problem_slug as _extract_problem_slug,
    format_timestamp as _format_timestamp,
    format_timestamp_compact as _format_timestamp_compact,
    leetcode_url as _leetcode_url,
    log_prompt as _log_prompt,
    neetcode_url as _neetcode_url,
    normalize_difficulty_input as _normalize_difficulty_input,
    normalize_solved_at as _normalize_solved_at,
    remind_usage_text as _remind_usage_text,
    render_due as _render_due,
    render_last_batch as _render_last_batch_impl,
    render_problem_detail as _render_problem_detail,
    render_problem_rows as _render_problem_rows,
    render_quiz_feedback as _render_quiz_feedback,
    render_quiz_question as _render_quiz_question,
    render_quiz_reveal as _render_quiz_reveal,
    render_remind_settings as _render_remind_settings,
    unknown_command_help_text as _unknown_command_help_text,
    unknown_text_help_text as _unknown_text_help_text,
)
from leetcoach.app.interface.bot.token_store import DueTokenStore, ProblemToken


LOGGER = logging.getLogger("leetcoach.telegram")
BOT_BOOTSTRAP_RETRIES = 5

DIFFICULTY_OPTIONS = [["Easy", "Medium", "Hard"]]
LOG_DIFFICULTY_CALLBACK_PREFIX = "log:difficulty:"
LOG_PATTERN_CALLBACK_PREFIX = "log:pattern:"

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

def _clear_quiz_prompt_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("quiz_unknown_topic", None)


def _interrupt_quiz_if_needed(
    cfg: AppConfig, update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    interrupt_active_quiz(
        db_path=cfg.db_path,
        telegram_user_id=_telegram_user_id(update),
    )
    _clear_quiz_prompt_state(context)

async def _reply_log_inline_selection(target: Any, label: str) -> None:
    await target.reply_text(f"✓ Selected: {label}")


async def _send_typing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat is None:
        return
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING,
    )

def _difficulty_inline_markup() -> InlineKeyboardMarkup:
    return _difficulty_inline_markup_impl(
        difficulty_options=DIFFICULTY_OPTIONS,
        callback_prefix=LOG_DIFFICULTY_CALLBACK_PREFIX,
    )


def _pattern_inline_markup() -> InlineKeyboardMarkup:
    return _pattern_inline_markup_impl(callback_prefix=LOG_PATTERN_CALLBACK_PREFIX)


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
    _interrupt_quiz_if_needed(cfg, update, context)
    await update.message.reply_text(
        "👋 Hey, I’m leetcoach — Saahil Nayyer’s interview prep bot.\n"
        "I’m currently for personal use only.\n"
        "If you’d like access, please contact @nayyer28."
    )
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
    _interrupt_quiz_if_needed(cfg, update, context)
    await update.message.reply_text(_commands_help_text(), parse_mode=ParseMode.HTML)


async def register_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start_command(update, context)


def _parse_log_show_limit(args: list[str]) -> int | None:
    if not args or args[0].lower() != "show":
        return None
    if len(args) == 1:
        return 1
    if len(args) != 2:
        return -1
    try:
        value = int(args[1])
    except ValueError:
        return -1
    return value if value > 0 else -1


async def log_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    cfg = await _ensure_authorized(update, context)
    if cfg is None:
        return ConversationHandler.END
    _interrupt_quiz_if_needed(cfg, update, context)
    show_limit = _parse_log_show_limit(context.args)
    if show_limit is not None:
        if show_limit < 1:
            await update.message.reply_text("Usage: /log show [n], where n is a positive integer.")
            return ConversationHandler.END
        telegram_user_id = _telegram_user_id(update)
        rows = list_recent_problems(cfg.db_path, telegram_user_id, limit=show_limit)
        if not rows:
            await update.message.reply_text("🗂️ No logged problems yet.")
            return ConversationHandler.END
        token_map = _browse_token_map(context, telegram_user_id, rows)
        await _reply_long_text(update, _render_problem_rows(rows, token_map, cfg.timezone))
        return ConversationHandler.END
    await update.message.reply_text(
        _log_prompt(1, 10, "Enter problem title:"),
        reply_markup=ReplyKeyboardRemove(),
    )
    context.user_data["log_payload"] = {}
    return LOG_TITLE


async def log_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["log_payload"]["title"] = update.message.text.strip()
    await update.message.reply_text(
        _log_prompt(2, 10, "Difficulty? Choose below or type easy/medium/hard."),
        reply_markup=_difficulty_inline_markup(),
    )
    return LOG_DIFFICULTY


async def _clear_inline_keyboard(update: Update) -> None:
    query = update.callback_query
    if query is None:
        return
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        LOGGER.debug("Failed to clear inline keyboard", exc_info=True)


async def _set_log_difficulty(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    raw_value: str,
) -> int:
    difficulty = _normalize_difficulty_input(raw_value)
    if difficulty is None:
        target = update.callback_query.message if update.callback_query else update.message
        await target.reply_text(
            "⚠️ Unknown difficulty. Choose Easy, Medium, Hard, or type the exact value.",
            reply_markup=_difficulty_inline_markup(),
        )
        return LOG_DIFFICULTY
    context.user_data["log_payload"]["difficulty"] = difficulty
    target = update.callback_query.message if update.callback_query else update.message
    await target.reply_text(
        _log_prompt(3, 10, "LeetCode URL or slug? (or '-' to skip)"),
        reply_markup=ReplyKeyboardRemove(),
    )
    return LOG_LEETCODE_SLUG


async def log_difficulty(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _set_log_difficulty(update, context, update.message.text)


async def log_difficulty_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()
    await _clear_inline_keyboard(update)
    raw_value = query.data.removeprefix(LOG_DIFFICULTY_CALLBACK_PREFIX)
    await _reply_log_inline_selection(query.message, raw_value.title())
    return await _set_log_difficulty(update, context, raw_value)


async def log_leetcode_slug(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    slug = _extract_problem_slug(text, provider="leetcode")
    if text != "-" and slug is None:
        await update.message.reply_text(
            "⚠️ Invalid LeetCode input. Paste the full URL, the slug, or '-' to skip."
        )
        return LOG_LEETCODE_SLUG
    context.user_data["log_payload"]["leetcode_slug"] = slug
    await update.message.reply_text(
        _log_prompt(4, 10, "NeetCode URL or slug? (required)"),
    )
    return LOG_NEETCODE_SLUG


async def log_neetcode_slug(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    slug = _extract_problem_slug(text, provider="neetcode")
    if slug is None:
        await update.message.reply_text(
            "⚠️ Invalid NeetCode input. Paste the full URL or the slug."
        )
        return LOG_NEETCODE_SLUG
    context.user_data["log_payload"]["neetcode_slug"] = slug
    await update.message.reply_text(
        _log_prompt(5, 10, "Pattern? Choose below or type the exact known pattern."),
        reply_markup=_pattern_inline_markup(),
    )
    return LOG_PATTERN


async def _set_log_pattern(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    raw_value: str,
) -> int:
    pattern = _canonical_pattern_label(raw_value)
    if pattern is None:
        target = update.callback_query.message if update.callback_query else update.message
        await target.reply_text(
            "⚠️ Unknown pattern. Choose from the list or type the exact known pattern name.",
            reply_markup=_pattern_inline_markup(),
        )
        return LOG_PATTERN
    context.user_data["log_payload"]["pattern"] = pattern
    target = update.callback_query.message if update.callback_query else update.message
    await target.reply_text(
        _log_prompt(
            6,
            10,
            "Solved time? Use 'now', ISO 8601, or YYYY-MM-DD HH:MM (local time).",
        )
        ,
        reply_markup=ReplyKeyboardRemove(),
    )
    return LOG_SOLVED_AT


async def log_pattern(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _set_log_pattern(update, context, update.message.text)


async def log_pattern_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await _clear_inline_keyboard(update)
    raw_value = query.data.removeprefix(LOG_PATTERN_CALLBACK_PREFIX)
    label = _canonical_pattern_label(raw_value) or raw_value
    await _reply_log_inline_selection(query.message, label)
    return await _set_log_pattern(update, context, raw_value)


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


async def due_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = await _ensure_authorized(update, context)
    if cfg is None:
        return
    _interrupt_quiz_if_needed(cfg, update, context)
    token_store: DueTokenStore = context.application.bot_data["due_tokens"]
    telegram_user_id = _telegram_user_id(update)
    items = list_due_reviews(cfg.db_path, telegram_user_id)
    if not items:
        await update.message.reply_text(
            "✅ No outstanding reviews right now.\nUse /remind new or /list to keep going."
        )
        return
    token_map = token_store.put(
        telegram_user_id, [item.user_problem_id for item in items]
    )
    await _reply_long_text(update, _render_due(items, token_map, cfg.timezone))


async def remind_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = await _ensure_authorized(update, context)
    if cfg is None:
        return
    _interrupt_quiz_if_needed(cfg, update, context)
    telegram_user_id = _telegram_user_id(update)
    now_iso = datetime.now(UTC).isoformat()

    with get_connection(cfg.db_path) as conn:
        prefs = get_user_reminder_preferences(conn, telegram_user_id=telegram_user_id)
        if prefs is None:
            await update.message.reply_text("⚠️ Please run /start first.")
            return

        user_id = int(prefs["id"])
        custom_count = (
            int(prefs["reminder_daily_max"])
            if prefs["reminder_daily_max"] is not None
            else None
        )
        custom_hour = (
            int(prefs["reminder_hour_local"])
            if prefs["reminder_hour_local"] is not None
            else None
        )
        user_timezone = str(prefs["timezone"])

        if not context.args:
            await update.message.reply_text(
                _render_remind_settings(
                    custom_count=custom_count,
                    effective_count=custom_count or cfg.reminder_daily_max,
                    custom_hour=custom_hour,
                    effective_hour=(
                        custom_hour
                        if custom_hour is not None
                        else cfg.reminder_hour_local
                    ),
                )
            )
            return

        action = context.args[0].lower()
        if action == "count":
            if len(context.args) != 2:
                await update.message.reply_text("Usage: /remind count <n>")
                return
            try:
                value = int(context.args[1])
            except ValueError:
                await update.message.reply_text("⚠️ Reminder count must be a number.")
                return
            if value < 1 or value > 10:
                await update.message.reply_text(
                    "⚠️ Reminder count must be between 1 and 10."
                )
                return
            updated = set_user_reminder_daily_max(
                conn,
                telegram_user_id=telegram_user_id,
                reminder_daily_max=value,
                now_iso=now_iso,
            )
            if not updated:
                await update.message.reply_text("⚠️ Please run /start first.")
                return
            conn.commit()
            await update.message.reply_text(
                f"✅ Updated daily reminder count to {value}. Use /remind to check."
            )
            return

        if action == "time":
            if len(context.args) != 2:
                await update.message.reply_text("Usage: /remind time <hour>")
                return
            try:
                value = int(context.args[1])
            except ValueError:
                await update.message.reply_text("⚠️ Reminder hour must be a number.")
                return
            if value < 0 or value > 23:
                await update.message.reply_text(
                    "⚠️ Reminder hour must be between 0 and 23."
                )
                return
            updated = set_user_reminder_hour_local(
                conn,
                telegram_user_id=telegram_user_id,
                reminder_hour_local=value,
                now_iso=now_iso,
            )
            if not updated:
                await update.message.reply_text("⚠️ Please run /start first.")
                return
            conn.commit()
            await update.message.reply_text(
                f"✅ Updated reminder hour to {value:02d}:00. Use /remind to check."
            )
            return

        if action == "last":
            if len(context.args) != 1:
                await update.message.reply_text("Usage: /remind last")
                return
            batch = list_last_requested_batch_for_user(conn, user_id=user_id)
            if not batch:
                await update.message.reply_text("📭 No reminder batch has been sent yet.")
                return
            await _reply_long_text(
                update, _render_last_batch_impl(batch, user_timezone, row_to_candidate)
            )
            return

        if action == "new":
            if len(context.args) != 1:
                await update.message.reply_text("Usage: /remind new")
                return
            rows = list_next_review_candidates_for_user(conn, user_id=user_id)
            selected = select_candidates_for_batch(
                [row_to_candidate(row) for row in rows],
                now_iso=now_iso,
                daily_max=custom_count or cfg.reminder_daily_max,
            )
            if not selected:
                await update.message.reply_text(
                    "✅ No extra reminder candidate is available right now."
                )
                return
            candidate = selected[0]
            marked = mark_review_requested(
                conn,
                user_id=user_id,
                user_problem_id=candidate.user_problem_id,
                requested_at=now_iso,
            )
            if marked:
                conn.commit()
            await _reply_long_text(
                update, "🔁 Manual Reminder\n\n" + build_reminder_message(candidate)
            )
            return

    await update.message.reply_text(_remind_usage_text())


async def reminder_count_alias_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    context.args = ["count", *context.args]
    await remind_command(update, context)


def _resolve_problem_token(
    context: ContextTypes.DEFAULT_TYPE, telegram_user_id: str, token: str
) -> ProblemToken | None:
    due_store: DueTokenStore = context.application.bot_data["due_tokens"]
    browse_store: DueTokenStore = context.application.bot_data["browse_tokens"]
    return due_store.get(telegram_user_id, token) or browse_store.get(
        telegram_user_id, token
    )


async def reviewed_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = await _ensure_authorized(update, context)
    if cfg is None:
        return
    _interrupt_quiz_if_needed(cfg, update, context)
    telegram_user_id = _telegram_user_id(update)
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /reviewed <token> (example: /reviewed A1)")
        return
    token = context.args[0].upper()
    problem_ref = _resolve_problem_token(context, telegram_user_id, token)
    if problem_ref is None:
        await update.message.reply_text(
            "⚠️ Unknown/expired token. Run /due or /list again."
        )
        return
    ok = complete_review(cfg.db_path, telegram_user_id, problem_ref.user_problem_id)
    if not ok:
        await update.message.reply_text(
            "⚠️ Could not mark this problem as reviewed. Run /due or /list again."
        )
        return
    await update.message.reply_text(f"✅ Marked reviewed: {token}")

async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = await _ensure_authorized(update, context)
    if cfg is None:
        return
    provider: GeminiProvider | None = context.application.bot_data.get("quiz_provider")
    if provider is None:
        await update.message.reply_text(
            "⚠️ Quiz provider is not configured. Set GEMINI_API_KEY and restart bot."
        )
        return

    topic = " ".join(context.args).strip() if context.args else None
    if topic and not is_known_quiz_topic(topic):
        context.user_data["quiz_unknown_topic"] = topic
        await update.message.reply_text(
            "Not sure I know this topic. Do you want a general question instead? (yes/no)"
        )
        return

    await _send_typing(update, context)
    try:
        result = start_quiz(
            db_path=cfg.db_path,
            telegram_user_id=_telegram_user_id(update),
            topic=topic,
            provider=provider,
        )
    except (GeminiAllModelsFailed, ValueError, json.JSONDecodeError) as exc:
        LOGGER.exception("Quiz generation failed")
        await update.message.reply_text(
            f"⚠️ Could not generate quiz right now: {exc}\nTry again shortly."
        )
        return

    if result.status == "user_not_registered":
        await update.message.reply_text("⚠️ Please run /start first.")
        return
    if result.status == "unknown_topic":
        context.user_data["quiz_unknown_topic"] = topic
        await update.message.reply_text(
            "Not sure I know this topic. Do you want a general question instead? (yes/no)"
        )
        return
    if result.question is None:
        await update.message.reply_text("⚠️ Could not generate quiz. Try again.")
        return
    context.user_data.pop("quiz_unknown_topic", None)
    await update.message.reply_text(_render_quiz_question(result.question, result.model_used))


async def reveal_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = await _ensure_authorized(update, context)
    if cfg is None:
        return
    result = reveal_quiz(
        db_path=cfg.db_path,
        telegram_user_id=_telegram_user_id(update),
    )
    if result.status == "user_not_registered":
        await update.message.reply_text("⚠️ Please run /start first.")
        return
    if result.status == "expired_quiz":
        await update.message.reply_text("⌛ This quiz expired. Run /quiz again.")
        return
    if result.status == "no_active_quiz" or result.question is None:
        await update.message.reply_text("⚠️ No active quiz. Run /quiz first.")
        return
    await update.message.reply_text(_render_quiz_reveal(result.question))

async def _reply_long_text(update: Update, text: str) -> None:
    for chunk in _chunk_text(text):
        await update.message.reply_text(chunk)


def _browse_token_map(
    context: ContextTypes.DEFAULT_TYPE, telegram_user_id: str, rows: list[dict[str, Any]]
) -> dict[str, ProblemToken]:
    token_store: DueTokenStore = context.application.bot_data["browse_tokens"]
    user_problem_ids = [int(row["user_problem_id"]) for row in rows]
    return token_store.put(telegram_user_id, user_problem_ids)


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = await _ensure_authorized(update, context)
    if cfg is None:
        return
    _interrupt_quiz_if_needed(cfg, update, context)
    telegram_user_id = _telegram_user_id(update)
    if not context.args:
        await update.message.reply_text("Usage: /search <query>")
        return
    query = " ".join(context.args)
    rows = search_problems(cfg.db_path, telegram_user_id, query)
    if not rows:
        await update.message.reply_text("🔎 No matching problems.")
        return
    token_map = _browse_token_map(context, telegram_user_id, rows)
    await _reply_long_text(update, _render_problem_rows(rows, token_map, cfg.timezone))


async def pattern_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = await _ensure_authorized(update, context)
    if cfg is None:
        return
    _interrupt_quiz_if_needed(cfg, update, context)
    telegram_user_id = _telegram_user_id(update)
    if not context.args:
        await update.message.reply_text("Usage: /pattern <pattern>")
        return
    pattern = " ".join(context.args)
    rows = list_by_pattern(cfg.db_path, telegram_user_id, pattern)
    if not rows:
        await update.message.reply_text("🧠 No problems for this pattern.")
        return
    token_map = _browse_token_map(context, telegram_user_id, rows)
    await _reply_long_text(update, _render_problem_rows(rows, token_map, cfg.timezone))


async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = await _ensure_authorized(update, context)
    if cfg is None:
        return
    _interrupt_quiz_if_needed(cfg, update, context)
    telegram_user_id = _telegram_user_id(update)
    rows = list_all_problems(cfg.db_path, telegram_user_id)
    if not rows:
        await update.message.reply_text("🗂️ No logged problems yet.")
        return
    token_map = _browse_token_map(context, telegram_user_id, rows)
    await _reply_long_text(update, _render_problem_rows(rows, token_map, cfg.timezone))


async def show_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = await _ensure_authorized(update, context)
    if cfg is None:
        return
    _interrupt_quiz_if_needed(cfg, update, context)
    telegram_user_id = _telegram_user_id(update)
    if not context.args:
        await update.message.reply_text("Usage: /show <token>")
        return
    token_store: DueTokenStore = context.application.bot_data["browse_tokens"]
    token = token_store.get(telegram_user_id, context.args[0])
    if token is None:
        await update.message.reply_text(
            "⚠️ Unknown/expired token. Run /list, /search, or /pattern again."
        )
        return
    row = get_problem_detail(
        cfg.db_path, telegram_user_id, user_problem_id=token.user_problem_id
    )
    if row is None:
        await update.message.reply_text(
            "⚠️ Could not find this problem anymore. Run /list again."
        )
        return
    await _reply_long_text(update, _render_problem_detail(row, cfg.timezone))


async def default_text_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = await _ensure_authorized(update, context)
    if cfg is None:
        return
    text = (update.message.text or "").strip()

    unknown_topic = context.user_data.get("quiz_unknown_topic")
    if unknown_topic is not None:
        lowered = text.lower()
        if lowered in {"yes", "y"}:
            provider: GeminiProvider | None = context.application.bot_data.get(
                "quiz_provider"
            )
            if provider is None:
                await update.message.reply_text(
                    "⚠️ Quiz provider is not configured. Set GEMINI_API_KEY and restart bot."
                )
                return
            await _send_typing(update, context)
            try:
                result = start_quiz(
                    db_path=cfg.db_path,
                    telegram_user_id=_telegram_user_id(update),
                    topic=None,
                    provider=provider,
                )
            except (GeminiAllModelsFailed, ValueError, json.JSONDecodeError) as exc:
                LOGGER.exception("General fallback quiz generation failed")
                await update.message.reply_text(
                    f"⚠️ Could not generate general question right now: {exc}"
                )
                return
            context.user_data.pop("quiz_unknown_topic", None)
            if result.status == "ok" and result.question is not None:
                await update.message.reply_text(
                    _render_quiz_question(result.question, result.model_used)
                )
                return
            await update.message.reply_text("⚠️ Could not generate quiz. Try /quiz again.")
            return
        if lowered in {"no", "n"}:
            context.user_data.pop("quiz_unknown_topic", None)
            await update.message.reply_text("Okay. Send /quiz with another topic.")
            return
        await update.message.reply_text("Please reply with yes or no.")
        return

    provider: GeminiProvider | None = context.application.bot_data.get("quiz_provider")
    if provider is not None:
        try:
            answer_result = answer_quiz(
                db_path=cfg.db_path,
                telegram_user_id=_telegram_user_id(update),
                user_answer_text=text,
                provider=provider,
            )
        except (GeminiAllModelsFailed, ValueError, json.JSONDecodeError) as exc:
            LOGGER.exception("Quiz answer evaluation failed")
            await update.message.reply_text(
                f"⚠️ Could not evaluate answer right now: {exc}\nTry again shortly."
            )
            return
        if answer_result.status == "ok":
            await update.message.reply_text(_render_quiz_feedback(answer_result))
            return
        if answer_result.status == "expired_quiz":
            await update.message.reply_text("⌛ This quiz expired. Run /quiz again.")
            return
        if answer_result.status == "invalid_answer":
            await update.message.reply_text(
                "⚠️ Please answer with A, B, C, or D. "
                "You can add your reasoning after the option, for example: "
                "`B because ...`",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

    await update.message.reply_text(_unknown_text_help_text())


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = await _ensure_authorized(update, context)
    if cfg is None:
        return
    command_text = (update.message.text or "").strip().split()[0]
    await update.message.reply_text(
        _unknown_command_help_text(command_text),
        parse_mode=ParseMode.MARKDOWN,
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
    app.bot_data["browse_tokens"] = DueTokenStore()
    if config.gemini_api_key:
        app.bot_data["quiz_provider"] = GeminiProvider(
            api_key=config.gemini_api_key,
            model_priority=DEFAULT_GEMINI_MODEL_PRIORITY,
            max_transient_retries=1,
        )
    else:
        app.bot_data["quiz_provider"] = None

    log_flow = ConversationHandler(
        entry_points=[CommandHandler("log", log_command)],
        states={
            LOG_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, log_title)],
            LOG_DIFFICULTY: [
                CallbackQueryHandler(
                    log_difficulty_callback,
                    pattern=rf"^{LOG_DIFFICULTY_CALLBACK_PREFIX}",
                ),
                MessageHandler(filters.TEXT & ~filters.COMMAND, log_difficulty),
            ],
            LOG_LEETCODE_SLUG: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, log_leetcode_slug)
            ],
            LOG_NEETCODE_SLUG: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, log_neetcode_slug)
            ],
            LOG_PATTERN: [
                CallbackQueryHandler(
                    log_pattern_callback,
                    pattern=rf"^{LOG_PATTERN_CALLBACK_PREFIX}",
                ),
                MessageHandler(filters.TEXT & ~filters.COMMAND, log_pattern),
            ],
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
    app.add_handler(CommandHandler(["help", "hi"], help_command))
    app.add_handler(log_flow)
    app.add_handler(CommandHandler("due", due_command))
    app.add_handler(CommandHandler(["remind", "reminder"], remind_command))
    app.add_handler(
        CommandHandler(["reminder_count", "remindercount"], reminder_count_alias_command)
    )
    app.add_handler(CommandHandler(["reviewed", "done"], reviewed_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("pattern", pattern_command))
    app.add_handler(CommandHandler("list", list_command))
    app.add_handler(CommandHandler("show", show_command))
    app.add_handler(CommandHandler("quiz", quiz_command))
    app.add_handler(CommandHandler("reveal", reveal_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, default_text_command))
    app.add_handler(MessageHandler(filters.COMMAND, unknown_command))
    app.add_error_handler(app_error_handler)
    return app


def run_bot(config: AppConfig) -> int:
    application = build_application(config)
    LOGGER.info("Starting Telegram bot polling")
    try:
        application.run_polling(
            close_loop=False,
            bootstrap_retries=BOT_BOOTSTRAP_RETRIES,
        )
    except Conflict:
        LOGGER.error(
            "Telegram polling conflict at startup. Ensure only one bot process "
            "is running for this token."
        )
        return 1
    except NetworkError as exc:
        LOGGER.error(
            "Telegram network error during startup after retries (%d): %s",
            BOT_BOOTSTRAP_RETRIES,
            exc,
        )
        return 1
    return 0
