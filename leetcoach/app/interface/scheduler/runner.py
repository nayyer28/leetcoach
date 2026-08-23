"""Scheduler interface runner.

This module is the time-driven entrypoint into the shared reminder engine.
"""

from leetcoach.app.application.reviews.reminder_engine import (  # noqa: F401
    ReminderCandidate,
    ReminderRunStats,
    SchedulerPreflightResult,
    build_reminder_message,
    row_to_candidate,
    run_scheduler_loop,
    run_scheduler_once,
    scheduler_preflight,
    was_user_reminded_today,
)
