from __future__ import annotations

import os
import sys
from pathlib import Path

from loguru import logger

from clawlite.utils.logger import render_loguru_message, sidebar_text_lines

_LOGGING_CONFIGURED = False
_DEFAULT_EXTRA = {"event": "-", "session": "-", "channel": "-", "tool": "-", "run": "-"}


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


def _escape_braces(text: str) -> str:
    return text.replace("{", "{{").replace("}", "}}")


def _stderr_supports_color() -> bool:
    force_color = os.getenv("FORCE_COLOR", "").strip()
    if force_color and force_color != "0":
        return True
    if os.getenv("NO_COLOR"):
        return False
    return sys.stderr.isatty()


def _make_text_formatter(*, enable_color: bool):
    def _formatter(record: dict) -> str:
        lines = sidebar_text_lines(record, enable_color=enable_color)
        escaped = [_escape_braces(line) for line in lines]
        return "\n".join(escaped) + "\n"

    return _formatter


def _text_format(record: dict) -> str:
    return _make_text_formatter(enable_color=False)(record)


def _is_clawlite_record(record: dict) -> bool:
    extra = record.get("extra") if isinstance(record.get("extra"), dict) else {}
    event = str(extra.get("event", "-") or "-")
    name = str(record.get("name") or "")
    return event != "-" or name.startswith("clawlite")


def _runtime_filter(record: dict) -> bool:
    level_no = int(getattr(record.get("level"), "no", 20))
    if level_no <= 10 and not _is_clawlite_record(record):
        return False
    return True


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
        if log_format == "json":
            base_logger.add(
                sys.stderr,
                level=resolved_level,
                format="{message}",
                filter=_runtime_filter,
                enqueue=False,
                backtrace=False,
                diagnose=False,
                serialize=True,
            )
        else:
            base_logger.add(
                render_loguru_message,
                level=resolved_level,
                filter=_runtime_filter,
                enqueue=False,
                backtrace=False,
                diagnose=False,
                serialize=False,
            )

    if file_path:
        path = Path(file_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        base_logger.add(
            str(path),
            level=resolved_level,
            format=_text_format if log_format != "json" else "{message}",
            filter=_runtime_filter,
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
