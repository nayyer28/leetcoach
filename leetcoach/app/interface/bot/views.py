from __future__ import annotations

import re
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from leetcoach.patterns import roadmap_pattern_info
from leetcoach.app.application.quiz.common import AnswerQuizResult, QuizQuestionPayload
from leetcoach.app.application.reviews.due_reviews import DueReviewItem


TELEGRAM_MESSAGE_CHUNK_SIZE = 3500
SLUG_INPUT_RE = re.compile(r"^[a-z0-9-]+$", re.IGNORECASE)
LEETCODE_INPUT_RE = re.compile(
    r"^https?://leetcode\.com/problems/([^/?#]+)(?:/.*)?$",
    re.IGNORECASE,
)
NEETCODE_INPUT_RE = re.compile(
    r"^https?://neetcode\.io/problems/([^/?#]+)(?:/.*)?$",
    re.IGNORECASE,
)


def resolve_timezone(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def format_timestamp(iso_ts: str, timezone_name: str) -> str:
    dt = datetime.fromisoformat(iso_ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    local_dt = dt.astimezone(resolve_timezone(timezone_name))
    return local_dt.strftime("%d %b %Y, %H:%M %Z")


def format_timestamp_compact(iso_ts: str, timezone_name: str) -> str:
    dt = datetime.fromisoformat(iso_ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    local_dt = dt.astimezone(resolve_timezone(timezone_name))
    return local_dt.strftime("%d %b %H:%M %Z")


def leetcode_url(leetcode_slug: str | None) -> str | None:
    if not leetcode_slug:
        return None
    return f"https://leetcode.com/problems/{leetcode_slug}/description/"


def neetcode_url(neetcode_slug: str | None) -> str | None:
    if not neetcode_slug:
        return None
    return f"https://neetcode.io/problems/{neetcode_slug}/question"


def normalize_solved_at(raw_value: str, timezone_name: str) -> str | None:
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
        parsed = parsed.replace(tzinfo=resolve_timezone(timezone_name))
    else:
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=resolve_timezone(timezone_name))

    return parsed.astimezone(UTC).isoformat()


def commands_help_text() -> str:
    return (
        "🤖 <b>leetcoach Command Menu</b>\n\n"
        "📝 <b>Log</b>\n"
        "• /log\n"
        "• /log show [n]\n\n"
        "🧠 <b>Quiz</b>\n"
        "• /quiz\n"
        "• /quiz &lt;topic&gt;\n"
        "• /reveal\n\n"
        "⏰ <b>Review</b>\n"
        "• /due\n"
        "• /reviewed P1\n\n"
        "• /remind\n"
        "• /remind last\n"
        "• /remind new\n"
        "• /remind count &lt;n&gt;\n"
        "• /remind time &lt;hour&gt;\n\n"
        "📚 <b>Browse</b>\n"
        "• /list\n"
        "• /pattern &lt;text&gt;\n"
        "• /search &lt;text&gt;\n\n"
        "🔍 <b>Details</b>\n"
        "• /show P1\n"
        "• /edit P1 lc <slug-or-url>\n\n"
        "👤 <b>Registration</b>\n"
        "• /register\n\n"
        "ℹ️ <b>Help</b>\n"
        "• /help\n"
        "• /hi"
    )


def unknown_text_help_text() -> str:
    return (
        "🤔 I didn’t understand that.\n\n"
        "Try one of these commands:\n"
        "• /help\n"
        "• /log\n"
        "• /due\n"
        "• /remind\n"
        "• /reviewed <id>\n"
        "• /list\n"
        "• /search <text>\n"
        "• /pattern <name>\n"
        "• /show <id>\n"
        "• /edit <id> <field> <value>\n"
        "• /quiz [topic]\n"
        "• /reveal"
    )


def unknown_command_help_text(command_text: str) -> str:
    return (
        f"🤔 I don’t recognize `{command_text}`.\n\n"
        "Try one of these commands:\n"
        "• /help\n"
        "• /log\n"
        "• /due\n"
        "• /remind\n"
        "• /reviewed <id>\n"
        "• /list\n"
        "• /search <text>\n"
        "• /pattern <name>\n"
        "• /show <id>\n"
        "• /edit <id> <field> <value>\n"
        "• /quiz [topic]\n"
        "• /reveal"
    )


def log_prompt(step: int, total: int, text: str) -> str:
    return f"🧩 [{step}/{total}] {text}\nSend /cancel to stop."


def normalize_difficulty_input(raw_value: str) -> str | None:
    normalized = raw_value.strip().lower()
    if normalized in {"easy", "medium", "hard"}:
        return normalized
    return None


def extract_problem_slug(raw_value: str, *, provider: str) -> str | None:
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


def render_due(items: list[DueReviewItem], timezone_name: str) -> str:
    lines: list[str] = ["⏰ Due Reviews", ""]
    for idx, item in enumerate(items, start=1):
        lines.append(f"{idx}. [{item.problem_ref}] {item.title}")
        lines.append(
            f"   First attempt • {format_timestamp_compact(item.solved_at, timezone_name)}"
        )
        lines.append(f"   Reviews completed • {item.review_count}")
        lines.append(
            "   Outstanding since • "
            + format_timestamp_compact(item.requested_at, timezone_name)
        )
        if item.last_reviewed_at:
            lines.append(
                "   Last reviewed • "
                + format_timestamp_compact(item.last_reviewed_at, timezone_name)
            )
        lc = leetcode_url(item.leetcode_slug)
        if lc:
            lines.append(f"   🔗 LC: {lc}")
        nc = neetcode_url(item.neetcode_slug)
        if nc:
            lines.append(f"   🔗 NC: {nc}")
        lines.append("")
    if lines and not lines[-1]:
        lines.pop()
    lines.append("")
    lines.append("Use /reviewed P1")
    return "\n".join(lines)


def render_remind_settings(
    *,
    custom_count: int | None,
    effective_count: int,
    custom_hour: int | None,
    effective_hour: int,
) -> str:
    return "\n".join(
        [
            "⏰ Reminder Settings",
            f"Daily reminder count: {effective_count}",
            f"Reminder hour: {effective_hour:02d}:00",
            (
                "Count source: app default"
                if custom_count is None
                else "Count source: your custom setting"
            ),
            (
                "Hour source: app default"
                if custom_hour is None
                else "Hour source: your custom setting"
            ),
            "",
            "Commands: /remind last, /remind new, /remind count <n>, /remind time <hour>",
        ]
    )


def render_last_batch(batch: list[object], timezone_name: str, row_to_candidate) -> str:
    sent_at = str(batch[0]["last_review_requested_at"])
    lines = [
        "🕘 Last Reminder Batch",
        f"Sent at: {format_timestamp(sent_at, timezone_name)}",
        "",
    ]
    for index, row in enumerate(batch, start=1):
        candidate = row_to_candidate(row)
        lines.append(f"{index}. [{candidate.problem_ref}] {candidate.title}")
        lines.append(f"   Reviews completed: {candidate.review_count}")
        lc = leetcode_url(candidate.leetcode_slug)
        if lc:
            lines.append(f"   🔗 LC: {lc}")
        nc = neetcode_url(candidate.neetcode_slug)
        if nc:
            lines.append(f"   🔗 NC: {nc}")
    return "\n".join(lines)


def remind_usage_text() -> str:
    return (
        "Usage:\n"
        "/remind\n"
        "/remind last\n"
        "/remind new\n"
        "/remind count <n>\n"
        "/remind time <hour>"
    )


def render_quiz_question(question: QuizQuestionPayload, model_used: str | None) -> str:
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


def render_quiz_feedback(result: AnswerQuizResult) -> str:
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


def render_quiz_reveal(question: QuizQuestionPayload) -> str:
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


def render_problem_rows(
    rows: list[dict[str, str]],
    timezone_name: str,
) -> str:
    lines: list[str] = ["📚 Your Problems", ""]
    grouped: dict[tuple[str, int, str], list[dict[str, str]]] = {}
    for row in rows:
        level, pattern_label, pattern_key = roadmap_pattern_info(row["pattern"])
        group_key = (pattern_key, level, pattern_label)
        grouped.setdefault(group_key, []).append(row)

    ordered_groups = sorted(
        grouped.items(), key=lambda item: (item[0][1], item[0][2].lower())
    )
    idx = 1
    for (_, _, pattern_label), group_rows in ordered_groups:
        lines.append(f"🧩 {pattern_label}")
        sorted_rows = sorted(
            group_rows,
            key=lambda row: (row["solved_at"], row["title"].lower()),
        )
        for row in sorted_rows:
            lc = leetcode_url(row["leetcode_slug"] or None)
            nc = neetcode_url(row["neetcode_slug"] or None)
            lines.append(f"{idx}. [{row['problem_ref']}] {row['title']}")
            lines.append(
                (
                    f"   {row['difficulty'].title()} • {row['pattern']} • "
                    f"{format_timestamp_compact(row['solved_at'], timezone_name)}"
                )
            )
            lines.append(f"   Use /show {row['problem_ref']}")
            if lc:
                lines.append(f"   🔗 LC: {lc}")
            if nc:
                lines.append(f"   🔗 NC: {nc}")
            idx += 1
        lines.append("")
    if lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def render_problem_detail(row: dict[str, str], timezone_name: str) -> str:
    lc = leetcode_url(row["leetcode_slug"] or None)
    nc = neetcode_url(row["neetcode_slug"] or None)
    lines = [
        f"📘 {row['title']}",
        f"ID: {row['problem_ref']}",
        f"Difficulty: {row['difficulty'].title()}",
        f"Pattern: {row['pattern']}",
        f"Solved: {format_timestamp(row['solved_at'], timezone_name)}",
    ]
    if lc:
        lines.append(f"LeetCode: {lc}")
    if nc:
        lines.append(f"NeetCode: {nc}")
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


def chunk_text(text: str, chunk_size: int = TELEGRAM_MESSAGE_CHUNK_SIZE) -> list[str]:
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
