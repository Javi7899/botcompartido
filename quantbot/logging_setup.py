"""Loguru configuration: console + persistent local file.

The local log file is the backup notification channel required by spec
section 4.5 (email can fail; the local log must always exist).
"""

import sys
from pathlib import Path

from loguru import logger

from quantbot.config import AppConfig


def setup_logging(config: AppConfig) -> Path:
    """Configure loguru sinks. Returns the log file path pattern in use."""
    log_dir = Path(config.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "quantbot_{time:YYYY-MM-DD}.log"

    logger.remove()
    logger.add(sys.stderr, level=config.log_level)
    logger.add(
        log_file,
        level=config.log_level,
        rotation="00:00",
        retention="400 days",
        encoding="utf-8",
        backtrace=True,
        diagnose=config.environment == "dev",
    )
    logger.info(
        "logging configurado (env={}, level={}, dir={})",
        config.environment,
        config.log_level,
        log_dir,
    )
    return log_file
