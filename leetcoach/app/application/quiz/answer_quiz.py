from __future__ import annotations

from datetime import UTC, datetime
import json

from leetcoach.app.application.quiz.common import (
    AnswerQuizResult,
    LLMProvider,
    answer_check_prompt,
    extract_quiz_answer_option,
    parse_feedback_payload,
    parse_question_payload,
)
from leetcoach.app.infrastructure.config.db import get_connection
from leetcoach.app.infrastructure.dao.active_quiz_sessions_dao import (
    close_quiz_session,
    get_active_quiz_session_by_user_id,
    mark_quiz_answered,
)
from leetcoach.app.infrastructure.dao.users_dao import get_user_id_by_telegram_user_id


def _user_id_or_none(db_path: str, telegram_user_id: str) -> int | None:
    with get_connection(db_path) as conn:
        return get_user_id_by_telegram_user_id(conn, telegram_user_id=telegram_user_id)


def answer_quiz(
    *,
    db_path: str,
    telegram_user_id: str,
    user_answer_text: str,
    provider: LLMProvider,
    now_iso_fn,
) -> AnswerQuizResult:
    user_id = _user_id_or_none(db_path, telegram_user_id)
    if user_id is None:
        return AnswerQuizResult(status="user_not_registered")

    with get_connection(db_path) as conn:
        row = get_active_quiz_session_by_user_id(conn, user_id=user_id)
        if row is None or str(row["status"]) not in {"asked", "answered"}:
            return AnswerQuizResult(status="no_active_quiz")
        now_iso = now_iso_fn()
        if str(row["expires_at"]) < now_iso:
            closed = close_quiz_session(
                conn,
                user_id=user_id,
                closed_at=now_iso,
                expires_at=now_iso,
                now_iso=now_iso,
            )
            if closed:
                conn.commit()
            return AnswerQuizResult(status="expired_quiz")
        question = parse_question_payload(str(row["question_payload_json"]))

    normalized_option = extract_quiz_answer_option(user_answer_text)
    if normalized_option is None:
        return AnswerQuizResult(status="invalid_answer", question=question)

    llm_out = provider.generate_text(answer_check_prompt(question, user_answer_text))
    feedback = parse_feedback_payload(llm_out.text)
    now_iso = now_iso_fn()
    with get_connection(db_path) as conn:
        marked = mark_quiz_answered(
            conn,
            user_id=user_id,
            user_answer_text=user_answer_text,
            answer_feedback_json=json.dumps(
                {
                    "user_answer_normalized": feedback.user_answer_normalized,
                    "is_correct": feedback.is_correct,
                    "verdict_summary": feedback.verdict_summary,
                    "formal_feedback": feedback.formal_feedback,
                    "concept_takeaway": feedback.concept_takeaway,
                },
                sort_keys=True,
            ),
            answered_at=now_iso,
            now_iso=now_iso,
        )
        if marked:
            conn.commit()
    return AnswerQuizResult(
        status="ok",
        feedback=feedback,
        question=question,
        model_used=llm_out.model,
    )


def default_now_iso() -> str:
    return datetime.now(UTC).isoformat()
