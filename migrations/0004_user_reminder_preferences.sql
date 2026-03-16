ALTER TABLE users
ADD COLUMN reminder_daily_max INTEGER
    CHECK (reminder_daily_max IS NULL OR reminder_daily_max >= 1);
