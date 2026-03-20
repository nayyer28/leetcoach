from __future__ import annotations

from datetime import UTC, datetime, timedelta

from leetcoach.app.application.quiz.answer_quiz import (
    answer_quiz as _answer_quiz_impl,
)
from leetcoach.app.application.quiz.common import (
    LLMProvider,
    KNOWN_QUIZ_TOPICS,
    QUIZ_ANSWER_OPTION_RE,
    QUIZ_TTL_HOURS,
    AnswerQuizResult,
    QuizFeedbackPayload,
    QuizQuestionPayload,
    RevealQuizResult,
    StartQuizResult,
    answer_check_prompt as _answer_check_prompt,
    extract_json_payload as _extract_json_payload_impl,
    extract_quiz_answer_option,
    is_known_quiz_topic,
    normalize_quiz_topic,
    parse_feedback_payload as _parse_feedback_payload_impl,
    parse_question_payload as _parse_question_payload_impl,
    question_prompt as _question_prompt,
)
from leetcoach.app.application.quiz.reveal_quiz import (
    reveal_quiz as _reveal_quiz_impl,
)
from leetcoach.app.application.quiz.start_quiz import (
    start_quiz as _start_quiz_impl,
)
from leetcoach.app.infrastructure.config.db import get_connection
from leetcoach.app.infrastructure.dao.active_quiz_sessions_dao import (
    close_quiz_session,
    get_active_quiz_session_by_user_id,
)
from leetcoach.app.infrastructure.dao.users_dao import get_user_id_by_telegram_user_id


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _expires_iso_from(now_iso: str, *, ttl_hours: int = QUIZ_TTL_HOURS) -> str:
    return (datetime.fromisoformat(now_iso) + timedelta(hours=ttl_hours)).isoformat()


def _extract_json_payload(text: str) -> dict[str, object]:
    return _extract_json_payload_impl(text)


def _parse_question_payload(text: str) -> QuizQuestionPayload:
    return _parse_question_payload_impl(text)


def _parse_feedback_payload(text: str) -> QuizFeedbackPayload:
    return _parse_feedback_payload_impl(text)


def _user_id_or_none(db_path: str, telegram_user_id: str) -> int | None:
    with get_connection(db_path) as conn:
        return get_user_id_by_telegram_user_id(conn, telegram_user_id=telegram_user_id)


def _is_row_expired(row: object, *, now_iso: str) -> bool:
    expires_at = str(row["expires_at"])
    return expires_at < now_iso


def interrupt_active_quiz(*, db_path: str, telegram_user_id: str) -> bool:
    user_id = _user_id_or_none(db_path, telegram_user_id)
    if user_id is None:
        return False

    now_iso = _now_iso()
    with get_connection(db_path) as conn:
        row = get_active_quiz_session_by_user_id(conn, user_id=user_id)
        if row is None or str(row["status"]) not in {"asked", "answered", "revealed"}:
            return False
        closed = close_quiz_session(
            conn,
            user_id=user_id,
            closed_at=now_iso,
            expires_at=now_iso,
            now_iso=now_iso,
        )
        if closed:
            conn.commit()
        return closed


def start_quiz(
    *,
    db_path: str,
    telegram_user_id: str,
    topic: str | None,
    provider: LLMProvider,
) -> StartQuizResult:
    return _start_quiz_impl(
        db_path=db_path,
        telegram_user_id=telegram_user_id,
        topic=topic,
        provider=provider,
        now_iso_fn=_now_iso,
    )


def answer_quiz(
    *,
    db_path: str,
    telegram_user_id: str,
    user_answer_text: str,
    provider: LLMProvider,
) -> AnswerQuizResult:
    return _answer_quiz_impl(
        db_path=db_path,
        telegram_user_id=telegram_user_id,
        user_answer_text=user_answer_text,
        provider=provider,
        now_iso_fn=_now_iso,
    )


def reveal_quiz(*, db_path: str, telegram_user_id: str) -> RevealQuizResult:
    return _reveal_quiz_impl(
        db_path=db_path,
        telegram_user_id=telegram_user_id,
        now_iso_fn=_now_iso,
    )


__all__ = [
    "AnswerQuizResult",
    "KNOWN_QUIZ_TOPICS",
    "LLMProvider",
    "QUIZ_ANSWER_OPTION_RE",
    "QUIZ_TTL_HOURS",
    "QuizFeedbackPayload",
    "QuizQuestionPayload",
    "RevealQuizResult",
    "StartQuizResult",
    "_answer_check_prompt",
    "_expires_iso_from",
    "_extract_json_payload",
    "_is_row_expired",
    "_now_iso",
    "_parse_feedback_payload",
    "_parse_question_payload",
    "_question_prompt",
    "_user_id_or_none",
    "answer_quiz",
    "extract_quiz_answer_option",
    "interrupt_active_quiz",
    "is_known_quiz_topic",
    "normalize_quiz_topic",
    "reveal_quiz",
    "start_quiz",
]
