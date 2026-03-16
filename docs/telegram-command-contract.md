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
- `/show <token>`
- `/quiz [topic]`
- `/reveal`

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
2. difficulty (`easy|medium|hard`) via inline button choices or exact typed value
3. LeetCode URL or slug (`-` to skip)
4. NeetCode URL or slug (required)
5. pattern via inline button choices or exact typed value
6. solved timestamp (`now` or ISO 8601)
7. concepts (`-` to skip)
8. time complexity (`-` to skip)
9. space complexity (`-` to skip)
10. notes (`-` to skip)

Behavior:
- upserts canonical problem
- upserts user problem record
- ensures day-7 and day-21 review rows
- difficulty is case-insensitive but must be an exact known value
- pattern is normalized to the canonical roadmap label and unknown values are rejected
- LeetCode / NeetCode full URLs are accepted and normalized to stored slugs

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

## `/remind`

Purpose:
- show the effective reminder settings for the current user

Input:
- no arguments, or one of:
  - `last`
  - `new`
  - `count <n>`
  - `time <hour>`

Behavior:
- with no arguments, shows:
  - daily reminder count
  - reminder hour
  - whether count/hour come from app defaults or user overrides
- `/remind count <n>`:
  - accepts values from `1` to `10`
  - stores a user-specific daily reminder count
- `/remind time <hour>`:
  - accepts values from `0` to `23`
  - stores a user-specific reminder hour
- `/remind last`:
  - shows the most recent reminder batch sent to the user
- `/remind new`:
  - selects one additional due reminder candidate immediately
  - marks that candidate as reminded

Error responses:
- invalid or missing subcommand args -> usage hint
- non-numeric count/hour -> validation error
- out of range -> validation error

## Outbound Reminder Messages (Scheduler)

Source:
- periodic scheduler loop (`lch scheduler`) querying pending review checkpoints

Behavior:
- sends reminders for due checkpoints (`due_at <= now`) with priority balancing:
  - pending checkpoints first
  - then overdue backlog (oldest first)
- daily max reminder picks use user override when present, otherwise `LEETCOACH_REMINDER_DAILY_MAX` (default `2`)
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

## `/show <token>`

Purpose:
- show the full stored detail for one logged problem

Input:
- short token from the latest `/list`, `/search`, or `/pattern` output
- example: `/show A1`

Behavior:
- resolves token to one `user_problem_id`
- returns full stored problem detail:
  - title
  - difficulty
  - pattern
  - solved timestamp
  - LeetCode / NeetCode links
  - concepts
  - time complexity
  - space complexity
  - notes

Error responses:
- missing token -> usage hint
- unknown/expired token -> ask user to run `/list`, `/search`, or `/pattern` again

## `/quiz [topic]`

Purpose:
- generate one MCQ interview-style theory question

Input:
- optional topic text (for example `dp`, `graphs`, `system design`)

Behavior:
- requires configured `GEMINI_API_KEY`
- if topic is not recognized, bot asks:
  - `Not sure I know this topic yet. Do you want a general question instead? (yes/no)`
  - `yes` starts a general quiz
  - `no` cancels and asks for another topic
- on success, creates/replaces active quiz session for the user
- response shows question text and options `A-D`
- any other non-quiz command interrupts the active quiz session
- quiz session expires after 30 minutes of inactivity/age

Error responses:
- provider not configured -> ask to set `GEMINI_API_KEY`
- generation failure -> retry hint

## Free-Text Answer Message (after `/quiz`)

Purpose:
- check answer using normal chat message without extra command

Input:
- any non-command message while active quiz exists

Behavior:
- message is treated as answer input
- answer must include one of `A`, `B`, `C`, or `D`
- explanation after the option is allowed (example: `B because hash maps are O(1) average`)
- bot returns:
  - correctness
  - selected vs correct option
  - short explanation
  - short why-other-options-are-wrong summary

Validation:
- if no option choice is detected, bot asks the user to answer with `A/B/C/D`

If no active quiz exists:
- bot returns a compact help / command hint instead of treating the text as an answer

## `/reveal`

Purpose:
- reveal correct option and full explanation for active quiz

Input:
- no arguments

Behavior:
- works before or after answer submission
- marks session revealed and sets short retention TTL window

If no active quiz exists:
- `⚠️ No active quiz. Run /quiz first.`

If quiz expired:
- `⌛ This quiz expired. Run /quiz again.`
