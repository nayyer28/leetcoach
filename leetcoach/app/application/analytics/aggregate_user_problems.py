from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from leetcoach.app.infrastructure.config.db import get_connection
from leetcoach.app.infrastructure.dao.analytics_dao import (
    list_aggregated_user_problems,
)
from leetcoach.app.infrastructure.dao.users_dao import get_user_id_by_telegram_user_id
from leetcoach.app.application.shared.patterns import (
    ROADMAP_PATTERN_LEVELS,
    canonical_pattern_label,
)

AggregateGroupBy = Literal["none", "difficulty", "pattern", "solved_date", "solved_month"]
AggregateMetric = Literal["problem_count", "review_count_sum", "strength_score"]
AggregateSort = Literal["metric_desc", "metric_asc", "group_asc", "group_desc"]

VALID_GROUP_BY: tuple[AggregateGroupBy, ...] = (
    "none",
    "difficulty",
    "pattern",
    "solved_date",
    "solved_month",
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
VALID_DIFFICULTIES: tuple[str, ...] = ("easy", "medium", "hard")
VALID_PATTERN_LABELS: tuple[str, ...] = tuple(
    label for _, label in sorted(ROADMAP_PATTERN_LEVELS.values(), key=lambda item: item[0])
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


@dataclass(frozen=True)
class ValidatedAggregateUserProblemsRequest:
    group_by: AggregateGroupBy
    metric: AggregateMetric
    sort: AggregateSort
    limit: int
    difficulty: str | None
    pattern: str | None
    solved_date_from: date | None
    solved_date_to: date | None


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
                            "enum": list(VALID_DIFFICULTIES),
                        },
                        "pattern": {"type": "string", "enum": list(VALID_PATTERN_LABELS)},
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


def _normalize_difficulty(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized not in VALID_DIFFICULTIES:
        raise ValueError(f"difficulty must be one of {', '.join(VALID_DIFFICULTIES)}")
    return normalized


def _parse_local_date(value: str | None, field_name: str) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be YYYY-MM-DD") from exc


def validate_aggregate_user_problems_request(
    request: AggregateUserProblemsRequest,
) -> ValidatedAggregateUserProblemsRequest:
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
    return ValidatedAggregateUserProblemsRequest(
        group_by=request.group_by,
        metric=request.metric,
        sort=request.sort,
        limit=request.limit,
        difficulty=difficulty,
        pattern=pattern,
        solved_date_from=date_from,
        solved_date_to=date_to,
    )


def aggregate_user_problems(
    db_path: str,
    telegram_user_id: str,
    request: AggregateUserProblemsRequest,
) -> AggregateUserProblemsResult:
    validated = validate_aggregate_user_problems_request(request)

    with get_connection(db_path) as conn:
        user_id = get_user_id_by_telegram_user_id(
            conn, telegram_user_id=telegram_user_id
        )
        if user_id is None:
            return AggregateUserProblemsResult(
                metric=validated.metric,
                group_by=validated.group_by,
                filters_applied={},
                rows=[],
            )
        rows = list_aggregated_user_problems(
            conn,
            user_id=user_id,
            group_by=validated.group_by,
            metric=validated.metric,
            sort=validated.sort,
            limit=validated.limit,
            difficulty=validated.difficulty,
            pattern=validated.pattern,
            solved_date_from=(
                validated.solved_date_from.isoformat()
                if validated.solved_date_from is not None
                else None
            ),
            solved_date_to=(
                validated.solved_date_to.isoformat()
                if validated.solved_date_to is not None
                else None
            ),
        )

    result_rows = [
        AggregateResultRow(group=str(row["group_value"]), value=int(row["metric_value"]))
        for row in rows
    ]

    filters_applied: dict[str, str] = {}
    if validated.difficulty is not None:
        filters_applied["difficulty"] = validated.difficulty
    if validated.pattern is not None:
        filters_applied["pattern"] = validated.pattern
    if validated.solved_date_from is not None:
        filters_applied["solved_date_from"] = validated.solved_date_from.isoformat()
    if validated.solved_date_to is not None:
        filters_applied["solved_date_to"] = validated.solved_date_to.isoformat()

    return AggregateUserProblemsResult(
        metric=validated.metric,
        group_by=validated.group_by,
        filters_applied=filters_applied,
        rows=result_rows,
    )
