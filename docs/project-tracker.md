# Project Tracker

## Current Phase

MVP implementation phase (v1).

## Completed

- GitHub App based PR workflow for bot-driven contributions
- Local bot tooling configuration and helper scripts
- v1 data and behavior specification drafted in [`docs/v1-spec.md`](docs/v1-spec.md)
- Python app skeleton in place (entrypoint, config, logging)
- SQLite schema migration runner and initial schema (`0001_init.sql`)
- DAO + service layer for core log flow (`log_problem`)
- CLI uniformity: `run`, `migrate`, `test`, `bot`
- Telegram command interface (D1): `/start`, guided `/log`, `/due`, `/done`, `/search`, `/pattern`

## Next

- add test coverage for Telegram-facing workflows and query services
- implement reminder scheduler loop (D2) with daily pending reminders + dedupe
- final usage polish and command examples as behavior evolves
