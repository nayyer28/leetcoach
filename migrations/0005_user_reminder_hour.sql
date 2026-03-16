ALTER TABLE users
ADD COLUMN reminder_hour_local INTEGER
    CHECK (
        reminder_hour_local IS NULL
        OR (reminder_hour_local >= 0 AND reminder_hour_local <= 23)
    );
