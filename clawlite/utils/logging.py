from __future__ import annotations

import os
import sys

from loguru import logger

_LOGGING_CONFIGURED = False


def setup_logging(level: str | None = None) -> None:
    """Configure loguru once with a consistent module:function:line format."""
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return

    logger.remove()
    logger.add(
        sys.stderr,
        level=(level or os.getenv("CLAWLITE_LOG_LEVEL", "INFO")).upper(),
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<5} | {name}:{function}:{line} - {message}",
        enqueue=False,
        backtrace=False,
        diagnose=False,
    )
    _LOGGING_CONFIGURED = True

