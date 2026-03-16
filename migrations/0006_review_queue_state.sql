ALTER TABLE user_problems
ADD COLUMN queue_position INTEGER NOT NULL DEFAULT 0;

ALTER TABLE user_problems
ADD COLUMN review_count INTEGER NOT NULL DEFAULT 0;

ALTER TABLE user_problems
ADD COLUMN last_review_requested_at TEXT;

ALTER TABLE user_problems
ADD COLUMN last_reviewed_at TEXT;

UPDATE user_problems
SET review_count = COALESCE(
        (
            SELECT COUNT(*)
            FROM problem_reviews pr
            WHERE pr.user_problem_id = user_problems.id
              AND pr.completed_at IS NOT NULL
        ),
        0
    ),
    last_review_requested_at = (
        SELECT MAX(pr.last_reminded_at)
        FROM problem_reviews pr
        WHERE pr.user_problem_id = user_problems.id
    ),
    last_reviewed_at = (
        SELECT MAX(pr.completed_at)
        FROM problem_reviews pr
        WHERE pr.user_problem_id = user_problems.id
    );

WITH ranked AS (
    SELECT
        id,
        ROW_NUMBER() OVER (
            PARTITION BY user_id
            ORDER BY solved_at ASC, id ASC
        ) * 10 AS next_position
    FROM user_problems
)
UPDATE user_problems
SET queue_position = (
    SELECT ranked.next_position
    FROM ranked
    WHERE ranked.id = user_problems.id
);

CREATE INDEX idx_user_problems_user_queue_position
    ON user_problems(user_id, queue_position);

CREATE INDEX idx_user_problems_user_review_requested
    ON user_problems(user_id, last_review_requested_at);
