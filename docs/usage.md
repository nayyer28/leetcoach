# Usage Guide

This is the operational entrypoint for day-to-day usage.

## Setup

Create and activate a project-local virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Optional global install with isolated environment (no manual venv activation):

```bash
pipx install .
```

`.env` is auto-loaded by the CLI on startup (if present in repo root).
You can still override values by exporting env vars in the shell.

After install, use the real CLI command:

```bash
lch --help
```

Legacy compatibility is still available:

```bash
python main.py --help
```

## CLI Help

```bash
lch --help
```

Expected commands:
- `run` (default when no subcommand is passed)
- `migrate`
- `test`
- `bot`
- `scheduler`
- `doctor`
- `import-notion`

## Run App Bootstrap

```bash
lch
```

Equivalent explicit command:

```bash
lch run
```

## Apply Database Migrations

```bash
lch migrate
```

This applies any pending SQL files from `migrations/` and records them in `schema_migrations`.

## Run Telegram Bot (Long Polling)

### 1) Create a bot token

Use BotFather in Telegram:
- open `@BotFather`
- run `/newbot`
- copy the generated token

### 2) Export token locally

Set bot token in `.env` (recommended):

```env
LEETCOACH_TELEGRAM_BOT_TOKEN=<your-token>
LEETCOACH_ALLOWED_USER_IDS=<telegram_user_id_1>,<telegram_user_id_2>
```

Or export in the shell (overrides `.env`):

```bash
export LEETCOACH_TELEGRAM_BOT_TOKEN="<your-token>"
export LEETCOACH_ALLOWED_USER_IDS="123456789"
```

Allow-list behavior:
- if `LEETCOACH_ALLOWED_USER_IDS` is empty/unset, bot is open to any Telegram user
- if set, only listed Telegram user IDs can use commands
- blocked users get: `⛔ Access denied for this bot.`

### 3) Start the bot process

Start bot:

```bash
lch bot
```

Bot startup now retries transient bootstrap network failures up to 5 times before exiting.

## Doctor Check

Quick health check for config and Telegram API reachability:

```bash
lch doctor
```

This validates:
- token presence (masked in output)
- DB path/timezone/allow-list visibility
- Telegram `getMe` API connectivity

## Reminder Scheduler

Run one scheduler tick and exit:

```bash
lch scheduler --once
```

Run continuous scheduler loop (default 60 seconds):

```bash
lch scheduler --interval-seconds 60
```

Scheduler behavior:
- scans pending review checkpoints (`due_at <= now <= buffer_until`)
- sends reminder messages via Telegram Bot API
- updates `last_reminded_at` on successful send
- avoids duplicate reminders within the same local user day

### 4) Start chat with your bot

In Telegram:
- open your bot and run `/start`

This registers your Telegram user/chat in the local database.

Telegram command details (input/behavior/examples) are defined in:
- [`docs/telegram-command-contract.md`](docs/telegram-command-contract.md)

Current command set:
- `/start`, `/register`, `/help`, guided `/log`, `/due`, `/done <token> <7th|21st>`, `/search <query>`, `/list`, `/pattern <pattern-substring>`

Notes:
- `/start` is register-or-welcome: first call registers, later calls welcome you back
- `/log` solved-time input accepts: `now`, ISO 8601, or `YYYY-MM-DD HH:MM` (local time)
- list/search/pattern responses are grouped by pattern and ordered by NeetCode roadmap progression
- list/search/pattern/due responses are rendered as compact numbered cards
- `/due` shows one token per problem with day-7/day-21 checkpoints under that problem
- `/done` requires both token and checkpoint day (example: `/done A1 7th`)
- timestamps are shown in configured local timezone
- list/search/pattern/due include LeetCode + NeetCode URLs built from slugs
- Telegram link previews are disabled globally to avoid noisy URL cards in chat

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
lch test
```

Run only unit tests:

```bash
lch test unit
```

Run only integration tests:

```bash
lch test integration
```

Run a specific test target:

```bash
lch test unit tests.unit.dao.test_problem_reviews_dao
```

## Import From Notion

Dry-run first (no DB writes):

```bash
lch import-notion \
  --root-page-url "https://www.notion.so/NeetCode-150-2f25715dd0d080348fe1f65ac7c4cbae" \
  --telegram-user-id "<your_telegram_user_id>"
```

Apply import:

```bash
lch import-notion \
  --root-page-url "https://www.notion.so/NeetCode-150-2f25715dd0d080348fe1f65ac7c4cbae" \
  --telegram-user-id "<your_telegram_user_id>" \
  --apply
```

## Container Runtime

Start bot + scheduler containers (builds image if missing):

```bash
docker compose up -d bot scheduler
```

Force rebuild before start (recommended after dependency/code changes):

```bash
docker compose up -d --build bot scheduler
```

Run one-off CLI commands in container:

```bash
docker compose run --rm bot migrate
docker compose run --rm bot doctor
docker compose run --rm bot test unit
docker compose run --rm bot import-notion --root-page-url "<url>" --telegram-user-id "<id>" --apply
docker compose run --rm bot scheduler --once
```

Open an interactive shell in the app container:

```bash
docker compose exec bot sh
```

Then run commands directly inside container:

```bash
lch --help
lch migrate
lch doctor
```

Stop bot:

```bash
docker compose down
```

Compose/build behavior note:
- `docker compose up -d bot` builds if image is not present
- it may not rebuild when files changed and an image already exists
- use `docker compose up -d --build bot` when you want guaranteed rebuild

Notes:
- requires a Notion token env var (default env key: `MCP_BEARER_TOKEN`)
- parser expects the current numbered-list style in your NeetCode pattern pages
- importer requires `neetcode_slug` for each parsed problem
- command prints live progress lines prefixed with `[import]`

## Troubleshooting

- `ModuleNotFoundError: click` or Telegram imports missing
  - re-run: `python -m pip install -e .`

- migration command runs but DB not where expected
  - check `LEETCOACH_DB_PATH`
  - default is `.local/leetcoach.db`

- `/done <token> <7th|21st>` says unknown/expired token
  - run `/due` again to refresh short tokens

- `telegram.error.Conflict: terminated by other getUpdates request`
  - only one long-polling bot process can run per bot token
  - stop other instances first, then restart this one
  - example process cleanup:
    - `pgrep -af "python.*main.py bot"`
    - `pkill -f "python.*main.py bot"`

- startup fails with `telegram.error.NetworkError: httpx.ReadError`
  - run `lch doctor` and check `telegram_getMe`
  - if doctor fails, verify network/VPN/proxy and retry

- scheduler sends duplicate reminders
  - verify `users.timezone` values are valid
  - inspect `problem_reviews.last_reminded_at` in DB
  - run `lch scheduler --once` to observe one-tick behavior
