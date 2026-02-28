from __future__ import annotations

import logging

from leetcoach.config import AppConfig, load_config
from leetcoach.logging_setup import configure_logging


LOGGER = logging.getLogger("leetcoach")


def bootstrap() -> AppConfig:
    config = load_config()
    configure_logging(config.log_level)
    LOGGER.info(
        "Leetcoach bootstrap complete (env=%s, timezone=%s)",
        config.environment,
        config.timezone,
    )
    return config


def run() -> int:
    bootstrap()
    LOGGER.info("Leetcoach skeleton is running.")
    return 0

