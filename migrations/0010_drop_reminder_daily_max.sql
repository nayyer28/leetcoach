-- Remove users.reminder_daily_max. The priority-queue scheduler sends exactly
-- one problem per user per local day; a configurable daily cap is dead
-- config. Only reminder_hour_local and reminders_paused survive.

ALTER TABLE users DROP COLUMN reminder_daily_max;
