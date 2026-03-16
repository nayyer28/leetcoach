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
from leetcoach.dao.review_queue_dao import (
    get_last_review_requested_at_for_user,
    list_next_review_candidates_for_scheduler,
    mark_review_requested,
)
from leetcoach.db.connection import get_connection


LOGGER = logging.getLogger("leetcoach.scheduler")


@dataclass(frozen=True)
class ReminderCandidate:
    user_problem_id: int
    user_id: int
    queue_position: int
    last_review_requested_at: str | None
    last_reviewed_at: str | None
    review_count: int
    solved_at: str
    title: str
    leetcode_slug: str | None
    neetcode_slug: str | None
    telegram_chat_id: str
    timezone: str
    reminder_daily_max: int | None
    reminder_hour_local: int | None


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
    if not candidate.last_review_requested_at:
        return True
    return _local_date(candidate.last_review_requested_at, candidate.timezone) < _local_date(
        now_iso, candidate.timezone
    )


def was_group_reminded_today(
    candidates: list[ReminderCandidate], now_iso: str, timezone_name: str
) -> bool:
    today = _local_date(now_iso, timezone_name)
    return any(
        candidate.last_review_requested_at
        and _local_date(candidate.last_review_requested_at, timezone_name) == today
        for candidate in candidates
    )


def was_user_reminded_today(
    *, last_requested_at: str | None, now_iso: str, timezone_name: str
) -> bool:
    if not last_requested_at:
        return False
    return _local_date(last_requested_at, timezone_name) == _local_date(
        now_iso, timezone_name
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
    lines = [
        "⏰ LeetCoach Reminder",
        f"Problem: {candidate.title}",
        f"First attempt: {_format_compact(candidate.solved_at, candidate.timezone)}",
        f"Reviews completed: {candidate.review_count}",
        f"Queue position: {candidate.queue_position}",
    ]
    if candidate.last_reviewed_at:
        lines.append(
            f"Last reviewed: {_format_compact(candidate.last_reviewed_at, candidate.timezone)}"
        )
    lc = _leetcode_url(candidate.leetcode_slug)
    if lc:
        lines.append(f"🔗 LC: {lc}")
    nc = _neetcode_url(candidate.neetcode_slug)
    if nc:
        lines.append(f"🔗 NC: {nc}")
    lines.append("Use /due, then /reviewed <token>")
    return "\n".join(lines)


def build_daily_header_message() -> str:
    return (
        "📌 Daily LeetCoach Review Plan\n"
        "All messages below this are today’s reminder picks."
    )


def row_to_candidate(row: sqlite3.Row) -> ReminderCandidate:
    return ReminderCandidate(
        user_problem_id=int(row["user_problem_id"]),
        user_id=int(row["user_id"]) if row["user_id"] is not None else 0,
        queue_position=int(row["queue_position"]),
        last_review_requested_at=(
            str(row["last_review_requested_at"])
            if row["last_review_requested_at"]
            else None
        ),
        last_reviewed_at=(
            str(row["last_reviewed_at"]) if row["last_reviewed_at"] else None
        ),
        review_count=int(row["review_count"]),
        solved_at=str(row["solved_at"]),
        title=str(row["title"]),
        leetcode_slug=(str(row["leetcode_slug"]) if row["leetcode_slug"] else None),
        neetcode_slug=(str(row["neetcode_slug"]) if row["neetcode_slug"] else None),
        telegram_chat_id=str(row["telegram_chat_id"]),
        timezone=str(row["timezone"]),
        reminder_daily_max=(
            int(row["reminder_daily_max"]) if row["reminder_daily_max"] is not None else None
        ),
        reminder_hour_local=(
            int(row["reminder_hour_local"])
            if row["reminder_hour_local"] is not None
            else None
        ),
    )


def select_candidates_for_batch(
    candidates: list[ReminderCandidate], *, now_iso: str, daily_max: int
) -> list[ReminderCandidate]:
    eligible = [candidate for candidate in candidates if should_send_today(candidate, now_iso)]
    eligible.sort(key=lambda item: item.queue_position)
    return eligible[:daily_max]


def _required_tables_exist(conn: sqlite3.Connection) -> tuple[bool, tuple[str, ...]]:
    expected = {
        "schema_migrations",
        "users",
        "problems",
        "user_problems",
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
        rows = list_next_review_candidates_for_scheduler(conn)
        candidates = [row_to_candidate(r) for r in rows]

        sent = 0
        skipped = 0
        skipped_hour = 0
        failed = 0
        due_and_unsent_total = 0
        selected_total = 0
        header_sent = 0

        by_chat: dict[tuple[int, str, str, int | None, int | None], list[ReminderCandidate]] = {}
        for c in candidates:
            by_chat.setdefault(
                (
                    c.user_id,
                    c.telegram_chat_id,
                    c.timezone,
                    c.reminder_daily_max,
                    c.reminder_hour_local,
                ),
                [],
            ).append(c)

        for (user_id, chat_id, timezone, reminder_daily_max, reminder_hour_local), group in by_chat.items():
            effective_reminder_hour = (
                reminder_hour_local
                if reminder_hour_local is not None
                else config.reminder_hour_local
            )
            if not _is_send_hour(timezone, now, effective_reminder_hour):
                skipped_hour += len(group)
                continue

            last_requested_at = get_last_review_requested_at_for_user(
                conn, user_id=user_id
            )
            if was_user_reminded_today(
                last_requested_at=last_requested_at,
                now_iso=now,
                timezone_name=timezone,
            ):
                skipped += len(group)
                continue

            selectable = [c for c in group if should_send_today(c, now)]
            due_and_unsent_total += len(selectable)
            skipped += len(group) - len(selectable)
            if not selectable:
                continue

            effective_daily_max = reminder_daily_max or config.reminder_daily_max
            selected = select_candidates_for_batch(
                group, now_iso=now, daily_max=effective_daily_max
            )

            if not selected:
                continue
            selected_total += len(selected)

            LOGGER.info(
                "[scheduler.chat] %s",
                json.dumps(
                    {
                        "chat_id": chat_id,
                        "timezone": timezone,
                        "reminder_daily_max": effective_daily_max,
                        "reminder_hour_local": effective_reminder_hour,
                        "group_size": len(group),
                        "due_and_unsent": len(selectable),
                        "selected": len(selected),
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
                        "Reminder send failed (user_problem_id=%s, chat_id=%s): %s",
                        candidate.user_problem_id,
                        candidate.telegram_chat_id,
                        detail,
                    )
                    continue

                marked = mark_review_requested(
                    conn,
                    user_id=candidate.user_id,
                    user_problem_id=candidate.user_problem_id,
                    requested_at=now,
                )
                if marked:
                    sent += 1
                    if progress:
                        progress(
                            f"[scheduler] sent user_problem_id={candidate.user_problem_id}"
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
