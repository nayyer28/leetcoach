from __future__ import annotations

import logging

from leetcoach.app.infrastructure.config.app_config import AppConfig, load_config
from leetcoach.app.bootstrap.logging import configure_logging


LOGGER = logging.getLogger("leetcoach")


def bootstrap() -> AppConfig:
    config = load_config()
    configure_logging(config.log_level)
    LOGGER.info(
        "Leetcoach bootstrap complete (env=%s, timezone=%s, db_path=%s)",
        config.environment,
        config.timezone,
        config.db_path,
    )
    return config


def run() -> int:
    bootstrap()
    LOGGER.info("Leetcoach skeleton is running.")
    return 0
