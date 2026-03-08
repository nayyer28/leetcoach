# Usage Guide

This is the operational entrypoint for day-to-day usage.

## Setup

Create and activate a project-local virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

## What "v1" means

`v1` refers to the first MVP phase of leetcoach:
- log problems
- retrieve/search/pattern listing
- due/complete review checkpoints
- schema and command foundations

## CLI Help

```bash
python main.py --help
```

Expected commands:
- `run` (default when no subcommand is passed)
- `migrate`
- `test`
- `bot`

## Run App Bootstrap

```bash
python main.py
```

Equivalent explicit command:

```bash
python main.py run
```

## Apply Database Migrations

```bash
python main.py migrate
```

This applies any pending SQL files from `migrations/` and records them in `schema_migrations`.

## Run Telegram Bot (Long Polling)

### 1) Create a bot token

Use BotFather in Telegram:
- open `@BotFather`
- run `/newbot`
- copy the generated token

### 2) Export token locally

Set bot token:

```bash
export LEETCOACH_TELEGRAM_BOT_TOKEN="<your-token>"
```

### 3) Start the bot process

Start bot:

```bash
python main.py bot
```

### 4) Start chat with your bot

In Telegram:
- open your bot and run `/start`

This registers your Telegram user/chat in the local database.

## Telegram Command Reference

- `/start`
  - registers/updates user record for this chat

- `/log`
  - guided flow that asks for:
    - title
    - difficulty
    - leetcode slug
    - neetcode slug (optional via `-`)
    - pattern
    - solved timestamp (`now` or ISO)
    - concepts/time complexity/space complexity/notes (optional via `-`)

- `/due`
  - lists due review checkpoints with short tokens (example: `A1`, `A2`)

- `/done <token>`
  - marks a due checkpoint complete
  - example: `/done A1`
  - token comes from latest `/due` output

- `/search <query>`
  - searches title/pattern/notes/concepts

- `/pattern <pattern>`
  - lists problems for a specific pattern

## Inspect Database

Open SQLite shell:

```bash
sqlite3 .local/leetcoach.db
```

Quick checks:

```bash
sqlite3 .local/leetcoach.db ".tables"
sqlite3 .local/leetcoach.db "SELECT version, applied_at FROM schema_migrations ORDER BY version;"
```

Detailed schema checks:

```bash
sqlite3 .local/leetcoach.db ".schema users"
sqlite3 .local/leetcoach.db ".schema problems"
sqlite3 .local/leetcoach.db ".schema user_problems"
sqlite3 .local/leetcoach.db ".schema problem_reviews"
sqlite3 .local/leetcoach.db "SELECT name, tbl_name FROM sqlite_master WHERE type='index' ORDER BY tbl_name, name;"
```

## Run Integration Tests

```bash
python main.py test
```
