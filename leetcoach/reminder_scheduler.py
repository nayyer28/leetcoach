"""Backward-compatible scheduler import path."""

from leetcoach.app.application.reviews import reminder_engine as _engine

ReminderCandidate = _engine.ReminderCandidate
ReminderRunStats = _engine.ReminderRunStats
SchedulerPreflightResult = _engine.SchedulerPreflightResult
build_daily_header_message = _engine.build_daily_header_message
build_reminder_message = _engine.build_reminder_message
row_to_candidate = _engine.row_to_candidate
scheduler_preflight = _engine.scheduler_preflight
select_candidates_for_batch = _engine.select_candidates_for_batch
should_send_today = _engine.should_send_today
was_group_reminded_today = _engine.was_group_reminded_today
was_user_reminded_today = _engine.was_user_reminded_today
_send_telegram_message = _engine._send_telegram_message


def run_scheduler_once(*args, **kwargs):
    _engine._send_telegram_message = _send_telegram_message
    return _engine.run_scheduler_once(*args, **kwargs)


def run_scheduler_loop(*args, **kwargs):
    _engine._send_telegram_message = _send_telegram_message
    return _engine.run_scheduler_loop(*args, **kwargs)
