PRAGMA foreign_keys = OFF;

CREATE TABLE problems_new (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    difficulty TEXT NOT NULL CHECK (difficulty IN ('easy', 'medium', 'hard')),
    leetcode_slug TEXT UNIQUE,
    neetcode_slug TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

INSERT INTO problems_new (
    id,
    title,
    difficulty,
    leetcode_slug,
    neetcode_slug,
    created_at,
    updated_at
)
SELECT
    id,
    title,
    difficulty,
    leetcode_slug,
    neetcode_slug,
    created_at,
    updated_at
FROM problems;

DROP INDEX IF EXISTS idx_problems_title;
DROP INDEX IF EXISTS idx_problems_neetcode_slug_unique;

DROP TABLE problems;
ALTER TABLE problems_new RENAME TO problems;

CREATE INDEX idx_problems_title ON problems(title);

PRAGMA foreign_keys = ON;
