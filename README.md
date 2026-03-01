# leetcoach

LeetCode prep assistant focused on logging solved problems, scheduling review reminders, and later adding interview trivia/flashcards.

## Project Docs

- v1 data model and behavior specification: [`docs/v1-spec.md`](docs/v1-spec.md)
- database migrations and local DB inspection: [`docs/db-quickstart.md`](docs/db-quickstart.md)
- v1 software design and module architecture: [`docs/v1-software-design.md`](docs/v1-software-design.md)
- database migrations and local DB inspection: [`docs/db-quickstart.md`](docs/db-quickstart.md)
- project status and next steps tracker: [`docs/project-tracker.md`](docs/project-tracker.md)
- scripts usage and daily bot workflow: [`scripts/README.md`](scripts/README.md)

## Developer Tooling

- GitHub App token helper for `gh` CLI: [`scripts/README.md`](scripts/README.md)
- Local bot tooling config template: [`.bot.local.env.example`](.bot.local.env.example)

## Python Environment

Use a project-local virtual environment to avoid polluting the global Python installation.

```bash
python3 -m venv .venv
source .venv/bin/activate
python main.py
```

Apply database migrations:

```bash
source .venv/bin/activate
python main.py migrate
```

Inspect DB schema and data:

```bash
source .venv/bin/activate
sqlite3 .local/leetcoach.db
```
