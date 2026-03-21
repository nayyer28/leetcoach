ALTER TABLE user_problems
ADD COLUMN display_id INTEGER NOT NULL DEFAULT 0;

WITH ranked AS (
    SELECT
        id,
        ROW_NUMBER() OVER (
            PARTITION BY user_id
            ORDER BY solved_at ASC, id ASC
        ) AS next_display_id
    FROM user_problems
)
UPDATE user_problems
SET display_id = (
    SELECT ranked.next_display_id
    FROM ranked
    WHERE ranked.id = user_problems.id
);

CREATE UNIQUE INDEX idx_user_problems_user_display_id_unique
    ON user_problems(user_id, display_id);
