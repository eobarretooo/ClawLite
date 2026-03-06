from __future__ import annotations

import asyncio
import datetime as dt
import hmac
import json
import time
import uuid
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from loguru import logger
from pydantic import BaseModel

from clawlite.bus.queue import MessageQueue
from clawlite.channels.manager import ChannelManager
from clawlite.config.loader import load_config
from clawlite.config.schema import AppConfig
from clawlite.core.engine import AgentEngine, LoopDetectionSettings
from clawlite.core.memory import MemoryStore
from clawlite.core.memory_backend import resolve_memory_backend
from clawlite.core.memory_monitor import MemoryMonitor, MemorySuggestion
from clawlite.core.prompt import PromptBuilder
from clawlite.core.skills import SkillsLoader
from clawlite.providers import build_provider, detect_provider_name
from clawlite.providers.discovery import probe_local_provider_runtime
from clawlite.scheduler.cron import CronService
from clawlite.scheduler.heartbeat import HeartbeatDecision, HeartbeatService
from clawlite.session.store import SessionStore
from clawlite.runtime import AutonomyWakeCoordinator
from clawlite.gateway.tool_catalog import build_tools_catalog_payload, parse_include_schema_flag
from clawlite.tools.cron import CronTool
from clawlite.tools.apply_patch import ApplyPatchTool
from clawlite.tools.exec import ExecTool
from clawlite.tools.files import EditFileTool, EditTool, ListDirTool, ReadFileTool, ReadTool, WriteFileTool, WriteTool
from clawlite.tools.mcp import MCPTool
from clawlite.tools.message import MessageTool
from clawlite.tools.memory import (
    MemoryAnalyzeTool,
    MemoryForgetTool,
    MemoryGetTool,
    MemoryLearnTool,
    MemoryRecallTool,
    MemorySearchTool,
)
from clawlite.tools.registry import ToolRegistry
from clawlite.tools.process import ProcessTool
from clawlite.tools.skill import SkillTool
from clawlite.tools.sessions import (
    SessionStatusTool,
    SessionsHistoryTool,
    SessionsListTool,
    SessionsSendTool,
    SessionsSpawnTool,
    SubagentsTool,
)
from clawlite.tools.spawn import SpawnTool
from clawlite.tools.web import WebFetchTool, WebSearchTool
from clawlite.utils.logging import bind_event, setup_logging
from clawlite.workspace.loader import WorkspaceLoader


GATEWAY_CONTRACT_VERSION = "2026-03-04"
TELEGRAM_WEBHOOK_MAX_BODY_BYTES = 1024 * 1024
GATEWAY_CHAT_WS_ENGINE_TIMEOUT_S = 300.0
GATEWAY_CRON_ENGINE_TIMEOUT_S = 90.0
GATEWAY_HEARTBEAT_ENGINE_TIMEOUT_S = 120.0
LATEST_MEMORY_ROUTE_CACHE_TTL_S = 5.0
LATEST_MEMORY_ROUTE_TAIL_BYTES = 32 * 1024

_TUNING_DEFAULT_ACTION_BY_SEVERITY: dict[str, str] = {
    "low": "notify_operator",
    "medium": "semantic_backfill",
    "high": "memory_snapshot",
}

_TUNING_REASONING_LAYER_ALIASES: dict[str, str] = {
    "factual": "fact",
    "procedural": "decision",
    "episodic": "outcome",
}

_TUNING_LAYER_ACTION_PLAYBOOKS: dict[str, dict[str, str]] = {
    "fact": {
        "low": "semantic_backfill",
        "medium": "semantic_backfill",
        "high": "memory_snapshot",
    },
    "hypothesis": {
        "low": "notify_operator",
        "medium": "semantic_backfill",
        "high": "memory_snapshot",
    },
    "decision": {
        "low": "notify_operator",
        "medium": "memory_snapshot",
        "high": "memory_snapshot",
    },
    "outcome": {
        "low": "notify_operator",
        "medium": "semantic_backfill",
        "high": "memory_snapshot",
    },
}

_TUNING_SEVERITY_LEVELS: tuple[str, ...] = ("low", "medium", "high")

_TUNING_LAYER_BACKFILL_LIMITS: dict[str, dict[str, dict[str, int]]] = {
    "fact": {
        "low": {"floor": 8, "ceiling": 24, "default": 14},
        "medium": {"floor": 16, "ceiling": 42, "default": 24},
        "high": {"floor": 24, "ceiling": 64, "default": 40},
    },
    "hypothesis": {
        "low": {"floor": 6, "ceiling": 20, "default": 12},
        "medium": {"floor": 12, "ceiling": 34, "default": 20},
        "high": {"floor": 18, "ceiling": 50, "default": 30},
    },
    "decision": {
        "low": {"floor": 5, "ceiling": 16, "default": 10},
        "medium": {"floor": 8, "ceiling": 26, "default": 16},
        "high": {"floor": 12, "ceiling": 36, "default": 24},
    },
    "outcome": {
        "low": {"floor": 7, "ceiling": 22, "default": 12},
        "medium": {"floor": 14, "ceiling": 38, "default": 22},
        "high": {"floor": 20, "ceiling": 56, "default": 32},
    },
}

_TUNING_LAYER_SNAPSHOT_TAGS: dict[str, dict[str, str]] = {
    "fact": {
        "low": "quality-drift-fact-low",
        "medium": "quality-drift-fact-medium",
        "high": "quality-drift-fact-high",
    },
    "hypothesis": {
        "low": "quality-drift-hypothesis-low",
        "medium": "quality-drift-hypothesis-medium",
        "high": "quality-drift-hypothesis-high",
    },
    "decision": {
        "low": "quality-drift-decision-low",
        "medium": "quality-drift-decision-medium",
        "high": "quality-drift-decision-high",
    },
    "outcome": {
        "low": "quality-drift-outcome-low",
        "medium": "quality-drift-outcome-medium",
        "high": "quality-drift-outcome-high",
    },
}

_TUNING_NOTIFY_TEMPLATES: dict[str, dict[str, dict[str, str]]] = {
    "fact": {
        "low": {"template_id": "notify.fact.low.v1", "marker": "fact-low"},
        "medium": {"template_id": "notify.fact.medium.v1", "marker": "fact-medium"},
        "high": {"template_id": "notify.fact.high.v1", "marker": "fact-high"},
    },
    "hypothesis": {
        "low": {"template_id": "notify.hypothesis.low.v1", "marker": "hypothesis-low"},
        "medium": {"template_id": "notify.hypothesis.medium.v1", "marker": "hypothesis-medium"},
        "high": {"template_id": "notify.hypothesis.high.v1", "marker": "hypothesis-high"},
    },
    "decision": {
        "low": {"template_id": "notify.decision.low.v1", "marker": "decision-low"},
        "medium": {"template_id": "notify.decision.medium.v1", "marker": "decision-medium"},
        "high": {"template_id": "notify.decision.high.v1", "marker": "decision-high"},
    },
    "outcome": {
        "low": {"template_id": "notify.outcome.low.v1", "marker": "outcome-low"},
        "medium": {"template_id": "notify.outcome.medium.v1", "marker": "outcome-medium"},
        "high": {"template_id": "notify.outcome.high.v1", "marker": "outcome-high"},
    },
}


def _normalize_reasoning_layer(layer: str) -> str:
    normalized_layer = str(layer or "").strip().lower()
    if not normalized_layer:
        return ""
    return _TUNING_REASONING_LAYER_ALIASES.get(normalized_layer, normalized_layer)


def _select_tuning_action_playbook(*, severity: str, weakest_layer: str) -> tuple[str, str]:
    normalized_severity = str(severity or "").strip().lower()
    if normalized_severity not in _TUNING_DEFAULT_ACTION_BY_SEVERITY:
        normalized_severity = "low"

    default_action = _TUNING_DEFAULT_ACTION_BY_SEVERITY[normalized_severity]
    normalized_layer = _normalize_reasoning_layer(weakest_layer)
    if not normalized_layer:
        return default_action, f"severity_default_{normalized_severity}_v1"

    layer_playbook = _TUNING_LAYER_ACTION_PLAYBOOKS.get(normalized_layer)
    if not isinstance(layer_playbook, dict):
        return default_action, f"severity_default_{normalized_severity}_v1"

    action = str(layer_playbook.get(normalized_severity, "") or "").strip()
    if not action:
        action = default_action
    return action, f"layer_{normalized_layer}_{normalized_severity}_v1"


def _normalize_tuning_severity(value: str) -> str:
    severity = str(value or "").strip().lower()
    if severity in _TUNING_SEVERITY_LEVELS:
        return severity
    return "low"


def _resolve_tuning_layer(value: str) -> str:
    layer = _normalize_reasoning_layer(value)
    if layer in _TUNING_LAYER_ACTION_PLAYBOOKS:
        return layer
    return "unknown"


def _resolve_tuning_backfill_limit(*, layer: str, severity: str, missing_records: int) -> int:
    normalized_layer = _resolve_tuning_layer(layer)
    normalized_severity = _normalize_tuning_severity(severity)
    layer_cfg = _TUNING_LAYER_BACKFILL_LIMITS.get(normalized_layer) or _TUNING_LAYER_BACKFILL_LIMITS.get("hypothesis", {})
    bounds = layer_cfg.get(normalized_severity, {"floor": 8, "ceiling": 24, "default": 16})
    floor = max(1, int(bounds.get("floor", 8) or 8))
    ceiling = max(floor, int(bounds.get("ceiling", 24) or 24))
    default = int(bounds.get("default", floor) or floor)
    if default < floor:
        default = floor
    if default > ceiling:
        default = ceiling
    if missing_records <= 0:
        return default
    return max(floor, min(ceiling, int(missing_records)))


def _resolve_tuning_snapshot_tag(*, layer: str, severity: str) -> str:
    normalized_layer = _resolve_tuning_layer(layer)
    normalized_severity = _normalize_tuning_severity(severity)
    layer_tags = _TUNING_LAYER_SNAPSHOT_TAGS.get(normalized_layer) or _TUNING_LAYER_SNAPSHOT_TAGS.get("hypothesis", {})
    return str(layer_tags.get(normalized_severity, "quality-drift-auto") or "quality-drift-auto")


def _resolve_tuning_notify_variant(*, layer: str, severity: str) -> tuple[str, str]:
    normalized_layer = _resolve_tuning_layer(layer)
    normalized_severity = _normalize_tuning_severity(severity)
    layer_templates = _TUNING_NOTIFY_TEMPLATES.get(normalized_layer) or _TUNING_NOTIFY_TEMPLATES.get("hypothesis", {})
    template = layer_templates.get(normalized_severity, {"template_id": "notify.generic.low.v1", "marker": "generic-low"})
    template_id = str(template.get("template_id", "notify.generic.low.v1") or "notify.generic.low.v1")
    marker = str(template.get("marker", "generic-low") or "generic-low")
    return template_id, marker


def _normalize_webhook_path(value: str, *, default: str = "/api/webhooks/telegram") -> str:
    raw = str(value or "").strip() or default
    return raw if raw.startswith("/") else f"/{raw}"


class ChatRequest(BaseModel):
    session_id: str
    text: str


class ChatResponse(BaseModel):
    text: str
    model: str


class CronAddRequest(BaseModel):
    session_id: str
    expression: str
    prompt: str
    name: str = ""


class ControlPlaneResponse(BaseModel):
    ready: bool
    phase: str
    contract_version: str
    server_time: str
    components: dict[str, Any]
    auth: dict[str, Any]
    memory_proactive_enabled: bool = False


class DiagnosticsResponse(BaseModel):
    schema_version: str
    contract_version: str
    generated_at: str
    uptime_s: int
    control_plane: ControlPlaneResponse
    queue: dict[str, Any]
    channels: dict[str, Any]
    channels_delivery: dict[str, Any] = {}
    cron: dict[str, Any]
    heartbeat: dict[str, Any]
    autonomy_wake: dict[str, Any] = {}
    bootstrap: dict[str, Any]
    memory_monitor: dict[str, Any] = {}
    memory_quality_tuning: dict[str, Any] = {}
    engine: dict[str, Any] = {}
    environment: dict[str, Any] = {}
    http: dict[str, Any] = {}
    ws: dict[str, Any] = {}


@dataclass(slots=True)
class HttpRequestTelemetry:
    total_requests: int = 0
    in_flight: int = 0
    by_method: dict[str, int] = field(default_factory=dict)
    by_path: dict[str, int] = field(default_factory=dict)
    by_status: dict[str, int] = field(default_factory=dict)
    latency_count: int = 0
    latency_sum_ms: float = 0.0
    latency_min_ms: float = 0.0
    latency_max_ms: float = 0.0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def start(self, *, method: str, path: str) -> None:
        normalized_method = (method or "UNKNOWN").upper()
        normalized_path = str(path or "") or "/"
        async with self.lock:
            self.total_requests += 1
            self.in_flight += 1
            self.by_method[normalized_method] = self.by_method.get(normalized_method, 0) + 1
            self.by_path[normalized_path] = self.by_path.get(normalized_path, 0) + 1

    async def finish(self, *, status_code: int, latency_ms: float) -> None:
        normalized_status = str(int(status_code) if status_code else 500)
        elapsed_ms = max(0.0, float(latency_ms))
        async with self.lock:
            self.in_flight = max(0, self.in_flight - 1)
            self.by_status[normalized_status] = self.by_status.get(normalized_status, 0) + 1
            self.latency_count += 1
            self.latency_sum_ms += elapsed_ms
            if self.latency_count == 1:
                self.latency_min_ms = elapsed_ms
                self.latency_max_ms = elapsed_ms
            else:
                self.latency_min_ms = min(self.latency_min_ms, elapsed_ms)
                self.latency_max_ms = max(self.latency_max_ms, elapsed_ms)

    async def snapshot(self) -> dict[str, Any]:
        async with self.lock:
            avg_ms = (self.latency_sum_ms / self.latency_count) if self.latency_count else 0.0
            return {
                "total_requests": self.total_requests,
                "in_flight": self.in_flight,
                "by_method": dict(self.by_method),
                "by_path": dict(self.by_path),
                "by_status": dict(self.by_status),
                "latency_ms": {
                    "count": self.latency_count,
                    "min": round(self.latency_min_ms, 3) if self.latency_count else 0.0,
                    "max": round(self.latency_max_ms, 3) if self.latency_count else 0.0,
                    "avg": round(avg_ms, 3),
                },
            }


@dataclass(slots=True)
class WebSocketTelemetry:
    connections_opened: int = 0
    connections_closed: int = 0
    active_connections: int = 0
    frames_in: int = 0
    frames_out: int = 0
    by_path: dict[str, int] = field(default_factory=dict)
    by_message_type_in: dict[str, int] = field(default_factory=dict)
    by_message_type_out: dict[str, int] = field(default_factory=dict)
    req_methods: dict[str, int] = field(default_factory=dict)
    error_codes: dict[str, int] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @staticmethod
    def _message_type(payload: Any) -> str:
        if isinstance(payload, dict):
            value = str(payload.get("type", "") or "").strip().lower()
            return value or "legacy"
        return "non_object"

    @staticmethod
    def _error_code(payload: Any) -> str | None:
        if not isinstance(payload, dict):
            return None
        payload_type = str(payload.get("type", "") or "").strip().lower()
        if payload_type == "res" and payload.get("ok") is False:
            error = payload.get("error")
            if isinstance(error, dict):
                explicit_code = str(error.get("code", "") or "").strip()
                if explicit_code:
                    return explicit_code
                status_code = error.get("status_code")
            else:
                status_code = payload.get("status_code")
            if status_code is not None:
                try:
                    return f"http_{int(status_code)}"
                except Exception:
                    pass
            return "error"
        if payload_type == "error" or ("error" in payload and not payload_type):
            explicit_code = str(payload.get("code", "") or "").strip()
            if explicit_code:
                return explicit_code
            status_code = payload.get("status_code")
            if status_code is not None:
                try:
                    return f"http_{int(status_code)}"
                except Exception:
                    pass
            return "error"
        return None

    async def connection_opened(self, *, path: str) -> None:
        normalized_path = str(path or "") or "/"
        async with self.lock:
            self.connections_opened += 1
            self.active_connections += 1
            self.by_path[normalized_path] = self.by_path.get(normalized_path, 0) + 1

    async def connection_closed(self) -> None:
        async with self.lock:
            self.connections_closed += 1
            self.active_connections = max(0, self.active_connections - 1)

    async def frame_inbound(self, *, path: str, payload: Any) -> None:
        normalized_path = str(path or "") or "/"
        message_type = self._message_type(payload)
        async with self.lock:
            self.frames_in += 1
            self.by_message_type_in[message_type] = self.by_message_type_in.get(message_type, 0) + 1
            self.by_path.setdefault(normalized_path, self.by_path.get(normalized_path, 0))
            if isinstance(payload, dict) and message_type == "req":
                method = str(payload.get("method", "") or "").strip().lower()
                if method:
                    self.req_methods[method] = self.req_methods.get(method, 0) + 1

    async def frame_outbound(self, *, payload: Any) -> None:
        message_type = self._message_type(payload)
        error_code = self._error_code(payload)
        async with self.lock:
            self.frames_out += 1
            self.by_message_type_out[message_type] = self.by_message_type_out.get(message_type, 0) + 1
            if error_code:
                self.error_codes[error_code] = self.error_codes.get(error_code, 0) + 1

    async def snapshot(self) -> dict[str, Any]:
        async with self.lock:
            return {
                "connections_opened": self.connections_opened,
                "connections_closed": self.connections_closed,
                "active_connections": self.active_connections,
                "frames_in": self.frames_in,
                "frames_out": self.frames_out,
                "by_path": dict(self.by_path),
                "by_message_type_in": dict(self.by_message_type_in),
                "by_message_type_out": dict(self.by_message_type_out),
                "req_methods": dict(self.req_methods),
                "error_codes": dict(self.error_codes),
            }


ROOT_ENTRYPOINT_HTML = """<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>ClawLite Gateway</title>
  </head>
  <body>
    <h1>ClawLite Gateway</h1>
    <p>Available endpoints:</p>
    <ul>
      <li>GET /health</li>
      <li>GET /v1/status, GET /api/status</li>
      <li>GET /v1/tools/catalog, GET /api/tools/catalog</li>
      <li>POST /v1/chat, POST /api/message</li>
      <li>GET /api/token</li>
      <li>WS /v1/ws, WS /ws</li>
    </ul>
  </body>
</html>
"""


def _mask_secret(value: str, *, keep: int = 4) -> str:
    token = str(value or "").strip()
    if not token:
        return ""
    if len(token) <= keep:
        return "*" * len(token)
    return f"{'*' * max(3, len(token) - keep)}{token[-keep:]}"


_SENSITIVE_KEY_MARKERS: tuple[str, ...] = (
    "api_key",
    "access_token",
    "token",
    "authorization",
    "auth",
    "credential",
    "credentials",
    "secret",
    "password",
)


def _is_sensitive_telemetry_key(key: Any) -> bool:
    value = str(key or "").strip().lower()
    if not value:
        return False
    return any(marker in value for marker in _SENSITIVE_KEY_MARKERS)


def _sanitize_telemetry_payload(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, nested in value.items():
            if _is_sensitive_telemetry_key(key):
                continue
            sanitized[str(key)] = _sanitize_telemetry_payload(nested)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_telemetry_payload(item) for item in value]
    return value


def _provider_telemetry_snapshot(provider: Any) -> dict[str, Any]:
    minimal: dict[str, Any] = {
        "provider": str(getattr(provider, "provider_name", provider.__class__.__name__.lower()) or provider.__class__.__name__.lower()),
        "model": str(getattr(provider, "model", "") or ""),
        "diagnostics_available": False,
        "counters": {},
    }
    diagnostics_fn = getattr(provider, "diagnostics", None)
    if not callable(diagnostics_fn):
        return minimal
    try:
        raw = diagnostics_fn()
    except Exception:
        return minimal
    if not isinstance(raw, dict):
        return minimal

    telemetry = _sanitize_telemetry_payload(raw)
    if not isinstance(telemetry, dict):
        return minimal
    telemetry.setdefault("provider", minimal["provider"])
    telemetry.setdefault("model", minimal["model"])
    telemetry["diagnostics_available"] = True
    if not isinstance(telemetry.get("counters"), dict):
        telemetry["counters"] = {}
    return telemetry


async def _run_engine_with_timeout(
    *,
    engine: AgentEngine,
    session_id: str,
    user_text: str,
    timeout_s: float,
) -> Any:
    try:
        return await asyncio.wait_for(
            engine.run(session_id=session_id, user_text=user_text),
            timeout=max(0.001, float(timeout_s)),
        )
    except (asyncio.TimeoutError, TimeoutError) as exc:
        raise RuntimeError("engine_run_timeout") from exc


async def _normalize_background_task(task: asyncio.Task[Any] | None) -> tuple[asyncio.Task[Any] | None, str]:
    if task is None:
        return None, "missing"
    if not task.done():
        return task, "running"
    try:
        await task
    except asyncio.CancelledError:
        return None, "cancelled"
    except Exception:
        return None, "failed"
    return None, "done"


@dataclass(slots=True)
class RuntimeContainer:
    config: AppConfig
    bus: MessageQueue
    engine: AgentEngine
    channels: ChannelManager
    cron: CronService
    heartbeat: HeartbeatService
    autonomy_wake: AutonomyWakeCoordinator
    workspace: WorkspaceLoader
    memory_monitor: MemoryMonitor | None = None


@dataclass(slots=True)
class GatewayLifecycleState:
    phase: str = "created"
    ready: bool = False
    startup_error: str = ""
    components: dict[str, dict[str, Any]] | None = None

    def __post_init__(self) -> None:
        if self.components is None:
            self.components = {
                "channels": {"enabled": True, "running": False, "last_error": ""},
                "cron": {"enabled": True, "running": False, "last_error": ""},
                "heartbeat": {"enabled": True, "running": False, "last_error": ""},
                "proactive_monitor": {"enabled": False, "running": False, "last_error": ""},
                "memory_quality_tuning": {"enabled": False, "running": False, "last_error": ""},
                "autonomy_wake": {"enabled": True, "running": False, "last_error": ""},
                "bootstrap": {"enabled": True, "running": False, "pending": False, "last_status": "", "last_error": ""},
                "engine": {"enabled": True, "running": True, "last_error": ""},
            }

    def mark_component(self, name: str, *, running: bool, error: str = "") -> None:
        row = self.components.setdefault(name, {"enabled": True, "running": False, "last_error": ""})
        row["running"] = running
        row["last_error"] = str(error or "")


@dataclass(slots=True)
class GatewayAuthGuard:
    mode: str
    token: str
    allow_loopback_without_auth: bool
    header_name: str
    query_param: str
    protect_health: bool

    @classmethod
    def from_config(cls, config: AppConfig) -> GatewayAuthGuard:
        auth_cfg = config.gateway.auth
        configured_mode = str(auth_cfg.mode or "off").strip().lower()
        if configured_mode not in {"off", "optional", "required"}:
            configured_mode = "off"
        token = str(auth_cfg.token or "").strip()
        host = str(config.gateway.host or "").strip()
        effective_mode = configured_mode
        if configured_mode == "off" and token and not cls._is_loopback(host):
            effective_mode = "required"
            bind_event("gateway.auth").warning(
                "gateway auth auto-hardened configured_mode={} effective_mode={} host={} token_configured=true",
                configured_mode,
                effective_mode,
                host or "-",
            )
        return cls(
            mode=effective_mode,
            token=token,
            allow_loopback_without_auth=bool(auth_cfg.allow_loopback_without_auth),
            header_name=str(auth_cfg.header_name or "Authorization").strip() or "Authorization",
            query_param=str(auth_cfg.query_param or "token").strip() or "token",
            protect_health=bool(auth_cfg.protect_health),
        )

    def posture(self) -> str:
        if self.mode == "required":
            return "strict"
        if self.mode == "optional":
            return "optional"
        return "open"

    @staticmethod
    def _is_loopback(host: str | None) -> bool:
        value = str(host or "").strip().lower()
        if not value:
            return False
        if value in {"127.0.0.1", "::1", "localhost"}:
            return True
        return value.startswith("127.")

    def _extract_token(self, *, header_value: str, query_value: str) -> str:
        if query_value:
            return query_value.strip()
        value = header_value.strip()
        if not value:
            return ""
        if value.lower().startswith("bearer "):
            return value[7:].strip()
        return value

    def _require_for_scope(self, *, scope: str, host: str | None, diagnostics_auth: bool) -> bool:
        if self.mode == "off":
            return False
        if scope == "health":
            return self.protect_health and self.mode == "required"
        if scope == "diagnostics":
            return diagnostics_auth and self.mode == "required"
        if self.mode != "required":
            return False
        if self.allow_loopback_without_auth and self._is_loopback(host):
            return False
        return True

    def _token_matches(self, supplied_token: str) -> bool:
        return bool(self.token) and hmac.compare_digest(supplied_token, self.token)

    def check_http(self, *, request: Request, scope: str, diagnostics_auth: bool) -> None:
        client_host = request.client.host if request.client is not None else None
        should_require = self._require_for_scope(scope=scope, host=client_host, diagnostics_auth=diagnostics_auth)
        header_value = str(request.headers.get(self.header_name, "") or "")
        query_value = str(request.query_params.get(self.query_param, "") or "")
        supplied_token = self._extract_token(header_value=header_value, query_value=query_value)
        if should_require and not self._token_matches(supplied_token):
            raise HTTPException(status_code=401, detail="gateway_auth_required")
        if self.mode == "optional" and supplied_token and self.token and not self._token_matches(supplied_token):
            raise HTTPException(status_code=401, detail="gateway_auth_invalid")

    async def check_ws(self, *, socket: WebSocket, scope: str, diagnostics_auth: bool) -> bool:
        client_host = socket.client.host if socket.client is not None else None
        should_require = self._require_for_scope(scope=scope, host=client_host, diagnostics_auth=diagnostics_auth)
        header_value = str(socket.headers.get(self.header_name, "") or "")
        query_value = str(socket.query_params.get(self.query_param, "") or "")
        supplied_token = self._extract_token(header_value=header_value, query_value=query_value)
        if should_require and not self._token_matches(supplied_token):
            await socket.close(code=4401, reason="gateway_auth_required")
            return False
        if self.mode == "optional" and supplied_token and self.token and not self._token_matches(supplied_token):
            await socket.close(code=4401, reason="gateway_auth_invalid")
            return False
        return True


class _CronAPI:
    def __init__(self, service: CronService) -> None:
        self.service = service

    async def add_job(
        self,
        *,
        session_id: str,
        expression: str,
        prompt: str,
        name: str = "",
        timezone_name: str | None = None,
        channel: str = "",
        target: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        return await self.service.add_job(
            session_id=session_id,
            expression=expression,
            prompt=prompt,
            name=name,
            timezone_name=timezone_name,
            channel=channel,
            target=target,
            metadata=metadata,
        )

    def list_jobs(self, *, session_id: str) -> list[dict[str, Any]]:
        return self.service.list_jobs(session_id=session_id)

    def remove_job(self, job_id: str) -> bool:
        return self.service.remove_job(job_id)

    def enable_job(self, job_id: str, *, enabled: bool) -> bool:
        return self.service.enable_job(job_id, enabled=enabled)

    async def run_job(self, job_id: str, *, force: bool = True) -> str | None:
        return await self.service.run_job(job_id, force=force)


class _MessageAPI:
    def __init__(self, manager: ChannelManager) -> None:
        self.manager = manager

    async def send(
        self,
        *,
        channel: str,
        target: str,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        return await self.manager.send(channel=channel, target=target, text=text, metadata=metadata)


def _provider_config(config: AppConfig) -> dict[str, Any]:
    active_model = str(config.agents.defaults.model or config.provider.model).strip() or config.provider.model
    model_hint_name = detect_provider_name(active_model)
    hint_selected = getattr(config.providers, model_hint_name, None)
    hint_api_key = str(getattr(hint_selected, "api_key", "") or "").strip()
    hint_api_base = str(getattr(hint_selected, "api_base", "") or "").strip()
    local_base_hint = ""
    for local_name in ("ollama", "vllm"):
        local_selected = getattr(config.providers, local_name, None)
        local_candidate = str(getattr(local_selected, "api_base", "") or "").strip()
        if local_candidate:
            local_base_hint = local_candidate
            break
    provider_name = detect_provider_name(
        active_model,
        api_key=hint_api_key or str(config.provider.litellm_api_key or "").strip(),
        base_url=hint_api_base or str(config.provider.litellm_base_url or "").strip() or local_base_hint,
    )
    selected = getattr(config.providers, provider_name, None) or hint_selected
    selected_api_key = selected.api_key if selected is not None else ""
    selected_api_base = selected.api_base if selected is not None else ""

    return {
        "model": active_model,
        "auth": {
            "providers": {
                "openai_codex": {
                    "access_token": config.auth.providers.openai_codex.access_token,
                    "account_id": config.auth.providers.openai_codex.account_id,
                    "source": config.auth.providers.openai_codex.source,
                }
            }
        },
        "providers": {
            "litellm": {
                "base_url": selected_api_base or config.provider.litellm_base_url,
                "api_key": selected_api_key or config.provider.litellm_api_key,
                "extra_headers": selected.extra_headers if selected is not None else {},
            },
            "custom": {
                "api_base": config.providers.custom.api_base,
                "api_key": config.providers.custom.api_key,
                "extra_headers": dict(config.providers.custom.extra_headers),
            },
            "openrouter": {
                "api_key": config.providers.openrouter.api_key,
                "api_base": config.providers.openrouter.api_base,
            },
            "gemini": {
                "api_key": config.providers.gemini.api_key,
                "api_base": config.providers.gemini.api_base,
            },
            "openai": {
                "api_key": config.providers.openai.api_key,
                "api_base": config.providers.openai.api_base,
            },
            "anthropic": {
                "api_key": config.providers.anthropic.api_key,
                "api_base": config.providers.anthropic.api_base,
            },
            "deepseek": {
                "api_key": config.providers.deepseek.api_key,
                "api_base": config.providers.deepseek.api_base,
            },
            "groq": {
                "api_key": config.providers.groq.api_key,
                "api_base": config.providers.groq.api_base,
            },
            "ollama": {
                "api_key": config.providers.ollama.api_key,
                "api_base": config.providers.ollama.api_base,
            },
            "vllm": {
                "api_key": config.providers.vllm.api_key,
                "api_base": config.providers.vllm.api_base,
            },
        },
    }


def build_runtime(config: AppConfig) -> RuntimeContainer:
    bind_event("gateway.runtime").info("building runtime workspace={} state={}", config.workspace_path, config.state_path)
    workspace = WorkspaceLoader(workspace_path=config.workspace_path)
    workspace.bootstrap()
    workspace_path = Path(config.workspace_path).expanduser().resolve()

    provider = build_provider(_provider_config(config))
    provider_runtime = getattr(provider, "primary", provider)
    local_runtime_probe = probe_local_provider_runtime(
        model=provider.get_default_model(),
        base_url=str(getattr(provider_runtime, "base_url", "") or ""),
    )
    if local_runtime_probe["checked"] and not local_runtime_probe["ok"]:
        raise RuntimeError(str(local_runtime_probe["error"] or "provider_config_error:local_runtime_unavailable"))
    cron = CronService(
        store_path=Path(config.state_path) / "cron_jobs.json",
        default_timezone=config.scheduler.timezone,
    )
    heartbeat_interval = int(config.gateway.heartbeat.interval_s or 1800)
    scheduler_interval = int(getattr(config.scheduler, "heartbeat_interval_seconds", heartbeat_interval) or heartbeat_interval)
    if heartbeat_interval == 1800 and scheduler_interval != 1800:
        heartbeat_interval = scheduler_interval
    heartbeat = HeartbeatService(
        interval_seconds=heartbeat_interval,
        state_path=workspace_path / "memory" / "heartbeat-state.json",
    )
    wake_backlog = int(getattr(config.gateway.autonomy, "max_queue_backlog", 200) or 200)
    if wake_backlog <= 0:
        wake_backlog = 200
    autonomy_wake = AutonomyWakeCoordinator(max_pending=wake_backlog)

    tools = ToolRegistry(safety=config.tools.safety)
    tools.register(
        ExecTool(
            workspace_path=workspace_path,
            restrict_to_workspace=config.tools.restrict_to_workspace,
            path_append=config.tools.exec.path_append,
            timeout_seconds=config.tools.exec.timeout,
            deny_patterns=config.tools.exec.deny_patterns,
            allow_patterns=config.tools.exec.allow_patterns,
            deny_path_patterns=config.tools.exec.deny_path_patterns,
            allow_path_patterns=config.tools.exec.allow_path_patterns,
        )
    )
    tools.register(
        ApplyPatchTool(
            workspace_path=workspace_path,
            restrict_to_workspace=config.tools.restrict_to_workspace,
        )
    )
    tools.register(
        ProcessTool(
            workspace_path=workspace_path,
            restrict_to_workspace=config.tools.restrict_to_workspace,
            path_append=config.tools.exec.path_append,
            deny_patterns=config.tools.exec.deny_patterns,
            allow_patterns=config.tools.exec.allow_patterns,
            deny_path_patterns=config.tools.exec.deny_path_patterns,
            allow_path_patterns=config.tools.exec.allow_path_patterns,
        )
    )
    tools.register(ReadFileTool(workspace_path=workspace_path, restrict_to_workspace=config.tools.restrict_to_workspace))
    tools.register(WriteFileTool(workspace_path=workspace_path, restrict_to_workspace=config.tools.restrict_to_workspace))
    tools.register(EditFileTool(workspace_path=workspace_path, restrict_to_workspace=config.tools.restrict_to_workspace))
    tools.register(ReadTool(workspace_path=workspace_path, restrict_to_workspace=config.tools.restrict_to_workspace))
    tools.register(WriteTool(workspace_path=workspace_path, restrict_to_workspace=config.tools.restrict_to_workspace))
    tools.register(EditTool(workspace_path=workspace_path, restrict_to_workspace=config.tools.restrict_to_workspace))
    tools.register(ListDirTool(workspace_path=workspace_path, restrict_to_workspace=config.tools.restrict_to_workspace))
    tools.register(
        WebFetchTool(
            proxy=config.tools.web.proxy,
            max_redirects=config.tools.web.max_redirects,
            timeout=config.tools.web.timeout,
            max_chars=config.tools.web.max_chars,
            allowlist=config.tools.web.allowlist,
            denylist=config.tools.web.denylist,
            block_private_addresses=config.tools.web.block_private_addresses,
        )
    )
    tools.register(WebSearchTool(proxy=config.tools.web.proxy, timeout=config.tools.web.search_timeout))
    tools.register(CronTool(_CronAPI(cron)))
    tools.register(MCPTool(config.tools.mcp))
    skills = SkillsLoader()

    sessions = SessionStore(
        root=Path(config.state_path) / "sessions",
        max_messages_per_session=config.agents.defaults.session_retention_messages,
    )
    memory_backend = resolve_memory_backend(
        backend_name=str(config.agents.defaults.memory.backend or "sqlite"),
        pgvector_url=str(config.agents.defaults.memory.pgvector_url or ""),
    )
    if memory_backend.name == "pgvector" and not memory_backend.is_supported():
        raise RuntimeError(
            "memory backend 'pgvector' is not supported in this runtime: configure "
            "agents.defaults.memory.pgvector_url with postgres:// or postgresql://, "
            "or use backend=sqlite"
        )

    memory = MemoryStore(
        db_path=Path(config.state_path) / "memory.jsonl",
        semantic_enabled=bool(
            getattr(config.agents.defaults.memory, "semantic_search", config.agents.defaults.semantic_memory)
        ),
        memory_auto_categorize=bool(
            getattr(config.agents.defaults.memory, "auto_categorize", config.agents.defaults.memory_auto_categorize)
        ),
        emotional_tracking=bool(
            getattr(config.agents.defaults.memory, "emotional_tracking", False)
        ),
        memory_backend_name=str(config.agents.defaults.memory.backend or "sqlite"),
        memory_backend_url=str(config.agents.defaults.memory.pgvector_url or ""),
    )
    tools.register(SkillTool(loader=skills, registry=tools, memory=memory))
    memory_monitor = MemoryMonitor(memory) if bool(getattr(config.agents.defaults.memory, "proactive", False)) else None
    tools.register(MemoryRecallTool(memory))
    tools.register(MemorySearchTool(memory))
    tools.register(MemoryGetTool(workspace_path=workspace_path))
    tools.register(MemoryLearnTool(memory))
    tools.register(MemoryForgetTool(memory))
    tools.register(MemoryAnalyzeTool(memory))
    prompt = PromptBuilder(workspace_path=config.workspace_path)

    engine = AgentEngine(
        provider=provider,
        tools=tools,
        sessions=sessions,
        memory=memory,
        prompt_builder=prompt,
        skills_loader=skills,
        subagent_state_path=Path(config.state_path) / "subagents",
        max_iterations=config.agents.defaults.max_tool_iterations,
        max_tokens=config.agents.defaults.max_tokens,
        temperature=config.agents.defaults.temperature,
        memory_window=config.agents.defaults.memory_window,
        reasoning_effort_default=config.agents.defaults.reasoning_effort,
        loop_detection=LoopDetectionSettings(
            enabled=config.tools.loop_detection.enabled,
            history_size=config.tools.loop_detection.history_size,
            repeat_threshold=config.tools.loop_detection.repeat_threshold,
            critical_threshold=config.tools.loop_detection.critical_threshold,
        ),
    )

    async def _subagent_runner(session_id: str, task: str) -> str:
        result = await engine.run(session_id=session_id, user_text=task)
        return result.text

    async def _session_runner(session_id: str, task: str):
        return await engine.run(session_id=session_id, user_text=task)

    tools.register(SpawnTool(engine.subagents, _subagent_runner, memory=memory))
    tools.register(SessionsListTool(sessions))
    tools.register(SessionsHistoryTool(sessions))
    tools.register(SessionsSendTool(_session_runner))
    tools.register(SessionsSpawnTool(engine.subagents, _session_runner))
    tools.register(SubagentsTool(engine.subagents))
    tools.register(SessionStatusTool(sessions, engine.subagents))

    bus = MessageQueue()
    channels = ChannelManager(bus=bus, engine=engine)
    tools.register(MessageTool(_MessageAPI(channels)))

    bind_event("gateway.runtime").info("runtime ready provider_model={} tools={}", config.agents.defaults.model, len(tools.schema()))
    return RuntimeContainer(
        config=config,
        bus=bus,
        engine=engine,
        channels=channels,
        cron=cron,
        heartbeat=heartbeat,
        autonomy_wake=autonomy_wake,
        workspace=workspace,
        memory_monitor=memory_monitor,
    )


async def _route_cron_job(runtime: RuntimeContainer, job) -> str | None:
    bind_event("cron.dispatch", session=job.session_id).info("cron dispatch start job_id={}", job.id)
    try:
        result = await _run_engine_with_timeout(
            engine=runtime.engine,
            session_id=job.session_id,
            user_text=job.payload.prompt,
            timeout_s=GATEWAY_CRON_ENGINE_TIMEOUT_S,
        )
    except RuntimeError as exc:
        if str(exc) == "engine_run_timeout":
            bind_event("cron.dispatch", session=job.session_id).warning(
                "cron dispatch timed out job_id={} timeout_s={}",
                job.id,
                GATEWAY_CRON_ENGINE_TIMEOUT_S,
            )
            return "engine_run_timeout"
        raise
    channel = job.payload.channel.strip() or job.session_id.split(":", 1)[0]
    target = job.payload.target.strip() or job.session_id.split(":", 1)[-1]
    if channel and target:
        try:
            await runtime.channels.send(channel=channel, target=target, text=result.text)
        except Exception:
            bind_event("channel.send", session=job.session_id, channel=channel).error("cron dispatch send failed job_id={} target={}", job.id, target)
            return "cron_send_skipped"
    bind_event("cron.dispatch", session=job.session_id).info("cron dispatch finished job_id={}", job.id)
    return result.text


def _default_heartbeat_route() -> tuple[str, str]:
    return "cli", "profile"


_LATEST_MEMORY_ROUTE_CACHE: dict[int, tuple[float, tuple[str, str]]] = {}


def _latest_source_from_history_tail(memory_store: Any, *, tail_bytes: int = LATEST_MEMORY_ROUTE_TAIL_BYTES) -> str:
    history_path = getattr(memory_store, "history_path", None)
    if history_path is None:
        return ""
    try:
        path = Path(history_path)
    except Exception:
        return ""
    if not path.exists() or not path.is_file():
        return ""

    try:
        with path.open("rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            start = max(0, size - max(512, int(tail_bytes)))
            fh.seek(start)
            chunk = fh.read()
    except Exception:
        return ""

    if not chunk:
        return ""
    raw_text = chunk.decode("utf-8", errors="ignore")
    lines = raw_text.splitlines()
    for raw_line in reversed(lines):
        line = str(raw_line or "").strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        source = str(payload.get("source", "") or "").strip()
        if source:
            return source
    return ""


async def _latest_memory_route(memory_store: Any) -> tuple[str, str]:
    channel, target = _default_heartbeat_route()
    if memory_store is None:
        return channel, target

    cache_key = id(memory_store)
    now = time.monotonic()
    cached = _LATEST_MEMORY_ROUTE_CACHE.get(cache_key)
    if cached is not None:
        cached_at, cached_route = cached
        if (now - cached_at) <= LATEST_MEMORY_ROUTE_CACHE_TTL_S:
            return cached_route

    source = ""
    try:
        source = await asyncio.to_thread(_latest_source_from_history_tail, memory_store)
    except Exception:
        return channel, target

    resolved_route = MemoryMonitor._delivery_route_from_source(source) if source else (channel, target)
    _LATEST_MEMORY_ROUTE_CACHE[cache_key] = (now, resolved_route)
    return resolved_route


async def _run_proactive_monitor(runtime: RuntimeContainer) -> dict[str, Any]:
    monitor = getattr(runtime, "memory_monitor", None)
    channels = getattr(runtime, "channels", None)
    memory_store = getattr(getattr(runtime, "engine", None), "memory", None)

    result: dict[str, Any] = {
        "status": "disabled",
        "scanned": 0,
        "delivered": 0,
        "failed": 0,
        "next_step_sent": False,
        "error": "",
    }
    if monitor is None or channels is None:
        return result

    result["status"] = "ok"
    try:
        suggestions = await monitor.scan()
    except Exception as exc:
        bind_event("proactive.memory", session="autonomy:proactive").warning("memory monitor scan failed error={}", exc)
        result["status"] = "scan_error"
        result["error"] = str(exc)
        suggestions = []

    result["scanned"] = len(suggestions)
    for suggestion in suggestions:
        if not monitor.should_deliver(suggestion, min_priority=0.7):
            continue
        try:
            priority = float(getattr(suggestion, "priority", 0.0) or 0.0)
        except Exception:
            priority = 0.0
        metadata = {
            "source": "memory_monitor",
            "suggestion_id": suggestion.suggestion_id,
            "trigger": suggestion.trigger,
            "priority": priority,
            **dict(getattr(suggestion, "metadata", {}) or {}),
        }
        try:
            await channels.send(
                channel=suggestion.channel,
                target=suggestion.target,
                text=suggestion.text,
                metadata=metadata,
            )
        except Exception as exc:
            bind_event("proactive.memory", session="autonomy:proactive").warning(
                "memory suggestion delivery failed suggestion_id={} channel={} target={} error={}",
                suggestion.suggestion_id,
                suggestion.channel,
                suggestion.target,
                exc,
            )
            result["failed"] = int(result.get("failed", 0) or 0) + 1
            try:
                monitor.mark_failed(suggestion, error=str(exc))
            except Exception:
                pass
            continue
        result["delivered"] = int(result.get("delivered", 0) or 0) + 1
        try:
            monitor.mark_delivered(suggestion)
        except Exception as exc:
            bind_event("proactive.memory", session="autonomy:proactive").warning(
                "memory suggestion mark_delivered failed suggestion_id={} error={}",
                suggestion.suggestion_id,
                exc,
            )

    try:
        channel, target = await _latest_memory_route(memory_store)
        if memory_store is not None and hasattr(memory_store, "retrieve"):
            proactive = await memory_store.retrieve(
                "What should be the next proactive follow-up question?",
                method="llm",
                limit=5,
            )
            next_step_query = str(proactive.get("next_step_query", "") or "").strip()
            if next_step_query:
                suggestion = MemorySuggestion(
                    text=next_step_query,
                    priority=0.74,
                    trigger="next_step_query",
                    channel=channel,
                    target=target,
                    metadata={
                        "trigger": "next_step_query",
                        "source": "memory_llm",
                    },
                )
                if monitor.should_deliver(suggestion, min_priority=0.7):
                    metadata = {
                        "source": "memory_monitor",
                        "suggestion_id": suggestion.suggestion_id,
                        "trigger": "next_step_query",
                        "priority": float(getattr(suggestion, "priority", 0.0) or 0.0),
                        **dict(getattr(suggestion, "metadata", {}) or {}),
                    }
                    try:
                        await channels.send(
                            channel=suggestion.channel,
                            target=suggestion.target,
                            text=suggestion.text,
                            metadata=metadata,
                        )
                    except Exception as exc:
                        bind_event("proactive.memory", session="autonomy:proactive").warning(
                            "next-step suggestion delivery failed channel={} target={} error={}",
                            suggestion.channel,
                            suggestion.target,
                            exc,
                        )
                        result["failed"] = int(result.get("failed", 0) or 0) + 1
                        try:
                            monitor.mark_failed(suggestion, error=str(exc))
                        except Exception:
                            pass
                    else:
                        result["delivered"] = int(result.get("delivered", 0) or 0) + 1
                        result["next_step_sent"] = True
                        try:
                            monitor.mark_delivered(suggestion)
                        except Exception:
                            pass
    except Exception as exc:
        bind_event("proactive.memory", session="autonomy:proactive").warning(
            "next-step proactive retrieval failed error={}",
            exc,
        )
        result["status"] = "next_step_error"
        result["error"] = str(exc)

    return result


async def _run_heartbeat(runtime: RuntimeContainer) -> HeartbeatDecision:
    heartbeat_prompt = (
        "Read HEARTBEAT.md if it exists (workspace context). Follow it strictly. "
        "Do not infer or repeat old tasks from prior chats. "
        "If nothing needs attention, reply HEARTBEAT_OK."
    )
    workspace_heartbeat = ""
    workspace = getattr(runtime, "workspace", None)
    workspace_heartbeat_prompt = getattr(workspace, "heartbeat_prompt", None)
    if callable(workspace_heartbeat_prompt):
        try:
            workspace_heartbeat = str(workspace_heartbeat_prompt() or "").strip()
        except Exception:
            workspace_heartbeat = ""
    if workspace_heartbeat:
        heartbeat_prompt = f"{heartbeat_prompt}\n\nHEARTBEAT.md content:\n{workspace_heartbeat}"
    session_id = "heartbeat:system"
    bind_event("heartbeat.tick", session="heartbeat:system").debug("heartbeat callback running")
    result = await _run_engine_with_timeout(
        engine=runtime.engine,
        session_id=session_id,
        user_text=heartbeat_prompt,
        timeout_s=GATEWAY_HEARTBEAT_ENGINE_TIMEOUT_S,
    )
    bind_event("heartbeat.tick", session="heartbeat:system").debug("heartbeat callback completed")
    decision = HeartbeatDecision.from_result(result.text)

    channels = getattr(runtime, "channels", None)
    memory_store = getattr(getattr(runtime, "engine", None), "memory", None)

    if decision.action == "run" and decision.text:
        channel, target = await _latest_memory_route(memory_store)
        metadata = {
            "source": "heartbeat",
            "trigger": "heartbeat_loop",
            "decision_reason": decision.reason,
        }
        try:
            if channels is None:
                raise RuntimeError("channels_unavailable")
            await channels.send(channel=channel, target=target, text=decision.text, metadata=metadata)
        except Exception as exc:
            bind_event("heartbeat.tick", session="heartbeat:system").warning(
                "actionable heartbeat dispatch failed channel={} target={} error={}",
                channel,
                target,
                exc,
            )
            decision = HeartbeatDecision(action="run", reason="actionable_dispatch_failed", text=decision.text)
        else:
            decision = HeartbeatDecision(action="run", reason="actionable_dispatched", text=decision.text)

    return decision


def create_app(config: AppConfig | None = None) -> FastAPI:
    setup_logging()
    cfg = config or load_config()
    runtime = build_runtime(cfg)
    auth_guard = GatewayAuthGuard.from_config(cfg)
    if auth_guard.mode == "required" and not auth_guard.token:
        raise RuntimeError("gateway_auth_required_but_token_missing")
    if auth_guard.mode == "off" and not GatewayAuthGuard._is_loopback(cfg.gateway.host):
        bind_event("gateway.auth").warning("gateway running on non-loopback host without auth host={}", cfg.gateway.host)
    lifecycle = GatewayLifecycleState()
    http_telemetry = HttpRequestTelemetry()
    ws_telemetry = WebSocketTelemetry()
    started_monotonic = time.monotonic()
    lifecycle.components["heartbeat"]["enabled"] = bool(cfg.gateway.heartbeat.enabled)
    lifecycle.components["proactive_monitor"]["enabled"] = bool(runtime.memory_monitor is not None)
    lifecycle.components["memory_quality_tuning"]["enabled"] = bool(cfg.gateway.autonomy.tuning_loop_enabled)
    proactive_interval_seconds = max(5, int(cfg.gateway.heartbeat.interval_s or 1800))
    proactive_task: asyncio.Task[Any] | None = None
    proactive_running = False
    proactive_stop_event = asyncio.Event()
    proactive_runner_state: dict[str, Any] = {
        "enabled": bool(runtime.memory_monitor is not None),
        "running": False,
        "interval_seconds": proactive_interval_seconds,
        "ticks": 0,
        "success_count": 0,
        "error_count": 0,
        "backpressure_count": 0,
        "delivered_count": 0,
        "last_trigger": "",
        "last_result": "",
        "last_error": "",
        "last_run_iso": "",
    }
    tuning_loop_interval_seconds = max(1, int(cfg.gateway.autonomy.tuning_loop_interval_s or 1800))
    tuning_loop_timeout_seconds = max(1.0, float(cfg.gateway.autonomy.tuning_loop_timeout_s or 45.0))
    tuning_loop_cooldown_seconds = max(0, int(cfg.gateway.autonomy.tuning_loop_cooldown_s or 300))
    tuning_degrading_streak_threshold = max(1, int(cfg.gateway.autonomy.tuning_degrading_streak_threshold or 2))
    tuning_recent_actions_limit = max(1, int(cfg.gateway.autonomy.tuning_recent_actions_limit or 20))
    tuning_error_backoff_seconds = max(1, int(cfg.gateway.autonomy.tuning_error_backoff_s or 900))
    tuning_actions_per_hour_cap = max(1, int(cfg.gateway.autonomy.action_rate_limit_per_hour or 20))
    tuning_task: asyncio.Task[Any] | None = None
    tuning_running = False
    tuning_stop_event = asyncio.Event()
    tuning_runner_state: dict[str, Any] = {
        "enabled": bool(cfg.gateway.autonomy.tuning_loop_enabled),
        "running": False,
        "interval_seconds": tuning_loop_interval_seconds,
        "timeout_seconds": tuning_loop_timeout_seconds,
        "cooldown_seconds": tuning_loop_cooldown_seconds,
        "actions_per_hour_cap": tuning_actions_per_hour_cap,
        "ticks": 0,
        "success_count": 0,
        "error_count": 0,
        "action_count": 0,
        "last_result": "",
        "last_error": "",
        "last_run_iso": "",
        "next_run_iso": "",
        "last_action": "",
        "last_action_status": "",
        "last_action_reason": "",
        "actions_by_layer": {},
        "actions_by_playbook": {},
        "actions_by_action": {},
        "action_status_by_layer": {},
        "last_action_metadata": {},
    }
    memory_quality_cache: dict[str, Any] = {
        "fingerprint": "",
        "payload": None,
    }

    def _bootstrap_status_snapshot() -> dict[str, Any]:
        fallback = {
            "pending": False,
            "bootstrap_exists": False,
            "bootstrap_path": str(runtime.workspace.bootstrap_path()),
            "state_path": str(runtime.workspace.bootstrap_state_path()),
            "last_run_iso": "",
            "completed_at": "",
            "last_status": "",
            "last_error": "",
            "run_count": 0,
            "last_session_id": "",
        }
        try:
            payload = runtime.workspace.bootstrap_status()
        except Exception as exc:
            fallback["last_status"] = "error"
            fallback["last_error"] = str(exc)
            return fallback
        if not isinstance(payload, dict):
            return fallback
        for key in tuple(fallback.keys()):
            if key in payload:
                fallback[key] = payload[key]
        fallback["pending"] = bool(fallback.get("pending", False))
        fallback["bootstrap_exists"] = bool(fallback.get("bootstrap_exists", False))
        fallback["run_count"] = max(0, int(fallback.get("run_count", 0) or 0))
        return fallback

    def _refresh_bootstrap_component() -> dict[str, Any]:
        status = _bootstrap_status_snapshot()
        row = lifecycle.components.setdefault(
            "bootstrap",
            {"enabled": True, "running": False, "pending": False, "last_status": "", "last_error": ""},
        )
        row["enabled"] = True
        row["pending"] = bool(status.get("pending", False))
        row["running"] = bool(status.get("pending", False))
        row["last_status"] = str(status.get("last_status", "") or "")
        row["last_error"] = str(status.get("last_error", "") or "")
        row["completed_at"] = str(status.get("completed_at", "") or "")
        row["run_count"] = int(status.get("run_count", 0) or 0)
        return status

    async def _dispatch_autonomy_wake(kind: str, payload: dict[str, Any]) -> Any:
        if kind == "heartbeat":
            return await _run_heartbeat(runtime)
        if kind == "proactive":
            return await _run_proactive_monitor(runtime)
        if kind == "cron":
            job = payload.get("job")
            if job is None:
                return "cron_job_missing"
            return await _route_cron_job(runtime, job)
        return None

    async def _submit_heartbeat_wake() -> HeartbeatDecision:
        fallback = HeartbeatDecision(action="skip", reason="wake_backpressure")
        decision = await runtime.autonomy_wake.submit(
            kind="heartbeat",
            key="heartbeat:loop",
            priority=10,
            payload={},
            fallback_result=fallback,
        )
        return HeartbeatDecision.from_result(decision)

    async def _submit_cron_wake(job) -> str | None:
        return await runtime.autonomy_wake.submit(
            kind="cron",
            key=f"cron:{job.id}",
            priority=50,
            payload={"job": job},
            fallback_result="cron_backpressure_skipped",
        )

    async def _submit_proactive_wake() -> dict[str, Any]:
        fallback = {
            "status": "wake_backpressure",
            "scanned": 0,
            "delivered": 0,
            "failed": 0,
            "next_step_sent": False,
            "error": "",
        }
        response = await runtime.autonomy_wake.submit(
            kind="proactive",
            key="proactive:memory_monitor",
            priority=30,
            payload={},
            fallback_result=fallback,
        )
        if isinstance(response, dict):
            return dict(response)
        return fallback

    def _is_internal_session_id(session_id: str) -> bool:
        normalized = str(session_id or "").strip().lower()
        return normalized.startswith("heartbeat:") or normalized.startswith("autonomy:") or normalized.startswith("bootstrap:")

    def _finalize_bootstrap_for_user_turn(session_id: str) -> None:
        if _is_internal_session_id(session_id):
            _refresh_bootstrap_component()
            return

        status = _bootstrap_status_snapshot()
        if not bool(status.get("pending", False)):
            _refresh_bootstrap_component()
            return

        try:
            completed = runtime.workspace.complete_bootstrap()
            if completed:
                runtime.workspace.record_bootstrap_result(status="completed", session_id=session_id)
            else:
                runtime.workspace.record_bootstrap_result(
                    status="error",
                    session_id=session_id,
                    error="complete_bootstrap_returned_false",
                )
        except Exception as exc:
            try:
                runtime.workspace.record_bootstrap_result(status="error", session_id=session_id, error=str(exc))
            except Exception:
                pass
        finally:
            _refresh_bootstrap_component()

    def _utc_now_iso() -> str:
        return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

    def _control_plane_payload(server_time: str | None = None) -> ControlPlaneResponse:
        now = server_time or _utc_now_iso()
        _refresh_bootstrap_component()
        return ControlPlaneResponse(
            ready=bool(lifecycle.ready),
            phase=str(lifecycle.phase),
            contract_version=GATEWAY_CONTRACT_VERSION,
            server_time=now,
            components=dict(lifecycle.components),
            auth={
                "posture": auth_guard.posture(),
                "mode": auth_guard.mode,
                "allow_loopback_without_auth": auth_guard.allow_loopback_without_auth,
                "protect_health": auth_guard.protect_health,
                "token_configured": bool(auth_guard.token),
                "header_name": auth_guard.header_name,
                "query_param": auth_guard.query_param,
            },
            memory_proactive_enabled=bool(runtime.memory_monitor is not None),
        )

    def _parse_iso(value: str) -> dt.datetime | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)

    def _semantic_metrics_from_payload(payload: Any) -> dict[str, Any]:
        semantic_raw = payload.get("semantic", {}) if isinstance(payload, dict) else {}
        if not isinstance(semantic_raw, dict):
            semantic_raw = {}
        return {
            "enabled": bool(semantic_raw.get("enabled", False)),
            "coverage_ratio": float(semantic_raw.get("coverage_ratio", 0.0) or 0.0),
            "missing_records": int(semantic_raw.get("missing_records", 0) or 0),
            "total_records": int(semantic_raw.get("total_records", 0) or 0),
        }

    def _reasoning_layer_metrics_from_payload(payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {}

        reasoning_raw = payload.get("reasoning_layers")
        if reasoning_raw is None:
            reasoning_raw = payload.get("reasoningLayers")
        if reasoning_raw is None:
            reasoning_raw = payload.get("layers")

        reasoning_payload: dict[str, Any] = {}
        if isinstance(reasoning_raw, dict) and reasoning_raw:
            reasoning_payload["reasoning_layers"] = dict(reasoning_raw)

        confidence_raw = payload.get("confidence")
        if isinstance(confidence_raw, dict) and confidence_raw:
            reasoning_payload["confidence"] = dict(confidence_raw)

        return reasoning_payload

    async def _collect_memory_analysis_metrics() -> tuple[dict[str, Any], dict[str, Any]]:
        semantic_metrics = {
            "enabled": False,
            "coverage_ratio": 0.0,
            "missing_records": 0,
            "total_records": 0,
        }
        reasoning_layer_metrics: dict[str, Any] = {}
        memory_store = getattr(runtime.engine, "memory", None)
        diagnostics_payload: dict[str, Any] = {}

        analysis_stats_fn = getattr(memory_store, "analysis_stats", None)
        if callable(analysis_stats_fn):
            try:
                raw_payload = await asyncio.wait_for(
                    asyncio.to_thread(analysis_stats_fn),
                    timeout=tuning_loop_timeout_seconds,
                )
            except Exception:
                raw_payload = {}
            if isinstance(raw_payload, dict):
                diagnostics_payload = raw_payload

        if not diagnostics_payload:
            analyze_fn = getattr(memory_store, "analyze", None)
            if callable(analyze_fn):
                try:
                    raw_payload = await asyncio.wait_for(
                        asyncio.to_thread(analyze_fn),
                        timeout=tuning_loop_timeout_seconds,
                    )
                except Exception:
                    raw_payload = {}
                if isinstance(raw_payload, dict):
                    diagnostics_payload = raw_payload

        semantic_metrics.update(_semantic_metrics_from_payload(diagnostics_payload))
        reasoning_layer_metrics = _reasoning_layer_metrics_from_payload(diagnostics_payload)
        return semantic_metrics, reasoning_layer_metrics

    async def _collect_memory_quality_inputs() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
        retrieval_metrics_snapshot = runtime.engine.retrieval_metrics_snapshot()
        turn_metrics_snapshot = runtime.engine.turn_metrics_snapshot()
        retrieval_metrics = {
            "attempts": int(retrieval_metrics_snapshot.get("retrieval_attempts", 0) or 0),
            "hits": int(retrieval_metrics_snapshot.get("retrieval_hits", 0) or 0),
            "rewrites": int(retrieval_metrics_snapshot.get("retrieval_rewrites", 0) or 0),
        }
        turn_metrics = {
            "successes": int(turn_metrics_snapshot.get("turns_success", 0) or 0),
            "errors": int(turn_metrics_snapshot.get("turns_provider_errors", 0) or 0)
            + int(turn_metrics_snapshot.get("turns_cancelled", 0) or 0),
        }

        semantic_metrics, reasoning_layer_metrics = await _collect_memory_analysis_metrics()

        return retrieval_metrics, turn_metrics, semantic_metrics, reasoning_layer_metrics

    async def _start_memory_quality_tuning() -> None:
        nonlocal tuning_task, tuning_running
        tuning_task, task_state = await _normalize_background_task(tuning_task)
        if task_state == "running":
            tuning_running = True
            tuning_runner_state["running"] = True
            return
        if task_state == "failed":
            tuning_runner_state["last_error"] = "previous_task_failed"

        tuning_stop_event.clear()
        tuning_running = True
        tuning_runner_state["running"] = True

        async def _tick() -> None:
            now = dt.datetime.now(dt.timezone.utc)
            now_iso = now.isoformat(timespec="seconds")
            memory_store = getattr(runtime.engine, "memory", None)
            update_quality_fn = getattr(memory_store, "update_quality_state", None)
            snapshot_fn = getattr(memory_store, "quality_state_snapshot", None)
            update_tuning_fn = getattr(memory_store, "update_quality_tuning_state", None)

            if not callable(update_quality_fn) or not callable(snapshot_fn):
                tuning_runner_state["last_result"] = "unsupported"
                tuning_runner_state["last_error"] = "memory_quality_methods_unavailable"
                tuning_runner_state["last_run_iso"] = now_iso
                tuning_runner_state["next_run_iso"] = (now + dt.timedelta(seconds=tuning_loop_interval_seconds)).isoformat(timespec="seconds")
                return

            action = ""
            action_status = "noop"
            action_reason = ""
            action_metadata: dict[str, Any] = {}
            tick_error = ""
            next_wait_seconds = tuning_loop_interval_seconds

            try:
                retrieval_metrics, turn_metrics, semantic_metrics, reasoning_layer_metrics = await _collect_memory_quality_inputs()

                def _call_quality_update_tuning() -> Any:
                    kwargs = {
                        "retrieval_metrics": retrieval_metrics,
                        "turn_stability_metrics": turn_metrics,
                        "semantic_metrics": {
                            "enabled": bool(semantic_metrics.get("enabled", False)),
                            "coverage_ratio": float(semantic_metrics.get("coverage_ratio", 0.0) or 0.0),
                        },
                        "sampled_at": now_iso,
                    }
                    if reasoning_layer_metrics:
                        try:
                            return update_quality_fn(
                                **kwargs,
                                reasoning_layer_metrics=reasoning_layer_metrics,
                            )
                        except TypeError:
                            return update_quality_fn(**kwargs)
                    return update_quality_fn(**kwargs)

                report = await asyncio.wait_for(
                    asyncio.to_thread(_call_quality_update_tuning),
                    timeout=tuning_loop_timeout_seconds,
                )
                snapshot = await asyncio.wait_for(asyncio.to_thread(snapshot_fn), timeout=tuning_loop_timeout_seconds)
                tuning_state = snapshot.get("tuning", {}) if isinstance(snapshot, dict) else {}

                drift = str((report.get("drift", {}) if isinstance(report, dict) else {}).get("assessment", "") or "")
                score = int((report.get("score", 0) if isinstance(report, dict) else 0) or 0)
                reasoning_report = report.get("reasoning_layers", {}) if isinstance(report, dict) else {}
                weakest_layer = ""
                if isinstance(reasoning_report, dict):
                    weakest_layer = _normalize_reasoning_layer(str(reasoning_report.get("weakest_layer", "") or ""))
                degrading_streak = int(tuning_state.get("degrading_streak", 0) or 0)
                if drift == "degrading":
                    degrading_streak += 1
                else:
                    degrading_streak = 0

                if drift == "degrading":
                    severity = ""
                    playbook_id = ""
                    if degrading_streak >= (tuning_degrading_streak_threshold + 2) or score <= 40:
                        severity = "high"
                    elif degrading_streak >= tuning_degrading_streak_threshold:
                        severity = "medium"
                    else:
                        severity = "low"

                    action, playbook_id = _select_tuning_action_playbook(
                        severity=severity,
                        weakest_layer=weakest_layer,
                    )
                    action_reason = f"quality_drift_{severity}:playbook_id={playbook_id}:severity={severity}"
                    if weakest_layer:
                        action_reason = f"{action_reason}:weakest_layer={weakest_layer}"

                    action_metadata = {
                        "severity": severity,
                        "playbook_id": playbook_id,
                    }
                    if weakest_layer:
                        action_metadata["weakest_layer"] = weakest_layer
                    action_metadata["action_variant"] = f"{playbook_id}:{action}:v2"

                    last_action_at = _parse_iso(str(tuning_state.get("last_action_at", "") or ""))
                    in_cooldown = (
                        last_action_at is not None
                        and tuning_loop_cooldown_seconds > 0
                        and (now - last_action_at).total_seconds() < float(tuning_loop_cooldown_seconds)
                    )

                    recent_actions_raw = tuning_state.get("recent_actions", [])
                    recent_actions = list(recent_actions_raw) if isinstance(recent_actions_raw, list) else []
                    recent_actions = recent_actions[-tuning_recent_actions_limit:]
                    one_hour_ago = now - dt.timedelta(hours=1)
                    action_events_last_hour = 0
                    for entry in recent_actions:
                        if not isinstance(entry, dict):
                            continue
                        status = str(entry.get("status", "") or "")
                        if status in {"cooldown_skipped", "rate_limited", "noop"}:
                            continue
                        at_dt = _parse_iso(str(entry.get("at", "") or ""))
                        if at_dt is None or at_dt < one_hour_ago:
                            continue
                        action_events_last_hour += 1

                    if in_cooldown:
                        action_status = "cooldown_skipped"
                    elif action_events_last_hour >= tuning_actions_per_hour_cap:
                        action_status = "rate_limited"
                    else:
                        if action == "notify_operator":
                            channel, target = await _latest_memory_route(memory_store)
                            layer_suffix = f" layer={weakest_layer}." if weakest_layer else ""
                            template_id, text_marker = _resolve_tuning_notify_variant(
                                layer=weakest_layer,
                                severity=severity,
                            )
                            action_metadata["template_id"] = template_id
                            await runtime.channels.send(
                                channel=channel,
                                target=target,
                                text=(
                                    f"Memory quality drift detected ({severity}). "
                                    f"score={score} streak={degrading_streak}.{layer_suffix} "
                                    f"variant={text_marker} Monitoring in progress."
                                ),
                                metadata={
                                    "source": "memory_quality_tuning",
                                    "trigger": "quality_loop",
                                    "drift": drift,
                                    **action_metadata,
                                },
                            )
                            action_status = "ok"
                        elif action == "semantic_backfill":
                            missing_records = int(semantic_metrics.get("missing_records", 0) or 0)
                            backfill_limit = _resolve_tuning_backfill_limit(
                                layer=weakest_layer,
                                severity=severity,
                                missing_records=missing_records,
                            )
                            action_metadata["backfill_limit"] = backfill_limit
                            backfill_fn = getattr(memory_store, "backfill_embeddings", None)
                            if callable(backfill_fn):
                                await asyncio.wait_for(
                                    asyncio.to_thread(backfill_fn, limit=backfill_limit),
                                    timeout=tuning_loop_timeout_seconds,
                                )
                                action_status = "ok"
                            else:
                                action_status = "unsupported"
                        elif action == "memory_snapshot":
                            snapshot_memory_fn = getattr(memory_store, "snapshot", None)
                            snapshot_tag = _resolve_tuning_snapshot_tag(layer=weakest_layer, severity=severity)
                            action_metadata["snapshot_tag"] = snapshot_tag
                            if callable(snapshot_memory_fn):
                                await asyncio.wait_for(
                                    asyncio.to_thread(snapshot_memory_fn, snapshot_tag),
                                    timeout=tuning_loop_timeout_seconds,
                                )
                                action_status = "ok"
                            else:
                                action_status = "unsupported"

                action_entry = None
                if action:
                    action_entry = {
                        "action": action,
                        "status": action_status,
                        "reason": action_reason,
                        "at": now_iso,
                        "metadata": dict(action_metadata),
                    }

                if action_status == "ok":
                    tuning_runner_state["action_count"] = int(tuning_runner_state.get("action_count", 0) or 0) + 1

                if action:
                    layer_key = _resolve_tuning_layer(weakest_layer)
                    actions_by_layer = tuning_runner_state.setdefault("actions_by_layer", {})
                    actions_by_layer[layer_key] = int(actions_by_layer.get(layer_key, 0) or 0) + 1

                    actions_by_playbook = tuning_runner_state.setdefault("actions_by_playbook", {})
                    if playbook_id:
                        actions_by_playbook[playbook_id] = int(actions_by_playbook.get(playbook_id, 0) or 0) + 1

                    actions_by_action = tuning_runner_state.setdefault("actions_by_action", {})
                    actions_by_action[action] = int(actions_by_action.get(action, 0) or 0) + 1

                    status_by_layer = tuning_runner_state.setdefault("action_status_by_layer", {})
                    layer_status_raw = status_by_layer.get(layer_key, {})
                    layer_status = dict(layer_status_raw) if isinstance(layer_status_raw, dict) else {}
                    layer_status[action_status] = int(layer_status.get(action_status, 0) or 0) + 1
                    status_by_layer[layer_key] = layer_status
                    tuning_runner_state["last_action_metadata"] = dict(action_metadata)

                if callable(update_tuning_fn):
                    tuning_patch: dict[str, Any] = {
                        "degrading_streak": degrading_streak,
                        "last_run_at": now_iso,
                        "next_run_at": (now + dt.timedelta(seconds=tuning_loop_interval_seconds)).isoformat(timespec="seconds"),
                        "last_error": "",
                    }
                    if action_entry is not None:
                        tuning_patch["last_action"] = action_entry.get("action", "")
                        tuning_patch["last_action_status"] = action_entry.get("status", "")
                        tuning_patch["last_reason"] = action_entry.get("reason", "")
                        tuning_patch["recent_actions"] = [action_entry]
                        if action_entry.get("status", "") not in {"cooldown_skipped", "rate_limited"}:
                            tuning_patch["last_action_at"] = action_entry.get("at", "")
                    await asyncio.wait_for(asyncio.to_thread(update_tuning_fn, tuning_patch), timeout=tuning_loop_timeout_seconds)

                tuning_runner_state["success_count"] = int(tuning_runner_state.get("success_count", 0) or 0) + 1
                tuning_runner_state["last_result"] = "ok"
                tuning_runner_state["last_error"] = ""
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                tick_error = str(exc)
                next_wait_seconds = tuning_error_backoff_seconds
                tuning_runner_state["error_count"] = int(tuning_runner_state.get("error_count", 0) or 0) + 1
                tuning_runner_state["last_result"] = "error"
                tuning_runner_state["last_error"] = tick_error
                bind_event("memory.quality.tuning").warning("tuning tick failed error={}", exc)
                if callable(update_tuning_fn):
                    try:
                        await asyncio.wait_for(
                            asyncio.to_thread(
                                update_tuning_fn,
                                {
                                    "last_run_at": now_iso,
                                    "next_run_at": (now + dt.timedelta(seconds=tuning_error_backoff_seconds)).isoformat(timespec="seconds"),
                                    "last_error": tick_error,
                                },
                            ),
                            timeout=tuning_loop_timeout_seconds,
                        )
                    except Exception:
                        pass
            finally:
                tuning_runner_state["last_run_iso"] = now_iso
                tuning_runner_state["next_run_iso"] = (now + dt.timedelta(seconds=next_wait_seconds)).isoformat(timespec="seconds")
                tuning_runner_state["last_action"] = str(action or "")
                tuning_runner_state["last_action_status"] = str(action_status or "")
                tuning_runner_state["last_action_reason"] = str(action_reason or "")
                if tick_error and not tuning_runner_state.get("last_error"):
                    tuning_runner_state["last_error"] = tick_error

        async def _loop() -> None:
            first_tick = True
            while tuning_running:
                if not first_tick:
                    try:
                        await asyncio.wait_for(tuning_stop_event.wait(), timeout=tuning_loop_interval_seconds)
                    except (asyncio.TimeoutError, TimeoutError):
                        pass
                    if tuning_stop_event.is_set() or not tuning_running:
                        break
                first_tick = False

                await _tick()
                tuning_runner_state["ticks"] = int(tuning_runner_state.get("ticks", 0) or 0) + 1

        tuning_task = asyncio.create_task(_loop())
        bind_event("memory.quality.tuning").info(
            "memory quality tuning loop started interval={} timeout={}",
            tuning_loop_interval_seconds,
            tuning_loop_timeout_seconds,
        )

    async def _stop_memory_quality_tuning() -> None:
        nonlocal tuning_task, tuning_running
        tuning_running = False
        tuning_stop_event.set()
        tuning_runner_state["running"] = False
        if tuning_task is None:
            return
        tuning_task.cancel()
        try:
            await tuning_task
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            tuning_runner_state["last_error"] = str(exc)
            bind_event("memory.quality.tuning").warning("memory quality tuning stop failed error={}", exc)
        tuning_task = None
        bind_event("memory.quality.tuning").info("memory quality tuning loop stopped")

    async def _start_proactive_monitor() -> None:
        nonlocal proactive_task, proactive_running
        proactive_task, task_state = await _normalize_background_task(proactive_task)
        if task_state == "running":
            proactive_running = True
            proactive_runner_state["running"] = True
            return
        if task_state == "failed":
            proactive_runner_state["last_error"] = "previous_task_failed"

        proactive_stop_event.clear()
        proactive_running = True
        proactive_runner_state["running"] = True

        async def _loop() -> None:
            first_tick = True
            while proactive_running:
                if not first_tick:
                    try:
                        await asyncio.wait_for(proactive_stop_event.wait(), timeout=proactive_interval_seconds)
                    except (asyncio.TimeoutError, TimeoutError):
                        pass
                    if proactive_stop_event.is_set() or not proactive_running:
                        break
                first_tick = False

                proactive_runner_state["ticks"] = int(proactive_runner_state.get("ticks", 0) or 0) + 1
                proactive_runner_state["last_trigger"] = "startup" if proactive_runner_state["ticks"] == 1 else "interval"
                proactive_runner_state["last_run_iso"] = _utc_now_iso()
                try:
                    scan_result = await _submit_proactive_wake()
                    status = str(scan_result.get("status", "") or "").strip().lower()
                    if status == "wake_backpressure":
                        proactive_runner_state["backpressure_count"] = int(proactive_runner_state.get("backpressure_count", 0) or 0) + 1
                    elif status in {"ok", "disabled"}:
                        proactive_runner_state["success_count"] = int(proactive_runner_state.get("success_count", 0) or 0) + 1
                    else:
                        proactive_runner_state["error_count"] = int(proactive_runner_state.get("error_count", 0) or 0) + 1
                    proactive_runner_state["delivered_count"] = int(proactive_runner_state.get("delivered_count", 0) or 0) + int(scan_result.get("delivered", 0) or 0)
                    proactive_runner_state["last_result"] = status or "unknown"
                    proactive_runner_state["last_error"] = str(scan_result.get("error", "") or "")
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    proactive_runner_state["error_count"] = int(proactive_runner_state.get("error_count", 0) or 0) + 1
                    proactive_runner_state["last_result"] = "error"
                    proactive_runner_state["last_error"] = str(exc)
                    bind_event("proactive.lifecycle").error("proactive loop tick failed error={}", exc)

        proactive_task = asyncio.create_task(_loop())
        bind_event("proactive.lifecycle").info("proactive monitor started interval_seconds={}", proactive_interval_seconds)

    async def _stop_proactive_monitor() -> None:
        nonlocal proactive_task, proactive_running
        proactive_running = False
        proactive_stop_event.set()
        proactive_runner_state["running"] = False
        if proactive_task is None:
            return
        proactive_task.cancel()
        try:
            await proactive_task
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            proactive_runner_state["last_error"] = str(exc)
            bind_event("proactive.lifecycle").error("proactive monitor stop failed error={}", exc)
        proactive_task = None
        bind_event("proactive.lifecycle").info("proactive monitor stopped")

    async def _start_subsystems() -> None:
        started: list[tuple[str, Any]] = []
        steps: list[tuple[str, Any, Any, bool]] = [
            ("channels", runtime.channels.start, runtime.channels.stop, True),
            ("autonomy_wake", runtime.autonomy_wake.start, runtime.autonomy_wake.stop, True),
            ("cron", runtime.cron.start, runtime.cron.stop, True),
            ("heartbeat", runtime.heartbeat.start, runtime.heartbeat.stop, bool(cfg.gateway.heartbeat.enabled)),
            ("proactive_monitor", _start_proactive_monitor, _stop_proactive_monitor, bool(runtime.memory_monitor is not None)),
            ("memory_quality_tuning", _start_memory_quality_tuning, _stop_memory_quality_tuning, bool(cfg.gateway.autonomy.tuning_loop_enabled)),
        ]

        for name, start_fn, stop_fn, enabled in steps:
            lifecycle.components.setdefault(name, {"enabled": enabled, "running": False, "last_error": ""})
            lifecycle.components[name]["enabled"] = enabled
            if not enabled:
                lifecycle.mark_component(name, running=False, error="disabled")
                continue
            try:
                if name == "channels":
                    await start_fn(cfg.to_dict())
                elif name == "autonomy_wake":
                    await start_fn(_dispatch_autonomy_wake)
                elif name == "cron":
                    await start_fn(_submit_cron_wake)
                elif name == "proactive_monitor":
                    await start_fn()
                elif name == "memory_quality_tuning":
                    await start_fn()
                else:
                    await start_fn(_submit_heartbeat_wake)
                lifecycle.mark_component(name, running=True)
                started.append((name, stop_fn))
                bind_event("gateway.lifecycle").info("subsystem started name={}", name)
            except Exception as exc:
                lifecycle.mark_component(name, running=False, error=str(exc))
                lifecycle.startup_error = str(exc)
                bind_event("gateway.lifecycle").error("subsystem failed to start name={} error={}", name, exc)
                for stop_name, stop in reversed(started):
                    try:
                        await stop()
                        lifecycle.mark_component(stop_name, running=False)
                        bind_event("gateway.lifecycle").info("subsystem rollback stopped name={}", stop_name)
                    except Exception as stop_exc:
                        lifecycle.mark_component(stop_name, running=False, error=str(stop_exc))
                        bind_event("gateway.lifecycle").error("subsystem rollback failed name={} error={}", stop_name, stop_exc)
                raise RuntimeError(f"gateway_startup_failed:{name}") from exc

    async def _stop_subsystems() -> None:
        steps: list[tuple[str, Any, bool]] = [
            ("heartbeat", runtime.heartbeat.stop, bool(cfg.gateway.heartbeat.enabled)),
            ("proactive_monitor", _stop_proactive_monitor, bool(runtime.memory_monitor is not None)),
            ("memory_quality_tuning", _stop_memory_quality_tuning, bool(cfg.gateway.autonomy.tuning_loop_enabled)),
            ("cron", runtime.cron.stop, True),
            ("autonomy_wake", runtime.autonomy_wake.stop, True),
            ("channels", runtime.channels.stop, True),
        ]
        for name, stop_fn, enabled in steps:
            if not enabled:
                lifecycle.mark_component(name, running=False, error="disabled")
                continue
            try:
                await stop_fn()
                lifecycle.mark_component(name, running=False)
                bind_event("gateway.lifecycle").info("subsystem stopped name={}", name)
            except Exception as exc:
                lifecycle.mark_component(name, running=False, error=str(exc))
                bind_event("gateway.lifecycle").error("subsystem stop failed name={} error={}", name, exc)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        lifecycle.phase = "starting"
        lifecycle.ready = False
        bind_event("gateway.lifecycle").info("gateway startup begin host={} port={}", cfg.gateway.host, cfg.gateway.port)
        await _start_subsystems()
        lifecycle.phase = "running"
        lifecycle.ready = True
        bind_event("gateway.lifecycle").info("gateway startup complete")
        try:
            yield
        finally:
            lifecycle.phase = "stopping"
            lifecycle.ready = False
            bind_event("gateway.lifecycle").info("gateway shutdown begin")
            await _stop_subsystems()
            lifecycle.phase = "stopped"
            bind_event("gateway.lifecycle").info("gateway shutdown complete")

    app = FastAPI(title="ClawLite Gateway", version="1.0.0", lifespan=lifespan)
    app.state.runtime = runtime
    app.state.lifecycle = lifecycle
    app.state.auth_guard = auth_guard
    app.state.http_telemetry = http_telemetry
    app.state.ws_telemetry = ws_telemetry
    telegram_webhook_path = _normalize_webhook_path(cfg.channels.telegram.webhook_path)

    @app.middleware("http")
    async def _http_telemetry_middleware(request: Request, call_next):
        started_at = time.perf_counter()
        await http_telemetry.start(method=request.method, path=request.url.path)
        status_code = 500
        try:
            response = await call_next(request)
            status_code = int(getattr(response, "status_code", 500) or 500)
            return response
        except HTTPException as exc:
            status_code = int(exc.status_code)
            raise
        except Exception:
            status_code = 500
            raise
        finally:
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            await http_telemetry.finish(status_code=status_code, latency_ms=elapsed_ms)

    @app.exception_handler(HTTPException)
    async def _http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail
        if isinstance(detail, str):
            payload: dict[str, Any] = {"error": detail, "status": exc.status_code, "code": detail}
        else:
            payload = {"error": "http_error", "status": exc.status_code, "code": "http_error", "detail": detail}
        return JSONResponse(status_code=exc.status_code, content=payload)

    def _provider_error_payload(exc: RuntimeError) -> tuple[int, str]:
        message = str(exc)
        if message == "engine_run_timeout":
            return (504, "engine_run_timeout")
        provider_http_code = None
        provider_http_detail = ""
        if message.startswith("provider_http_error:"):
            _, _, raw = message.partition("provider_http_error:")
            code, _, detail = raw.partition(":")
            provider_http_code = code.strip()
            provider_http_detail = detail.strip()

        if message.startswith("provider_auth_error:missing_api_key:"):
            provider = message.rsplit(":", 1)[-1]
            return (
                400,
                f"Chave de API ausente para o provedor '{provider}'. Defina CLAWLITE_LITELLM_API_KEY ou a chave especifica do provedor.",
            )
        if message.startswith("provider_config_error:missing_base_url:"):
            provider = message.rsplit(":", 1)[-1]
            return (
                400,
                f"Base URL ausente para o provedor '{provider}'. Configure CLAWLITE_LITELLM_BASE_URL.",
            )
        if message.startswith("provider_config_error:"):
            return (400, "Configuracao invalida do provedor. Revise modelo, base URL e chave de API.")
        if provider_http_code == "400":
            hint = provider_http_detail or "Verifique modelo, chave de API e base URL do provedor."
            return (400, f"Requisicao invalida ao provedor (400). {hint}")
        if provider_http_code == "401":
            return (
                502,
                "Falha de autenticacao no provedor (401). Verifique CLAWLITE_MODEL e CLAWLITE_LITELLM_API_KEY."
                + (f" Detalhe: {provider_http_detail}" if provider_http_detail else ""),
            )
        if provider_http_code == "429" or message == "provider_429_exhausted":
            return (429, "Limite de requisicoes no provedor. Tente novamente em instantes.")
        if provider_http_code:
            detail = f" Detalhe: {provider_http_detail}" if provider_http_detail else ""
            return (502, f"Falha no provedor remoto (HTTP {provider_http_code}).{detail}")
        if message.startswith("provider_network_error:"):
            return (503, "Provedor remoto indisponivel no momento (erro de rede).")
        if message.startswith("codex_http_error:401"):
            return (502, "Falha de autenticacao no Codex (401). Refaça login OAuth do provedor Codex.")
        if message == "codex_auth_error:missing_access_token":
            return (
                400,
                "Token OAuth do Codex ausente. Execute 'clawlite provider login openai-codex' para autenticar.",
            )
        if message.startswith("codex_auth_error:401"):
            return (
                502,
                "Sessao OAuth do Codex invalida ou expirada (401). Execute 'clawlite provider login openai-codex' novamente.",
            )
        if message.startswith("codex_http_error:429") or message == "codex_429_exhausted":
            return (429, "Limite de requisicoes no Codex. Tente novamente em instantes.")
        if message.startswith("codex_http_error:"):
            code = message.split(":", 1)[1]
            return (502, f"Falha no Codex (HTTP {code}).")
        if message.startswith("codex_network_error:"):
            return (503, "Codex indisponivel no momento (erro de rede).")
        return (500, "Falha interna ao processar a solicitacao.")

    @app.get("/health")
    async def health(request: Request) -> dict[str, Any]:
        auth_guard.check_http(request=request, scope="health", diagnostics_auth=cfg.gateway.diagnostics.require_auth)
        return {
            "ok": True,
            "ready": lifecycle.ready,
            "phase": lifecycle.phase,
            "channels": runtime.channels.status(),
            "queue": runtime.bus.stats(),
        }

    async def _status_handler(request: Request) -> ControlPlaneResponse:
        auth_guard.check_http(request=request, scope="control", diagnostics_auth=cfg.gateway.diagnostics.require_auth)
        return _control_plane_payload()

    @app.get("/v1/status", response_model=ControlPlaneResponse)
    async def status(request: Request) -> ControlPlaneResponse:
        return await _status_handler(request)

    @app.get("/api/status", response_model=ControlPlaneResponse)
    async def api_status(request: Request) -> ControlPlaneResponse:
        return await _status_handler(request)

    async def _diagnostics_handler(request: Request) -> DiagnosticsResponse:
        if not cfg.gateway.diagnostics.enabled:
            raise HTTPException(status_code=404, detail="diagnostics_disabled")
        auth_guard.check_http(request=request, scope="diagnostics", diagnostics_auth=cfg.gateway.diagnostics.require_auth)
        generated_at = _utc_now_iso()
        environment: dict[str, Any] = {}
        if cfg.gateway.diagnostics.include_config:
            environment = {
                "workspace_path": cfg.workspace_path,
                "state_path": cfg.state_path,
                "provider_model": cfg.agents.defaults.model,
            }
        retrieval_metrics_snapshot = runtime.engine.retrieval_metrics_snapshot()
        turn_metrics_snapshot = runtime.engine.turn_metrics_snapshot()
        engine_payload: dict[str, Any] = {
            "retrieval_metrics": retrieval_metrics_snapshot,
            "turn_metrics": turn_metrics_snapshot,
        }
        memory_payload: dict[str, Any]
        memory_store = getattr(runtime.engine, "memory", None)
        memory_diagnostics = getattr(memory_store, "diagnostics", None)
        if callable(memory_diagnostics):
            try:
                raw_memory_payload = memory_diagnostics()
            except Exception as exc:
                memory_payload = {
                    "available": True,
                    "error": str(exc),
                }
            else:
                if isinstance(raw_memory_payload, dict):
                    memory_payload = dict(raw_memory_payload)
                else:
                    memory_payload = {
                        "available": True,
                        "error": "invalid_memory_diagnostics_payload",
                    }
                memory_payload.setdefault("available", True)
        else:
            memory_payload = {
                "available": False,
            }
        engine_payload["memory"] = memory_payload
        memory_analysis_payload: dict[str, Any] = {
            "available": False,
        }
        memory_analysis_stats = getattr(memory_store, "analysis_stats", None)
        if callable(memory_analysis_stats):
            try:
                raw_memory_analysis_payload = memory_analysis_stats()
            except Exception as exc:
                memory_analysis_payload = {
                    "available": True,
                    "error": str(exc),
                }
            else:
                if isinstance(raw_memory_analysis_payload, dict):
                    memory_analysis_payload = dict(raw_memory_analysis_payload)
                else:
                    memory_analysis_payload = {
                        "available": True,
                        "error": "invalid_memory_analysis_payload",
                    }
                memory_analysis_payload.setdefault("available", True)
        engine_payload["memory_analysis"] = memory_analysis_payload

        memory_quality_payload: dict[str, Any] = {
            "available": False,
            "updated": False,
            "report": {},
            "state": {},
            "tuning": {},
            "error": {
                "type": "not_supported",
                "message": "memory_quality_methods_unavailable",
            },
        }
        quality_update = getattr(memory_store, "update_quality_state", None)
        quality_snapshot = getattr(memory_store, "quality_state_snapshot", None)
        if callable(quality_update) and callable(quality_snapshot):
            retrieval_metrics = {
                "attempts": int(retrieval_metrics_snapshot.get("retrieval_attempts", 0) or 0),
                "hits": int(retrieval_metrics_snapshot.get("retrieval_hits", 0) or 0),
                "rewrites": int(retrieval_metrics_snapshot.get("retrieval_rewrites", 0) or 0),
            }
            turn_metrics = {
                "successes": int(turn_metrics_snapshot.get("turns_success", 0) or 0),
                "errors": int(turn_metrics_snapshot.get("turns_provider_errors", 0) or 0)
                + int(turn_metrics_snapshot.get("turns_cancelled", 0) or 0),
            }
            semantic_raw, reasoning_layer_metrics = await _collect_memory_analysis_metrics()
            semantic_metrics = {
                "enabled": bool(semantic_raw.get("enabled", False)),
                "coverage_ratio": float(semantic_raw.get("coverage_ratio", 0.0) or 0.0),
            }

            fingerprint_payload = {
                "retrieval": retrieval_metrics,
                "turn": turn_metrics,
                "semantic": semantic_metrics,
                "reasoning_layers": reasoning_layer_metrics,
            }
            try:
                fingerprint = json.dumps(fingerprint_payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
            except Exception:
                fingerprint = repr(fingerprint_payload)

            cached_payload = memory_quality_cache.get("payload")
            if memory_quality_cache.get("fingerprint") == fingerprint and isinstance(cached_payload, dict):
                memory_quality_payload = dict(cached_payload)
                try:
                    snapshot = quality_snapshot()
                    if isinstance(snapshot, dict):
                        tuning_snapshot = snapshot.get("tuning", {})
                        tuning_payload = dict(tuning_snapshot) if isinstance(tuning_snapshot, dict) else {}
                        state_payload = memory_quality_payload.get("state", {})
                        if isinstance(state_payload, dict):
                            state_payload = dict(state_payload)
                        else:
                            state_payload = {}
                        state_payload["tuning"] = tuning_payload
                        memory_quality_payload["state"] = state_payload
                        memory_quality_payload["tuning"] = tuning_payload
                        report_payload = memory_quality_payload.get("report", {})
                        if isinstance(report_payload, dict):
                            report_payload = dict(report_payload)
                            report_payload["tuning"] = dict(tuning_payload)
                            memory_quality_payload["report"] = report_payload
                except Exception:
                    pass
            else:
                try:
                    def _call_quality_update_diagnostics() -> Any:
                        kwargs = {
                            "retrieval_metrics": retrieval_metrics,
                            "turn_stability_metrics": turn_metrics,
                            "semantic_metrics": semantic_metrics,
                            "sampled_at": generated_at,
                        }
                        if reasoning_layer_metrics:
                            try:
                                return quality_update(
                                    **kwargs,
                                    reasoning_layer_metrics=reasoning_layer_metrics,
                                )
                            except TypeError:
                                return quality_update(**kwargs)
                        return quality_update(**kwargs)

                    report = _call_quality_update_diagnostics()
                    snapshot = quality_snapshot()
                    memory_quality_payload = {
                        "available": True,
                        "updated": True,
                        "report": dict(report) if isinstance(report, dict) else {},
                        "state": dict(snapshot) if isinstance(snapshot, dict) else {},
                        "tuning": (snapshot.get("tuning", {}) if isinstance(snapshot, dict) else {}),
                        "error": None,
                    }
                    if isinstance(memory_quality_payload["report"], dict):
                        memory_quality_payload["report"].setdefault("tuning", dict(memory_quality_payload.get("tuning", {})))
                except Exception as exc:
                    state_payload: dict[str, Any] = {}
                    try:
                        snapshot = quality_snapshot()
                        if isinstance(snapshot, dict):
                            state_payload = dict(snapshot)
                    except Exception:
                        state_payload = {}
                    memory_quality_payload = {
                        "available": True,
                        "updated": False,
                        "report": {},
                        "state": state_payload,
                        "tuning": (state_payload.get("tuning", {}) if isinstance(state_payload, dict) else {}),
                        "error": {
                            "type": exc.__class__.__name__,
                            "message": str(exc),
                        },
                    }
                memory_quality_cache["fingerprint"] = fingerprint
                memory_quality_cache["payload"] = dict(memory_quality_payload)

        engine_payload["memory_quality"] = memory_quality_payload
        memory_integration_payload: dict[str, Any] = {"available": False}
        memory_integration_snapshot = getattr(memory_store, "integration_policies_snapshot", None)
        if callable(memory_integration_snapshot):
            try:
                try:
                    raw_memory_integration_payload = memory_integration_snapshot(session_id="")
                except TypeError:
                    raw_memory_integration_payload = memory_integration_snapshot()
            except Exception as exc:
                memory_integration_payload = {
                    "available": True,
                    "error": str(exc),
                }
            else:
                if isinstance(raw_memory_integration_payload, dict):
                    memory_integration_payload = dict(raw_memory_integration_payload)
                else:
                    memory_integration_payload = {
                        "available": True,
                        "error": "invalid_memory_integration_payload",
                    }
                memory_integration_payload.setdefault("available", True)
        engine_payload["memory_integration"] = memory_integration_payload
        if cfg.gateway.diagnostics.include_provider_telemetry:
            engine_payload["provider"] = _provider_telemetry_snapshot(runtime.engine.provider)
        monitor_payload: dict[str, Any]
        if runtime.memory_monitor is None:
            monitor_payload = {"enabled": False, "runner": dict(proactive_runner_state)}
        else:
            try:
                monitor_payload = dict(runtime.memory_monitor.telemetry())
            except Exception:
                monitor_payload = {}
            monitor_payload["enabled"] = True
            monitor_payload["runner"] = dict(proactive_runner_state)

        return DiagnosticsResponse(
            schema_version="2026-03-02",
            contract_version=GATEWAY_CONTRACT_VERSION,
            generated_at=generated_at,
            uptime_s=max(0, int(time.monotonic() - started_monotonic)),
            control_plane=_control_plane_payload(generated_at),
            queue=runtime.bus.stats(),
            channels=runtime.channels.status(),
            channels_delivery=runtime.channels.delivery_diagnostics(),
            cron=runtime.cron.status(),
            heartbeat=runtime.heartbeat.status(),
            autonomy_wake=runtime.autonomy_wake.status(),
            bootstrap=_bootstrap_status_snapshot(),
            memory_monitor=monitor_payload,
            memory_quality_tuning=dict(tuning_runner_state),
            engine=engine_payload,
            environment=environment,
            http=await http_telemetry.snapshot(),
            ws=await ws_telemetry.snapshot(),
        )

    @app.get("/v1/diagnostics", response_model=DiagnosticsResponse)
    async def diagnostics(request: Request) -> DiagnosticsResponse:
        return await _diagnostics_handler(request)

    @app.get("/api/diagnostics", response_model=DiagnosticsResponse)
    async def api_diagnostics(request: Request) -> DiagnosticsResponse:
        return await _diagnostics_handler(request)

    @app.post("/v1/control/heartbeat/trigger")
    async def trigger_heartbeat(request: Request) -> dict[str, Any]:
        auth_guard.check_http(request=request, scope="control", diagnostics_auth=cfg.gateway.diagnostics.require_auth)
        if not cfg.gateway.heartbeat.enabled:
            raise HTTPException(status_code=409, detail="heartbeat_disabled")
        decision = await runtime.heartbeat.trigger_now(_submit_heartbeat_wake)
        return {
            "ok": True,
            "decision": {
                "action": decision.action,
                "reason": decision.reason,
                "text": decision.text,
            },
        }

    async def _chat_handler(req: ChatRequest, request: Request) -> ChatResponse:
        auth_guard.check_http(request=request, scope="control", diagnostics_auth=cfg.gateway.diagnostics.require_auth)
        if not req.session_id.strip() or not req.text.strip():
            raise HTTPException(status_code=400, detail="session_id and text are required")
        logger.debug("chat request received session={} chars={}", req.session_id, len(req.text))
        try:
            out = await _run_engine_with_timeout(
                engine=runtime.engine,
                session_id=req.session_id,
                user_text=req.text,
                timeout_s=GATEWAY_CHAT_WS_ENGINE_TIMEOUT_S,
            )
        except RuntimeError as exc:
            status_code, detail = _provider_error_payload(exc)
            bind_event("gateway.chat", session=req.session_id).error("chat request failed status={} detail={}", status_code, detail)
            raise HTTPException(status_code=status_code, detail=detail)
        _finalize_bootstrap_for_user_turn(req.session_id)
        bind_event("gateway.chat", session=req.session_id).info("chat response generated model={}", out.model)
        return ChatResponse(text=out.text, model=out.model)

    @app.post("/v1/chat", response_model=ChatResponse)
    async def chat(req: ChatRequest, request: Request) -> ChatResponse:
        return await _chat_handler(req, request)

    @app.post("/api/message", response_model=ChatResponse)
    async def api_message(req: ChatRequest, request: Request) -> ChatResponse:
        return await _chat_handler(req, request)

    async def _tools_catalog_handler(request: Request) -> dict[str, Any]:
        auth_guard.check_http(request=request, scope="control", diagnostics_auth=cfg.gateway.diagnostics.require_auth)
        include_schema = parse_include_schema_flag(request.query_params)
        return build_tools_catalog_payload(runtime.engine.tools.schema(), include_schema=include_schema)

    @app.get("/v1/tools/catalog")
    async def tools_catalog(request: Request) -> dict[str, Any]:
        return await _tools_catalog_handler(request)

    @app.get("/api/tools/catalog")
    async def api_tools_catalog(request: Request) -> dict[str, Any]:
        return await _tools_catalog_handler(request)

    @app.get("/api/token")
    async def api_token(request: Request) -> dict[str, Any]:
        auth_guard.check_http(request=request, scope="control", diagnostics_auth=cfg.gateway.diagnostics.require_auth)
        return {
            "token_configured": bool(auth_guard.token),
            "token_masked": _mask_secret(auth_guard.token),
            "mode": auth_guard.mode,
            "header_name": auth_guard.header_name,
            "query_param": auth_guard.query_param,
        }

    async def _telegram_webhook(request: Request) -> dict[str, Any]:
        if not cfg.channels.telegram.enabled:
            raise HTTPException(status_code=409, detail="telegram_channel_disabled")

        channel = runtime.channels.get_channel("telegram")
        if channel is None:
            raise HTTPException(status_code=409, detail="telegram_channel_unavailable")

        if not bool(getattr(channel, "webhook_mode_active", False)):
            raise HTTPException(status_code=409, detail="telegram_webhook_mode_inactive")

        expected_secret = str(getattr(channel, "webhook_secret", "") or "").strip()
        if expected_secret:
            supplied_secret = str(request.headers.get("X-Telegram-Bot-Api-Secret-Token", "") or "")
            if not supplied_secret or not hmac.compare_digest(supplied_secret, expected_secret):
                raise HTTPException(status_code=401, detail="telegram_webhook_secret_invalid")

        try:
            raw_body = await asyncio.wait_for(request.body(), timeout=5.0)
        except asyncio.TimeoutError as exc:
            raise HTTPException(status_code=408, detail="telegram_webhook_payload_timeout") from exc
        if len(raw_body) > TELEGRAM_WEBHOOK_MAX_BODY_BYTES:
            raise HTTPException(status_code=413, detail="telegram_webhook_payload_too_large")
        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="telegram_webhook_payload_invalid") from exc
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="telegram_webhook_payload_invalid")

        handler = getattr(channel, "handle_webhook_update", None)
        if not callable(handler):
            raise HTTPException(status_code=409, detail="telegram_webhook_handler_unavailable")

        processed = bool(await handler(payload))
        if (not processed) and bool(getattr(cfg.channels.telegram, "webhook_fail_fast_on_error", False)):
            raise HTTPException(status_code=503, detail="telegram_webhook_processing_failed")
        return {"ok": True, "processed": processed}

    app.add_api_route(telegram_webhook_path, _telegram_webhook, methods=["POST"])

    @app.post("/v1/cron/add")
    async def cron_add(req: CronAddRequest, request: Request) -> dict[str, Any]:
        auth_guard.check_http(request=request, scope="control", diagnostics_auth=cfg.gateway.diagnostics.require_auth)
        job_id = await runtime.cron.add_job(
            session_id=req.session_id,
            expression=req.expression,
            prompt=req.prompt,
            name=req.name,
        )
        return {"ok": True, "status": "created", "id": job_id}

    @app.get("/v1/cron/list")
    async def cron_list(session_id: str, request: Request) -> dict[str, Any]:
        auth_guard.check_http(request=request, scope="control", diagnostics_auth=cfg.gateway.diagnostics.require_auth)
        return {"jobs": runtime.cron.list_jobs(session_id=session_id)}

    @app.delete("/v1/cron/{job_id}")
    async def cron_remove(job_id: str, request: Request) -> dict[str, Any]:
        auth_guard.check_http(request=request, scope="control", diagnostics_auth=cfg.gateway.diagnostics.require_auth)
        removed = await asyncio.to_thread(runtime.cron.remove_job, job_id)
        return {"ok": removed, "status": "removed" if removed else "not_found"}

    async def _ws_chat(socket: WebSocket, *, path_label: str) -> None:
        def _ws_envelope_error(*, error: str, status_code: int, request_id: str | None = None) -> dict[str, Any]:
            payload: dict[str, Any] = {
                "type": "error",
                "error": str(error or "invalid_request"),
                "status_code": int(status_code),
            }
            if request_id:
                payload["request_id"] = request_id
            return payload

        def _ws_req_error(
            *,
            request_id: str | int | None,
            code: str,
            message: str,
            status_code: int,
        ) -> dict[str, Any]:
            return {
                "type": "res",
                "id": request_id,
                "ok": False,
                "error": {
                    "code": str(code or "invalid_request"),
                    "message": str(message or "invalid_request"),
                    "status_code": int(status_code),
                },
            }

        def _coerce_req_id(value: Any) -> str | int | None:
            if isinstance(value, bool):
                return None
            if isinstance(value, (str, int)):
                return value
            return None

        def _coerce_req_payload(payload: dict[str, Any]) -> tuple[str | int | None, str, dict[str, Any] | None]:
            request_id = _coerce_req_id(payload.get("id"))
            method = str(payload.get("method", "") or "").strip()
            params = payload.get("params")
            if params is None:
                params = {}
            if not isinstance(params, dict):
                return request_id, method, None
            return request_id, method, params

        async def _ws_req_chat_send(
            *,
            request_id: str | int | None,
            params: dict[str, Any],
        ) -> dict[str, Any]:
            session_id = str(params.get("session_id") or params.get("sessionId") or "").strip()
            text = str(params.get("text") or "").strip()
            if not session_id or not text:
                return _ws_req_error(
                    request_id=request_id,
                    code="invalid_request",
                    message="session_id/sessionId and text are required",
                    status_code=400,
                )
            try:
                out = await _run_engine_with_timeout(
                    engine=runtime.engine,
                    session_id=session_id,
                    user_text=text,
                    timeout_s=GATEWAY_CHAT_WS_ENGINE_TIMEOUT_S,
                )
            except RuntimeError as exc:
                status_code, detail = _provider_error_payload(exc)
                bind_event("gateway.ws", session=session_id, channel="ws").error(
                    "websocket request failed status={} detail={}",
                    status_code,
                    detail,
                )
                return _ws_req_error(
                    request_id=request_id,
                    code=detail,
                    message=detail,
                    status_code=status_code,
                )

            _finalize_bootstrap_for_user_turn(session_id)
            return {
                "type": "res",
                "id": request_id,
                "ok": True,
                "result": {
                    "session_id": session_id,
                    "text": out.text,
                    "model": out.model,
                },
            }

        if not await auth_guard.check_ws(socket=socket, scope="control", diagnostics_auth=cfg.gateway.diagnostics.require_auth):
            return
        await socket.accept()
        await ws_telemetry.connection_opened(path=path_label)

        async def _send_ws(payload: Any) -> None:
            await socket.send_json(payload)
            await ws_telemetry.frame_outbound(payload=payload)

        await _send_ws(
            {
                "type": "event",
                "event": "connect.challenge",
                "params": {
                    "nonce": uuid.uuid4().hex,
                    "issued_at": _utc_now_iso(),
                },
            }
        )
        bind_event("gateway.ws", channel="ws").info("websocket client connected path={}", path_label)
        req_connected = False
        try:
            while True:
                payload = await socket.receive_json()
                await ws_telemetry.frame_inbound(path=path_label, payload=payload)
                if not isinstance(payload, dict):
                    await _send_ws({"error": "session_id and text are required"})
                    continue

                message_type = str(payload.get("type", "") or "").strip().lower()
                if message_type:
                    if message_type == "req":
                        request_id, method, params = _coerce_req_payload(payload)
                        if request_id is None or not method or params is None:
                            await _send_ws(
                                _ws_req_error(
                                    request_id=request_id,
                                    code="invalid_request",
                                    message="req frames require string|number id, string method, and object params",
                                    status_code=400,
                                )
                            )
                            continue

                        normalized_method = method.lower()
                        if normalized_method == "connect":
                            req_connected = True
                            await _send_ws(
                                {
                                    "type": "res",
                                    "id": request_id,
                                    "ok": True,
                                    "result": {
                                        "connected": req_connected,
                                        "contract_version": GATEWAY_CONTRACT_VERSION,
                                        "server_time": _utc_now_iso(),
                                    },
                                }
                            )
                            continue
                        if not req_connected:
                            await _send_ws(
                                _ws_req_error(
                                    request_id=request_id,
                                    code="not_connected",
                                    message="connect handshake required",
                                    status_code=409,
                                )
                            )
                            continue
                        if normalized_method == "ping":
                            await _send_ws(
                                {
                                    "type": "res",
                                    "id": request_id,
                                    "ok": True,
                                    "result": {
                                        "server_time": _utc_now_iso(),
                                    },
                                }
                            )
                            continue
                        if normalized_method == "health":
                            await _send_ws(
                                {
                                    "type": "res",
                                    "id": request_id,
                                    "ok": True,
                                    "result": {
                                        "ok": True,
                                        "ready": lifecycle.ready,
                                        "phase": lifecycle.phase,
                                        "channels": runtime.channels.status(),
                                        "queue": runtime.bus.stats(),
                                    },
                                }
                            )
                            continue
                        if normalized_method == "status":
                            status_payload = _control_plane_payload().dict()
                            await _send_ws(
                                {
                                    "type": "res",
                                    "id": request_id,
                                    "ok": True,
                                    "result": status_payload,
                                }
                            )
                            continue
                        if normalized_method == "tools.catalog":
                            include_schema = parse_include_schema_flag(params)
                            await _send_ws(
                                {
                                    "type": "res",
                                    "id": request_id,
                                    "ok": True,
                                    "result": build_tools_catalog_payload(
                                        runtime.engine.tools.schema(),
                                        include_schema=include_schema,
                                    ),
                                }
                            )
                            continue
                        if normalized_method in {"chat.send", "message.send"}:
                            await _send_ws(
                                await _ws_req_chat_send(request_id=request_id, params=params)
                            )
                            continue

                        await _send_ws(
                            _ws_req_error(
                                request_id=request_id,
                                code="unsupported_method",
                                message=f"unsupported req method: {method}",
                                status_code=400,
                            )
                        )
                        continue

                    request_id = str(payload.get("request_id", "") or "").strip() or None
                    if message_type == "hello":
                        await _send_ws(
                            {
                                "type": "ready",
                                "contract_version": GATEWAY_CONTRACT_VERSION,
                                "server_time": _utc_now_iso(),
                            }
                        )
                        continue
                    if message_type == "ping":
                        await _send_ws({"type": "pong", "server_time": _utc_now_iso()})
                        continue
                    if message_type != "message":
                        await _send_ws(
                            _ws_envelope_error(
                                error="unsupported_message_type",
                                status_code=400,
                                request_id=request_id,
                            )
                        )
                        continue

                    session_id = str(payload.get("session_id", "") or "").strip()
                    text = str(payload.get("text", "") or "").strip()
                    if not session_id or not text:
                        await _send_ws(
                            _ws_envelope_error(
                                error="session_id and text are required",
                                status_code=400,
                                request_id=request_id,
                            )
                        )
                        continue

                    try:
                        out = await _run_engine_with_timeout(
                            engine=runtime.engine,
                            session_id=session_id,
                            user_text=text,
                            timeout_s=GATEWAY_CHAT_WS_ENGINE_TIMEOUT_S,
                        )
                    except RuntimeError as exc:
                        status_code, detail = _provider_error_payload(exc)
                        bind_event("gateway.ws", session=session_id, channel="ws").error(
                            "websocket request failed status={} detail={}",
                            status_code,
                            detail,
                        )
                        await _send_ws(
                            _ws_envelope_error(error=detail, status_code=status_code, request_id=request_id)
                        )
                        continue

                    _finalize_bootstrap_for_user_turn(session_id)
                    response_payload: dict[str, Any] = {
                        "type": "message_result",
                        "session_id": session_id,
                        "text": out.text,
                        "model": out.model,
                    }
                    if request_id:
                        response_payload["request_id"] = request_id
                    await _send_ws(response_payload)
                    bind_event("gateway.ws", session=session_id, channel="ws").debug(
                        "websocket response sent model={}",
                        out.model,
                    )
                    continue

                session_id = str(payload.get("session_id", "")).strip()
                text = str(payload.get("text", "")).strip()
                if not session_id or not text:
                    await _send_ws({"error": "session_id and text are required"})
                    continue
                try:
                    out = await _run_engine_with_timeout(
                        engine=runtime.engine,
                        session_id=session_id,
                        user_text=text,
                        timeout_s=GATEWAY_CHAT_WS_ENGINE_TIMEOUT_S,
                    )
                except RuntimeError as exc:
                    status_code, detail = _provider_error_payload(exc)
                    bind_event("gateway.ws", session=session_id, channel="ws").error("websocket request failed status={} detail={}", status_code, detail)
                    await _send_ws({"error": detail, "status_code": status_code})
                    continue
                _finalize_bootstrap_for_user_turn(session_id)
                await _send_ws({"text": out.text, "model": out.model})
                bind_event("gateway.ws", session=session_id, channel="ws").debug("websocket response sent model={}", out.model)
        except WebSocketDisconnect:
            bind_event("gateway.ws", channel="ws").info("websocket client disconnected path={}", path_label)
        finally:
            await ws_telemetry.connection_closed()

    @app.websocket("/v1/ws")
    async def ws_chat(socket: WebSocket) -> None:
        await _ws_chat(socket, path_label="/v1/ws")

    @app.websocket("/ws")
    async def ws_chat_alias(socket: WebSocket) -> None:
        await _ws_chat(socket, path_label="/ws")

    @app.get("/", response_class=HTMLResponse)
    async def root() -> HTMLResponse:
        return HTMLResponse(content=ROOT_ENTRYPOINT_HTML, status_code=200)

    return app


def run_gateway(host: str | None = None, port: int | None = None) -> None:
    cfg = load_config()
    app = create_app(cfg)
    resolved_host = host or cfg.gateway.host
    resolved_port = port or int(cfg.gateway.port)
    bind_event("gateway.lifecycle").info("running gateway host={} port={}", resolved_host, resolved_port)
    uvicorn.run(
        app,
        host=resolved_host,
        port=resolved_port,
        access_log=False,
        log_level="warning",
    )


class _LazyGatewayApp:
    def __init__(self, factory: Callable[[], FastAPI]) -> None:
        self._factory = factory
        self._app: FastAPI | None = None

    def _get(self) -> FastAPI:
        if self._app is None:
            self._app = self._factory()
        return self._app

    async def __call__(self, scope, receive, send) -> None:
        await self._get()(scope, receive, send)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._get(), name)


app = _LazyGatewayApp(create_app)


if __name__ == "__main__":
    run_gateway()
