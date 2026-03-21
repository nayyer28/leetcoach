from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from leetcoach.app.infrastructure.config.db import get_connection
from leetcoach.app.infrastructure.dao.analytics_dao import (
    list_user_problem_analytics_rows,
)
from leetcoach.app.infrastructure.dao.users_dao import get_user_id_by_telegram_user_id
from leetcoach.patterns import canonical_pattern_label

AggregateGroupBy = Literal["none", "difficulty", "pattern", "solved_date"]
AggregateMetric = Literal["problem_count", "review_count_sum", "strength_score"]
AggregateSort = Literal["metric_desc", "metric_asc", "group_asc", "group_desc"]

VALID_GROUP_BY: tuple[AggregateGroupBy, ...] = (
    "none",
    "difficulty",
    "pattern",
    "solved_date",
)
VALID_METRICS: tuple[AggregateMetric, ...] = (
    "problem_count",
    "review_count_sum",
    "strength_score",
)
VALID_SORTS: tuple[AggregateSort, ...] = (
    "metric_desc",
    "metric_asc",
    "group_asc",
    "group_desc",
)


@dataclass(frozen=True)
class AggregateProblemFilters:
    difficulty: str | None = None
    pattern: str | None = None
    solved_date_from: str | None = None
    solved_date_to: str | None = None


@dataclass(frozen=True)
class AggregateUserProblemsRequest:
    group_by: AggregateGroupBy
    metric: AggregateMetric
    sort: AggregateSort = "metric_desc"
    limit: int = 10
    filters: AggregateProblemFilters = AggregateProblemFilters()


@dataclass(frozen=True)
class AggregateResultRow:
    group: str
    value: int


@dataclass(frozen=True)
class AggregateUserProblemsResult:
    metric: AggregateMetric
    group_by: AggregateGroupBy
    filters_applied: dict[str, str]
    rows: list[AggregateResultRow]


def aggregate_user_problems_tool_definition() -> dict[str, Any]:
    return {
        "name": "aggregate_user_problems",
        "description": (
            "Aggregate the current user's solved problems and review state using "
            "safe read-only filters, grouping, and metrics."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "group_by": {"type": "string", "enum": list(VALID_GROUP_BY)},
                "metric": {"type": "string", "enum": list(VALID_METRICS)},
                "sort": {"type": "string", "enum": list(VALID_SORTS)},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                "filters": {
                    "type": "object",
                    "properties": {
                        "difficulty": {
                            "type": "string",
                            "enum": ["easy", "medium", "hard"],
                        },
                        "pattern": {"type": "string"},
                        "solved_date_from": {"type": "string"},
                        "solved_date_to": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
            },
            "required": ["group_by", "metric"],
            "additionalProperties": False,
        },
    }


def _resolve_timezone(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _normalize_difficulty(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized not in {"easy", "medium", "hard"}:
        raise ValueError("difficulty must be one of easy, medium, hard")
    return normalized


def _parse_local_date(value: str | None, field_name: str) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be YYYY-MM-DD") from exc


def _validate_request(
    request: AggregateUserProblemsRequest,
) -> tuple[str | None, str | None, date | None, date | None]:
    if request.group_by not in VALID_GROUP_BY:
        raise ValueError(f"group_by must be one of {', '.join(VALID_GROUP_BY)}")
    if request.metric not in VALID_METRICS:
        raise ValueError(f"metric must be one of {', '.join(VALID_METRICS)}")
    if request.sort not in VALID_SORTS:
        raise ValueError(f"sort must be one of {', '.join(VALID_SORTS)}")
    if request.limit < 1 or request.limit > 20:
        raise ValueError("limit must be between 1 and 20")

    difficulty = _normalize_difficulty(request.filters.difficulty)
    pattern = None
    if request.filters.pattern is not None:
        pattern = canonical_pattern_label(request.filters.pattern)
        if pattern is None:
            raise ValueError("pattern must resolve to a known roadmap pattern")
    date_from = _parse_local_date(request.filters.solved_date_from, "solved_date_from")
    date_to = _parse_local_date(request.filters.solved_date_to, "solved_date_to")
    if date_from and date_to and date_from > date_to:
        raise ValueError("solved_date_from cannot be after solved_date_to")
    return difficulty, pattern, date_from, date_to


def _matches_filters(
    row: dict[str, Any],
    *,
    difficulty: str | None,
    pattern: str | None,
    solved_date_from: date | None,
    solved_date_to: date | None,
) -> bool:
    if difficulty is not None and str(row["difficulty"]).lower() != difficulty:
        return False
    if pattern is not None and canonical_pattern_label(str(row["pattern"])) != pattern:
        return False

    row_date = datetime.fromisoformat(str(row["solved_at"])).astimezone(
        _resolve_timezone(str(row["timezone"]))
    ).date()
    if solved_date_from is not None and row_date < solved_date_from:
        return False
    if solved_date_to is not None and row_date > solved_date_to:
        return False
    return True


def _group_value(row: dict[str, Any], group_by: AggregateGroupBy) -> str:
    if group_by == "none":
        return "all"
    if group_by == "difficulty":
        return str(row["difficulty"]).lower()
    if group_by == "pattern":
        return canonical_pattern_label(str(row["pattern"])) or str(row["pattern"])
    if group_by == "solved_date":
        return (
            datetime.fromisoformat(str(row["solved_at"]))
            .astimezone(_resolve_timezone(str(row["timezone"])))
            .date()
            .isoformat()
        )
    raise ValueError(f"unsupported group_by: {group_by}")


def _metric_value(
    metric: AggregateMetric, *, problem_count: int, review_count_sum: int
) -> int:
    if metric == "problem_count":
        return problem_count
    if metric == "review_count_sum":
        return review_count_sum
    if metric == "strength_score":
        return problem_count + review_count_sum
    raise ValueError(f"unsupported metric: {metric}")


def aggregate_user_problems(
    db_path: str,
    telegram_user_id: str,
    request: AggregateUserProblemsRequest,
) -> AggregateUserProblemsResult:
    difficulty, pattern, date_from, date_to = _validate_request(request)

    with get_connection(db_path) as conn:
        user_id = get_user_id_by_telegram_user_id(
            conn, telegram_user_id=telegram_user_id
        )
        if user_id is None:
            return AggregateUserProblemsResult(
                metric=request.metric,
                group_by=request.group_by,
                filters_applied={},
                rows=[],
            )
        rows = list_user_problem_analytics_rows(conn, user_id=user_id)

    filtered_rows = [
        row
        for row in rows
        if _matches_filters(
            row,
            difficulty=difficulty,
            pattern=pattern,
            solved_date_from=date_from,
            solved_date_to=date_to,
        )
    ]

    grouped: dict[str, tuple[int, int]] = {}
    for row in filtered_rows:
        key = _group_value(row, request.group_by)
        problem_count, review_count_sum = grouped.get(key, (0, 0))
        grouped[key] = (problem_count + 1, review_count_sum + int(row["review_count"]))

    result_rows = [
        AggregateResultRow(
            group=group,
            value=_metric_value(
                request.metric,
                problem_count=problem_count,
                review_count_sum=review_count_sum,
            ),
        )
        for group, (problem_count, review_count_sum) in grouped.items()
    ]

    if request.sort == "metric_desc":
        result_rows.sort(key=lambda row: (-row.value, row.group.lower()))
    elif request.sort == "metric_asc":
        result_rows.sort(key=lambda row: (row.value, row.group.lower()))
    elif request.sort == "group_asc":
        result_rows.sort(key=lambda row: row.group.lower())
    elif request.sort == "group_desc":
        result_rows.sort(key=lambda row: row.group.lower(), reverse=True)

    filters_applied: dict[str, str] = {}
    if difficulty is not None:
        filters_applied["difficulty"] = difficulty
    if pattern is not None:
        filters_applied["pattern"] = pattern
    if date_from is not None:
        filters_applied["solved_date_from"] = date_from.isoformat()
    if date_to is not None:
        filters_applied["solved_date_to"] = date_to.isoformat()

    return AggregateUserProblemsResult(
        metric=request.metric,
        group_by=request.group_by,
        filters_applied=filters_applied,
        rows=result_rows[: request.limit],
    )
