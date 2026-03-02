from __future__ import annotations

import os
import sys
from pathlib import Path

from loguru import logger

_LOGGING_CONFIGURED = False
_DEFAULT_EXTRA = {"event": "-", "session": "-", "channel": "-", "tool": "-", "run": "-"}
_ANSI_RESET = "\x1b[0m"
_LEVEL_COLOR = {
    "DEBUG": "\x1b[34m",
    "INFO": "\x1b[32m",
    "WARNING": "\x1b[33m",
    "ERROR": "\x1b[31m",
    "CRITICAL": "\x1b[31m",
}


def _patch_record(record: dict) -> None:
    extra = record.get("extra")
    if not isinstance(extra, dict):
        extra = {}
        record["extra"] = extra
    for key, value in _DEFAULT_EXTRA.items():
        extra.setdefault(key, value)


def _truthy(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    raw = value.strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _event_color(event: str) -> str | None:
    if event == "agent.loop":
        return "\x1b[36m"
    if event.startswith("channel."):
        return "\x1b[35m"
    if event.startswith("tool."):
        return "\x1b[37m"
    if event.startswith("scheduler."):
        return "\x1b[34m"
    if event.startswith("gateway."):
        return "\x1b[32m"
    return None


def _colorize(text: str, color: str | None, *, enable_color: bool) -> str:
    if not enable_color or not color:
        return text
    return f"{color}{text}{_ANSI_RESET}"


def _stderr_supports_color() -> bool:
    force_color = os.getenv("FORCE_COLOR", "").strip()
    if force_color and force_color != "0":
        return True
    if os.getenv("NO_COLOR"):
        return False
    return sys.stderr.isatty()


def _make_text_formatter(*, enable_color: bool):
    def _formatter(record: dict) -> str:
        extra = record.get("extra") if isinstance(record.get("extra"), dict) else {}
        event = str(extra.get("event", "-") or "-")
        timestamp = record["time"].strftime("%Y-%m-%d %H:%M:%S")
        level_name = str(record["level"].name)
        level = _colorize(level_name, _LEVEL_COLOR.get(level_name), enable_color=enable_color)
        module = str(record.get("name") or "-")
        colored_event = _colorize(event, _event_color(event), enable_color=enable_color)
        message = str(record.get("message", ""))
        exception = record.get("exception")
        exception_text = f"\n{exception}" if exception else ""
        return f"{timestamp} | {level} | {colored_event} | {module} | {message}{exception_text}\n"

    return _formatter


def _text_format(record: dict) -> str:
    return _make_text_formatter(enable_color=False)(record)


def setup_logging(level: str | None = None) -> None:
    """Configure loguru once with structured/txt sinks."""
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return

    logger.remove()
    logger.configure(extra=_DEFAULT_EXTRA, patcher=_patch_record)
    resolved_level = (level or os.getenv("CLAWLITE_LOG_LEVEL", "INFO")).upper()
    log_format = os.getenv("CLAWLITE_LOG_FORMAT", "text").strip().lower()
    stderr_enabled = _truthy(os.getenv("CLAWLITE_LOG_STDERR"), default=True)
    file_path = os.getenv("CLAWLITE_LOG_FILE", "").strip()

    base_logger = logger

    if stderr_enabled:
        base_logger.add(
            sys.stderr,
            level=resolved_level,
            format=_make_text_formatter(enable_color=_stderr_supports_color()) if log_format != "json" else "{message}",
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
            format=_text_format if log_format != "json" else "{message}",
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
