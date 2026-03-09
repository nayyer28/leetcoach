from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
import json
import logging
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
    failed: int


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
    if not config.telegram_bot_token:
        raise RuntimeError("LEETCOACH_TELEGRAM_BOT_TOKEN is not configured")

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
        failed = 0
        for candidate in candidates:
            if not should_send_today(candidate, now):
                skipped += 1
                continue
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
    return ReminderRunStats(
        scanned=len(candidates),
        sent=sent,
        skipped_already_reminded_today=skipped,
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
                    f"skipped={stats.skipped_already_reminded_today} failed={stats.failed}"
                )
            )
        time.sleep(interval_seconds)

