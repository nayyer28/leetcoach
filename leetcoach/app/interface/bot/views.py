from __future__ import annotations

from html import escape
import re
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import dateparser

from leetcoach.app.application.shared.patterns import roadmap_pattern_info
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

    parsed: datetime | None = None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d %H:%M")
        except ValueError:
            parsed = _parse_human_datetime(value, timezone_name)
            if parsed is None:
                return None
        else:
            parsed = parsed.replace(tzinfo=resolve_timezone(timezone_name))
    else:
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=resolve_timezone(timezone_name))

    return parsed.astimezone(UTC).isoformat()


def _parse_human_datetime(value: str, timezone_name: str) -> datetime | None:
    timezone = resolve_timezone(timezone_name)
    relative_base = datetime.now(timezone)
    normalized_value = re.sub(
        r"\b(today|yesterday|day before yesterday)\s+at\s+(\d{1,2})(?!:\d{2})\b",
        r"\1 \2:00",
        value,
        flags=re.IGNORECASE,
    )
    normalized_value = re.sub(
        r"\b(today|yesterday|day before yesterday)\s+at\s+",
        r"\1 ",
        normalized_value,
        flags=re.IGNORECASE,
    )
    parsed = dateparser.parse(
        normalized_value,
        languages=["en"],
        settings={
            "RELATIVE_BASE": relative_base,
            "TIMEZONE": timezone_name,
            "TO_TIMEZONE": timezone_name,
            "RETURN_AS_TIMEZONE_AWARE": True,
            "PREFER_DATES_FROM": "past",
        },
    )
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone)
    return parsed.astimezone(timezone)


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
        "💬 <b>Ask</b>\n"
        "• /ask &lt;question&gt;\n\n"
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
        "• /edit P1\n\n"
        "👤 <b>Registration</b>\n"
        "• /register\n\n"
        "ℹ️ <b>Help</b>\n"
        "• /hi"
    )


def unknown_text_help_text() -> str:
    return (
        "🤔 I didn’t understand that.\n\n"
        "Try one of these commands:\n"
        "• /hi\n"
        "• /ask <question>\n"
        "• /log\n"
        "• /due\n"
        "• /remind\n"
        "• /reviewed <id>\n"
        "• /list\n"
        "• /search <text>\n"
        "• /pattern <name>\n"
        "• /show <id>\n"
        "• /edit <id>\n"
        "• /quiz [topic]\n"
        "• /reveal"
    )


def unknown_command_help_text(command_text: str) -> str:
    return (
        f"🤔 I don’t recognize `{command_text}`.\n\n"
        "Try one of these commands:\n"
        "• /hi\n"
        "• /ask <question>\n"
        "• /log\n"
        "• /due\n"
        "• /remind\n"
        "• /reviewed <id>\n"
        "• /list\n"
        "• /search <text>\n"
        "• /pattern <name>\n"
        "• /show <id>\n"
        "• /edit <id>\n"
        "• /quiz [topic]\n"
        "• /reveal"
    )


def log_prompt(step: int, total: int, text: str) -> str:
    return f"🧩 [{step}/{total}] {text}\nSend /cancel to stop."


def _display_optional_value(value: str | None) -> str:
    return value if value else "-"


def _bold(label: str) -> str:
    return f"<b>{escape(label)}</b>"


def _code(value: str) -> str:
    return f"<code>{escape(value)}</code>"


def _link(label: str, url: str) -> str:
    return f'<a href="{escape(url, quote=True)}">{escape(label)}</a>'


def _optional_text(value: str | None) -> str:
    return escape(value) if value else "-"


def _highlight_html(value: str, query: str) -> str:
    if not query.strip():
        return escape(value)
    pattern = re.compile(re.escape(query.strip()), re.IGNORECASE)
    parts: list[str] = []
    last_end = 0
    for match in pattern.finditer(value):
        parts.append(escape(value[last_end : match.start()]))
        parts.append(f"<b>{escape(match.group(0))}</b>")
        last_end = match.end()
    parts.append(escape(value[last_end:]))
    return "".join(parts)


def _render_notes_html(value: str) -> str:
    text = value.strip()
    fence_pattern = re.compile(r"```(?:[A-Za-z0-9_+-]+)?\n?(.*?)```", re.DOTALL)
    if "```" not in text:
        return escape(text)

    parts: list[str] = []
    last_end = 0
    for match in fence_pattern.finditer(text):
        prefix = text[last_end : match.start()]
        if prefix.strip():
            parts.append(escape(prefix.strip()))
        code_body = match.group(1).strip("\n")
        parts.append(f"<pre><code>{escape(code_body)}</code></pre>")
        last_end = match.end()
    suffix = text[last_end:]
    if suffix.strip():
        parts.append(escape(suffix.strip()))
    return "\n\n".join(parts) if parts else escape(text)


def render_log_review(payload: dict[str, str | None], timezone_name: str) -> str:
    lines = [
        "🧾 <b>Review Problem Log</b>",
        "",
        f"{_bold('Title:')} {_optional_text(payload.get('title'))}",
        f"{_bold('Difficulty:')} {_optional_text((payload.get('difficulty') or '').title() or None)}",
        f"{_bold('LeetCode URL:')} {_optional_text(leetcode_url(payload.get('leetcode_slug')))}",
        f"{_bold('NeetCode URL:')} {_optional_text(neetcode_url(payload.get('neetcode_slug')))}",
        f"{_bold('Pattern:')} {_optional_text(payload.get('pattern'))}",
        f"{_bold('Solved:')} {_optional_text(format_timestamp(payload['solved_at'], timezone_name) if payload.get('solved_at') else None)}",
        f"{_bold('Concepts:')} {_optional_text(payload.get('concepts'))}",
        f"{_bold('Time Complexity:')} {_optional_text(payload.get('time_complexity'))}",
        f"{_bold('Space Complexity:')} {_optional_text(payload.get('space_complexity'))}",
        f"{_bold('Notes:')} {_optional_text(payload.get('notes'))}",
        "",
        "<i>Save this log, edit a field, or cancel.</i>",
    ]
    return "\n".join(lines)


def render_log_edit_prompt(field_label: str, current_value: str | None) -> str:
    return (
        f"✏️ <b>Editing {escape(field_label)}</b>\n"
        f"{_bold('Current value:')}\n{_optional_text(current_value)}\n\n"
        "Send the new value now.\n"
        "Use '-' to clear optional text fields."
    )


def render_edit_prompt(problem_ref: str, field_label: str, current_value: str | None) -> str:
    return (
        f"✏️ <b>Editing {escape(problem_ref)} · {escape(field_label)}</b>\n"
        f"{_bold('Current value:')}\n{_optional_text(current_value)}\n\n"
        "Send the new value now.\n"
        "Use '-' to clear optional text fields."
    )


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
    lines: list[str] = ["⏰ <b>Due Reviews</b>", ""]
    for idx, item in enumerate(items, start=1):
        lines.append(f"{idx}. {_code(item.problem_ref)} {escape(item.title)}")
        lines.append(
            f"   {_bold('First attempt:')} {escape(format_timestamp_compact(item.solved_at, timezone_name))}"
        )
        lines.append(f"   {_bold('Reviews completed:')} {item.review_count}")
        lines.append(
            f"   {_bold('Outstanding since:')} "
            + escape(format_timestamp_compact(item.requested_at, timezone_name))
        )
        if item.last_reviewed_at:
            lines.append(
                f"   {_bold('Last reviewed:')} "
                + escape(format_timestamp_compact(item.last_reviewed_at, timezone_name))
            )
        lc = leetcode_url(item.leetcode_slug)
        if lc:
            lines.append(f"   {_bold('LC:')} {_link('Open LeetCode', lc)}")
        nc = neetcode_url(item.neetcode_slug)
        if nc:
            lines.append(f"   {_bold('NC:')} {_link('Open NeetCode', nc)}")
        lines.append("")
    if lines and not lines[-1]:
        lines.pop()
    lines.append("")
    lines.append(f"Use {_code('/reviewed P1')}")
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
            "⏰ <b>Reminder Settings</b>",
            f"{_bold('Daily reminder count:')} {effective_count}",
            f"{_bold('Reminder hour:')} {effective_hour:02d}:00",
            (
                f"{_bold('Count source:')} app default"
                if custom_count is None
                else f"{_bold('Count source:')} your custom setting"
            ),
            (
                f"{_bold('Hour source:')} app default"
                if custom_hour is None
                else f"{_bold('Hour source:')} your custom setting"
            ),
            "",
            f"{_bold('Commands:')} /remind last, /remind new, /remind count &lt;n&gt;, /remind time &lt;hour&gt;",
        ]
    )


def render_last_batch(batch: list[object], timezone_name: str, row_to_candidate) -> str:
    sent_at = str(batch[0]["last_review_requested_at"])
    lines = [
        "🕘 <b>Last Reminder Batch</b>",
        f"{_bold('Sent at:')} {escape(format_timestamp(sent_at, timezone_name))}",
        "",
    ]
    for index, row in enumerate(batch, start=1):
        candidate = row_to_candidate(row)
        lines.append(f"{index}. {_code(candidate.problem_ref)} {escape(candidate.title)}")
        lines.append(f"   {_bold('Reviews completed:')} {candidate.review_count}")
        lc = leetcode_url(candidate.leetcode_slug)
        if lc:
            lines.append(f"   {_bold('LC:')} {_link('Open LeetCode', lc)}")
        nc = neetcode_url(candidate.neetcode_slug)
        if nc:
            lines.append(f"   {_bold('NC:')} {_link('Open NeetCode', nc)}")
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
    search_query: str | None = None,
) -> str:
    lines: list[str] = ["📚 <b>Your Problems</b>", ""]
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
        lines.append(f"🧩 <b>{escape(pattern_label)}</b>")
        sorted_rows = sorted(
            group_rows,
            key=lambda row: (row["solved_at"], row["title"].lower()),
        )
        for row in sorted_rows:
            lc = leetcode_url(row["leetcode_slug"] or None)
            nc = neetcode_url(row["neetcode_slug"] or None)
            lines.append(f"{idx}. {_code(row['problem_ref'])} {escape(row['title'])}")
            lines.append(
                (
                    f"   <i>{escape(row['difficulty'].title())} • {escape(row['pattern'])} • "
                    f"{escape(format_timestamp_compact(row['solved_at'], timezone_name))}</i>"
                )
            )
            lines.append(f"   Use {_code('/show ' + row['problem_ref'])}")
            if lc:
                lines.append(f"   {_bold('LC:')} {_link('Open LeetCode', lc)}")
            if nc:
                lines.append(f"   {_bold('NC:')} {_link('Open NeetCode', nc)}")
            if search_query and row.get("matched_field") and row.get("matched_text"):
                lines.append(
                    "   "
                    f"{_bold('Matched on:')} {escape(str(row['matched_field']).title())} "
                    f"({_highlight_html(str(row['matched_text']), search_query)})"
                )
            idx += 1
        lines.append("")
    if lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def render_problem_detail(row: dict[str, str], timezone_name: str) -> str:
    lc = leetcode_url(row["leetcode_slug"] or None)
    nc = neetcode_url(row["neetcode_slug"] or None)
    lines = [
        f"📘 <b>{escape(row['title'])}</b>",
        f"{_bold('ID:')} {_code(row['problem_ref'])}",
        f"{_bold('Difficulty:')} {escape(row['difficulty'].title())}",
        f"{_bold('Pattern:')} {escape(row['pattern'])}",
        f"{_bold('Solved:')} {escape(format_timestamp(row['solved_at'], timezone_name))}",
    ]
    if lc:
        lines.append(f"{_bold('LeetCode:')} {_link('Open LeetCode', lc)}")
    if nc:
        lines.append(f"{_bold('NeetCode:')} {_link('Open NeetCode', nc)}")
    lines.append("")
    lines.append(_bold("Concepts:"))
    lines.append(_optional_text(row["concepts"]))
    lines.append("")
    lines.append(_bold("Time complexity:"))
    lines.append(_optional_text(row["time_complexity"]))
    lines.append("")
    lines.append(_bold("Space complexity:"))
    lines.append(_optional_text(row["space_complexity"]))
    if row["notes"]:
        lines.append("")
        lines.append(_bold("Notes:"))
        lines.append(_render_notes_html(row["notes"]))
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
