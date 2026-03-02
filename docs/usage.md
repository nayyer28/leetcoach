# Usage Guide

This document covers day-to-day usage of the app CLI and database migrations.

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

For detailed DB commands, see [`docs/db-quickstart.md`](docs/db-quickstart.md).

## Run Integration Tests

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```
