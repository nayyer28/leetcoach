from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import logging
import sqlite3


LOGGER = logging.getLogger("leetcoach.db.migrate")

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = REPO_ROOT / "migrations"


def _discover_migrations() -> list[Path]:
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not files:
        raise FileNotFoundError(f"No migration files found in {MIGRATIONS_DIR}")
    return files


def _ensure_migration_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        );
        """
    )


def _applied_versions(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {row[0] for row in rows}


def migrate_database(db_path: str) -> int:
    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)

    migrations = _discover_migrations()
    applied_count = 0

    with sqlite3.connect(db_file) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        _ensure_migration_table(conn)
        applied = _applied_versions(conn)

        for migration in migrations:
            version = migration.name
            if version in applied:
                continue

            sql = migration.read_text(encoding="utf-8")
            LOGGER.info("Applying migration %s", version)
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES(?, ?)",
                (version, datetime.now(UTC).isoformat()),
            )
            applied_count += 1

    LOGGER.info("Migrations complete. Applied: %d", applied_count)
    return 0

