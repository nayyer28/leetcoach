# Telegram Command Contract

This document defines Telegram command behavior for the current app interface.
Outbound reminders are delivered by the scheduler process (`lch scheduler`), not by an inbound Telegram command.

## Command List

- `/start`
- `/register`
- `/help`
- `/log`
- `/due`
- `/done <token> <7th|21st>`
- `/search <query>`
- `/list`
- `/pattern <pattern>`

## Access Control

Behavior:
- bot checks `LEETCOACH_ALLOWED_USER_IDS` against Telegram `user_id`
- empty allow list: open mode (any user)
- non-empty allow list: only listed users can execute commands

Blocked response:
- `⛔ Access denied for this bot.`

## `/start`

Purpose:
- register or update user/chat mapping

Input:
- no arguments

Behavior:
- upserts user by Telegram user id
- stores Telegram chat id and timezone default

Success response:
- first run: registered confirmation + command menu
- later runs: welcome-back message + command menu

## `/register`

Purpose:
- explicit registration alias (same behavior as `/start`)

Input:
- no arguments

Behavior:
- calls same register-or-welcome flow as `/start`

## `/help`

Purpose:
- show command menu without re-registering the user

Input:
- no arguments

Behavior:
- returns grouped command help text

## `/log` (guided flow)

Purpose:
- create or update one logged problem and ensure review checkpoints

Input mode:
- guided, multi-step prompts in chat

Prompt sequence:
1. title
2. difficulty (`easy|medium|hard`)
3. leetcode slug
4. neetcode slug (`-` to skip)
5. pattern
6. solved timestamp (`now` or ISO 8601)
7. concepts (`-` to skip)
8. time complexity (`-` to skip)
9. space complexity (`-` to skip)
10. notes (`-` to skip)

Behavior:
- upserts canonical problem
- upserts user problem record
- ensures day-7 and day-21 review rows

Success response:
- confirms problem logged and shows `user_problem_id`

Accepted solved timestamp inputs:
- `now`
- ISO 8601 (for example `2026-03-08T12:00:00+00:00`)
- local datetime `YYYY-MM-DD HH:MM` (converted to UTC for storage)

Cancel:
- `/cancel` during flow aborts and clears pending state

## `/due`

Purpose:
- list due review checkpoints and provide short completion tokens

Input:
- no arguments

Behavior:
- finds pending/overdue review rows for the current user
- groups rows by problem so each problem appears once with a single token (`A1`, `A2`, ...)
- shows day-7/day-21 checkpoints under the same problem entry (when due)
- includes first-attempt timestamp (`solved_at`) for context

Success response:
- compact numbered list with token, title, review day, status, due time
- due time is rendered in configured local timezone
- includes LeetCode and NeetCode links built from stored slugs

No data response:
- `No pending/overdue reviews.`

## Outbound Reminder Messages (Scheduler)

Source:
- periodic scheduler loop (`lch scheduler`) querying pending review checkpoints

Behavior:
- sends reminders for due checkpoints (`due_at <= now`) with priority balancing:
  - pending checkpoints first
  - then overdue backlog (oldest first)
- daily max reminder picks are controlled by `LEETCOACH_REMINDER_DAILY_MAX` (default `2`)
- sends only at local hour `LEETCOACH_REMINDER_HOUR_LOCAL` (default `8`)
- de-duplicates by local user day using `last_reminded_at`
- sends a header message first so subsequent messages are clearly marked as reminder picks
- includes first-attempt time, due time, and checkpoint day
- includes LeetCode/NeetCode links when available
- instructs user to run `/due` and then `/done <token> <7th|21st>`

## `/done <token> <7th|21st>`

Purpose:
- mark one due review checkpoint as completed

Input:
- short token from latest `/due` output plus checkpoint day
- example: `/done A1 7th` or `/done A1 21st`

Behavior:
- resolves token to `user_problem_id`
- resolves day argument to `review_day` (7 or 21)
- updates `completed_at` if the selected day row is still open

Success response:
- `Marked complete: <token>`

Error responses:
- missing token -> usage hint
- unknown/expired token -> ask to run `/due` again
- stale token/update failure -> ask to run `/due` again

## `/search <query>`

Purpose:
- search problems by title/pattern/notes/concepts

Input:
- free text query

Behavior:
- case-insensitive search scoped to current user

Success response:
- compact numbered list with title, difficulty, pattern, solved time
- solved time is rendered in configured local timezone
- includes LeetCode and NeetCode links built from stored slugs

No data response:
- `No matching problems.`

## `/list`

Purpose:
- list all logged problems for the current user

Input:
- no arguments

Behavior:
- returns up to 100 user problems, newest solved first

Success response:
- compact numbered list with title, difficulty, pattern, solved time
- solved time is rendered in configured local timezone
- includes LeetCode and NeetCode links built from stored slugs

No data response:
- `No logged problems yet.`

## `/pattern <pattern>`

Purpose:
- list problems under one pattern name

Input:
- pattern substring

Behavior:
- case-insensitive partial match on stored pattern, scoped to current user

Success response:
- compact numbered list with title/difficulty/pattern/solved time
- solved time is rendered in configured local timezone
- includes LeetCode and NeetCode links built from stored slugs

No data response:
- `No problems for this pattern.`
