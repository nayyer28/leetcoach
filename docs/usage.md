# Usage Guide

This is the main runbook for running, debugging, and deploying leetcoach.

The app has three practical interfaces today:
- Telegram bot for normal usage
- scheduler worker for outbound reminders
- admin CLI for diagnostics and local developer workflows

Docker Compose is the normal runtime path, but the same `lch` commands can also be run directly on a machine with the project environment loaded.

## 1. Prerequisites

- Docker + Docker Compose v2
- Telegram bot token from `@BotFather`
- optional Gemini API key for `/quiz` and `/ask`

## 2. Configure Environment

Create your local runtime env file:

```bash
cp .bot.local.env.example .env
```

Minimum useful values:

```env
LEETCOACH_TELEGRAM_BOT_TOKEN=<your-token>
LEETCOACH_ALLOWED_USER_IDS=<telegram_user_id_1>,<telegram_user_id_2>
LEETCOACH_REMINDER_HOUR_LOCAL=8
LEETCOACH_REMINDER_DAILY_MAX=2
GEMINI_API_KEY=<your-gemini-api-key>
LEETCOACH_DB_PATH=/data/leetcoach.db
```

Notes:
- empty `LEETCOACH_ALLOWED_USER_IDS` means open mode
- `GEMINI_API_KEY` enables `/quiz`, `/reveal`, and `/ask`
- the container path for the SQLite DB is normally `/data/leetcoach.db`

## 3. Start The App

Apply migrations first:

```bash
docker compose run --rm bot migrate
```

Then start the bot and scheduler:

```bash
docker compose up -d bot scheduler
```

Inspect logs:

```bash
docker compose logs -f bot
docker compose logs -f scheduler
```

What each service does:
- `bot` runs Telegram long polling and all inbound commands
- `scheduler` scans the review queue and sends reminder messages during the configured reminder hour

## 4. Telegram Usage

Open the bot and start with:

```text
/start
/hi
```

Current Telegram surface:
- `/start`, `/register`, `/hi`
- `/log`, `/log show [n]`
- `/ask <question>`
- `/due`, `/reviewed P1`
- `/remind`, `/remind last`, `/remind new`, `/remind count <n>`, `/remind time <hour>`
- `/list`, `/pattern <text>`, `/search <text>`
- `/show P1`, `/edit P1`
- `/quiz`, `/quiz <topic>`, `/reveal`

See the full live contract here:
- [`docs/telegram-command-contract.md`](docs/telegram-command-contract.md)

## 5. Useful CLI Commands

These are the same commands the containers run internally:

```bash
lch doctor
lch scheduler-doctor
lch migrate
lch test
lch test unit
lch test integration
lch bot
lch scheduler --once
```

Run them inside Docker when you want to use the same runtime environment as production:

```bash
docker compose run --rm bot doctor
docker compose run --rm bot scheduler-doctor
docker compose run --rm bot scheduler --once
docker compose run --rm bot test unit
docker compose run --rm bot test integration
```

## 6. Admin CLI Diagnostics

For local `/ask` debugging, use:

```bash
lch admin ask --user <telegram_user_id> "what can you do?"
```

Helpful variants:

```bash
lch admin ask --user <telegram_user_id> --verbose "what did you remind me last?"
lch admin ask --user <telegram_user_id> --json-output "show my latest 5 problems"
lch admin ask --user <telegram_user_id> --debug-prompts --verbose "which month did I solve the most questions?"
```

What this does:
- uses the same ask service as Telegram `/ask`
- uses the same Gemini provider path as the bot
- prints ask trace events in the terminal when `--verbose` is used
- can include prompt/raw model text when `--debug-prompts` is enabled

Use this path when you want to inspect:
- which tools the model requested
- what arguments were sent
- what tool results came back
- where the model loop or final answer went wrong

## 7. Review And Reminder Behavior

Reminder behavior today:
- reminders are sent by the scheduler, not by an inbound Telegram command
- the scheduler respects the configured local reminder hour
- the scheduler respects user-specific daily max overrides when present
- reminded problems stay at the front until you mark them reviewed
- once marked reviewed, the problem moves to the back of the queue
- the scheduler no longer sends a separate daily header message before reminder entries

Reminder-related commands:
- `/due` shows outstanding reminded items
- `/reviewed P1` marks one due item reviewed
- `/remind` shows your effective reminder settings
- `/remind last` shows the last reminder batch
- `/remind new` sends one extra candidate immediately

## 8. Logging And Editing UX

Current problem-entry UX:
- `/log` is a guided multi-step flow
- after all fields are collected, the bot shows a review summary
- you can `Save`, `Edit`, or `Cancel`
- editing during log uses field pickers and current-value prompts

Stable problem IDs:
- user-facing problem references are deterministic per user
- examples: `P1`, `P2`, `P3`
- these IDs are used by `/show`, `/edit`, `/reviewed`, `/due`, `/list`, and `/ask`

## 9. Notion Import

Dry-run or apply a Notion import:

```bash
docker compose run --rm bot import-notion \
  --root-page-url "<notion_root_page_url>" \
  --telegram-user-id "<telegram_user_id>" \
  --apply
```

## 10. Data And Persistence

- Docker Compose uses the named volume `leetcoach_data`
- the live SQLite DB inside the container is normally `/data/leetcoach.db`
- container restarts do not wipe the DB because the named volume persists separately

Export the Docker-managed DB to a normal file:

```bash
docker run --rm \
  -v leetcoach_leetcoach_data:/from \
  -v "$PWD:/to" \
  alpine sh -c 'cp /from/leetcoach.db /to/leetcoach.volume.db'
```

Inspect it directly:

```bash
sqlite3 leetcoach.volume.db ".tables"
sqlite3 leetcoach.volume.db "SELECT version FROM schema_migrations ORDER BY version;"
sqlite3 leetcoach.volume.db "SELECT count(*) FROM users;"
sqlite3 leetcoach.volume.db "SELECT count(*) FROM user_problems;"
```

## 11. Deploy Recipe

Typical host deployment sequence:

1. clone repo
2. create `.env`
3. run migrations
4. start `bot` and `scheduler`
5. run doctor checks
6. inspect logs

Example:

```bash
docker compose build
docker compose run --rm bot migrate
docker compose up -d bot scheduler
docker compose run --rm bot doctor
docker compose run --rm bot scheduler-doctor
docker compose logs -f bot
docker compose logs -f scheduler
```

For the Fedora self-hosted GitHub Actions deployment path, see:
- [`docs/deploy-fedora-runner.md`](docs/deploy-fedora-runner.md)

## 12. Troubleshooting

- `telegram.error.Conflict`
  - another polling process is already using the bot token
  - stop duplicate bot instances

- `no such table ...`
  - migrations were not applied to the mounted DB
  - run `docker compose run --rm bot migrate`

- `Quiz provider is not configured`
  - `GEMINI_API_KEY` is missing
  - restart the bot after setting it

- `/ask` behaves strangely
  - use `lch admin ask --user ... --verbose`
  - add `--debug-prompts` if you need raw prompt/model text
  - inspect the ask trace before guessing

- reminders are not being sent
  - check `LEETCOACH_REMINDER_HOUR_LOCAL`
  - run `docker compose run --rm bot scheduler --once`
  - run `docker compose run --rm bot scheduler-doctor`

- want to confirm the DB path in use
  - run `docker compose run --rm bot doctor`
