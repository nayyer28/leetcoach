# leetcoach

LeetCode prep assistant focused on logging solved problems, scheduling review reminders, and later adding interview trivia/flashcards.

## Project Docs

- usage guide (setup, CLI, DB, troubleshooting): [`docs/usage.md`](docs/usage.md)
- Telegram command contract: [`docs/telegram-command-contract.md`](docs/telegram-command-contract.md)
- v1 data model and behavior specification: [`docs/v1-spec.md`](docs/v1-spec.md)
- v1 software design and module architecture: [`docs/v1-software-design.md`](docs/v1-software-design.md)
- scripts usage and daily bot workflow: [`scripts/README.md`](scripts/README.md)

## Project Status

Current phase:
- MVP implementation (`v1`)

Completed:
- data and behavior specification
- software design document
- CLI command via entrypoint: `lch` (`run`, `migrate`, `test`, `bot`, `doctor`, `import-notion`)
- schema migrations and DB layer
- Telegram D1 commands: `/start`, `/register`, `/help`, guided `/log`, `/due`, `/done <token> <7th|21st>`, `/search`, `/list`, `/pattern`
- container runtime baseline (`Dockerfile`, `docker-compose.yml`)
- Notion import command and parsing pipeline
- CI workflow for advisory unit/integration test runs on PRs
- reminder scheduler loop + outbound Telegram reminders (`lch scheduler`)
- scheduler preflight/doctor command and observability counters (`lch scheduler-doctor`)

Next:
- trivia/flashcards learning mode

v1 acceptance checklist:
- maintained in [`docs/v1-spec.md`](docs/v1-spec.md) under `V1 Acceptance Checklist`

## Developer Tooling

- GitHub App token helper for `gh` CLI: [`scripts/README.md`](scripts/README.md)
- Local bot tooling config template: [`.bot.local.env.example`](.bot.local.env.example)
