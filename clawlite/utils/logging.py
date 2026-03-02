from __future__ import annotations

import os
import sys
from pathlib import Path

from loguru import logger

_LOGGING_CONFIGURED = False


def _truthy(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    raw = value.strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _text_format() -> str:
    return (
        "{time:YYYY-MM-DD HH:mm:ss} | {level:<5} | "
        "event={extra[event]} session={extra[session]} channel={extra[channel]} tool={extra[tool]} run={extra[run]} | "
        "{name}:{function}:{line} - {message}"
    )


def setup_logging(level: str | None = None) -> None:
    """Configure loguru once with structured/txt sinks."""
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return

    logger.remove()
    resolved_level = (level or os.getenv("CLAWLITE_LOG_LEVEL", "INFO")).upper()
    log_format = os.getenv("CLAWLITE_LOG_FORMAT", "text").strip().lower()
    stderr_enabled = _truthy(os.getenv("CLAWLITE_LOG_STDERR"), default=True)
    file_path = os.getenv("CLAWLITE_LOG_FILE", "").strip()

    base_logger = logger.bind(event="-", session="-", channel="-", tool="-", run="-")

    if stderr_enabled:
        base_logger.add(
            sys.stderr,
            level=resolved_level,
            format=_text_format() if log_format != "json" else "{message}",
            enqueue=False,
            backtrace=False,
            diagnose=False,
            serialize=(log_format == "json"),
        )

    if file_path:
        path = Path(file_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        base_logger.add(
            str(path),
            level=resolved_level,
            format=_text_format() if log_format != "json" else "{message}",
            enqueue=True,
            backtrace=False,
            diagnose=False,
            serialize=(log_format == "json"),
            rotation="10 MB",
            retention=5,
        )

    _LOGGING_CONFIGURED = True


def bind_event(event: str, **fields: str) -> "logger":
    return logger.bind(
        event=str(event or "-"),
        session=str(fields.get("session", "-") or "-"),
        channel=str(fields.get("channel", "-") or "-"),
        tool=str(fields.get("tool", "-") or "-"),
        run=str(fields.get("run", "-") or "-"),
    )
