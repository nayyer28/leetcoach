from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json

from leetcoach.app.application.quiz.common import (
    LLMProvider,
    QUIZ_TTL_HOURS,
    StartQuizResult,
    is_known_quiz_topic,
    parse_question_payload,
    question_prompt,
)
from leetcoach.app.infrastructure.config.db import get_connection
from leetcoach.app.infrastructure.dao.active_quiz_sessions_dao import (
    delete_expired_terminal_sessions,
    upsert_active_quiz_session,
)
from leetcoach.app.infrastructure.dao.users_dao import get_user_id_by_telegram_user_id


def _user_id_or_none(db_path: str, telegram_user_id: str) -> int | None:
    with get_connection(db_path) as conn:
        return get_user_id_by_telegram_user_id(conn, telegram_user_id=telegram_user_id)


def start_quiz(
    *,
    db_path: str,
    telegram_user_id: str,
    topic: str | None,
    provider: LLMProvider,
    now_iso_fn,
) -> StartQuizResult:
    if topic and not is_known_quiz_topic(topic):
        return StartQuizResult(status="unknown_topic")

    user_id = _user_id_or_none(db_path, telegram_user_id)
    if user_id is None:
        return StartQuizResult(status="user_not_registered")

    llm_out = provider.generate_text(question_prompt(topic))
    parsed = parse_question_payload(llm_out.text)
    now_iso = now_iso_fn()
    expires_at = (
        datetime.fromisoformat(now_iso) + timedelta(hours=QUIZ_TTL_HOURS)
    ).isoformat()
    payload_json = json.dumps(
        {
            "topic": parsed.topic,
            "question": parsed.question,
            "options": parsed.options,
            "correct_option": parsed.correct_option,
            "why_correct": parsed.why_correct,
            "why_others_wrong": parsed.why_others_wrong,
            "concept_takeaway": parsed.concept_takeaway,
        },
        sort_keys=True,
    )
    with get_connection(db_path) as conn:
        delete_expired_terminal_sessions(conn, now_iso=now_iso)
        upsert_active_quiz_session(
            conn,
            user_id=user_id,
            topic=topic,
            question_payload_json=payload_json,
            model_used=llm_out.model,
            status="asked",
            asked_at=now_iso,
            expires_at=expires_at,
            now_iso=now_iso,
        )
        conn.commit()
    return StartQuizResult(status="ok", question=parsed, model_used=llm_out.model)


def default_now_iso() -> str:
    return datetime.now(UTC).isoformat()
