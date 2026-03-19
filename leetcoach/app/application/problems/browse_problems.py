"""Problem browsing use cases.

This module currently wraps the legacy query service while the browse and
review responsibilities are separated incrementally.
"""

from leetcoach.services.query_service import (  # noqa: F401
    get_problem_detail,
    list_all_problems,
    list_by_pattern,
    list_recent_problems,
    search_problems,
)
