from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Protocol


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


def normalize_quiz_topic(raw: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", raw.lower()).split())


def is_known_quiz_topic(raw_topic: str) -> bool:
    return normalize_quiz_topic(raw_topic) in KNOWN_QUIZ_TOPICS


def extract_quiz_answer_option(raw_answer: str) -> str | None:
    match = QUIZ_ANSWER_OPTION_RE.search(raw_answer.strip())
    if match is None:
        return None
    return match.group(1).upper()


def extract_json_payload(text: str) -> dict[str, object]:
    body = text.strip()
    if body.startswith("```"):
        lines = body.splitlines()
        if len(lines) >= 3:
            body = "\n".join(lines[1:-1]).strip()
    return json.loads(body)


def parse_question_payload(text: str) -> QuizQuestionPayload:
    payload = extract_json_payload(text)
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


def parse_feedback_payload(text: str) -> QuizFeedbackPayload:
    payload = extract_json_payload(text)
    return QuizFeedbackPayload(
        user_answer_normalized=str(payload.get("user_answer_normalized", "")).strip(),
        is_correct=bool(payload.get("is_correct", False)),
        verdict_summary=str(payload.get("verdict_summary", "")),
        formal_feedback=str(payload.get("formal_feedback", "")),
        concept_takeaway=str(payload.get("concept_takeaway", "")),
    )


def question_prompt(topic: str | None) -> str:
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


def answer_check_prompt(question: QuizQuestionPayload, user_answer: str) -> str:
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

