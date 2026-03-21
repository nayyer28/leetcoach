from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from leetcoach.app.application.analytics.aggregate_user_problems import (
    AggregateProblemFilters,
    AggregateUserProblemsRequest,
    AggregateUserProblemsResult,
    aggregate_user_problems,
    aggregate_user_problems_tool_definition,
)
from leetcoach.app.infrastructure.llm.gemini_provider import (
    GeminiGenerateResult,
    GeminiProvider,
)


@dataclass(frozen=True)
class AskToolExecution:
    tool_name: str
    arguments: dict[str, Any]
    result: dict[str, Any]


@dataclass(frozen=True)
class AskServiceResult:
    answer: str
    model: str
    tool_executions: list[AskToolExecution]


def _extract_json_payload(text: str) -> dict[str, Any]:
    body = text.strip()
    if body.startswith("```"):
        lines = body.splitlines()
        if len(lines) >= 3:
            body = "\n".join(lines[1:-1]).strip()
    parsed = json.loads(body)
    if not isinstance(parsed, dict):
        raise ValueError("LLM response must be a JSON object")
    return parsed


def _build_request(arguments: dict[str, Any]) -> AggregateUserProblemsRequest:
    filters_raw = arguments.get("filters", {})
    if filters_raw is None:
        filters_raw = {}
    if not isinstance(filters_raw, dict):
        raise ValueError("tool arguments.filters must be an object")
    return AggregateUserProblemsRequest(
        group_by=str(arguments["group_by"]),
        metric=str(arguments["metric"]),
        sort=str(arguments.get("sort", "metric_desc")),
        limit=int(arguments.get("limit", 10)),
        filters=AggregateProblemFilters(
            difficulty=_string_or_none(filters_raw.get("difficulty")),
            pattern=_string_or_none(filters_raw.get("pattern")),
            solved_date_from=_string_or_none(filters_raw.get("solved_date_from")),
            solved_date_to=_string_or_none(filters_raw.get("solved_date_to")),
        ),
    )


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _serialize_aggregate_result(result: AggregateUserProblemsResult) -> dict[str, Any]:
    return {
        "metric": result.metric,
        "group_by": result.group_by,
        "filters_applied": result.filters_applied,
        "rows": [{"group": row.group, "value": row.value} for row in result.rows],
    }


def _build_prompt(
    *,
    question: str,
    tool_executions: list[AskToolExecution],
) -> str:
    tool_definition = aggregate_user_problems_tool_definition()
    transcript = [
        {
            "tool_name": execution.tool_name,
            "arguments": execution.arguments,
            "result": execution.result,
        }
        for execution in tool_executions
    ]
    return (
        "You are a read-only analytics assistant for a LeetCode tracking app.\n"
        "You must return JSON only, no markdown and no prose outside JSON.\n"
        "Choose exactly one of these response shapes:\n"
        '{"type":"tool_call","tool_name":"aggregate_user_problems","arguments":{...}}\n'
        '{"type":"final_answer","answer":"..."}\n'
        "Use the tool when data lookup or aggregation is needed.\n"
        "Do not invent results.\n"
        "Available tool definition:\n"
        f"{json.dumps(tool_definition, ensure_ascii=True)}\n"
        "Previous tool executions:\n"
        f"{json.dumps(transcript, ensure_ascii=True)}\n"
        "User question:\n"
        f"{question}\n"
    )


def ask_question(
    *,
    db_path: str,
    telegram_user_id: str,
    question: str,
    provider: GeminiProvider,
    max_steps: int = 3,
) -> AskServiceResult:
    tool_executions: list[AskToolExecution] = []
    last_model = ""

    for _ in range(max_steps):
        prompt = _build_prompt(question=question, tool_executions=tool_executions)
        llm_result: GeminiGenerateResult = provider.generate_text(prompt)
        last_model = llm_result.model
        payload = _extract_json_payload(llm_result.text)
        response_type = payload.get("type")

        if response_type == "final_answer":
            answer = payload.get("answer")
            if not isinstance(answer, str) or not answer.strip():
                raise ValueError("final_answer response must include a non-empty answer")
            return AskServiceResult(
                answer=answer.strip(),
                model=last_model,
                tool_executions=tool_executions,
            )

        if response_type == "tool_call":
            tool_name = payload.get("tool_name")
            arguments = payload.get("arguments")
            if tool_name != "aggregate_user_problems":
                raise ValueError("unsupported tool_name from LLM")
            if not isinstance(arguments, dict):
                raise ValueError("tool_call arguments must be an object")

            request = _build_request(arguments)
            tool_result = aggregate_user_problems(
                db_path=db_path,
                telegram_user_id=telegram_user_id,
                request=request,
            )
            tool_executions.append(
                AskToolExecution(
                    tool_name=tool_name,
                    arguments=arguments,
                    result=_serialize_aggregate_result(tool_result),
                )
            )
            continue

        raise ValueError("LLM response must be final_answer or tool_call")

    raise ValueError("LLM did not finish within max_steps")
