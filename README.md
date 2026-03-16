# leetcoach

LeetCode prep assistant focused on logging solved problems, scheduling review reminders, and later adding interview trivia/flashcards.

## Project Docs

- usage guide (setup, CLI, DB, troubleshooting): [`docs/usage.md`](docs/usage.md)
- Fedora self-hosted deployment guide: [`docs/deploy-fedora-runner.md`](docs/deploy-fedora-runner.md)
- Telegram command contract: [`docs/telegram-command-contract.md`](docs/telegram-command-contract.md)
- v1 data model and behavior specification: [`docs/v1-spec.md`](docs/v1-spec.md)
- v2 LLM quiz specification: [`docs/v2-spec.md`](docs/v2-spec.md)
- v3 observability/deployment draft: [`docs/v3-spec.md`](docs/v3-spec.md)
- v1 software design and module architecture: [`docs/v1-software-design.md`](docs/v1-software-design.md)
- scripts usage and daily bot workflow: [`scripts/README.md`](scripts/README.md)

## Project Status

Current phase:
- post-v2 stabilization and v3 planning

Completed:
- data and behavior specification
- software design document
- CLI command via entrypoint: `lch` (`run`, `migrate`, `test`, `bot`, `doctor`, `import-notion`)
- schema migrations and DB layer
- Telegram commands: `/start`, `/register`, `/help`, guided `/log`, `/due`, `/done <token> <7th|21st>`, `/remind`, `/search`, `/list`, `/pattern`, `/quiz [topic]`, `/reveal`
- container runtime baseline (`Dockerfile`, `docker-compose.yml`)
- Notion import command and parsing pipeline
- CI workflow for advisory unit/integration test runs on PRs
- reminder scheduler loop + outbound Telegram reminders (`lch scheduler`)
- scheduler preflight/doctor command and observability counters (`lch scheduler-doctor`)
- v2 quiz flow with Gemini fallback (`/quiz [topic]`, free-text answer checking, `/reveal`)

Next:
- v2 follow-ups from spec (`docs/v2-spec.md`): quiz quality tuning and progress tracking
- v3 implementation from draft (`docs/v3-spec.md`)

v1 acceptance checklist:
- maintained in [`docs/v1-spec.md`](docs/v1-spec.md) under `V1 Acceptance Checklist`

## Developer Tooling

- GitHub App token helper for `gh` CLI: [`scripts/README.md`](scripts/README.md)
- Local bot tooling config template: [`.bot.local.env.example`](.bot.local.env.example)
