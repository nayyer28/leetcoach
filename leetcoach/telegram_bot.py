from __future__ import annotations

from dataclasses import dataclass
import json
import re
from datetime import UTC, datetime
from html import escape
import logging
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LinkPreviewOptions,
    ReplyKeyboardRemove,
    Update,
)
from telegram.constants import ParseMode
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

from leetcoach.config import AppConfig
from leetcoach.dao.users_dao import get_user_id_by_telegram_user_id, upsert_user
from leetcoach.db.connection import get_connection
from leetcoach.llm.gemini_provider import (
    DEFAULT_GEMINI_MODEL_PRIORITY,
    GeminiAllModelsFailed,
    GeminiProvider,
)
from leetcoach.services.due_tokens import DueTokenStore, ProblemToken
from leetcoach.services.log_problem_service import LogProblemInput, log_problem
from leetcoach.services.query_service import (
    DueReviewItem,
    complete_review,
    get_problem_detail,
    list_all_problems,
    list_by_pattern,
    list_due_reviews,
    search_problems,
)
from leetcoach.services.quiz_service import (
    AnswerQuizResult,
    QuizQuestionPayload,
    answer_quiz,
    interrupt_active_quiz,
    is_known_quiz_topic,
    reveal_quiz,
    start_quiz,
)


LOGGER = logging.getLogger("leetcoach.telegram")
TELEGRAM_MESSAGE_CHUNK_SIZE = 3500
BOT_BOOTSTRAP_RETRIES = 5
UNKNOWN_PATTERN_LEVEL = 999
SLUG_INPUT_RE = re.compile(r"^[a-z0-9-]+$", re.IGNORECASE)
LEETCODE_INPUT_RE = re.compile(
    r"^https?://leetcode\.com/problems/([^/?#]+)(?:/.*)?$",
    re.IGNORECASE,
)
NEETCODE_INPUT_RE = re.compile(
    r"^https?://neetcode\.io/problems/([^/?#]+)(?:/.*)?$",
    re.IGNORECASE,
)

# NeetCode roadmap-inspired ordering; same-level groups are alphabetical.
ROADMAP_PATTERN_LEVELS: dict[str, tuple[int, str]] = {
    "arrays and hashing": (1, "Arrays & Hashing"),
    "two pointers": (2, "Two Pointers"),
    "stack": (2, "Stack"),
    "binary search": (3, "Binary Search"),
    "sliding window": (3, "Sliding Window"),
    "linked list": (3, "Linked List"),
    "trees": (4, "Trees"),
    "tries": (5, "Tries"),
    "backtracking": (5, "Backtracking"),
    "heap priority queue": (5, "Heap / Priority Queue"),
    "graphs": (5, "Graphs"),
    "1 d dp": (6, "1-D DP"),
    "intervals": (6, "Intervals"),
    "greedy": (7, "Greedy"),
    "advanced graphs": (7, "Advanced Graphs"),
    "2 d dp": (7, "2-D DP"),
    "bit manipulation": (8, "Bit Manipulation"),
    "math geometry": (8, "Math & Geometry"),
}

ROADMAP_PATTERN_ALIASES: dict[str, str] = {
    "array and hashing": "arrays and hashing",
    "arrays hashing": "arrays and hashing",
    "two pointer": "two pointers",
    "linked lists": "linked list",
    "tree": "trees",
    "tree dfs": "trees",
    "tree bfs": "trees",
    "trie": "tries",
    "heap": "heap priority queue",
    "priority queue": "heap priority queue",
    "heaps": "heap priority queue",
    "graph": "graphs",
    "1d dp": "1 d dp",
    "dp 1d": "1 d dp",
    "1 d dynamic programming": "1 d dp",
    "2d dp": "2 d dp",
    "dp 2d": "2 d dp",
    "2 d dynamic programming": "2 d dp",
    "math and geometry": "math geometry",
    "bitwise": "bit manipulation",
}

DIFFICULTY_OPTIONS = [["Easy", "Medium", "Hard"]]
LOG_DIFFICULTY_CALLBACK_PREFIX = "log:difficulty:"
LOG_PATTERN_CALLBACK_PREFIX = "log:pattern:"


@dataclass(frozen=True)
class DueProblemEntry:
    user_problem_id: int
    title: str
    leetcode_slug: str | None
    neetcode_slug: str | None
    solved_at: str
    checkpoints: dict[int, DueReviewItem]


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


def _leetcode_url(leetcode_slug: str | None) -> str | None:
    if not leetcode_slug:
        return None
    return f"https://leetcode.com/problems/{leetcode_slug}/description/"


def _neetcode_url(neetcode_slug: str | None) -> str | None:
    if not neetcode_slug:
        return None
    return f"https://neetcode.io/problems/{neetcode_slug}/question"


def _normalize_pattern_key(pattern: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", pattern.lower()).split())


def _roadmap_pattern_info(pattern: str) -> tuple[int, str, str]:
    normalized = _normalize_pattern_key(pattern)
    canonical = ROADMAP_PATTERN_ALIASES.get(normalized, normalized)
    if canonical in ROADMAP_PATTERN_LEVELS:
        level, label = ROADMAP_PATTERN_LEVELS[canonical]
        return level, label, canonical

    if "advanced" in normalized and "graph" in normalized:
        level, label = ROADMAP_PATTERN_LEVELS["advanced graphs"]
        return level, label, "advanced graphs"
    if "graph" in normalized:
        level, label = ROADMAP_PATTERN_LEVELS["graphs"]
        return level, label, "graphs"
    if "tree" in normalized:
        level, label = ROADMAP_PATTERN_LEVELS["trees"]
        return level, label, "trees"

    return UNKNOWN_PATTERN_LEVEL, pattern.strip() or "Unknown", normalized


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
        "🤖 <b>leetcoach Command Menu</b>\n\n"
        "📝 <b>Log</b>\n"
        "• /log\n\n"
        "🧠 <b>Quiz</b>\n"
        "• /quiz\n"
        "• /quiz &lt;topic&gt;\n"
        "• /reveal\n\n"
        "⏰ <b>Review</b>\n"
        "• /due\n"
        "• /done A1 7th\n\n"
        "📚 <b>Browse</b>\n"
        "• /list\n"
        "• /pattern &lt;text&gt;\n"
        "• /search &lt;text&gt;\n\n"
        "🔍 <b>Details</b>\n"
        "• /show A1\n\n"
        "👤 <b>Registration</b>\n"
        "• /register\n\n"
        "ℹ️ <b>Help</b>\n"
        "• /help"
    )


def _unknown_text_help_text() -> str:
    return (
        "🤔 I didn’t understand that.\n\n"
        "Try one of these commands:\n"
        "• /help\n"
        "• /log\n"
        "• /due\n"
        "• /list\n"
        "• /search <text>\n"
        "• /pattern <name>\n"
        "• /show <token>\n"
        "• /quiz [topic]\n"
        "• /reveal"
    )


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


def _log_prompt(step: int, total: int, text: str) -> str:
    return f"🧩 [{step}/{total}] {text}\nSend /cancel to stop."


def _difficulty_inline_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    label,
                    callback_data=f"{LOG_DIFFICULTY_CALLBACK_PREFIX}{label.lower()}",
                )
                for label in DIFFICULTY_OPTIONS[0]
            ]
        ]
    )


def _pattern_option_rows() -> list[list[str]]:
    labels = [
        label
        for _, label in sorted(
            ROADMAP_PATTERN_LEVELS.values(), key=lambda item: (item[0], item[1].lower())
        )
    ]
    return [labels[idx : idx + 2] for idx in range(0, len(labels), 2)]


def _pattern_inline_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    label,
                    callback_data=(
                        f"{LOG_PATTERN_CALLBACK_PREFIX}{_normalize_pattern_key(label)}"
                    ),
                )
                for label in row
            ]
            for row in _pattern_option_rows()
        ]
    )


def _normalize_difficulty_input(raw_value: str) -> str | None:
    normalized = raw_value.strip().lower()
    if normalized in {"easy", "medium", "hard"}:
        return normalized
    return None


def _canonical_pattern_label(raw_value: str) -> str | None:
    normalized = _normalize_pattern_key(raw_value)
    canonical = ROADMAP_PATTERN_ALIASES.get(normalized, normalized)
    info = ROADMAP_PATTERN_LEVELS.get(canonical)
    if info is None:
        return None
    return info[1]


def _extract_problem_slug(raw_value: str, *, provider: str) -> str | None:
    value = raw_value.strip()
    if not value:
        return None
    if value == "-":
        return None

    regex = LEETCODE_INPUT_RE if provider == "leetcode" else NEETCODE_INPUT_RE
    matched = regex.match(value)
    if matched:
        return matched.group(1).lower()

    if SLUG_INPUT_RE.fullmatch(value):
        return value.lower()

    return None


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


async def log_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    cfg = await _ensure_authorized(update, context)
    if cfg is None:
        return ConversationHandler.END
    _interrupt_quiz_if_needed(cfg, update, context)
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


def _render_due(
    entries: list[DueProblemEntry], token_map: dict[str, ProblemToken], timezone_name: str
) -> str:
    rev_lookup = {v.user_problem_id: k for k, v in token_map.items()}
    lines: list[str] = ["⏰ Due Reviews", ""]
    for idx, entry in enumerate(entries, start=1):
        token = rev_lookup[entry.user_problem_id]
        lines.append(f"{idx}. [{token}] {entry.title}")
        lines.append(
            f"   First attempt • {_format_timestamp_compact(entry.solved_at, timezone_name)}"
        )
        for review_day in (7, 21):
            checkpoint = entry.checkpoints.get(review_day)
            if checkpoint is None:
                continue
            lines.append(
                (
                    f"   Day {review_day} • {checkpoint.status.upper()} • "
                    f"{_format_timestamp_compact(checkpoint.due_at, timezone_name)}"
                )
            )
        leetcode = _leetcode_url(entry.leetcode_slug)
        if leetcode:
            lines.append(f"   🔗 LC: {leetcode}")
        neetcode = _neetcode_url(entry.neetcode_slug)
        if neetcode:
            lines.append(f"   🔗 NC: {neetcode}")
        lines.append("")
    if lines and not lines[-1]:
        lines.pop()
    lines.append("")
    lines.append("Use /done A1 7th")
    return "\n".join(lines)


def _group_due_entries(items: list[DueReviewItem]) -> list[DueProblemEntry]:
    grouped: dict[int, DueProblemEntry] = {}
    for item in items:
        entry = grouped.get(item.user_problem_id)
        if entry is None:
            grouped[item.user_problem_id] = DueProblemEntry(
                user_problem_id=item.user_problem_id,
                title=item.title,
                leetcode_slug=item.leetcode_slug,
                neetcode_slug=item.neetcode_slug,
                solved_at=item.solved_at,
                checkpoints={item.review_day: item},
            )
            continue
        entry.checkpoints[item.review_day] = item

    def _sort_key(entry: DueProblemEntry) -> tuple[int, datetime]:
        overdue_due = [
            datetime.fromisoformat(cp.due_at)
            for cp in entry.checkpoints.values()
            if cp.status == "overdue"
        ]
        if overdue_due:
            return (0, min(overdue_due))
        all_due = [datetime.fromisoformat(cp.due_at) for cp in entry.checkpoints.values()]
        return (1, min(all_due))

    return sorted(grouped.values(), key=_sort_key)


def _parse_review_day(raw: str) -> int | None:
    value = raw.strip().lower()
    if value in {"7", "7th"}:
        return 7
    if value in {"21", "21st"}:
        return 21
    return None


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
            "✅ No pending/overdue reviews right now.\nUse /list to see your logged problems."
        )
        return
    entries = _group_due_entries(items)
    token_map = token_store.put(
        telegram_user_id, [entry.user_problem_id for entry in entries]
    )
    await _reply_long_text(update, _render_due(entries, token_map, cfg.timezone))


async def done_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = await _ensure_authorized(update, context)
    if cfg is None:
        return
    _interrupt_quiz_if_needed(cfg, update, context)
    token_store: DueTokenStore = context.application.bot_data["due_tokens"]
    telegram_user_id = _telegram_user_id(update)
    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage: /done <token> <7th|21st> (example: /done A1 7th)"
        )
        return
    token = context.args[0].upper()
    review_day = _parse_review_day(context.args[1])
    if review_day is None:
        await update.message.reply_text(
            "Review day must be 7th or 21st. Example: /done A1 21st"
        )
        return
    problem_ref = token_store.get(telegram_user_id, token)
    if problem_ref is None:
        await update.message.reply_text("⚠️ Unknown/expired token. Run /due again.")
        return
    ok = complete_review(
        cfg.db_path, telegram_user_id, problem_ref.user_problem_id, review_day
    )
    if not ok:
        await update.message.reply_text(
            "⚠️ Could not mark done for this review day. Run /due again."
        )
        return
    await update.message.reply_text(f"✅ Marked complete: {token} day {review_day}")


def _render_quiz_question(question: QuizQuestionPayload, model_used: str | None) -> str:
    lines = [
        "🧠 Quiz Time",
        f"Topic: {question.topic}",
        "",
        question.question,
        "",
    ]
    for key in ("A", "B", "C", "D"):
        lines.append(f"{key}) {question.options.get(key, '')}")
    lines.extend(
        [
            "",
            "Reply with A/B/C/D, optionally followed by your explanation.",
            "Use /reveal anytime to show the explanation.",
        ]
    )
    if model_used:
        lines.append(f"Model: {model_used}")
    return "\n".join(lines)


def _render_quiz_feedback(result: AnswerQuizResult) -> str:
    if result.feedback is None:
        return "⚠️ Could not evaluate answer."
    verdict = "✅ Correct" if result.feedback.is_correct else "❌ Not quite"
    lines = [
        verdict,
        f"Summary: {result.feedback.verdict_summary}",
        "",
        result.feedback.formal_feedback,
        "",
        f"Takeaway: {result.feedback.concept_takeaway}",
    ]
    if result.model_used:
        lines.append(f"Model: {result.model_used}")
    return "\n".join(lines)


def _render_quiz_reveal(question: QuizQuestionPayload) -> str:
    lines = [
        "📖 Reveal",
        f"Correct option: {question.correct_option}",
        f"Why: {question.why_correct}",
        "",
        "Other options:",
    ]
    for key in ("A", "B", "C", "D"):
        if key == question.correct_option:
            continue
        explanation = question.why_others_wrong.get(key)
        if explanation:
            lines.append(f"- {key}: {explanation}")
    lines.extend(["", f"Takeaway: {question.concept_takeaway}"])
    return "\n".join(lines)


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


def _render_problem_rows(
    rows: list[dict[str, str]],
    token_map: dict[str, ProblemToken],
    timezone_name: str,
) -> str:
    lines: list[str] = ["📚 Your Problems", ""]
    token_by_problem_id = {
        token.user_problem_id: key for key, token in token_map.items()
    }
    grouped: dict[tuple[str, int, str], list[dict[str, str]]] = {}
    for row in rows:
        level, pattern_label, pattern_key = _roadmap_pattern_info(row["pattern"])
        group_key = (pattern_key, level, pattern_label)
        grouped.setdefault(group_key, []).append(row)

    ordered_groups = sorted(grouped.items(), key=lambda item: (item[0][1], item[0][2].lower()))
    idx = 1
    for (_, _, pattern_label), group_rows in ordered_groups:
        lines.append(f"🧩 {pattern_label}")
        sorted_rows = sorted(
            group_rows,
            key=lambda row: (row["solved_at"], row["title"].lower()),
            reverse=True,
        )
        for row in sorted_rows:
            token = token_by_problem_id.get(int(row["user_problem_id"]))
            leetcode_url = _leetcode_url(row["leetcode_slug"] or None)
            neetcode_url = _neetcode_url(row["neetcode_slug"] or None)
            if token:
                lines.append(f"{idx}. [{token}] {row['title']}")
            else:
                lines.append(f"{idx}. {row['title']}")
            lines.append(
                (
                    f"   {row['difficulty'].title()} • {row['pattern']} • "
                    f"{_format_timestamp_compact(row['solved_at'], timezone_name)}"
                )
            )
            if token:
                lines.append(f"   Use /show {token}")
            if leetcode_url:
                lines.append(f"   🔗 LC: {leetcode_url}")
            if neetcode_url:
                lines.append(f"   🔗 NC: {neetcode_url}")
            idx += 1
        lines.append("")
    if lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def _render_problem_detail(row: dict[str, str], timezone_name: str) -> str:
    leetcode_url = _leetcode_url(row["leetcode_slug"] or None)
    neetcode_url = _neetcode_url(row["neetcode_slug"] or None)
    lines = [
        f"📘 {row['title']}",
        f"Difficulty: {row['difficulty'].title()}",
        f"Pattern: {row['pattern']}",
        f"Solved: {_format_timestamp(row['solved_at'], timezone_name)}",
    ]
    if leetcode_url:
        lines.append(f"LeetCode: {leetcode_url}")
    if neetcode_url:
        lines.append(f"NeetCode: {neetcode_url}")
    lines.append("")
    lines.append("Concepts:")
    lines.append(row["concepts"] or "-")
    lines.append("")
    lines.append("Time complexity:")
    lines.append(row["time_complexity"] or "-")
    lines.append("")
    lines.append("Space complexity:")
    lines.append(row["space_complexity"] or "-")
    if row["notes"]:
        lines.append("")
        lines.append("Notes:")
        lines.append(row["notes"])
    return "\n".join(lines)


def _chunk_text(text: str, chunk_size: int = TELEGRAM_MESSAGE_CHUNK_SIZE) -> list[str]:
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for line in text.splitlines(keepends=True):
        if len(line) > chunk_size:
            if current:
                chunks.append("".join(current).rstrip())
                current = []
                current_len = 0
            start = 0
            while start < len(line):
                chunks.append(line[start : start + chunk_size].rstrip())
                start += chunk_size
            continue

        if current_len + len(line) > chunk_size and current:
            chunks.append("".join(current).rstrip())
            current = [line]
            current_len = len(line)
        else:
            current.append(line)
            current_len += len(line)

    if current:
        chunks.append("".join(current).rstrip())
    return chunks


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
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(log_flow)
    app.add_handler(CommandHandler("due", due_command))
    app.add_handler(CommandHandler("done", done_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("pattern", pattern_command))
    app.add_handler(CommandHandler("list", list_command))
    app.add_handler(CommandHandler("show", show_command))
    app.add_handler(CommandHandler("quiz", quiz_command))
    app.add_handler(CommandHandler("reveal", reveal_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, default_text_command))
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
