from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
import re
from typing import Protocol

from leetcoach.dao.active_quiz_sessions_dao import (
    close_quiz_session,
    delete_expired_terminal_sessions,
    get_active_quiz_session_by_user_id,
    mark_quiz_answered,
    mark_quiz_revealed,
    upsert_active_quiz_session,
)
from leetcoach.dao.users_dao import get_user_id_by_telegram_user_id
from leetcoach.db.connection import get_connection


QUIZ_TTL_HOURS = 0.5
QUIZ_ANSWER_OPTION_RE = re.compile(r"\b([A-D])\b", re.IGNORECASE)

KNOWN_QUIZ_TOPICS = frozenset(
    {
        "array",
        "arrays",
        "hash map",
        "hash table",
        "string",
        "two pointers",
        "stack",
        "queue",
        "binary search",
        "sliding window",
        "linked list",
        "trees",
        "tree",
        "trie",
        "heap",
        "priority queue",
        "graph",
        "graphs",
        "dfs",
        "bfs",
        "union find",
        "disjoint set",
        "dynamic programming",
        "dp",
        "bit manipulation",
        "greedy",
        "intervals",
        "math",
        "geometry",
        "system design",
        "sorting",
    }
)


class LLMProvider(Protocol):
    def generate_text(self, prompt: str): ...


@dataclass(frozen=True)
class QuizQuestionPayload:
    topic: str
    question: str
    options: dict[str, str]
    correct_option: str
    why_correct: str
    why_others_wrong: dict[str, str]
    concept_takeaway: str


@dataclass(frozen=True)
class QuizFeedbackPayload:
    user_answer_normalized: str
    is_correct: bool
    verdict_summary: str
    formal_feedback: str
    concept_takeaway: str


@dataclass(frozen=True)
class StartQuizResult:
    status: str  # ok | user_not_registered | unknown_topic
    question: QuizQuestionPayload | None = None
    model_used: str | None = None


@dataclass(frozen=True)
class AnswerQuizResult:
    status: str  # ok | no_active_quiz | user_not_registered | invalid_answer | expired_quiz
    feedback: QuizFeedbackPayload | None = None
    question: QuizQuestionPayload | None = None
    model_used: str | None = None


@dataclass(frozen=True)
class RevealQuizResult:
    status: str  # ok | no_active_quiz | user_not_registered | expired_quiz
    question: QuizQuestionPayload | None = None


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _expires_iso_from(now_iso: str, *, ttl_hours: int = QUIZ_TTL_HOURS) -> str:
    return (datetime.fromisoformat(now_iso) + timedelta(hours=ttl_hours)).isoformat()


def normalize_quiz_topic(raw: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", raw.lower()).split())


def is_known_quiz_topic(raw_topic: str) -> bool:
    return normalize_quiz_topic(raw_topic) in KNOWN_QUIZ_TOPICS


def extract_quiz_answer_option(raw_answer: str) -> str | None:
    match = QUIZ_ANSWER_OPTION_RE.search(raw_answer.strip())
    if match is None:
        return None
    return match.group(1).upper()


def _extract_json_payload(text: str) -> dict[str, object]:
    body = text.strip()
    if body.startswith("```"):
        lines = body.splitlines()
        if len(lines) >= 3:
            body = "\n".join(lines[1:-1]).strip()
    return json.loads(body)


def _parse_question_payload(text: str) -> QuizQuestionPayload:
    payload = _extract_json_payload(text)
    options = payload.get("options")
    wrong = payload.get("why_others_wrong")
    correct = str(payload.get("correct_option", "")).strip().upper()
    if not isinstance(options, dict) or not isinstance(wrong, dict):
        raise ValueError("invalid question payload shape")
    for key in ("A", "B", "C", "D"):
        if key not in options:
            raise ValueError("missing option key")
    if correct not in {"A", "B", "C", "D"}:
        raise ValueError("invalid correct option")
    return QuizQuestionPayload(
        topic=str(payload.get("topic", "general")),
        question=str(payload.get("question", "")),
        options={k: str(v) for k, v in options.items()},
        correct_option=correct,
        why_correct=str(payload.get("why_correct", "")),
        why_others_wrong={k: str(v) for k, v in wrong.items()},
        concept_takeaway=str(payload.get("concept_takeaway", "")),
    )


def _parse_feedback_payload(text: str) -> QuizFeedbackPayload:
    payload = _extract_json_payload(text)
    return QuizFeedbackPayload(
        user_answer_normalized=str(payload.get("user_answer_normalized", "")).strip(),
        is_correct=bool(payload.get("is_correct", False)),
        verdict_summary=str(payload.get("verdict_summary", "")),
        formal_feedback=str(payload.get("formal_feedback", "")),
        concept_takeaway=str(payload.get("concept_takeaway", "")),
    )


def _question_prompt(topic: str | None) -> str:
    topic_line = topic if topic else "general dsa interview theory"
    return (
        "Generate one interview-style multiple choice question (MCQ).\n"
        f"Topic: {topic_line}\n"
        "Return ONLY valid JSON (no markdown fences) with keys:\n"
        "topic, question, options, correct_option, why_correct, why_others_wrong, concept_takeaway.\n"
        "options must be object with keys A,B,C,D.\n"
        "why_others_wrong must include explanations for wrong options.\n"
        "Keep question practical and interview-relevant."
    )


def _answer_check_prompt(question: QuizQuestionPayload, user_answer: str) -> str:
    question_json = json.dumps(
        {
            "topic": question.topic,
            "question": question.question,
            "options": question.options,
            "correct_option": question.correct_option,
            "why_correct": question.why_correct,
            "why_others_wrong": question.why_others_wrong,
            "concept_takeaway": question.concept_takeaway,
        }
    )
    return (
        "Evaluate the user's answer against the MCQ.\n"
        f"Question payload JSON: {question_json}\n"
        f"User answer: {user_answer}\n"
        "Return ONLY valid JSON with keys:\n"
        "user_answer_normalized, is_correct, verdict_summary, formal_feedback, concept_takeaway.\n"
        "formal_feedback should explain correctness and the reasoning."
    )


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
    if topic and not is_known_quiz_topic(topic):
        return StartQuizResult(status="unknown_topic")

    user_id = _user_id_or_none(db_path, telegram_user_id)
    if user_id is None:
        return StartQuizResult(status="user_not_registered")

    llm_out = provider.generate_text(_question_prompt(topic))
    parsed = _parse_question_payload(llm_out.text)
    now_iso = _now_iso()
    expires_at = _expires_iso_from(now_iso)
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


def answer_quiz(
    *,
    db_path: str,
    telegram_user_id: str,
    user_answer_text: str,
    provider: LLMProvider,
) -> AnswerQuizResult:
    user_id = _user_id_or_none(db_path, telegram_user_id)
    if user_id is None:
        return AnswerQuizResult(status="user_not_registered")

    with get_connection(db_path) as conn:
        row = get_active_quiz_session_by_user_id(conn, user_id=user_id)
        if row is None or str(row["status"]) not in {"asked", "answered"}:
            return AnswerQuizResult(status="no_active_quiz")
        now_iso = _now_iso()
        if _is_row_expired(row, now_iso=now_iso):
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
        question = _parse_question_payload(str(row["question_payload_json"]))

    normalized_option = extract_quiz_answer_option(user_answer_text)
    if normalized_option is None:
        return AnswerQuizResult(status="invalid_answer", question=question)

    llm_out = provider.generate_text(_answer_check_prompt(question, user_answer_text))
    feedback = _parse_feedback_payload(llm_out.text)
    now_iso = _now_iso()
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


def reveal_quiz(*, db_path: str, telegram_user_id: str) -> RevealQuizResult:
    user_id = _user_id_or_none(db_path, telegram_user_id)
    if user_id is None:
        return RevealQuizResult(status="user_not_registered")

    now_iso = _now_iso()
    expires_at = _expires_iso_from(now_iso)
    with get_connection(db_path) as conn:
        row = get_active_quiz_session_by_user_id(conn, user_id=user_id)
        if row is None or str(row["status"]) not in {"asked", "answered", "revealed"}:
            return RevealQuizResult(status="no_active_quiz")
        if _is_row_expired(row, now_iso=now_iso):
            closed = close_quiz_session(
                conn,
                user_id=user_id,
                closed_at=now_iso,
                expires_at=now_iso,
                now_iso=now_iso,
            )
            if closed:
                conn.commit()
            return RevealQuizResult(status="expired_quiz")
        question = _parse_question_payload(str(row["question_payload_json"]))
        marked = mark_quiz_revealed(
            conn,
            user_id=user_id,
            revealed_at=now_iso,
            expires_at=expires_at,
            now_iso=now_iso,
        )
        if marked:
            conn.commit()
    return RevealQuizResult(status="ok", question=question)
