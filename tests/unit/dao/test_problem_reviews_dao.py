from __future__ import annotations

from datetime import datetime, timedelta
import unittest

from leetcoach.dao.problem_reviews_dao import _compute_due_windows


class ProblemReviewsDaoUnitTest(unittest.TestCase):
    def test_compute_due_windows_returns_day7_and_day21(self) -> None:
        solved_at = "2026-03-08T10:00:00+00:00"
        windows = _compute_due_windows(solved_at)
        self.assertEqual(len(windows), 2)

        solved_dt = datetime.fromisoformat(solved_at)
        day7 = windows[0]
        day21 = windows[1]

        self.assertEqual(day7[0], 7)
        self.assertEqual(datetime.fromisoformat(day7[1]), solved_dt + timedelta(days=7))
        self.assertEqual(
            datetime.fromisoformat(day7[2]),
            solved_dt + timedelta(days=7, hours=48),
        )

        self.assertEqual(day21[0], 21)
        self.assertEqual(datetime.fromisoformat(day21[1]), solved_dt + timedelta(days=21))
        self.assertEqual(
            datetime.fromisoformat(day21[2]),
            solved_dt + timedelta(days=21, hours=48),
        )


if __name__ == "__main__":
    unittest.main()

