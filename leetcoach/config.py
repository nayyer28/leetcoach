from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class AppConfig:
    environment: str
    log_level: str
    timezone: str
    db_path: str


def load_config() -> AppConfig:
    return AppConfig(
        environment=os.getenv("LEETCOACH_ENV", "development"),
        log_level=os.getenv("LEETCOACH_LOG_LEVEL", "INFO"),
        timezone=os.getenv("LEETCOACH_TIMEZONE", "UTC"),
        db_path=os.getenv("LEETCOACH_DB_PATH", ".local/leetcoach.db"),
    )
