# Usage Guide (Docker-First)

This is the primary runbook for running leetcoach.

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
- `/search <query>`, `/list`, `/pattern <pattern-substring>`
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

- SQLite DB is persisted at `.local/leetcoach.db` via compose volume mount.
- If containers restart, data remains.
- Back up periodically:

```bash
cp .local/leetcoach.db ".local/leetcoach.db.backup.$(date +%Y%m%d-%H%M%S)"
```

## Troubleshooting

- `telegram.error.Conflict`:
  - another polling process is already using the bot token
  - stop duplicate bot instances

- `no such table ...`:
  - migrations were not applied to mounted DB
  - run `docker compose run --rm bot migrate`

- `Quiz provider is not configured`:
  - missing `GEMINI_API_KEY` in `.env`
  - restart bot after setting key

- no reminders sent:
  - check local-hour gate in `.env` (`LEETCOACH_REMINDER_HOUR_LOCAL`)
  - run one tick manually: `docker compose run --rm bot scheduler --once`
