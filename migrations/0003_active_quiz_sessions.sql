CREATE TABLE active_quiz_sessions (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    topic TEXT,
    question_payload_json TEXT NOT NULL,
    model_used TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('asked', 'answered', 'revealed', 'closed')),
    user_answer_text TEXT,
    answer_feedback_json TEXT,
    asked_at TEXT NOT NULL,
    answered_at TEXT,
    revealed_at TEXT,
    closed_at TEXT,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX idx_active_quiz_sessions_user_unique
    ON active_quiz_sessions(user_id);
CREATE INDEX idx_active_quiz_sessions_status
    ON active_quiz_sessions(status);
CREATE INDEX idx_active_quiz_sessions_expires_at
    ON active_quiz_sessions(expires_at);
