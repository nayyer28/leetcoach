-- Collapse the review queue to a single (review_count, entered_at) priority tuple
-- backed by one composite index. Drop the old queue_position / last_review_requested_at /
-- last_reviewed_at model. Track daily de-dupe per user via users.last_reminded_at.

ALTER TABLE user_problems
    ADD COLUMN entered_at TEXT NOT NULL DEFAULT '1970-01-01T00:00:00+00:00';

ALTER TABLE users
    ADD COLUMN last_reminded_at TEXT;

-- entered_at means "when did this problem enter its current review_count bucket".
-- For never-reviewed rows that is solved_at; for reviewed rows it is the last review time.
UPDATE user_problems
SET entered_at = COALESCE(last_reviewed_at, solved_at);

-- Rebuild the per-user daily de-dupe timestamp from the old per-row reminded-at column.
UPDATE users
SET last_reminded_at = (
    SELECT MAX(up.last_review_requested_at)
    FROM user_problems up
    WHERE up.user_id = users.id
);

DROP INDEX IF EXISTS idx_user_problems_user_queue_position;
DROP INDEX IF EXISTS idx_user_problems_user_review_requested;

ALTER TABLE user_problems DROP COLUMN queue_position;
ALTER TABLE user_problems DROP COLUMN last_review_requested_at;
ALTER TABLE user_problems DROP COLUMN last_reviewed_at;

CREATE INDEX idx_user_problems_user_review_count_entered_at
    ON user_problems(user_id, review_count, entered_at);

-- Old spaced-repetition checkpoint table (review_day 7/21). Superseded by the
-- level-fill priority queue; nothing reads it anymore.
DROP TABLE IF EXISTS problem_reviews;
