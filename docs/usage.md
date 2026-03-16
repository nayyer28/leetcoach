# Usage Guide (Docker-First)

This is the primary runbook for running leetcoach.
Docker is the main operational path, but the CLI commands described here are the same commands the containers run internally.

## Prerequisites

- Docker + Docker Compose v2
- Telegram bot token from `@BotFather`
- (optional, for quiz) Gemini API key

## Configure Environment

Create your local env file:

```bash
cp .bot.local.env.example .env
```

Set at least these values in `.env`:

```env
LEETCOACH_TELEGRAM_BOT_TOKEN=<your-token>
LEETCOACH_ALLOWED_USER_IDS=<telegram_user_id_1>,<telegram_user_id_2>
LEETCOACH_REMINDER_HOUR_LOCAL=8
LEETCOACH_REMINDER_DAILY_MAX=2
GEMINI_API_KEY=<your-gemini-api-key>
LEETCOACH_DB_PATH=/data/leetcoach.db
```

Notes:
- if `LEETCOACH_ALLOWED_USER_IDS` is empty, bot is open mode
- set `GEMINI_API_KEY` to enable `/quiz` and `/reveal`

## Start leetcoach

Apply DB migrations first:

```bash
docker compose run --rm bot migrate
```

Start bot + scheduler:

```bash
docker compose up -d bot scheduler
```

Check logs:

```bash
docker compose logs -f bot
docker compose logs -f scheduler
```

What these services do:
- `bot` runs long-polling Telegram handlers
- `scheduler` runs outbound reminder selection/sending every 60 seconds and only dispatches during the configured local reminder hour

## Telegram Commands

After startup, open your bot and run:

```text
/start
```

Command contract lives in:
- [`docs/telegram-command-contract.md`](docs/telegram-command-contract.md)

Current commands:
- `/start`, `/register`, `/help`
- `/log`, `/due`, `/done <token> <7th|21st>`
- `/search <query>`, `/list`, `/pattern <pattern-substring>`, `/show <token>`
- `/quiz [topic]`, `/reveal`

## Operational Commands (via container)

Run one-off commands:

```bash
docker compose run --rm bot doctor
docker compose run --rm bot scheduler-doctor
docker compose run --rm bot scheduler --once
docker compose run --rm bot test
docker compose run --rm bot test unit
docker compose run --rm bot test integration
```

Open a shell in the app container:

```bash
docker compose exec bot sh
```

Then run the same CLI directly inside the container:

```bash
lch --help
lch doctor
lch scheduler-doctor
lch migrate
```

## Doctor Commands

General environment + Telegram API check:

```bash
docker compose run --rm bot doctor
```

This checks:
- current DB path
- configured timezone
- count of allowed Telegram user IDs
- presence of Telegram bot token
- live `getMe` reachability against Telegram API

Scheduler preflight check:

```bash
docker compose run --rm bot scheduler-doctor
```

This checks:
- current DB path
- `LEETCOACH_REMINDER_HOUR_LOCAL`
- `LEETCOACH_REMINDER_DAILY_MAX`
- presence of Telegram bot token
- required DB tables for scheduler execution

Run one scheduler tick manually:

```bash
docker compose run --rm bot scheduler --once
```

This is useful when you want to inspect scheduler behavior without waiting for the loop.

## Logging UX Notes

- `/log` now offers inline button choices for difficulty and known roadmap patterns
- typed difficulty is accepted only for exact values: `easy`, `medium`, `hard` (case-insensitive)
- typed pattern is accepted only if it resolves to a known roadmap pattern
- common aliases like `tree` normalize to `Trees`
- LeetCode and NeetCode inputs accept either the full problem URL or the raw slug

Notion import:

```bash
docker compose run --rm bot import-notion \
  --root-page-url "<notion_root_page_url>" \
  --telegram-user-id "<telegram_user_id>" \
  --apply
```

## Deploy App (Recipe)

Use this sequence on any host (local machine, VM, home server):

1. Clone repo and enter directory.
2. Create env file:
   - `cp .bot.local.env.example .env`
   - fill required values
3. Prepare persistent local directory:
   - `mkdir -p .local`
4. Build and migrate:
   - `docker compose build`
   - `docker compose run --rm bot migrate`
5. Start services:
   - `docker compose up -d bot scheduler`
6. Verify health:
   - `docker compose run --rm bot doctor`
   - `docker compose run --rm bot scheduler-doctor`
7. Verify runtime:
   - `docker compose logs -f bot`
   - `docker compose logs -f scheduler`

## Data and Persistence

- Compose uses a named Docker volume: `leetcoach_data`.
- Inside the containers, the SQLite file path is `/data/leetcoach.db`.
- If containers restart, data remains because the named volume persists independently of the containers.

Export the active Docker-managed DB to a normal file:

```bash
docker run --rm \
  -v leetcoach_leetcoach_data:/from \
  -v "$PWD:/to" \
  alpine sh -c 'cp /from/leetcoach.db /to/leetcoach.volume.db'
```

Back up a file-based copy:

```bash
cp leetcoach.volume.db "leetcoach.volume.db.backup.$(date +%Y%m%d-%H%M%S)"
```

## Inspect SQLite Directly

Inspect an exported DB file:

```bash
sqlite3 leetcoach.volume.db ".tables"
sqlite3 leetcoach.volume.db "SELECT version FROM schema_migrations ORDER BY version;"
sqlite3 leetcoach.volume.db ".schema active_quiz_sessions"
sqlite3 leetcoach.volume.db "SELECT count(*) FROM users;"
sqlite3 leetcoach.volume.db "SELECT count(*) FROM user_problems;"
sqlite3 leetcoach.volume.db "SELECT count(*) FROM problem_reviews;"
sqlite3 leetcoach.volume.db "SELECT count(*) FROM active_quiz_sessions;"
```

Inspect the live DB by opening a shell in the container first:

```bash
docker compose exec bot sh
sqlite3 /data/leetcoach.db ".tables"
sqlite3 /data/leetcoach.db "SELECT version FROM schema_migrations ORDER BY version;"
```

## Troubleshooting

- `telegram.error.Conflict`:
  - another polling process is already using the bot token
  - stop duplicate bot instances

- `no such table ...`:
  - migrations were not applied to mounted DB
  - run `docker compose run --rm bot migrate`

- DB file looks stale or missing expected quiz data:
  - confirm you are inspecting the Docker volume DB, not an older host-side copy
  - export the current volume DB and inspect `schema_migrations`
  - `active_quiz_sessions` exists only after migration `0003_active_quiz_sessions.sql`

- `Quiz provider is not configured`:
  - missing `GEMINI_API_KEY` in `.env`
  - restart bot after setting key

- no reminders sent:
  - check local-hour gate in `.env` (`LEETCOACH_REMINDER_HOUR_LOCAL`)
  - run one tick manually: `docker compose run --rm bot scheduler --once`

- want to confirm the exact DB path the app is using:
  - run `docker compose run --rm bot doctor`
  - current Compose wiring should report `/data/leetcoach.db`
