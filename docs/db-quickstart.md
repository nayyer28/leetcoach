# DB Quickstart

This document explains how to run migrations and inspect the SQLite database created by PR B.

## 1) Create and activate local venv

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## 2) Run migrations

```bash
python main.py migrate
```

Default DB file path:
- `.local/leetcoach.db`

Override DB location:

```bash
LEETCOACH_DB_PATH=/absolute/path/leetcoach.db python main.py migrate
```

## 3) Check migration state

```bash
sqlite3 .local/leetcoach.db "SELECT version, applied_at FROM schema_migrations ORDER BY version;"
```

Expected after first run:
- `0001_init.sql` appears in `schema_migrations`

Re-running `python main.py migrate` is idempotent (no duplicate migration application).

## 4) List tables

```bash
sqlite3 .local/leetcoach.db ".tables"
```

Expected core tables:
- `users`
- `problems`
- `user_problems`
- `problem_reviews`
- `schema_migrations`

## 5) Inspect schema

```bash
sqlite3 .local/leetcoach.db ".schema users"
sqlite3 .local/leetcoach.db ".schema problems"
sqlite3 .local/leetcoach.db ".schema user_problems"
sqlite3 .local/leetcoach.db ".schema problem_reviews"
```

## 6) Inspect indexes

```bash
sqlite3 .local/leetcoach.db "SELECT name, tbl_name FROM sqlite_master WHERE type='index' ORDER BY tbl_name, name;"
```

## 7) Open interactive SQLite shell

```bash
sqlite3 .local/leetcoach.db
```

Useful interactive commands:
- `.tables`
- `.schema`
- `.mode column`
- `.headers on`
- `.quit`

