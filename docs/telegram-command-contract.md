# Telegram Command Contract

This document describes the current Telegram interface.

Important boundary:
- inbound chat commands are handled by the bot
- outbound reminders are sent by the scheduler process (`lch scheduler`)

## Live Command List

- `/start`
- `/register`
- `/hi`
- `/log`
- `/log show [n]`
- `/ask <question>`
- `/due`
- `/reviewed P1`
- `/remind`
- `/remind last`
- `/remind new`
- `/remind count <n>`
- `/remind time <hour>`
- `/list`
- `/pattern <text>`
- `/search <text>`
- `/show P1`
- `/edit P1`
- `/quiz`
- `/quiz <topic>`
- `/reveal`

## Access Control

Behavior:
- bot checks `LEETCOACH_ALLOWED_USER_IDS` against Telegram `user_id`
- empty allow-list means open mode
- non-empty allow-list means only listed users may use the bot

Blocked response:
- `⛔ Access denied for this bot.`

## Registration And Help

### `/start`
- registers or refreshes the user/chat mapping
- returns the command menu

### `/register`
- explicit alias for registration

### `/hi`
- shows the current command menu
- this is the live help command

## `/log`

Purpose:
- create or update one logged problem
- initialize or refresh review-queue state for that problem

Flow:
1. title
2. difficulty
3. LeetCode URL or slug
4. NeetCode URL or slug
5. pattern
6. solved time
7. concepts
8. time complexity
9. space complexity
10. notes

Current behavior:
- difficulty and pattern use guided choices
- URL or slug input is normalized to stored slugs
- after all fields are collected, the bot shows a review summary
- from the summary, the user can:
  - save
  - edit one field
  - cancel

Notes:
- optional text fields can be cleared with `-`
- solved time accepts:
  - `now`
  - ISO 8601
  - local `YYYY-MM-DD HH:MM`

### `/log show [n]`
- read-only shortcut
- shows the most recently logged `n` problems
- default is `1`
- does not start the guided log flow

## Stable Problem IDs

User-facing problem references are deterministic and per-user.

Examples:
- `P1`
- `P2`
- `P3`

These IDs are used by:
- `/show`
- `/edit`
- `/reviewed`
- `/due`
- `/list`
- `/search`
- `/pattern`
- `/ask`

## `/show P1`

Purpose:
- show full stored detail for one problem

Returns:
- title
- difficulty
- pattern
- solved time
- LeetCode URL
- NeetCode URL
- concepts
- time complexity
- space complexity
- notes

## `/edit P1`

Purpose:
- guided edit flow for one existing problem

Behavior:
- opens a field picker
- user chooses what to edit
- difficulty and pattern use guided selection
- text-like fields prompt with current value shown first
- on success, bot confirms the updated field

User-facing fields:
- title
- difficulty
- LeetCode URL
- NeetCode URL
- pattern
- concepts
- time complexity
- space complexity
- notes

## Browse Commands

### `/list`
- lists logged problems for the current user
- grouped and ordered for readability

### `/pattern <text>`
- filters problems by pattern text

### `/search <text>`
- searches across problem metadata and notes

Current search behavior includes fields such as:
- title
- difficulty
- LeetCode slug
- NeetCode slug
- pattern
- solved date text
- time complexity
- space complexity
- notes
- concepts

## Review Commands

### `/due`
- shows reminded-but-not-yet-reviewed problems
- uses stable problem IDs like `P1`

### `/reviewed P1`
- marks the problem reviewed
- increments review count
- updates review timestamps
- moves the problem to the back of the queue

## Reminder Commands

### `/remind`
- shows effective reminder settings for the current user

### `/remind count <n>`
- sets a user-specific daily reminder max

### `/remind time <hour>`
- sets a user-specific reminder hour

### `/remind last`
- shows the most recent reminder batch sent to the user

### `/remind new`
- sends one extra review candidate immediately

Scheduler notes:
- reminders are sent by the scheduler worker
- the scheduler respects local reminder hour
- the scheduler respects user-specific overrides when present
- the scheduler no longer sends a separate daily header message before reminder entries

## `/ask <question>`

Purpose:
- read-only natural-language interface over the user’s own data

Current ask surface includes:
- problem detail and lookup
- problem listing and filtering
- problem search
- due review reads
- last reminder batch reads
- aggregate analytics
- ask capability/help questions

Examples:
- `/ask what can you do?`
- `/ask show problem P1`
- `/ask show my latest 5 problems`
- `/ask show me all problems I solved in Feb 2026`
- `/ask what is due right now?`
- `/ask what did you remind me last?`
- `/ask how many easy problems have I solved in Trees?`

Important constraint:
- `/ask` is read-only for now
- write flows such as logging and editing are better done with explicit commands

## Quiz Commands

### `/quiz`
### `/quiz <topic>`

Behavior:
- generates one theory-style MCQ
- creates or replaces the active quiz session
- topic is optional
- session expires after a limited time window

### Free-text answer messages
- while a quiz is active, the next normal message is treated as answer input
- answer must contain `A`, `B`, `C`, or `D`
- bot returns correctness plus explanation

### `/reveal`
- reveals the correct answer and explanation for the active quiz

## Unknown Text / Unknown Commands

Behavior:
- bot returns a compact command hint
- the fallback help points users toward:
  - `/hi`
  - `/ask <question>`
  - the main read/write commands
