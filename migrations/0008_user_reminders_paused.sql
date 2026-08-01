ALTER TABLE users
ADD COLUMN reminders_paused INTEGER NOT NULL DEFAULT 0
    CHECK (reminders_paused IN (0, 1));
