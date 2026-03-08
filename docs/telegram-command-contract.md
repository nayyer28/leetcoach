# Telegram Command Contract

This document defines Telegram command behavior for the current app interface.

## Command List

- `/start`
- `/help`
- `/log`
- `/due`
- `/done <token>`
- `/search <query>`
- `/list`
- `/pattern <pattern>`

## `/start`

Purpose:
- register or update user/chat mapping

Input:
- no arguments

Behavior:
- upserts user by Telegram user id
- stores Telegram chat id and timezone default

Success response:
- command list summary for available actions

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
- returns entries with short tokens `A1`, `A2`, ...

Success response:
- structured list with token, title, review day, status, due time
- due time is rendered in configured local timezone

No data response:
- `No pending/overdue reviews.`

## `/done <token>`

Purpose:
- mark one due review checkpoint as completed

Input:
- short token from latest `/due` output (example: `A1`)

Behavior:
- resolves token to `{user_problem_id, review_day}`
- updates `completed_at` if row is still open

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
- structured list with title, difficulty, pattern, solved time
- solved time is rendered in configured local timezone

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
- structured list with title, difficulty, pattern, solved time
- solved time is rendered in configured local timezone

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
- structured list with title/difficulty/pattern/solved time
- solved time is rendered in configured local timezone

No data response:
- `No problems for this pattern.`
