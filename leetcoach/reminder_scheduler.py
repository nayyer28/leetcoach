from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
import json
import logging
import sqlite3
import time
from urllib import error, parse, request
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from leetcoach.config import AppConfig
from leetcoach.dao.problem_reviews_dao import (
    list_pending_review_candidates,
    mark_review_reminded,
)
from leetcoach.db.connection import get_connection


LOGGER = logging.getLogger("leetcoach.scheduler")


@dataclass(frozen=True)
class ReminderCandidate:
    review_id: int
    user_problem_id: int
    review_day: int
    due_at: str
    buffer_until: str
    last_reminded_at: str | None
    solved_at: str
    title: str
    leetcode_slug: str | None
    neetcode_slug: str | None
    telegram_chat_id: str
    timezone: str


@dataclass(frozen=True)
class ReminderRunStats:
    scanned: int
    sent: int
    skipped_already_reminded_today: int
    skipped_outside_send_hour: int
    failed: int
    due_and_unsent: int
    selected: int
    header_sent: int


@dataclass(frozen=True)
class SchedulerPreflightResult:
    ok: bool
    issues: tuple[str, ...]


def _resolve_timezone(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _parse_iso(iso_ts: str) -> datetime:
    dt = datetime.fromisoformat(iso_ts)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _local_date(iso_ts: str, timezone_name: str) -> date:
    return _parse_iso(iso_ts).astimezone(_resolve_timezone(timezone_name)).date()


def should_send_today(candidate: ReminderCandidate, now_iso: str) -> bool:
    if not candidate.last_reminded_at:
        return True
    return _local_date(candidate.last_reminded_at, candidate.timezone) < _local_date(
        now_iso, candidate.timezone
    )


def _is_send_hour(timezone_name: str, now_iso: str, target_hour_local: int) -> bool:
    local_dt = _parse_iso(now_iso).astimezone(_resolve_timezone(timezone_name))
    return local_dt.hour == target_hour_local


def _format_compact(iso_ts: str, timezone_name: str) -> str:
    return _parse_iso(iso_ts).astimezone(_resolve_timezone(timezone_name)).strftime(
        "%d %b %H:%M %Z"
    )


def _leetcode_url(leetcode_slug: str | None) -> str | None:
    if not leetcode_slug:
        return None
    return f"https://leetcode.com/problems/{leetcode_slug}/description/"


def _neetcode_url(neetcode_slug: str | None) -> str | None:
    if not neetcode_slug:
        return None
    return f"https://neetcode.io/problems/{neetcode_slug}/question"


def build_reminder_message(candidate: ReminderCandidate) -> str:
    day_label = "7th" if candidate.review_day == 7 else "21st"
    lines = [
        "⏰ LeetCoach Reminder",
        f"Problem: {candidate.title}",
        f"Checkpoint: Day {candidate.review_day} ({day_label})",
        f"First attempt: {_format_compact(candidate.solved_at, candidate.timezone)}",
        f"Due: {_format_compact(candidate.due_at, candidate.timezone)}",
        f"Grace until: {_format_compact(candidate.buffer_until, candidate.timezone)}",
    ]
    lc = _leetcode_url(candidate.leetcode_slug)
    if lc:
        lines.append(f"🔗 LC: {lc}")
    nc = _neetcode_url(candidate.neetcode_slug)
    if nc:
        lines.append(f"🔗 NC: {nc}")
    lines.append("Use /due, then /done <token> " + day_label)
    return "\n".join(lines)


def build_daily_header_message() -> str:
    return (
        "📌 Daily LeetCoach Review Plan\n"
        "All messages below this are today’s reminder picks."
    )


def _required_tables_exist(conn: sqlite3.Connection) -> tuple[bool, tuple[str, ...]]:
    expected = {
        "schema_migrations",
        "users",
        "problems",
        "user_problems",
        "problem_reviews",
    }
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    found = {str(r["name"]) for r in rows}
    missing = tuple(sorted(expected - found))
    return (len(missing) == 0, missing)


def scheduler_preflight(config: AppConfig) -> SchedulerPreflightResult:
    issues: list[str] = []
    if not config.telegram_bot_token:
        issues.append("LEETCOACH_TELEGRAM_BOT_TOKEN is missing")
    if not (0 <= config.reminder_hour_local <= 23):
        issues.append(
            f"LEETCOACH_REMINDER_HOUR_LOCAL out of range: {config.reminder_hour_local}"
        )
    if config.reminder_daily_max < 1:
        issues.append(
            f"LEETCOACH_REMINDER_DAILY_MAX must be >= 1 (got {config.reminder_daily_max})"
        )

    try:
        with get_connection(config.db_path) as conn:
            tables_ok, missing = _required_tables_exist(conn)
            if not tables_ok:
                issues.append(
                    "Database schema missing required tables: "
                    + ", ".join(missing)
                    + " (run `lch migrate`)"
                )
    except sqlite3.Error as exc:
        issues.append(f"Database open/validation failed: {exc}")

    return SchedulerPreflightResult(ok=len(issues) == 0, issues=tuple(issues))


def _send_telegram_message(token: str, chat_id: str, text: str) -> tuple[bool, str]:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = parse.urlencode(
        {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")
    req = request.Request(url, data=body, method="POST")
    try:
        with request.urlopen(req, timeout=20.0) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return False, f"HTTP {exc.code}: {detail}"
    except error.URLError as exc:
        return False, f"Network error: {exc.reason}"
    except TimeoutError:
        return False, "Request timed out"

    if payload.get("ok") is True:
        return True, "ok"
    return False, f"Telegram error payload: {payload}"


def run_scheduler_once(
    config: AppConfig,
    *,
    now_iso: str | None = None,
    progress: callable | None = None,
) -> ReminderRunStats:
    preflight = scheduler_preflight(config)
    if not preflight.ok:
        raise RuntimeError("Scheduler preflight failed: " + " | ".join(preflight.issues))

    now = now_iso or datetime.now(UTC).isoformat()
    with get_connection(config.db_path) as conn:
        rows = list_pending_review_candidates(conn, now_iso=now)
        candidates = [
            ReminderCandidate(
                review_id=int(r["review_id"]),
                user_problem_id=int(r["user_problem_id"]),
                review_day=int(r["review_day"]),
                due_at=str(r["due_at"]),
                buffer_until=str(r["buffer_until"]),
                last_reminded_at=(
                    str(r["last_reminded_at"]) if r["last_reminded_at"] else None
                ),
                solved_at=str(r["solved_at"]),
                title=str(r["title"]),
                leetcode_slug=(str(r["leetcode_slug"]) if r["leetcode_slug"] else None),
                neetcode_slug=(str(r["neetcode_slug"]) if r["neetcode_slug"] else None),
                telegram_chat_id=str(r["telegram_chat_id"]),
                timezone=str(r["timezone"]),
            )
            for r in rows
        ]

        sent = 0
        skipped = 0
        skipped_hour = 0
        failed = 0
        due_and_unsent_total = 0
        selected_total = 0
        header_sent = 0

        by_chat: dict[tuple[str, str], list[ReminderCandidate]] = {}
        for c in candidates:
            by_chat.setdefault((c.telegram_chat_id, c.timezone), []).append(c)

        for (chat_id, timezone), group in by_chat.items():
            if not _is_send_hour(timezone, now, config.reminder_hour_local):
                skipped_hour += len(group)
                continue

            due_and_unsent = [c for c in group if should_send_today(c, now)]
            due_and_unsent_total += len(due_and_unsent)
            skipped += len(group) - len(due_and_unsent)
            if not due_and_unsent:
                continue

            # Keep one candidate per problem to avoid sending two checkpoints for same problem in one day.
            unique_by_problem: dict[int, ReminderCandidate] = {}
            for c in sorted(due_and_unsent, key=lambda item: datetime.fromisoformat(item.due_at)):
                unique_by_problem.setdefault(c.user_problem_id, c)
            unique = list(unique_by_problem.values())

            def _is_pending(c: ReminderCandidate) -> bool:
                return _parse_iso(now) <= _parse_iso(c.buffer_until)

            pending = sorted(
                [c for c in unique if _is_pending(c)],
                key=lambda item: _parse_iso(item.due_at),
            )
            overdue = sorted(
                [c for c in unique if not _is_pending(c)],
                key=lambda item: _parse_iso(item.due_at),
            )

            selected: list[ReminderCandidate] = []
            if pending:
                selected.append(pending[0])
            if overdue and len(selected) < config.reminder_daily_max:
                selected.append(overdue[0])
            for c in pending[1:] + overdue[1:]:
                if len(selected) >= config.reminder_daily_max:
                    break
                selected.append(c)

            if not selected:
                continue
            selected_total += len(selected)

            LOGGER.info(
                "[scheduler.chat] %s",
                json.dumps(
                    {
                        "chat_id": chat_id,
                        "timezone": timezone,
                        "group_size": len(group),
                        "due_and_unsent": len(due_and_unsent),
                        "selected": len(selected),
                        "pending_selected": sum(
                            1 for c in selected if _parse_iso(now) <= _parse_iso(c.buffer_until)
                        ),
                        "overdue_selected": sum(
                            1 for c in selected if _parse_iso(now) > _parse_iso(c.buffer_until)
                        ),
                    },
                    sort_keys=True,
                ),
            )

            header_ok, header_detail = _send_telegram_message(
                config.telegram_bot_token, chat_id, build_daily_header_message()
            )
            if not header_ok:
                failed += 1
                LOGGER.error(
                    "Reminder header send failed (chat_id=%s): %s",
                    chat_id,
                    header_detail,
                )
                continue
            header_sent += 1

            for candidate in selected:
                text = build_reminder_message(candidate)
                ok, detail = _send_telegram_message(
                    config.telegram_bot_token, candidate.telegram_chat_id, text
                )
                if not ok:
                    failed += 1
                    LOGGER.error(
                        "Reminder send failed (review_id=%s, chat_id=%s): %s",
                        candidate.review_id,
                        candidate.telegram_chat_id,
                        detail,
                    )
                    continue

                marked = mark_review_reminded(
                    conn, review_id=candidate.review_id, reminded_at=now
                )
                if marked:
                    sent += 1
                    if progress:
                        progress(
                            f"[scheduler] sent review_id={candidate.review_id} day={candidate.review_day}"
                        )
                else:
                    failed += 1

        conn.commit()
    LOGGER.info(
        "[scheduler.run] %s",
        json.dumps(
            {
                "scanned": len(candidates),
                "due_and_unsent": due_and_unsent_total,
                "selected": selected_total,
                "header_sent": header_sent,
                "sent": sent,
                "skipped_already_reminded_today": skipped,
                "skipped_outside_send_hour": skipped_hour,
                "failed": failed,
            },
            sort_keys=True,
        ),
    )
    return ReminderRunStats(
        scanned=len(candidates),
        sent=sent,
        skipped_already_reminded_today=skipped,
        skipped_outside_send_hour=skipped_hour,
        failed=failed,
        due_and_unsent=due_and_unsent_total,
        selected=selected_total,
        header_sent=header_sent,
    )


def run_scheduler_loop(
    config: AppConfig,
    *,
    interval_seconds: int,
    progress: callable | None = None,
) -> None:
    if interval_seconds < 10:
        raise ValueError("interval_seconds must be at least 10")

    while True:
        stats = run_scheduler_once(config=config, progress=progress)
        if progress:
            progress(
                (
                    f"[scheduler] scanned={stats.scanned} sent={stats.sent} "
                    f"skipped={stats.skipped_already_reminded_today} "
                    f"outside_hour={stats.skipped_outside_send_hour} failed={stats.failed}"
                )
            )
        time.sleep(interval_seconds)
