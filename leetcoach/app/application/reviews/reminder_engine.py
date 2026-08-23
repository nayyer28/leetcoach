from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
import json
import logging
import sqlite3
import time
from urllib import error, parse, request
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from leetcoach.app.application.problems.problem_refs import format_problem_ref
from leetcoach.app.infrastructure.config.app_config import AppConfig
from leetcoach.app.infrastructure.config.db import get_connection
from leetcoach.app.infrastructure.dao.review_queue_dao import (
    list_next_review_candidates_for_scheduler,
    mark_reviewed,
)
from leetcoach.app.infrastructure.dao.users_dao import mark_user_reminded


LOGGER = logging.getLogger("leetcoach.scheduler")


@dataclass(frozen=True)
class ReminderCandidate:
    user_problem_id: int
    display_id: int
    problem_ref: str
    user_id: int
    review_count: int
    entered_at: str
    solved_at: str
    title: str
    leetcode_slug: str | None
    neetcode_slug: str | None
    telegram_chat_id: str
    timezone: str
    reminder_daily_max: int | None
    reminder_hour_local: int | None
    last_reminded_at: str | None


@dataclass(frozen=True)
class ReminderRunStats:
    scanned: int
    sent: int
    skipped_already_reminded_today: int
    skipped_outside_send_hour: int
    failed: int


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


def was_user_reminded_today(
    *, last_reminded_at: str | None, now_iso: str, timezone_name: str
) -> bool:
    if not last_reminded_at:
        return False
    return _local_date(last_reminded_at, timezone_name) == _local_date(
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
        f"ID: {candidate.problem_ref}",
        f"Problem: {candidate.title}",
        f"First attempt: {_format_compact(candidate.solved_at, candidate.timezone)}",
        f"Reviews completed: {candidate.review_count}",
    ]
    lc = _leetcode_url(candidate.leetcode_slug)
    if lc:
        lines.append(f"🔗 LC: {lc}")
    nc = _neetcode_url(candidate.neetcode_slug)
    if nc:
        lines.append(f"🔗 NC: {nc}")
    lines.append("Use /reviewed <id>")
    return "\n".join(lines)


def row_to_candidate(row: sqlite3.Row) -> ReminderCandidate:
    return ReminderCandidate(
        user_problem_id=int(row["user_problem_id"]),
        display_id=int(row["display_id"]),
        problem_ref=format_problem_ref(int(row["display_id"])),
        user_id=int(row["user_id"]) if row["user_id"] is not None else 0,
        review_count=int(row["review_count"]),
        entered_at=str(row["entered_at"]),
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
        last_reminded_at=(
            str(row["last_reminded_at"]) if row["last_reminded_at"] else None
        ),
    )


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
        # One row per user: the top of that user's priority queue. Users with no
        # problems or reminders_paused=1 are absent.
        rows = list_next_review_candidates_for_scheduler(conn)
        candidates = [row_to_candidate(r) for r in rows]

        sent = 0
        skipped_already_reminded = 0
        skipped_hour = 0
        failed = 0

        for candidate in candidates:
            effective_reminder_hour = (
                candidate.reminder_hour_local
                if candidate.reminder_hour_local is not None
                else config.reminder_hour_local
            )
            if not _is_send_hour(candidate.timezone, now, effective_reminder_hour):
                skipped_hour += 1
                continue

            if was_user_reminded_today(
                last_reminded_at=candidate.last_reminded_at,
                now_iso=now,
                timezone_name=candidate.timezone,
            ):
                skipped_already_reminded += 1
                continue

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

            # Scheduler-sent reminder counts as a review: bump the bucket. Also stamp
            # users.last_reminded_at so we don't double-send today.
            marked = mark_reviewed(
                conn,
                user_id=candidate.user_id,
                user_problem_id=candidate.user_problem_id,
                reviewed_at=now,
            )
            mark_user_reminded(conn, user_id=candidate.user_id, now_iso=now)
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
                "sent": sent,
                "skipped_already_reminded_today": skipped_already_reminded,
                "skipped_outside_send_hour": skipped_hour,
                "failed": failed,
            },
            sort_keys=True,
        ),
    )
    return ReminderRunStats(
        scanned=len(candidates),
        sent=sent,
        skipped_already_reminded_today=skipped_already_reminded,
        skipped_outside_send_hour=skipped_hour,
        failed=failed,
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
