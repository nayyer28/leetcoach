# Usage Guide

This is the operational entrypoint for day-to-day usage.

## Setup

Create and activate a project-local virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

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

Telegram command details (input/behavior/examples) are defined in:
- [`docs/telegram-command-contract.md`](docs/telegram-command-contract.md)

Current command set:
- `/start`, guided `/log`, `/due`, `/done <token>`, `/search <query>`, `/list`, `/pattern <pattern-substring>`

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

Run only unit tests:

```bash
python main.py test unit
```

Run only integration tests:

```bash
python main.py test integration
```

Run a specific test target:

```bash
python main.py test unit tests.unit.dao.test_problem_reviews_dao
```

## Troubleshooting

- `ModuleNotFoundError: click` or Telegram imports missing
  - re-run: `python -m pip install -e .`

- migration command runs but DB not where expected
  - check `LEETCOACH_DB_PATH`
  - default is `.local/leetcoach.db`

- `/done <token>` says unknown/expired token
  - run `/due` again to refresh short tokens
