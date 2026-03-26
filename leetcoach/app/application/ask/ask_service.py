from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
import os
from typing import Any
from uuid import uuid4

from leetcoach.app.application.analytics.aggregate_user_problems import (
    AggregateProblemFilters,
    AggregateUserProblemsRequest,
    AggregateUserProblemsResult,
    aggregate_user_problems,
    aggregate_user_problems_tool_definition,
)
from leetcoach.app.application.ask.problem_tools import (
    execute_get_problem_detail,
    execute_list_user_problems,
    execute_query_user_problems,
    execute_search_user_problems,
    get_problem_detail_tool_definition,
    list_user_problems_tool_definition,
    query_user_problems_tool_definition,
    search_user_problems_tool_definition,
)
from leetcoach.app.application.ask.help_tools import (
    describe_ask_capabilities_tool_definition,
    execute_describe_ask_capabilities,
)
from leetcoach.app.application.ask.review_tools import (
    execute_get_due_reviews,
    execute_get_last_reminder_batch,
    get_due_reviews_tool_definition,
    get_last_reminder_batch_tool_definition,
)
from leetcoach.app.infrastructure.llm.gemini_provider import (
    GeminiGenerateResult,
    GeminiProvider,
)

LOGGER = logging.getLogger("leetcoach.ask")


@dataclass(frozen=True)
class AskToolExecution:
    tool_name: str
    arguments: dict[str, Any]
    result: dict[str, Any]


@dataclass(frozen=True)
class AskServiceResult:
    response_type: str
    model: str
    tool_executions: list[AskToolExecution]
    answer: str | None = None
    confidence: str | None = None
    tool_fit: str | None = None
    answer_basis: str | None = None
    comments: str | None = None
    request_id: str = ""
    trace_events: list["AskTraceEvent"] = field(default_factory=list)


@dataclass(frozen=True)
class AskTraceEvent:
    event: str
    step: int | None
    payload: dict[str, Any]


@dataclass(frozen=True)
class AskServiceError(Exception):
    message: str
    request_id: str
    model: str
    tool_executions: list[AskToolExecution] = field(default_factory=list)
    trace_events: list[AskTraceEvent] = field(default_factory=list)

    def __str__(self) -> str:
        return self.message


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


def _prompt_debug_enabled() -> bool:
    return os.getenv("LEETCOACH_ASK_DEBUG_PROMPTS") == "1"


def _truncate_text(text: str, limit: int = 600) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "...<truncated>"


def _summarize_tool_result(result: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {"keys": sorted(result.keys())}
    for key, value in result.items():
        if isinstance(value, list):
            summary[f"{key}_count"] = len(value)
        elif isinstance(value, dict):
            summary[f"{key}_keys"] = sorted(value.keys())
        elif isinstance(value, str):
            summary[key] = _truncate_text(value, 160)
        elif isinstance(value, (int, float, bool)) or value is None:
            summary[key] = value
    return summary


def _has_duplicate_tool_call(
    tool_executions: list[AskToolExecution],
    *,
    tool_name: str,
    arguments: dict[str, Any],
) -> bool:
    return any(
        execution.tool_name == tool_name and execution.arguments == arguments
        for execution in tool_executions
    )


def _record_trace(
    trace_events: list[AskTraceEvent],
    *,
    request_id: str,
    event: str,
    step: int | None,
    payload: dict[str, Any],
) -> None:
    trace_events.append(AskTraceEvent(event=event, step=step, payload=payload))
    LOGGER.info(
        "[ask.trace] %s",
        json.dumps(
            {
                "request_id": request_id,
                "event": event,
                "step": step,
                **payload,
            },
            ensure_ascii=True,
            sort_keys=True,
        ),
    )


def _tool_definitions() -> list[dict[str, Any]]:
    return [
        describe_ask_capabilities_tool_definition(),
        aggregate_user_problems_tool_definition(),
        get_problem_detail_tool_definition(),
        list_user_problems_tool_definition(),
        search_user_problems_tool_definition(),
        query_user_problems_tool_definition(),
        get_due_reviews_tool_definition(),
        get_last_reminder_batch_tool_definition(),
    ]


def _execute_tool(
    *,
    tool_name: str,
    arguments: dict[str, Any],
    db_path: str,
    telegram_user_id: str,
) -> dict[str, Any]:
    if tool_name == "aggregate_user_problems":
        request = _build_request(arguments)
        tool_result = aggregate_user_problems(
            db_path=db_path,
            telegram_user_id=telegram_user_id,
            request=request,
        )
        return _serialize_aggregate_result(tool_result)
    if tool_name == "describe_ask_capabilities":
        return execute_describe_ask_capabilities(arguments=arguments)
    if tool_name == "get_problem_detail":
        return execute_get_problem_detail(
            db_path=db_path,
            telegram_user_id=telegram_user_id,
            arguments=arguments,
        )
    if tool_name == "list_user_problems":
        return execute_list_user_problems(
            db_path=db_path,
            telegram_user_id=telegram_user_id,
            arguments=arguments,
        )
    if tool_name == "search_user_problems":
        return execute_search_user_problems(
            db_path=db_path,
            telegram_user_id=telegram_user_id,
            arguments=arguments,
        )
    if tool_name == "query_user_problems":
        return execute_query_user_problems(
            db_path=db_path,
            telegram_user_id=telegram_user_id,
            arguments=arguments,
        )
    if tool_name == "get_due_reviews":
        return execute_get_due_reviews(
            db_path=db_path,
            telegram_user_id=telegram_user_id,
            arguments=arguments,
        )
    if tool_name == "get_last_reminder_batch":
        return execute_get_last_reminder_batch(
            db_path=db_path,
            telegram_user_id=telegram_user_id,
            arguments=arguments,
        )
    raise ValueError("unsupported tool_name from LLM")


def _build_prompt(
    *,
    question: str,
    tool_executions: list[AskToolExecution],
) -> str:
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
        '{"type":"tool_call","tool_name":"<tool_name>","arguments":{...}}\n'
        '{"type":"final_answer","answer":"...","confidence":"high|medium|low","tool_fit":"exact|approximate|insufficient","answer_basis":"direct_tool_result|light_inference|best_effort","comments":"..."}\n'
        '{"type":"cannot_answer_confidently","comments":"..."}\n'
        "Use the tool when data lookup or aggregation is needed.\n"
        "If previous tool executions already contain enough information to answer, return final_answer.\n"
        "Never call the same tool twice with the same arguments in a single request.\n"
        "After describe_ask_capabilities returns, respond with final_answer instead of calling it again.\n"
        "When you return final_answer, always include confidence, tool_fit, answer_basis, and comments.\n"
        "Use comments to briefly explain how you got the answer or any limitation/caveat.\n"
        "If the available tools are not a good fit for the question, return cannot_answer_confidently instead of guessing.\n"
        "If the user asks what /ask can do, asks for examples, or asks how to use it, call describe_ask_capabilities.\n"
        "Do not invent results.\n"
        "Useful examples:\n"
        '- "what can /ask do?" -> describe_ask_capabilities\n'
        '- "give me examples of ask questions" -> describe_ask_capabilities\n'
        '- "show P1" -> get_problem_detail\n'
        '- "list my latest 5 problems" -> list_user_problems\n'
        '- "show my tree problems" -> list_user_problems\n'
        '- "search for two sum" -> search_user_problems\n'
        '- "show me all problems I solved in Feb 2026" -> query_user_problems\n'
        '- "show my hard tree problems from March 2026" -> query_user_problems\n'
        '- "what is due?" -> get_due_reviews\n'
        '- "what did you remind me last?" -> get_last_reminder_batch\n'
        '- "how many easy problems have I solved in Trees?" -> aggregate_user_problems\n'
        "Available tool definitions:\n"
        f"{json.dumps(_tool_definitions(), ensure_ascii=True)}\n"
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
    max_steps: int = 5,
) -> AskServiceResult:
    request_id = uuid4().hex[:12]
    tool_executions: list[AskToolExecution] = []
    trace_events: list[AskTraceEvent] = []
    last_model = ""
    prompt_debug = _prompt_debug_enabled()

    _record_trace(
        trace_events,
        request_id=request_id,
        event="ask.start",
        step=None,
        payload={
            "telegram_user_id": telegram_user_id,
            "question": question,
            "max_steps": max_steps,
            "prompt_debug": prompt_debug,
        },
    )

    try:
        for step in range(1, max_steps + 1):
            prompt = _build_prompt(question=question, tool_executions=tool_executions)
            if prompt_debug:
                _record_trace(
                    trace_events,
                    request_id=request_id,
                    event="ask.prompt",
                    step=step,
                    payload={"prompt": _truncate_text(prompt, 4000)},
                )
            llm_result: GeminiGenerateResult = provider.generate_text(prompt)
            last_model = llm_result.model
            _record_trace(
                trace_events,
                request_id=request_id,
                event="ask.model_response",
                step=step,
                payload={
                    "model": last_model,
                    "raw_text": _truncate_text(llm_result.text, 2000)
                    if prompt_debug
                    else _truncate_text(llm_result.text, 300),
                },
            )
            payload = _extract_json_payload(llm_result.text)
            response_type = payload.get("type")
            _record_trace(
                trace_events,
                request_id=request_id,
                event="ask.parsed_response",
                step=step,
                payload={
                    "response_type": str(response_type),
                    "payload_keys": sorted(payload.keys()),
                },
            )

            if response_type == "final_answer":
                answer = payload.get("answer")
                if not isinstance(answer, str) or not answer.strip():
                    raise ValueError("final_answer response must include a non-empty answer")
                confidence = payload.get("confidence")
                tool_fit = payload.get("tool_fit")
                answer_basis = payload.get("answer_basis")
                comments = payload.get("comments")
                if confidence not in {"high", "medium", "low"}:
                    raise ValueError("final_answer confidence must be high, medium, or low")
                if tool_fit not in {"exact", "approximate", "insufficient"}:
                    raise ValueError(
                        "final_answer tool_fit must be exact, approximate, or insufficient"
                    )
                if answer_basis not in {
                    "direct_tool_result",
                    "light_inference",
                    "best_effort",
                }:
                    raise ValueError(
                        "final_answer answer_basis must be direct_tool_result, light_inference, or best_effort"
                    )
                if not isinstance(comments, str) or not comments.strip():
                    raise ValueError("final_answer comments must be a non-empty string")
                _record_trace(
                    trace_events,
                    request_id=request_id,
                    event="ask.final_answer",
                    step=step,
                    payload={
                        "model": last_model,
                        "answer": _truncate_text(answer.strip(), 500),
                        "confidence": confidence,
                        "tool_fit": tool_fit,
                        "answer_basis": answer_basis,
                        "comments": _truncate_text(comments.strip(), 300),
                        "tool_execution_count": len(tool_executions),
                    },
                )
                return AskServiceResult(
                    response_type="final_answer",
                    model=last_model,
                    tool_executions=tool_executions,
                    answer=answer.strip(),
                    confidence=confidence,
                    tool_fit=tool_fit,
                    answer_basis=answer_basis,
                    comments=comments.strip(),
                    request_id=request_id,
                    trace_events=trace_events,
                )

            if response_type == "cannot_answer_confidently":
                comments = payload.get("comments")
                if not isinstance(comments, str) or not comments.strip():
                    raise ValueError(
                        "cannot_answer_confidently comments must be a non-empty string"
                    )
                _record_trace(
                    trace_events,
                    request_id=request_id,
                    event="ask.cannot_answer_confidently",
                    step=step,
                    payload={
                        "model": last_model,
                        "comments": _truncate_text(comments.strip(), 300),
                        "tool_execution_count": len(tool_executions),
                    },
                )
                return AskServiceResult(
                    response_type="cannot_answer_confidently",
                    model=last_model,
                    tool_executions=tool_executions,
                    comments=comments.strip(),
                    request_id=request_id,
                    trace_events=trace_events,
                )

            if response_type == "tool_call":
                tool_name = payload.get("tool_name")
                arguments = payload.get("arguments")
                if not isinstance(tool_name, str) or not tool_name.strip():
                    raise ValueError("tool_call must include a non-empty tool_name")
                if not isinstance(arguments, dict):
                    raise ValueError("tool_call arguments must be an object")
                if _has_duplicate_tool_call(
                    tool_executions,
                    tool_name=tool_name,
                    arguments=arguments,
                ):
                    _record_trace(
                        trace_events,
                        request_id=request_id,
                        event="ask.fail",
                        step=step,
                        payload={
                            "reason": "duplicate_tool_call",
                            "tool_name": tool_name,
                            "arguments": arguments,
                            "tool_execution_count": len(tool_executions),
                            "last_model": last_model,
                        },
                    )
                    raise AskServiceError(
                        message=(
                            "LLM repeated the same tool call without producing a final answer"
                        ),
                        request_id=request_id,
                        model=last_model,
                        tool_executions=tool_executions,
                        trace_events=trace_events,
                    )
                _record_trace(
                    trace_events,
                    request_id=request_id,
                    event="ask.tool_call",
                    step=step,
                    payload={
                        "tool_name": tool_name,
                        "arguments": arguments,
                    },
                )
                tool_result = _execute_tool(
                    tool_name=tool_name,
                    arguments=arguments,
                    db_path=db_path,
                    telegram_user_id=telegram_user_id,
                )
                _record_trace(
                    trace_events,
                    request_id=request_id,
                    event="ask.tool_result",
                    step=step,
                    payload={
                        "tool_name": tool_name,
                        "result_summary": _summarize_tool_result(tool_result),
                    },
                )
                tool_executions.append(
                    AskToolExecution(
                        tool_name=tool_name,
                        arguments=arguments,
                        result=tool_result,
                    )
                )
                continue

            _record_trace(
                trace_events,
                request_id=request_id,
                event="ask.invalid_response",
                step=step,
                payload={"response_type": str(response_type)},
            )
            raise ValueError(
                "LLM response must be final_answer, cannot_answer_confidently, or tool_call"
            )
    except AskServiceError:
        raise
    except Exception as exc:
        if not any(event.event == "ask.fail" for event in trace_events):
            _record_trace(
                trace_events,
                request_id=request_id,
                event="ask.fail",
                step=None,
                payload={
                    "reason": "exception",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "tool_execution_count": len(tool_executions),
                    "last_model": last_model,
                },
            )
        raise AskServiceError(
            message=str(exc),
            request_id=request_id,
            model=last_model,
            tool_executions=tool_executions,
            trace_events=trace_events,
        ) from exc

    _record_trace(
        trace_events,
        request_id=request_id,
        event="ask.fail",
        step=max_steps,
        payload={
            "reason": "max_steps_exhausted",
            "tool_execution_count": len(tool_executions),
            "last_model": last_model,
        },
    )
    raise AskServiceError(
        message="LLM did not finish within max_steps",
        request_id=request_id,
        model=last_model,
        tool_executions=tool_executions,
        trace_events=trace_events,
    )
