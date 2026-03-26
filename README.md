# leetcoach

LeetCoach is a Telegram-first LeetCode prep assistant for:
- logging solved problems
- scheduling review reminders
- running short quiz prompts
- asking read-only questions over your own problem history

It runs as a small SQLite-backed app with:
- a Telegram bot interface
- a scheduler worker for outbound reminders
- an admin CLI for diagnostics and local development

## What You Can Use Today

### Telegram
- `/log` with guided review-before-save flow
- `/edit P1` with guided field selection
- `/show P1`, `/list`, `/pattern <text>`, `/search <text>`
- `/due`, `/reviewed P1`, `/remind ...`
- `/quiz`, `/quiz <topic>`, `/reveal`
- `/ask <question>` for read-only problem, review, reminder, and analytics queries

### CLI
- `lch bot`
- `lch scheduler`
- `lch doctor`
- `lch scheduler-doctor`
- `lch migrate`
- `lch test ...`
- `lch import-notion ...`
- `lch admin ask --user <telegram_user_id> "question"`

### Deployment
- Docker Compose for normal runtime
- Fedora self-hosted GitHub Actions deploy path

## Primary Docs

- usage and local runbook: [`docs/usage.md`](docs/usage.md)
- Telegram interface contract: [`docs/telegram-command-contract.md`](docs/telegram-command-contract.md)
- Fedora self-hosted deployment guide: [`docs/deploy-fedora-runner.md`](docs/deploy-fedora-runner.md)
- local scripts and GitHub App workflow: [`scripts/README.md`](scripts/README.md)

## Design Notes

These docs are still useful, but they are design/history references rather than the live product contract:

- v1 software design: [`docs/v1-software-design.md`](docs/v1-software-design.md)
- v1 data/behavior spec: [`docs/v1-spec.md`](docs/v1-spec.md)
- v2 quiz spec: [`docs/v2-spec.md`](docs/v2-spec.md)
- v3 observability/deployment draft: [`docs/v3-spec.md`](docs/v3-spec.md)

## Quick Start

```bash
cp .bot.local.env.example .env
docker compose run --rm bot migrate
docker compose up -d bot scheduler
docker compose run --rm bot doctor
docker compose run --rm bot scheduler-doctor
```

Then open the bot in Telegram and start with:

```text
/start
/hi
```

## Diagnostics

For local ask/LLM debugging:

```bash
lch admin ask --user <telegram_user_id> "what can you do?"
lch admin ask --user <telegram_user_id> --verbose "what did you remind me last?"
lch admin ask --user <telegram_user_id> --debug-prompts --verbose "which month did I solve the most questions?"
```

That path uses the same ask service as the bot, but prints request traces in the terminal so odd LLM behavior can be inspected locally before it shows up in production.
