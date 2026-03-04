from __future__ import annotations

import json
import sys
import traceback
from datetime import datetime
from typing import Any

from rich.console import Console
from rich.text import Text

_STDERR_CONSOLE = Console(stderr=True, soft_wrap=True)

_ANSI_RESET = "\x1b[0m"
_ACTION_STYLE = {
    "DEBUG": ("cyan", "\x1b[36m"),
    "INFO": ("cyan", "\x1b[36m"),
    "SUCCESS": ("green", "\x1b[32m"),
    "WARNING": ("yellow", "\x1b[33m"),
    "ERROR": ("red", "\x1b[31m"),
    "CRITICAL": ("red", "\x1b[31m"),
    "BACKGROUND": ("dim", "\x1b[90m"),
}

_ACRONYM_MAP = {
    "api": "API",
    "cli": "CLI",
    "llm": "LLM",
    "ws": "WS",
    "http": "HTTP",
    "mcp": "MCP",
}


def _pick_source_label(record: dict[str, Any]) -> str:
    extra = record.get("extra") if isinstance(record.get("extra"), dict) else {}
    event = str(extra.get("event", "-") or "-").strip()
    if event and event != "-":
        return event
    return str(record.get("name", "system") or "system")


def _normalize_module_label(raw: str) -> str:
    normalized = raw.replace("/", ".").replace(":", ".").replace("-", ".").replace("_", ".")
    parts = [chunk for chunk in normalized.split(".") if chunk]
    filtered = [chunk for chunk in parts if chunk.lower() not in {"clawlite", "src", "main", "__main__"}]
    tokens = filtered if filtered else parts
    if len(tokens) > 3:
        tokens = tokens[-3:]

    def _title_token(token: str) -> str:
        lowered = token.lower()
        if lowered in _ACRONYM_MAP:
            return _ACRONYM_MAP[lowered]
        if token.isupper() and len(token) <= 4:
            return token
        return token.capitalize()

    titled = [_title_token(token) for token in tokens]
    return ".".join(titled) if titled else "System"


def _action_key_from_level(level_name: str) -> str:
    return level_name if level_name in _ACTION_STYLE else "INFO"


def _format_timestamp(record: dict[str, Any]) -> str:
    moment = record.get("time")
    if hasattr(moment, "strftime"):
        return moment.strftime("%Y-%m-%d %H:%M:%S")
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _extract_exception_lines(exception: Any) -> list[str]:
    if not exception:
        return []

    from_traceback: list[str] = []
    tb = getattr(exception, "traceback", None)
    if tb:
        try:
            from_traceback = [line.rstrip() for line in traceback.format_list(tb) if line.strip()]
        except Exception:
            from_traceback = []

    value = getattr(exception, "value", None)
    if value is not None:
        from_traceback.append(f"{type(value).__name__}: {value}")

    if not from_traceback:
        from_traceback = [line.rstrip() for line in str(exception).splitlines() if line.strip()]

    return from_traceback


def sidebar_text_lines(record: dict[str, Any], *, enable_color: bool = False) -> list[str]:
    level_name = str(getattr(record.get("level"), "name", "INFO")).upper()
    action = _action_key_from_level(level_name)
    module = _normalize_module_label(_pick_source_label(record))
    timestamp = _format_timestamp(record)
    message = str(record.get("message", "")).rstrip("\n")
    message_lines = [line for line in message.splitlines() if line] or [""]
    color = _ACTION_STYLE[action][1] if enable_color else ""

    def _line(content: str) -> str:
        bar = "┃"
        if color:
            bar = f"{color}{bar}{_ANSI_RESET}"
        return f"[{timestamp}] {bar} [{module}]: {content}"

    lines = [_line(part) for part in message_lines]
    for detail in _extract_exception_lines(record.get("exception")):
        lines.append(_line(detail))
    return lines


class SidebarLogger:
    _instance: "SidebarLogger | None" = None

    def __new__(cls) -> "SidebarLogger":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        self._console = _STDERR_CONSOLE

    def _render_line(self, *, timestamp: str, module: str, message: str, action: str) -> Text:
        style = _ACTION_STYLE.get(action, _ACTION_STYLE["INFO"])[0]
        line = Text()
        line.append(f"[{timestamp}]", style="dim")
        line.append(" ")
        line.append("┃", style=style)
        line.append(" ")
        line.append(f"[{module}]", style=f"bold {style}" if style != "dim" else "dim")
        line.append(": ", style="dim")
        line.append(message, style="white" if action != "BACKGROUND" else "dim")
        return line

    def render_record(self, record: dict[str, Any]) -> None:
        level_name = str(getattr(record.get("level"), "name", "INFO")).upper()
        action = _action_key_from_level(level_name)
        module = _normalize_module_label(_pick_source_label(record))
        timestamp = _format_timestamp(record)
        message = str(record.get("message", "")).rstrip("\n")
        message_lines = [line for line in message.splitlines() if line] or [""]
        for line in message_lines:
            self._console.print(self._render_line(timestamp=timestamp, module=module, message=line, action=action))
        for detail in _extract_exception_lines(record.get("exception")):
            self._console.print(self._render_line(timestamp=timestamp, module=module, message=detail, action="ERROR"))

    def _semantic_record(self, level_name: str, message: str, category: str) -> dict[str, Any]:
        return {
            "time": datetime.now(),
            "level": type("Level", (), {"name": level_name})(),
            "name": category,
            "message": message,
            "extra": {"event": category},
            "exception": None,
        }

    def log_info(self, message: str, *, category: str = "system") -> None:
        self.render_record(self._semantic_record("INFO", message, category))

    def log_success(self, message: str, *, category: str = "system") -> None:
        self.render_record(self._semantic_record("SUCCESS", message, category))

    def log_warning(self, message: str, *, category: str = "system") -> None:
        self.render_record(self._semantic_record("WARNING", message, category))

    def log_error(self, message: str, *, category: str = "system") -> None:
        self.render_record(self._semantic_record("ERROR", message, category))

    def log_background(self, title: str, details: str) -> None:
        self.render_record(self._semantic_record("BACKGROUND", f"{title}: {details}", "background.task"))

    def log_thought_tree(self, root: str, nodes: list[str]) -> None:
        self.render_record(self._semantic_record("INFO", root, "thought.tree"))
        for node in nodes:
            self.render_record(self._semantic_record("BACKGROUND", f"- {node}", "thought.tree"))


_SIDEBAR_LOGGER = SidebarLogger()


def get_sidebar_logger() -> SidebarLogger:
    return _SIDEBAR_LOGGER


def render_log_record(record: dict[str, Any]) -> None:
    _SIDEBAR_LOGGER.render_record(record)


def render_loguru_message(message: Any) -> None:
    record = getattr(message, "record", None)
    if isinstance(record, dict):
        render_log_record(record)
        return
    _STDERR_CONSOLE.print(str(message).rstrip("\n"))


def log_info(message: str, *, category: str = "system") -> None:
    _SIDEBAR_LOGGER.log_info(message, category=category)


def log_success(message: str, *, category: str = "system") -> None:
    _SIDEBAR_LOGGER.log_success(message, category=category)


def log_warning(message: str, *, category: str = "system") -> None:
    _SIDEBAR_LOGGER.log_warning(message, category=category)


def log_error(message: str, *, category: str = "system") -> None:
    _SIDEBAR_LOGGER.log_error(message, category=category)


def log_background(title: str, details: str) -> None:
    _SIDEBAR_LOGGER.log_background(title, details)


def log_thought_tree(root: str, nodes: list[str]) -> None:
    _SIDEBAR_LOGGER.log_thought_tree(root, nodes)


def stdout_text(text: str) -> None:
    sys.stdout.write(f"{text}\n")


def stdout_json(payload: Any) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")
