"""Backward-compatible problem reviews DAO import path."""

from leetcoach.app.infrastructure.dao import problem_reviews_dao as _dao

_compute_due_windows = _dao._compute_due_windows
