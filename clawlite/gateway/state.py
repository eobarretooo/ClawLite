from __future__ import annotations

import os
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from fastapi import WebSocket

from clawlite.config.settings import CONFIG_DIR

try:
    from rich.console import Console
except Exception:
    Console = None  # type: ignore

connections: set[WebSocket] = set()
chat_connections: set[WebSocket] = set()
log_connections: dict[WebSocket, dict[str, str]] = {}
STARTED_AT = datetime.now(timezone.utc)
LOG_RING: deque[dict[str, Any]] = deque(maxlen=500)

_LOGS_DIR = CONFIG_DIR / "logs"
_GATEWAY_LOG_FILE = _LOGS_DIR / "gateway.log"
_CONSOLE = Console() if Console else None

DASHBOARD_DIR = CONFIG_DIR / "dashboard"
SESSIONS_FILE = DASHBOARD_DIR / "sessions.jsonl"
TELEMETRY_FILE = DASHBOARD_DIR / "telemetry.jsonl"
SETTINGS_FILE = DASHBOARD_DIR / "settings.json"
