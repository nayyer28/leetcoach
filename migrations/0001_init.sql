CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    telegram_user_id TEXT NOT NULL UNIQUE,
    telegram_chat_id TEXT NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'UTC',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE problems (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    difficulty TEXT NOT NULL CHECK (difficulty IN ('easy', 'medium', 'hard')),
    leetcode_slug TEXT NOT NULL UNIQUE,
    neetcode_slug TEXT UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX idx_problems_title ON problems(title);
CREATE UNIQUE INDEX idx_problems_neetcode_slug_unique
    ON problems(neetcode_slug)
    WHERE neetcode_slug IS NOT NULL;

CREATE TABLE user_problems (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    problem_id INTEGER NOT NULL REFERENCES problems(id) ON DELETE CASCADE,
    pattern TEXT NOT NULL,
    solved_at TEXT NOT NULL,
    concepts TEXT,
    time_complexity TEXT,
    space_complexity TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX idx_user_problems_user_problem_unique
    ON user_problems(user_id, problem_id);
CREATE INDEX idx_user_problems_user_pattern
    ON user_problems(user_id, pattern);
CREATE INDEX idx_user_problems_user_solved_at
    ON user_problems(user_id, solved_at);

CREATE TABLE problem_reviews (
    id INTEGER PRIMARY KEY,
    user_problem_id INTEGER NOT NULL REFERENCES user_problems(id) ON DELETE CASCADE,
    review_day INTEGER NOT NULL CHECK (review_day IN (7, 21)),
    due_at TEXT NOT NULL,
    buffer_until TEXT NOT NULL,
    completed_at TEXT,
    last_reminded_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX idx_problem_reviews_user_problem_day_unique
    ON problem_reviews(user_problem_id, review_day);
CREATE INDEX idx_problem_reviews_due_at
    ON problem_reviews(due_at);
CREATE INDEX idx_problem_reviews_buffer_until
    ON problem_reviews(buffer_until);
CREATE INDEX idx_problem_reviews_completed_at
    ON problem_reviews(completed_at);
