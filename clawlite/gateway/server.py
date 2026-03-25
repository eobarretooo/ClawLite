from __future__ import annotations

import asyncio
import datetime as dt
import hmac
import json
import math
import time
import uuid
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import uvicorn
from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from clawlite.bus.queue import MessageQueue
from clawlite.config.loader import load_config
from clawlite.config.schema import AppConfig
from clawlite.core.engine import AgentEngine
from clawlite.core.memory_monitor import MemoryMonitor, MemorySuggestion
from clawlite.providers import detect_provider_name
from clawlite.providers.catalog import default_provider_model, provider_profile
from clawlite.providers.reliability import is_quota_429_error
from clawlite.scheduler.heartbeat import HeartbeatDecision
from clawlite.runtime import (
    AutonomyLog,
    AutonomyService,
    AutonomyWakeCoordinator,
    RuntimeSupervisor,
    SupervisorComponentPolicy,
    SupervisorIncident,
)
from clawlite.gateway.control_handlers import GatewayControlHandlers
from clawlite.gateway.status_handlers import GatewayStatusHandlers
from clawlite.gateway.request_handlers import GatewayRequestHandlers
from clawlite.gateway.rate_limit import GatewayRateLimiter
from clawlite.gateway.autonomy_notice import (
    default_heartbeat_route as _default_heartbeat_route_helper,
    latest_memory_route as _latest_memory_route_helper,
    latest_route_from_history_tail as _latest_route_from_history_tail_helper,
    send_autonomy_notice as _send_autonomy_notice_helper,
)
from clawlite.gateway.background_runners import (
    run_proactive_monitor_loop as _run_proactive_monitor_loop_helper,
    run_self_evolution_loop as _run_self_evolution_loop_helper,
)
from clawlite.gateway.control_plane import (
    build_control_plane_payload as _build_control_plane_payload,
    control_plane_auth_payload as _control_plane_auth_payload,
    parse_iso_timestamp as _parse_iso_timestamp,
    reasoning_layer_metrics_from_payload as _reasoning_layer_metrics_from_payload_helper,
    semantic_metrics_from_payload as _semantic_metrics_from_payload_helper,
    utc_now_iso as _utc_now_iso_helper,
)
from clawlite.gateway.tuning_policy import (
    normalize_reasoning_layer as _normalize_reasoning_layer_helper,
    normalize_tuning_severity as _normalize_tuning_severity_helper,
    resolve_tuning_backfill_limit as _resolve_tuning_backfill_limit_helper,
    resolve_tuning_layer as _resolve_tuning_layer_helper,
    resolve_tuning_notify_variant as _resolve_tuning_notify_variant_helper,
    resolve_tuning_snapshot_tag as _resolve_tuning_snapshot_tag_helper,
    select_tuning_action_playbook as _select_tuning_action_playbook_helper,
)
from clawlite.gateway.tuning_decisions import (
    plan_tuning_action as _plan_tuning_action_helper,
)
from clawlite.gateway.tuning_runtime import (
    build_tuning_action_entry as _build_tuning_action_entry_helper,
    build_tuning_patch as _build_tuning_patch_helper,
    record_tuning_runner_action as _record_tuning_runner_action_helper,
)
from clawlite.gateway.runtime_state import (
    build_cron_wake_state as _build_cron_wake_state,
    build_memory_quality_cache as _build_memory_quality_cache,
    build_proactive_runner_state as _build_proactive_runner_state,
    build_self_evolution_runner_state as _build_self_evolution_runner_state,
    build_subagent_maintenance_state as _build_subagent_maintenance_state,
    build_tuning_runner_state as _build_tuning_runner_state,
    build_wake_pressure_state as _build_wake_pressure_state,
)
from clawlite.gateway.supervisor_runtime import (
    collect_supervisor_incidents as _collect_supervisor_incidents_helper,
)
from clawlite.gateway.supervisor_recovery import (
    handle_supervisor_incident as _handle_supervisor_incident_helper,
    recover_supervised_component as _recover_supervised_component_helper,
)
from clawlite.gateway.subagents_runtime import (
    resume_recoverable_subagents as _resume_recoverable_subagents_helper,
    run_subagent_maintenance_loop as _run_subagent_maintenance_loop_helper,
)
from clawlite.gateway.tuning_loop import (
    run_memory_quality_tuning_tick as _run_memory_quality_tuning_tick_helper,
)
from clawlite.gateway.tool_catalog import build_tools_catalog_payload, parse_include_schema_flag
from clawlite.gateway.dashboard_state import (
    dashboard_channels_summary as _dashboard_channels_summary_payload,
    dashboard_cron_summary as _dashboard_cron_summary_payload,
    dashboard_state_payload as _dashboard_state_payload_builder,
    dashboard_self_evolution_summary as _dashboard_self_evolution_summary_payload,
    operator_channel_summary as _operator_channel_summary,
    recent_dashboard_sessions as _recent_dashboard_sessions_payload,
)
from clawlite.gateway.dashboard_runtime import (
    dashboard_state_payload as _dashboard_state_payload_runtime,
)
from clawlite.gateway.dashboard_sessions import (
    DEFAULT_DASHBOARD_CLIENT_HEADER_NAME,
    DEFAULT_DASHBOARD_CLIENT_QUERY_PARAM,
    DEFAULT_DASHBOARD_HANDOFF_HEADER_NAME,
    DEFAULT_DASHBOARD_HANDOFF_QUERY_PARAM,
    DEFAULT_DASHBOARD_SESSION_HEADER_NAME,
    DEFAULT_DASHBOARD_SESSION_QUERY_PARAM,
    DashboardHandoffRegistry,
    DashboardSessionRegistry,
    dashboard_session_expiry_iso,
    verify_dashboard_handoff,
)
from clawlite.gateway.diagnostics_payload import (
    diagnostics_payload as _diagnostics_payload_builder,
)
from clawlite.gateway.engine_diagnostics import (
    engine_memory_integration_payload as _engine_memory_integration_payload,
    engine_memory_payloads as _engine_memory_payloads,
    engine_memory_quality_payload as _engine_memory_quality_payload,
    memory_monitor_payload as _memory_monitor_payload,
)
from clawlite.gateway.lifecycle_runtime import (
    start_subsystems as _start_subsystems_helper,
    stop_subsystems as _stop_subsystems_helper,
)
from clawlite.gateway.memory_dashboard import (
    dashboard_memory_summary as _dashboard_memory_summary_payload,
)
from clawlite.gateway.payloads import (
    autonomy_provider_suppression_hint as _autonomy_provider_suppression_hint,
    control_plane_to_dict as _control_plane_to_dict,
    dashboard_asset_text as _dashboard_asset_text,
    mask_secret as _mask_secret,
    provider_autonomy_snapshot as _provider_autonomy_snapshot,
    provider_telemetry_snapshot as _provider_telemetry_snapshot,
    render_root_dashboard_html as _render_root_dashboard_html,
)
from clawlite.gateway.runtime_builder import RuntimeContainer, _provider_config, build_runtime
from clawlite.gateway.webhooks import GatewayWebhookHandlers
from clawlite.gateway.websocket_handlers import GatewayWebSocketHandlers
from clawlite.cli.onboarding import build_dashboard_handoff
from clawlite.cli.ops import (
    memory_doctor_snapshot,
    memory_profile_snapshot,
    memory_quality_snapshot,
    memory_snapshot_create,
    memory_snapshot_rollback,
    memory_suggest_snapshot,
    memory_version_snapshot,
)
from clawlite.utils.logging import bind_event, setup_logging


GATEWAY_CONTRACT_VERSION = "2026-03-04"
TELEGRAM_WEBHOOK_MAX_BODY_BYTES = 1024 * 1024
WHATSAPP_WEBHOOK_MAX_BODY_BYTES = 1024 * 1024
GATEWAY_CHAT_WS_ENGINE_TIMEOUT_S = 300.0
GATEWAY_CRON_ENGINE_TIMEOUT_S = 90.0
GATEWAY_HEARTBEAT_ENGINE_TIMEOUT_S = 120.0
GATEWAY_BOOTSTRAP_ENGINE_TIMEOUT_S = 120.0
LATEST_MEMORY_ROUTE_CACHE_TTL_S = 5.0
LATEST_MEMORY_ROUTE_TAIL_BYTES = 32 * 1024
_DASHBOARD_ASSET_ROOT = "/_clawlite"
_DASHBOARD_BOOTSTRAP_TOKEN = "__CLAWLITE_DASHBOARD_BOOTSTRAP_JSON__"
_REQUEST_ID_HEADER_NAME = "X-Request-ID"
_MAX_REQUEST_ID_LEN = 128


def _normalize_request_id(raw: Any) -> str:
    value = str(raw or "").strip()
    if not value or len(value) > _MAX_REQUEST_ID_LEN:
        return f"req-{uuid.uuid4().hex}"
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")
    if any(char not in allowed for char in value):
        return f"req-{uuid.uuid4().hex}"
    return value


def _request_id_from_request(request: Request) -> str:
    state = getattr(request, "state", None)
    raw = getattr(state, "request_id", "") if state is not None else ""
    return _normalize_request_id(raw)

def _normalize_reasoning_layer(layer: str) -> str:
    return _normalize_reasoning_layer_helper(layer)


def _select_tuning_action_playbook(*, severity: str, weakest_layer: str) -> tuple[str, str]:
    return _select_tuning_action_playbook_helper(severity=severity, weakest_layer=weakest_layer)


def _normalize_tuning_severity(value: str) -> str:
    return _normalize_tuning_severity_helper(value)


def _resolve_tuning_layer(value: str) -> str:
    return _resolve_tuning_layer_helper(value)


def _resolve_tuning_backfill_limit(*, layer: str, severity: str, missing_records: int) -> int:
    return _resolve_tuning_backfill_limit_helper(layer=layer, severity=severity, missing_records=missing_records)


def _resolve_tuning_snapshot_tag(*, layer: str, severity: str) -> str:
    return _resolve_tuning_snapshot_tag_helper(layer=layer, severity=severity)


def _resolve_tuning_notify_variant(*, layer: str, severity: str) -> tuple[str, str]:
    return _resolve_tuning_notify_variant_helper(layer=layer, severity=severity)


def _normalize_webhook_path(value: str, *, default: str = "/api/webhooks/telegram") -> str:
    raw = str(value or "").strip() or default
    return raw if raw.startswith("/") else f"/{raw}"


class ChatRequest(BaseModel):
    session_id: str
    text: str
    channel: str = ""
    chat_id: str | None = None
    runtime_metadata: dict[str, Any] | None = None


class ChatResponse(BaseModel):
    text: str
    model: str


class CronAddRequest(BaseModel):
    session_id: str
    expression: str
    prompt: str
    name: str = ""


class CronToggleRequest(BaseModel):
    session_id: str = ""


class ChannelReplayRequest(BaseModel):
    limit: int = 25
    channel: str = ""
    reason: str = ""
    session_id: str = ""
    reasons: list[str] = Field(default_factory=list)


class ChannelRecoverRequest(BaseModel):
    channel: str = ""
    force: bool = True


class ChannelInboundReplayRequest(BaseModel):
    limit: int = 100
    channel: str = ""
    session_id: str = ""
    force: bool = False


class TelegramRefreshRequest(BaseModel):
    noop: bool = False


class TelegramPairingApproveRequest(BaseModel):
    code: str = ""


class TelegramOffsetCommitRequest(BaseModel):
    update_id: int = 0


class TelegramOffsetSyncRequest(BaseModel):
    next_offset: int = 0
    allow_reset: bool = False


class TelegramOffsetResetRequest(BaseModel):
    confirm: bool = False


class TelegramPairingRejectRequest(BaseModel):
    code: str = ""


class TelegramPairingRevokeRequest(BaseModel):
    entry: str = ""


class SupervisorRecoverRequest(BaseModel):
    component: str = ""
    force: bool = True
    reason: str = "operator_recover"


class ProviderRecoverRequest(BaseModel):
    role: str = ""
    model: str = ""


class AutonomyWakeRequest(BaseModel):
    kind: str = "proactive"


class MemorySuggestRefreshRequest(BaseModel):
    noop: bool = False


class MemoryDoctorRequest(BaseModel):
    noop: bool = False


class MemoryQualityRequest(BaseModel):
    noop: bool = False


class SkillsRefreshRequest(BaseModel):
    force: bool = True


class SkillsSyncRequest(BaseModel):
    noop: bool = False


class SkillsDoctorRequest(BaseModel):
    include_all: bool = False
    status: str = ""
    source: str = ""
    query: str = ""


class SkillsValidateRequest(BaseModel):
    force: bool = True
    include_all: bool = False
    status: str = ""
    source: str = ""
    query: str = ""


class MemorySnapshotCreateRequest(BaseModel):
    tag: str = ""


class MemorySnapshotRollbackRequest(BaseModel):
    version_id: str = ""
    confirm: bool = False


class DiscordRefreshRequest(BaseModel):
    noop: bool = False


class ToolApprovalReviewRequest(BaseModel):
    actor: str = ""
    note: str = ""


class ToolGrantRevokeRequest(BaseModel):
    session_id: str = ""
    channel: str = ""
    rule: str = ""


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
    channels_dispatcher: dict[str, Any] = {}
    channels_delivery: dict[str, Any] = {}
    channels_inbound: dict[str, Any] = {}
    channels_recovery: dict[str, Any] = {}
    cron: dict[str, Any]
    heartbeat: dict[str, Any]
    autonomy: dict[str, Any] = {}
    supervisor: dict[str, Any] = {}
    autonomy_wake: dict[str, Any] = {}
    autonomy_log: dict[str, Any] = {}
    subagents: dict[str, Any] = {}
    bootstrap: dict[str, Any]
    workspace: dict[str, Any] = {}
    memory_monitor: dict[str, Any] = {}
    memory_quality_tuning: dict[str, Any] = {}
    engine: dict[str, Any] = {}
    environment: dict[str, Any] = {}
    http: dict[str, Any] = {}
    ws: dict[str, Any] = {}
    self_evolution: dict[str, Any] = {}


@dataclass(slots=True)
class HttpRequestTelemetry:
    total_requests: int = 0
    in_flight: int = 0
    by_method: dict[str, int] = field(default_factory=dict)
    by_path: dict[str, int] = field(default_factory=dict)
    by_status: dict[str, int] = field(default_factory=dict)
    last_request_id: str = ""
    last_request_method: str = ""
    last_request_path: str = ""
    last_request_started_at: str = ""
    last_error_request_id: str = ""
    last_error_method: str = ""
    last_error_path: str = ""
    last_error_at: str = ""
    last_error_status: int | None = None
    last_error_code: str = ""
    last_error_message: str = ""
    latency_count: int = 0
    latency_sum_ms: float = 0.0
    latency_min_ms: float = 0.0
    latency_max_ms: float = 0.0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @staticmethod
    def _utc_now_iso() -> str:
        return dt.datetime.now(dt.timezone.utc).isoformat()

    async def start(self, *, method: str, path: str, request_id: str = "") -> None:
        normalized_method = (method or "UNKNOWN").upper()
        normalized_path = str(path or "") or "/"
        normalized_request_id = str(request_id or "").strip()
        async with self.lock:
            self.total_requests += 1
            self.in_flight += 1
            self.by_method[normalized_method] = self.by_method.get(normalized_method, 0) + 1
            self.by_path[normalized_path] = self.by_path.get(normalized_path, 0) + 1
            self.last_request_id = normalized_request_id
            self.last_request_method = normalized_method
            self.last_request_path = normalized_path
            self.last_request_started_at = self._utc_now_iso()

    async def finish(self, *, status_code: int, latency_ms: float, request_id: str = "", method: str = "", path: str = "") -> None:
        normalized_status = str(int(status_code) if status_code else 500)
        elapsed_ms = max(0.0, float(latency_ms))
        normalized_request_id = str(request_id or "").strip()
        normalized_method = (method or "UNKNOWN").upper()
        normalized_path = str(path or "") or "/"
        numeric_status = int(status_code) if status_code else 500
        async with self.lock:
            self.in_flight = max(0, self.in_flight - 1)
            self.by_status[normalized_status] = self.by_status.get(normalized_status, 0) + 1
            if numeric_status >= 400 and not (
                self.last_error_request_id == normalized_request_id and self.last_error_status == numeric_status
            ):
                self.last_error_request_id = normalized_request_id
                self.last_error_method = normalized_method
                self.last_error_path = normalized_path
                self.last_error_at = self._utc_now_iso()
                self.last_error_status = numeric_status
                self.last_error_code = f"http_{numeric_status}"
                self.last_error_message = ""
            self.latency_count += 1
            self.latency_sum_ms += elapsed_ms
            if self.latency_count == 1:
                self.latency_min_ms = elapsed_ms
                self.latency_max_ms = elapsed_ms
            else:
                self.latency_min_ms = min(self.latency_min_ms, elapsed_ms)
                self.latency_max_ms = max(self.latency_max_ms, elapsed_ms)

    async def record_error(
        self,
        *,
        request_id: str,
        method: str,
        path: str,
        status_code: int,
        code: str = "",
        message: str = "",
    ) -> None:
        normalized_request_id = str(request_id or "").strip()
        normalized_method = (method or "UNKNOWN").upper()
        normalized_path = str(path or "") or "/"
        numeric_status = int(status_code) if status_code else 500
        normalized_code = str(code or "").strip() or f"http_{numeric_status}"
        normalized_message = str(message or "").strip()
        async with self.lock:
            self.last_error_request_id = normalized_request_id
            self.last_error_method = normalized_method
            self.last_error_path = normalized_path
            self.last_error_at = self._utc_now_iso()
            self.last_error_status = numeric_status
            self.last_error_code = normalized_code
            self.last_error_message = normalized_message

    async def snapshot(self) -> dict[str, Any]:
        async with self.lock:
            avg_ms = (self.latency_sum_ms / self.latency_count) if self.latency_count else 0.0
            return {
                "total_requests": self.total_requests,
                "in_flight": self.in_flight,
                "by_method": dict(self.by_method),
                "by_path": dict(self.by_path),
                "by_status": dict(self.by_status),
                "last_request_id": self.last_request_id,
                "last_request_method": self.last_request_method,
                "last_request_path": self.last_request_path,
                "last_request_started_at": self.last_request_started_at,
                "last_error_request_id": self.last_error_request_id,
                "last_error_method": self.last_error_method,
                "last_error_path": self.last_error_path,
                "last_error_at": self.last_error_at,
                "last_error_status": self.last_error_status,
                "last_error_code": self.last_error_code,
                "last_error_message": self.last_error_message,
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
    last_connection_id: str = ""
    last_connection_path: str = ""
    last_connection_opened_at: str = ""
    last_connection_closed_id: str = ""
    last_connection_closed_at: str = ""
    last_request_id: str = ""
    last_error_connection_id: str = ""
    last_error_request_id: str = ""
    last_error_at: str = ""
    last_error_code: str = ""
    last_error_message: str = ""
    last_error_status: int | None = None
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

    @staticmethod
    def _error_message(payload: Any) -> str:
        if not isinstance(payload, dict):
            return ""
        payload_type = str(payload.get("type", "") or "").strip().lower()
        if payload_type == "res" and payload.get("ok") is False:
            error = payload.get("error")
            if isinstance(error, dict):
                return str(error.get("message", "") or "").strip()
            return str(payload.get("error", "") or "").strip()
        if payload_type == "error" or ("error" in payload and not payload_type):
            return str(payload.get("error", "") or "").strip()
        return ""

    @staticmethod
    def _error_status(payload: Any) -> int | None:
        if not isinstance(payload, dict):
            return None
        payload_type = str(payload.get("type", "") or "").strip().lower()
        status_code: Any = None
        if payload_type == "res" and payload.get("ok") is False:
            error = payload.get("error")
            if isinstance(error, dict):
                status_code = error.get("status_code")
        elif payload_type == "error" or ("error" in payload and not payload_type):
            status_code = payload.get("status_code")
        if status_code is None:
            return None
        try:
            return int(status_code)
        except Exception:
            return None

    @staticmethod
    def _utc_now_iso() -> str:
        return dt.datetime.now(dt.timezone.utc).isoformat()

    @staticmethod
    def _request_id(payload: Any) -> str:
        if not isinstance(payload, dict):
            return ""
        payload_type = str(payload.get("type", "") or "").strip().lower()
        if payload_type in {"req", "res"}:
            value = payload.get("id")
            if isinstance(value, (str, int)) and not isinstance(value, bool):
                return str(value).strip()
            return ""
        value = payload.get("request_id")
        if isinstance(value, (str, int)) and not isinstance(value, bool):
            return str(value).strip()
        return ""

    async def connection_opened(self, *, path: str, connection_id: str) -> None:
        normalized_path = str(path or "") or "/"
        async with self.lock:
            self.connections_opened += 1
            self.active_connections += 1
            self.by_path[normalized_path] = self.by_path.get(normalized_path, 0) + 1
            self.last_connection_id = str(connection_id or "").strip()
            self.last_connection_path = normalized_path
            self.last_connection_opened_at = self._utc_now_iso()

    async def connection_closed(self, *, connection_id: str) -> None:
        async with self.lock:
            self.connections_closed += 1
            self.active_connections = max(0, self.active_connections - 1)
            self.last_connection_closed_id = str(connection_id or "").strip()
            self.last_connection_closed_at = self._utc_now_iso()

    async def frame_inbound(self, *, path: str, payload: Any) -> None:
        normalized_path = str(path or "") or "/"
        message_type = self._message_type(payload)
        request_id = self._request_id(payload)
        async with self.lock:
            self.frames_in += 1
            self.by_message_type_in[message_type] = self.by_message_type_in.get(message_type, 0) + 1
            self.by_path.setdefault(normalized_path, self.by_path.get(normalized_path, 0))
            if request_id:
                self.last_request_id = request_id
            if isinstance(payload, dict) and message_type == "req":
                method = str(payload.get("method", "") or "").strip().lower()
                if method:
                    self.req_methods[method] = self.req_methods.get(method, 0) + 1

    async def frame_outbound(self, *, payload: Any, connection_id: str = "") -> None:
        message_type = self._message_type(payload)
        error_code = self._error_code(payload)
        error_message = self._error_message(payload)
        error_status = self._error_status(payload)
        request_id = self._request_id(payload)
        async with self.lock:
            self.frames_out += 1
            self.by_message_type_out[message_type] = self.by_message_type_out.get(message_type, 0) + 1
            if error_code:
                self.error_codes[error_code] = self.error_codes.get(error_code, 0) + 1
                self.last_error_connection_id = str(connection_id or "").strip()
                self.last_error_request_id = request_id
                self.last_error_at = self._utc_now_iso()
                self.last_error_code = error_code
                self.last_error_message = error_message
                self.last_error_status = error_status

    async def snapshot(self) -> dict[str, Any]:
        async with self.lock:
            return self.snapshot_nowait()

    def snapshot_nowait(self) -> dict[str, Any]:
        return {
            "connections_opened": self.connections_opened,
            "connections_closed": self.connections_closed,
            "active_connections": self.active_connections,
            "frames_in": self.frames_in,
            "frames_out": self.frames_out,
            "last_connection_id": self.last_connection_id,
            "last_connection_path": self.last_connection_path,
            "last_connection_opened_at": self.last_connection_opened_at,
            "last_connection_closed_id": self.last_connection_closed_id,
            "last_connection_closed_at": self.last_connection_closed_at,
            "last_request_id": self.last_request_id,
            "last_error_connection_id": self.last_error_connection_id,
            "last_error_request_id": self.last_error_request_id,
            "last_error_at": self.last_error_at,
            "last_error_code": self.last_error_code,
            "last_error_message": self.last_error_message,
            "last_error_status": self.last_error_status,
            "by_path": dict(self.by_path),
            "by_message_type_in": dict(self.by_message_type_in),
            "by_message_type_out": dict(self.by_message_type_out),
            "req_methods": dict(self.req_methods),
            "error_codes": dict(self.error_codes),
        }


async def _run_engine_with_timeout(
    *,
    engine: AgentEngine,
    session_id: str,
    user_text: str,
    timeout_s: float,
    channel: str | None = None,
    chat_id: str | None = None,
    runtime_metadata: dict[str, Any] | None = None,
) -> Any:
    run_kwargs: dict[str, Any] = {
        "session_id": session_id,
        "user_text": user_text,
    }
    if str(channel or "").strip():
        run_kwargs["channel"] = str(channel).strip()
    if str(chat_id or "").strip():
        run_kwargs["chat_id"] = str(chat_id).strip()
    if isinstance(runtime_metadata, dict) and runtime_metadata:
        run_kwargs["runtime_metadata"] = dict(runtime_metadata)
    try:
        return await asyncio.wait_for(
            engine.run(**run_kwargs),
            timeout=max(0.001, float(timeout_s)),
        )
    except (asyncio.TimeoutError, TimeoutError) as exc:
        raise RuntimeError("engine_run_timeout") from exc


async def _stream_engine_with_timeout(
    *,
    engine: AgentEngine,
    session_id: str,
    user_text: str,
    timeout_s: float,
    channel: str | None = None,
    chat_id: str | None = None,
    runtime_metadata: dict[str, Any] | None = None,
):
    stream_kwargs: dict[str, Any] = {
        "session_id": session_id,
        "user_text": user_text,
    }
    if str(channel or "").strip():
        stream_kwargs["channel"] = str(channel).strip()
    if str(chat_id or "").strip():
        stream_kwargs["chat_id"] = str(chat_id).strip()
    if isinstance(runtime_metadata, dict) and runtime_metadata:
        stream_kwargs["runtime_metadata"] = dict(runtime_metadata)
    stream = engine.stream_run(**stream_kwargs)
    deadline = time.monotonic() + max(0.001, float(timeout_s))
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError("engine_run_timeout")
            try:
                chunk = await asyncio.wait_for(anext(stream), timeout=remaining)
            except StopAsyncIteration:
                break
            except (asyncio.TimeoutError, TimeoutError) as exc:
                raise RuntimeError("engine_run_timeout") from exc
            yield chunk
    finally:
        close_fn = getattr(stream, "aclose", None)
        if callable(close_fn):
            await close_fn()


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
class GatewayLifecycleState:
    phase: str = "created"
    ready: bool = False
    startup_error: str = ""
    components: dict[str, dict[str, Any]] | None = None

    def __post_init__(self) -> None:
        if self.components is None:
            self.components = {
                "channels": {"enabled": True, "running": False, "last_error": ""},
                "channels_dispatcher": {"enabled": True, "running": False, "last_error": ""},
                "channels_recovery": {"enabled": True, "running": False, "last_error": ""},
                "cron": {"enabled": True, "running": False, "last_error": ""},
                "heartbeat": {"enabled": True, "running": False, "last_error": ""},
                "autonomy": {"enabled": False, "running": False, "last_error": "disabled"},
                "supervisor": {"enabled": True, "running": False, "last_error": ""},
                "skills_watcher": {"enabled": True, "running": False, "last_error": ""},
                "proactive_monitor": {"enabled": False, "running": False, "last_error": ""},
                "memory_quality_tuning": {"enabled": False, "running": False, "last_error": ""},
                "self_evolution": {"enabled": False, "running": False, "last_error": ""},
                "autonomy_wake": {"enabled": True, "running": False, "last_error": ""},
                "subagent_maintenance": {"enabled": True, "running": False, "last_error": ""},
                "job_workers": {"enabled": True, "running": False, "last_error": ""},
                "wake_pressure": {
                    "enabled": True,
                    "running": False,
                    "last_error": "",
                    "event_count": 0,
                    "notice_count": 0,
                    "last_kind": "",
                    "last_reason": "",
                },
                "subagent_replay": {"enabled": True, "running": False, "last_error": "", "replayed": 0, "failed": 0},
                "delivery_replay": {"enabled": True, "running": False, "last_error": "", "replayed": 0, "failed": 0, "skipped": 0},
                "inbound_replay": {"enabled": True, "running": False, "last_error": "", "replayed": 0, "remaining": 0},
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
    dashboard_session_header_name: str
    dashboard_session_query_param: str
    dashboard_client_header_name: str
    dashboard_client_query_param: str
    dashboard_handoff_header_name: str
    dashboard_handoff_query_param: str
    dashboard_sessions: DashboardSessionRegistry | None = None
    dashboard_handoffs: DashboardHandoffRegistry | None = None

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
            dashboard_session_header_name=DEFAULT_DASHBOARD_SESSION_HEADER_NAME,
            dashboard_session_query_param=DEFAULT_DASHBOARD_SESSION_QUERY_PARAM,
            dashboard_client_header_name=DEFAULT_DASHBOARD_CLIENT_HEADER_NAME,
            dashboard_client_query_param=DEFAULT_DASHBOARD_CLIENT_QUERY_PARAM,
            dashboard_handoff_header_name=DEFAULT_DASHBOARD_HANDOFF_HEADER_NAME,
            dashboard_handoff_query_param=DEFAULT_DASHBOARD_HANDOFF_QUERY_PARAM,
            dashboard_sessions=DashboardSessionRegistry() if token else None,
            dashboard_handoffs=DashboardHandoffRegistry() if token else None,
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

    @staticmethod
    def _extract_dashboard_session(*, header_value: str, query_value: str) -> str:
        if query_value:
            return query_value.strip()
        return header_value.strip()

    @staticmethod
    def _extract_dashboard_client(*, header_value: str, query_value: str) -> str:
        if query_value:
            return query_value.strip()
        return header_value.strip()

    def _dashboard_session_matches(self, supplied_token: str, *, client_id: str) -> bool:
        return bool(self.dashboard_sessions) and self.dashboard_sessions.verify(supplied_token, client_id=client_id)

    @staticmethod
    def _extract_dashboard_handoff(*, header_value: str, query_value: str) -> str:
        if query_value:
            return query_value.strip()
        return header_value.strip()

    def _dashboard_handoff_matches(self, supplied_token: str) -> bool:
        return verify_dashboard_handoff(supplied_token, gateway_token=self.token)

    def _consume_dashboard_handoff(self, supplied_token: str) -> bool:
        if not self.token:
            return False
        if self.dashboard_handoffs is None:
            return self._dashboard_handoff_matches(supplied_token)
        return self.dashboard_handoffs.verify_and_consume(supplied_token, gateway_token=self.token)

    def _extract_dashboard_client_from_request(self, *, request: Request) -> str:
        if not self.token or self.dashboard_sessions is None:
            raise HTTPException(status_code=404, detail="dashboard_session_disabled")
        client_id = self._extract_dashboard_client(
            header_value=str(request.headers.get(self.dashboard_client_header_name, "") or ""),
            query_value="",
        )
        if not client_id:
            raise HTTPException(status_code=400, detail="dashboard_client_required")
        return client_id

    def check_http_dashboard_bootstrap(self, *, request: Request) -> str:
        if not self.token:
            raise HTTPException(status_code=404, detail="dashboard_session_disabled")
        header_value = str(request.headers.get(self.header_name, "") or "")
        supplied_token = self._extract_token(header_value=header_value, query_value="")
        handoff_header = str(request.headers.get(self.dashboard_handoff_header_name, "") or "")
        handoff_query = str(request.query_params.get(self.dashboard_handoff_query_param, "") or "")
        supplied_handoff = self._extract_dashboard_handoff(
            header_value=handoff_header,
            query_value=handoff_query,
        )
        if supplied_token and self._token_matches(supplied_token):
            return "gateway_token"
        if supplied_handoff and self._consume_dashboard_handoff(supplied_handoff):
            return "dashboard_handoff"
        if supplied_token or supplied_handoff:
            raise HTTPException(status_code=401, detail="gateway_auth_invalid")
        raise HTTPException(status_code=401, detail="gateway_auth_required")

    def check_http(
        self,
        *,
        request: Request,
        scope: str,
        diagnostics_auth: bool,
        require_token_if_configured: bool = False,
        allow_dashboard_session: bool = False,
    ) -> None:
        client_host = request.client.host if request.client is not None else None
        header_value = str(request.headers.get(self.header_name, "") or "")
        query_value = str(request.query_params.get(self.query_param, "") or "")
        supplied_token = self._extract_token(header_value=header_value, query_value=query_value)
        dashboard_header = str(request.headers.get(self.dashboard_session_header_name, "") or "")
        dashboard_query = str(request.query_params.get(self.dashboard_session_query_param, "") or "")
        dashboard_client_header = str(request.headers.get(self.dashboard_client_header_name, "") or "")
        dashboard_client_query = str(request.query_params.get(self.dashboard_client_query_param, "") or "")
        dashboard_session = (
            self._extract_dashboard_session(header_value=dashboard_header, query_value=dashboard_query)
            if allow_dashboard_session and scope == "control" and self.token
            else ""
        )
        dashboard_client = (
            self._extract_dashboard_client(header_value=dashboard_client_header, query_value=dashboard_client_query)
            if allow_dashboard_session and scope == "control" and self.token
            else ""
        )
        raw_valid = self._token_matches(supplied_token)
        dashboard_present = bool(dashboard_session or dashboard_client)
        dashboard_valid = (
            self._dashboard_session_matches(dashboard_session, client_id=dashboard_client)
            if dashboard_session and dashboard_client
            else False
        )
        if require_token_if_configured and self.token:
            if raw_valid or dashboard_valid:
                return
            if supplied_token or dashboard_present:
                raise HTTPException(status_code=401, detail="gateway_auth_invalid")
            if not supplied_token and not dashboard_present:
                raise HTTPException(status_code=401, detail="gateway_auth_required")
        should_require = self._require_for_scope(scope=scope, host=client_host, diagnostics_auth=diagnostics_auth)
        if should_require and not (raw_valid or dashboard_valid):
            if supplied_token or dashboard_present:
                raise HTTPException(status_code=401, detail="gateway_auth_invalid")
            raise HTTPException(status_code=401, detail="gateway_auth_required")
        if self.mode == "optional" and supplied_token and self.token and not raw_valid:
            raise HTTPException(status_code=401, detail="gateway_auth_invalid")
        if self.mode == "optional" and dashboard_present and self.token and not dashboard_valid:
            raise HTTPException(status_code=401, detail="gateway_auth_invalid")

    async def check_ws(
        self,
        *,
        socket: WebSocket,
        scope: str,
        diagnostics_auth: bool,
        allow_dashboard_session: bool = False,
    ) -> bool:
        client_host = socket.client.host if socket.client is not None else None
        header_value = str(socket.headers.get(self.header_name, "") or "")
        query_value = str(socket.query_params.get(self.query_param, "") or "")
        supplied_token = self._extract_token(header_value=header_value, query_value=query_value)
        dashboard_header = str(socket.headers.get(self.dashboard_session_header_name, "") or "")
        dashboard_query = str(socket.query_params.get(self.dashboard_session_query_param, "") or "")
        dashboard_client_header = str(socket.headers.get(self.dashboard_client_header_name, "") or "")
        dashboard_client_query = str(socket.query_params.get(self.dashboard_client_query_param, "") or "")
        dashboard_session = (
            self._extract_dashboard_session(header_value=dashboard_header, query_value=dashboard_query)
            if allow_dashboard_session and scope == "control" and self.token
            else ""
        )
        dashboard_client = (
            self._extract_dashboard_client(header_value=dashboard_client_header, query_value=dashboard_client_query)
            if allow_dashboard_session and scope == "control" and self.token
            else ""
        )
        raw_valid = self._token_matches(supplied_token)
        dashboard_present = bool(dashboard_session or dashboard_client)
        dashboard_valid = (
            self._dashboard_session_matches(dashboard_session, client_id=dashboard_client)
            if dashboard_session and dashboard_client
            else False
        )
        should_require = self._require_for_scope(scope=scope, host=client_host, diagnostics_auth=diagnostics_auth)
        require_token_if_configured = scope == "control" and bool(self.token)
        if require_token_if_configured:
            if raw_valid or dashboard_valid:
                return True
            if supplied_token or dashboard_present:
                await socket.close(code=4401, reason="gateway_auth_invalid")
                return False
            if not supplied_token and not dashboard_present:
                await socket.close(code=4401, reason="gateway_auth_required")
                return False
        if should_require and not (raw_valid or dashboard_valid):
            if supplied_token or dashboard_present:
                await socket.close(code=4401, reason="gateway_auth_invalid")
                return False
            await socket.close(code=4401, reason="gateway_auth_required")
            return False
        if self.mode == "optional" and supplied_token and self.token and not raw_valid:
            await socket.close(code=4401, reason="gateway_auth_invalid")
            return False
        if self.mode == "optional" and dashboard_present and self.token and not dashboard_valid:
            await socket.close(code=4401, reason="gateway_auth_invalid")
            return False
        return True


def _request_rate_limit_credential(
    *,
    request: Request,
    auth_guard: GatewayAuthGuard,
    allow_dashboard_session: bool = False,
) -> str:
    header_value = str(request.headers.get(auth_guard.header_name, "") or "")
    query_value = str(request.query_params.get(auth_guard.query_param, "") or "")
    supplied_token = auth_guard._extract_token(header_value=header_value, query_value=query_value)
    if supplied_token:
        return supplied_token
    if allow_dashboard_session:
        dashboard_header = str(request.headers.get(auth_guard.dashboard_session_header_name, "") or "")
        dashboard_query = str(request.query_params.get(auth_guard.dashboard_session_query_param, "") or "")
        dashboard_session = auth_guard._extract_dashboard_session(header_value=dashboard_header, query_value=dashboard_query)
        if dashboard_session:
            return dashboard_session
    return ""


async def _http_chat_rate_limit_response(
    *,
    request: Request,
    auth_guard: GatewayAuthGuard,
    rate_limiter: GatewayRateLimiter | None,
    allow_dashboard_session: bool = False,
) -> JSONResponse | None:
    if rate_limiter is None:
        return None
    decision = rate_limiter.consume_http_chat(
        client_ip=request.client.host if request.client is not None else None,
        credential=_request_rate_limit_credential(
            request=request,
            auth_guard=auth_guard,
            allow_dashboard_session=allow_dashboard_session,
        ),
    )
    if decision.allowed:
        return None
    retry_after_s = max(1, int(math.ceil(float(decision.retry_after_s or 0.0))))
    request_id = _request_id_from_request(request)
    telemetry = getattr(request.app.state, "http_telemetry", None)
    if isinstance(telemetry, HttpRequestTelemetry):
        await telemetry.record_error(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status_code=429,
            code="gateway_rate_limited",
            message="gateway chat rate limit exceeded; retry shortly",
        )
    return JSONResponse(
        status_code=429,
        content={
            "error": "gateway_rate_limited",
            "code": "gateway_rate_limited",
            "status": 429,
            "message": "gateway chat rate limit exceeded; retry shortly",
            "retry_after_s": round(float(decision.retry_after_s or 0.0), 3),
        },
        headers={"Retry-After": str(retry_after_s)},
    )


async def _route_cron_job(runtime: RuntimeContainer, job) -> str | None:
    bind_event("cron.dispatch", session=job.session_id).info("cron dispatch start job_id={}", job.id)
    resolved_channel = str(getattr(job.payload, "channel", "") or "").strip() or job.session_id.split(":", 1)[0]
    resolved_target = str(getattr(job.payload, "target", "") or "").strip() or job.session_id.split(":", 1)[-1]
    raw_runtime_metadata = getattr(job.payload, "runtime_metadata", None)
    runtime_metadata = dict(raw_runtime_metadata) if isinstance(raw_runtime_metadata, dict) and raw_runtime_metadata else None
    try:
        result = await _run_engine_with_timeout(
            engine=runtime.engine,
            session_id=job.session_id,
            user_text=job.payload.prompt,
            timeout_s=GATEWAY_CRON_ENGINE_TIMEOUT_S,
            channel=resolved_channel or None,
            chat_id=resolved_target or None,
            runtime_metadata=runtime_metadata,
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
    if resolved_channel and resolved_target:
        try:
            await runtime.channels.send(channel=resolved_channel, target=resolved_target, text=result.text)
        except Exception:
            bind_event("channel.send", session=job.session_id, channel=resolved_channel).error("cron dispatch send failed job_id={} target={}", job.id, resolved_target)
            return "cron_send_skipped"
    bind_event("cron.dispatch", session=job.session_id).info("cron dispatch finished job_id={}", job.id)
    return result.text


def _default_heartbeat_route() -> tuple[str, str]:
    return _default_heartbeat_route_helper()


_LATEST_MEMORY_ROUTE_CACHE: dict[tuple[int, str], tuple[float, tuple[str, str]]] = {}


def _latest_route_from_history_tail(
    memory_store: Any,
    *,
    tail_bytes: int = LATEST_MEMORY_ROUTE_TAIL_BYTES,
    preferred_channel: str = "",
) -> tuple[str, str]:
    return _latest_route_from_history_tail_helper(
        memory_store,
        tail_bytes=tail_bytes,
        preferred_channel=preferred_channel,
    )


async def _latest_memory_route(memory_store: Any, *, preferred_channel: str = "") -> tuple[str, str]:
    return await _latest_memory_route_helper(
        memory_store,
        preferred_channel=preferred_channel,
        cache=_LATEST_MEMORY_ROUTE_CACHE,
        cache_ttl_s=LATEST_MEMORY_ROUTE_CACHE_TTL_S,
    )


async def _run_proactive_monitor(runtime: RuntimeContainer) -> dict[str, Any]:
    monitor = getattr(runtime, "memory_monitor", None)
    channels = getattr(runtime, "channels", None)
    memory_store = getattr(getattr(runtime, "engine", None), "memory", None)

    result: dict[str, Any] = {
        "status": "disabled",
        "scanned": 0,
        "delivered": 0,
        "replayed": 0,
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
        suggestion_metadata = dict(getattr(suggestion, "metadata", {}) or {})
        delivery_status = str(suggestion_metadata.get("_delivery_status", "pending") or "pending").strip().lower()
        try:
            priority = float(getattr(suggestion, "priority", 0.0) or 0.0)
        except Exception:
            priority = 0.0
        metadata = {
            "source": "memory_monitor",
            "suggestion_id": suggestion.suggestion_id,
            "trigger": suggestion.trigger,
            "priority": priority,
            **suggestion_metadata,
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
        if delivery_status == "failed":
            result["replayed"] = int(result.get("replayed", 0) or 0) + 1
        try:
            monitor.mark_delivered(suggestion)
        except Exception as exc:
            bind_event("proactive.memory", session="autonomy:proactive").warning(
                "memory suggestion mark_delivered failed suggestion_id={} error={}",
                suggestion.suggestion_id,
                exc,
            )

    try:
        channel, target = await _latest_memory_route(memory_store, preferred_channel="telegram")
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

    if (
        str(result.get("status", "") or "") not in {"ok", "disabled"}
        or int(result.get("delivered", 0) or 0) > 0
        or int(result.get("replayed", 0) or 0) > 0
        or int(result.get("failed", 0) or 0) > 0
        or bool(result.get("next_step_sent", False))
    ):
        summary = (
            f"status={result.get('status', '')} scanned={int(result.get('scanned', 0) or 0)} "
            f"delivered={int(result.get('delivered', 0) or 0)} replayed={int(result.get('replayed', 0) or 0)} "
            f"failed={int(result.get('failed', 0) or 0)}"
        )
        try:
            runtime.autonomy_log.record(
                source="memory_monitor",
                action="proactive_scan",
                status=str(result.get("status", "") or "ok"),
                summary=summary,
                metadata=dict(result),
            )
        except Exception as exc:
            bind_event("autonomy.log", source="memory_monitor", action="proactive_scan").warning(
                "autonomy log record failed error={}",
                exc,
            )

    return result


async def _run_heartbeat(runtime: RuntimeContainer) -> HeartbeatDecision:
    def _is_effectively_empty_heartbeat(content: str | None) -> bool:
        if content is None:
            return False
        for raw_line in str(content).splitlines():
            trimmed = raw_line.strip()
            if not trimmed:
                continue
            if trimmed.startswith("#"):
                continue
            if trimmed in {"-", "*", "+", "- [ ]", "* [ ]", "+ [ ]"}:
                continue
            return False
        return True

    def _append_current_time_line(text: str, *, workspace: Any | None) -> str:
        base = str(text or "").rstrip()
        if not base or "Current time:" in base:
            return base
        timezone_name = "UTC"
        user_profile = getattr(workspace, "user_profile", None)
        if callable(user_profile):
            try:
                profile = user_profile()
                timezone_name = str(getattr(profile, "timezone", "") or "").strip() or "UTC"
            except Exception:
                timezone_name = "UTC"
        try:
            tz = ZoneInfo(timezone_name)
        except Exception:
            timezone_name = "UTC"
            tz = dt.timezone.utc
        now_utc = dt.datetime.now(dt.timezone.utc)
        formatted = now_utc.astimezone(tz).strftime("%Y-%m-%d %H:%M")
        utc_time = now_utc.strftime("%Y-%m-%d %H:%M UTC")
        return f"{base}\nCurrent time: {formatted} ({timezone_name}) / {utc_time}"

    heartbeat_prompt = (
        "Read HEARTBEAT.md if it exists (workspace context). Follow it strictly. "
        "Do not infer or repeat old tasks from prior chats. "
        "If nothing needs attention, reply HEARTBEAT_OK."
    )
    sessions_store = getattr(getattr(runtime, "engine", None), "sessions", None)
    prune_sessions = getattr(sessions_store, "prune_expired", None)
    if callable(prune_sessions):
        try:
            pruned_sessions = int(await asyncio.to_thread(prune_sessions))
        except Exception as exc:
            bind_event("heartbeat.tick", session="heartbeat:system").warning(
                "session ttl prune failed error={}",
                exc,
            )
        else:
            if pruned_sessions > 0:
                bind_event("heartbeat.tick", session="heartbeat:system").info(
                    "session ttl prune deleted_sessions={}",
                    pruned_sessions,
                )
    workspace_heartbeat = ""
    workspace = getattr(runtime, "workspace", None)
    workspace_heartbeat_prompt = getattr(workspace, "heartbeat_prompt", None)
    if callable(workspace_heartbeat_prompt):
        try:
            workspace_heartbeat = str(workspace_heartbeat_prompt() or "").strip()
        except Exception:
            workspace_heartbeat = ""
    workspace_root = getattr(workspace, "workspace", None)
    heartbeat_path = Path(workspace_root) / "HEARTBEAT.md" if workspace_root else None
    if heartbeat_path is not None and heartbeat_path.exists() and _is_effectively_empty_heartbeat(workspace_heartbeat):
        return HeartbeatDecision(action="skip", reason="heartbeat_empty")
    if workspace_heartbeat:
        heartbeat_prompt = f"{heartbeat_prompt}\n\nHEARTBEAT.md content:\n{workspace_heartbeat}"
    heartbeat_prompt = _append_current_time_line(heartbeat_prompt, workspace=workspace)
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
        channel, target = await _latest_memory_route(memory_store, preferred_channel="telegram")
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


async def _run_bootstrap_cycle(runtime: RuntimeContainer) -> dict[str, Any]:
    workspace = getattr(runtime, "workspace", None)
    if workspace is None:
        return {"attempted": False, "status": "skipped", "reason": "workspace_unavailable"}

    should_run = getattr(workspace, "should_run", None)
    if callable(should_run):
        try:
            if not bool(should_run()):
                return {"attempted": False, "status": "skipped", "reason": "not_pending"}
        except Exception as exc:
            return {
                "attempted": True,
                "status": "error",
                "reason": "status_check_failed",
                "error": str(exc),
            }

    bootstrap_prompt = getattr(workspace, "get_prompt", None)
    prompt_text = ""
    if callable(bootstrap_prompt):
        try:
            prompt_text = str(bootstrap_prompt() or "").strip()
        except Exception as exc:
            prompt_text = ""
            return {
                "attempted": True,
                "status": "error",
                "reason": "prompt_load_failed",
                "error": str(exc),
            }
    if not prompt_text:
        return {"attempted": False, "status": "skipped", "reason": "prompt_missing"}

    session_id = "bootstrap:system"
    user_text = (
        "Run the bootstrap cycle now. Read BOOTSTRAP.md from the workspace context, "
        "follow it completely, and finish the first-run initialization without asking the operator to intervene. "
        "When complete, reply with a short confirmation."
    )
    try:
        result = await _run_engine_with_timeout(
            engine=runtime.engine,
            session_id=session_id,
            user_text=user_text,
            timeout_s=GATEWAY_BOOTSTRAP_ENGINE_TIMEOUT_S,
        )
        model_name = str(getattr(result, "model", "") or "").strip()
        if not model_name or model_name.startswith("engine/"):
            error = f"bootstrap_run_unsatisfied:{model_name or 'unknown_model'}"
            try:
                workspace.record_bootstrap_result(status="error", session_id=session_id, error=error)
            except Exception:
                pass
            return {
                "attempted": True,
                "status": "error",
                "reason": error,
                "result_excerpt": str(getattr(result, "text", "") or "")[:200],
            }
        completed = bool(workspace.complete())
        if not completed:
            try:
                workspace.record_bootstrap_result(
                    status="error",
                    session_id=session_id,
                    error="complete_bootstrap_returned_false",
                )
            except Exception:
                pass
            return {
                "attempted": True,
                "status": "error",
                "reason": "complete_bootstrap_returned_false",
            }
        try:
            workspace.record_bootstrap_result(status="completed", session_id=session_id)
        except Exception:
            pass
        return {
            "attempted": True,
            "status": "completed",
            "reason": "startup_bootstrap_completed",
            "result_excerpt": str(getattr(result, "text", "") or "")[:200],
        }
    except Exception as exc:
        try:
            workspace.record_bootstrap_result(status="error", session_id=session_id, error=str(exc))
        except Exception:
            pass
        return {
            "attempted": True,
            "status": "error",
            "reason": "bootstrap_run_failed",
            "error": str(exc),
        }


def create_app(
    config: AppConfig | None = None,
    *,
    config_path: str | Path | None = None,
    config_profile: str | None = None,
) -> FastAPI:
    setup_logging()
    if config_path is not None or config_profile is not None:
        cfg = load_config(config_path, profile=config_profile)
    else:
        cfg = config or load_config()
    runtime = build_runtime(cfg, config_path=config_path, config_profile=config_profile)
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
    lifecycle.components["autonomy"]["enabled"] = bool(cfg.gateway.autonomy.enabled)
    lifecycle.components["autonomy"]["last_error"] = "" if cfg.gateway.autonomy.enabled else "disabled"
    lifecycle.components["supervisor"]["enabled"] = bool(cfg.gateway.supervisor.enabled)
    lifecycle.components["skills_watcher"]["enabled"] = True
    lifecycle.components["proactive_monitor"]["enabled"] = bool(runtime.memory_monitor is not None)
    lifecycle.components["memory_quality_tuning"]["enabled"] = bool(cfg.gateway.autonomy.tuning_loop_enabled)
    lifecycle.components["self_evolution"]["enabled"] = bool(
        cfg.gateway.autonomy.self_evolution_enabled and runtime.self_evolution is not None
    )
    proactive_interval_seconds = max(5, int(cfg.gateway.heartbeat.interval_s or 1800))
    proactive_task: asyncio.Task[Any] | None = None
    proactive_running = False
    proactive_stop_event = asyncio.Event()
    proactive_runner_state = _build_proactive_runner_state(
        enabled=bool(runtime.memory_monitor is not None),
        interval_seconds=proactive_interval_seconds,
    )
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
    supervisor_incident_notice_until: dict[str, float] = {}
    job_workers_started = False
    wake_pressure_notice_until: dict[str, float] = {}
    wake_pressure_state = _build_wake_pressure_state()
    cron_wake_state = _build_cron_wake_state()
    tuning_runner_state = _build_tuning_runner_state(
        enabled=bool(cfg.gateway.autonomy.tuning_loop_enabled),
        interval_seconds=tuning_loop_interval_seconds,
        timeout_seconds=tuning_loop_timeout_seconds,
        cooldown_seconds=tuning_loop_cooldown_seconds,
        actions_per_hour_cap=tuning_actions_per_hour_cap,
    )
    self_evolution_task: asyncio.Task[Any] | None = None
    self_evolution_running = False
    self_evolution_stop_event = asyncio.Event()
    self_evolution_status = runtime.self_evolution.status() if runtime.self_evolution is not None else {}
    self_evolution_runner_state = _build_self_evolution_runner_state(
        enabled=bool(self_evolution_status.get("background_enabled", self_evolution_status.get("enabled", False))),
        cooldown_seconds=float(getattr(runtime.self_evolution, "cooldown_s", 3600.0)) if runtime.self_evolution is not None else 0.0,
        activation_mode=str(self_evolution_status.get("activation_mode", "") or ""),
        activation_reason=str(self_evolution_status.get("activation_reason", "") or ""),
        enabled_for_sessions=list(self_evolution_status.get("enabled_for_sessions", []) or []),
        autonomy_session_id=str(self_evolution_status.get("autonomy_session_id", "") or ""),
    )
    subagent_maintenance_interval_seconds = max(1.0, float(runtime.engine.subagents.maintenance_interval_seconds()))
    subagent_maintenance_task: asyncio.Task[Any] | None = None
    subagent_maintenance_running = False
    subagent_maintenance_stop_event = asyncio.Event()
    subagent_maintenance_state = _build_subagent_maintenance_state(
        interval_seconds=subagent_maintenance_interval_seconds,
    )

    def _record_autonomy_event(
        source: str,
        action: str,
        status: str,
        *,
        summary: str = "",
        metadata: dict[str, Any] | None = None,
        event_at: str = "",
    ) -> None:
        try:
            runtime.autonomy_log.record(
                source=source,
                action=action,
                status=status,
                summary=summary,
                metadata=metadata,
                event_at=event_at,
            )
        except Exception as exc:
            bind_event("autonomy.log", source=source, action=action).warning("autonomy log record failed error={}", exc)

    async def _autonomy_snapshot_payload() -> dict[str, Any]:
        queue_snapshot = runtime.bus.stats()
        channels_snapshot = runtime.channels.status()
        supervisor_snapshot = runtime.supervisor.status() if runtime.supervisor is not None else {}
        provider_snapshot = _provider_autonomy_snapshot(
            provider=runtime.engine.provider,
            default_circuit_cooldown_s=float(cfg.provider.circuit_cooldown_s or 30.0),
        )
        return {
            "queue": queue_snapshot if isinstance(queue_snapshot, dict) else {},
            "channels": channels_snapshot if isinstance(channels_snapshot, dict) else {},
            "supervisor": supervisor_snapshot if isinstance(supervisor_snapshot, dict) else {},
            "provider": provider_snapshot,
        }

    async def _run_autonomy_tick(snapshot: dict[str, Any]) -> str:
        provider_snapshot = snapshot.get("provider") if isinstance(snapshot, dict) else {}
        provider_name = str(provider_snapshot.get("provider", "") or "provider").strip().lower() or "provider"
        suppression_reason = ""
        suppression_backoff_s = 0.0
        if isinstance(provider_snapshot, dict):
            suppression_reason = str(provider_snapshot.get("suppression_reason", "") or "").strip().lower()
            try:
                suppression_backoff_s = float(provider_snapshot.get("suppression_backoff_s", 0.0) or 0.0)
            except (TypeError, ValueError):
                suppression_backoff_s = 0.0
        if suppression_reason and suppression_backoff_s > 0.0:
            raise RuntimeError(
                f"autonomy_provider_backoff:{provider_name}:{suppression_reason}:{round(max(0.0, suppression_backoff_s), 3)}"
            )

        prompt_text = (
            "Autonomy tick. Review the runtime snapshot and workspace context. "
            "If nothing needs operator attention right now, reply AUTONOMY_IDLE. "
            "If the operator needs a concise autonomous update, reply with only that notice text."
        )
        snapshot_text = json.dumps(snapshot or {}, ensure_ascii=False, sort_keys=True)
        result = await _run_engine_with_timeout(
            engine=runtime.engine,
            session_id=str(cfg.gateway.autonomy.session_id or "autonomy:system"),
            user_text=f"{prompt_text}\n\nRuntime snapshot:\n{snapshot_text}",
            timeout_s=float(cfg.gateway.autonomy.timeout_s or 45.0),
        )
        model_name = str(getattr(result, "model", "") or "").strip()
        if not model_name or model_name.startswith("engine/"):
            provider_snapshot = _provider_autonomy_snapshot(
                provider=runtime.engine.provider,
                default_circuit_cooldown_s=float(cfg.provider.circuit_cooldown_s or 30.0),
            )
            provider_name = str(provider_snapshot.get("provider", "") or "provider").strip().lower() or "provider"
            suppression_reason = str(provider_snapshot.get("suppression_reason", "") or "").strip().lower()
            suppression_backoff_s = 0.0
            try:
                suppression_backoff_s = float(provider_snapshot.get("suppression_backoff_s", 0.0) or 0.0)
            except (TypeError, ValueError):
                suppression_backoff_s = 0.0
            if suppression_reason and suppression_backoff_s > 0.0:
                raise RuntimeError(
                    f"autonomy_provider_backoff:{provider_name}:{suppression_reason}:{round(max(0.0, suppression_backoff_s), 3)}"
                )
            raise RuntimeError(f"autonomy_tick_unsatisfied:{model_name or 'unknown_model'}")

        text = str(getattr(result, "text", "") or "").strip() or "AUTONOMY_IDLE"
        metadata = {
            "source": "autonomy",
            "trigger": "continuous_loop",
            "session_id": str(cfg.gateway.autonomy.session_id or "autonomy:system"),
            "snapshot": dict(snapshot or {}),
        }
        if text == "AUTONOMY_IDLE" or text.startswith("AUTONOMY_IDLE\n"):
            _record_autonomy_event(
                "autonomy",
                "continuous_tick",
                "idle",
                summary="continuous autonomy tick returned idle",
                metadata=metadata,
            )
            return text

        _record_autonomy_event(
            "autonomy",
            "continuous_tick",
            "actionable",
            summary="continuous autonomy tick produced operator notice",
            metadata={**metadata, "result_excerpt": text[:200]},
        )
        sent = await _send_autonomy_notice(
            "autonomy",
            "continuous_tick",
            "actionable",
            text=text,
            metadata=metadata,
            summary="continuous autonomy tick operator notice",
        )
        return "AUTONOMY_NOTICE_SENT" if sent else "AUTONOMY_NOTICE_UNROUTED"

    def _wake_backpressure_row(snapshot: dict[str, Any], kind: str) -> dict[str, int]:
        by_kind = snapshot.get("by_kind") if isinstance(snapshot, dict) else {}
        row = by_kind.get(kind) if isinstance(by_kind, dict) else {}
        if not isinstance(row, dict):
            row = {}
        return {
            "dropped_backpressure": int(row.get("dropped_backpressure", 0) or 0),
            "dropped_quota": int(row.get("dropped_quota", 0) or 0),
            "dropped_global_backpressure": int(row.get("dropped_global_backpressure", 0) or 0),
        }

    def _wake_metric_delta(before: dict[str, Any], after: dict[str, Any], kind: str, metric: str) -> int:
        before_row = _wake_backpressure_row(before, kind)
        after_row = _wake_backpressure_row(after, kind)
        if metric == "coalesced":
            before_by_kind = before.get("by_kind") if isinstance(before.get("by_kind"), dict) else {}
            after_by_kind = after.get("by_kind") if isinstance(after.get("by_kind"), dict) else {}
            before_metric = before_by_kind.get(kind) if isinstance(before_by_kind.get(kind), dict) else {}
            after_metric = after_by_kind.get(kind) if isinstance(after_by_kind.get(kind), dict) else {}
            return int(after_metric.get("coalesced", 0) or 0) - int(before_metric.get("coalesced", 0) or 0)
        return int(after_row.get(metric, 0) or 0) - int(before_row.get(metric, 0) or 0)

    def _record_wake_policy_event(
        *,
        state: dict[str, Any],
        source: str,
        kind: str,
        action: str,
        reason: str,
        summary: str,
        metadata: dict[str, Any],
    ) -> None:
        event_at = _utc_now_iso()
        normalized_action = str(action or "unknown").strip() or "unknown"
        normalized_reason = str(reason or "unknown").strip() or "unknown"
        state["policy_event_count"] = int(state.get("policy_event_count", 0) or 0) + 1
        if normalized_action == "delayed":
            state["delayed_count"] = int(state.get("delayed_count", 0) or 0) + 1
        elif normalized_action == "discarded":
            state["discarded_count"] = int(state.get("discarded_count", 0) or 0) + 1
        policy_by_action = state.get("policy_by_action")
        if not isinstance(policy_by_action, dict):
            policy_by_action = {}
            state["policy_by_action"] = policy_by_action
        policy_by_action[normalized_action] = int(policy_by_action.get(normalized_action, 0) or 0) + 1
        policy_by_reason = state.get("policy_by_reason")
        if not isinstance(policy_by_reason, dict):
            policy_by_reason = {}
            state["policy_by_reason"] = policy_by_reason
        policy_by_reason[normalized_reason] = int(policy_by_reason.get(normalized_reason, 0) or 0) + 1
        state["last_policy_action"] = normalized_action
        state["last_policy_reason"] = normalized_reason
        state["last_policy_at"] = event_at
        state["last_result"] = summary
        recent_events = state.get("recent_policy_events")
        if not isinstance(recent_events, list):
            recent_events = []
        recent_events.append(
            {
                "at": event_at,
                "kind": kind,
                "source": source,
                "action": normalized_action,
                "reason": normalized_reason,
                "summary": summary,
            }
        )
        state["recent_policy_events"] = recent_events[-10:]
        _record_autonomy_event(
            source,
            "wake_policy",
            normalized_action,
            summary=summary,
            metadata={
                "wake_kind": kind,
                "policy_action": normalized_action,
                "policy_reason": normalized_reason,
                **metadata,
            },
            event_at=event_at,
        )

    def _classify_wake_backpressure(
        kind: str,
        *,
        before: dict[str, Any],
        after: dict[str, Any],
    ) -> tuple[str, int]:
        before_row = _wake_backpressure_row(before, kind)
        after_row = _wake_backpressure_row(after, kind)
        quota_delta = after_row["dropped_quota"] - before_row["dropped_quota"]
        if quota_delta > 0:
            return ("quota", quota_delta)
        global_delta = after_row["dropped_global_backpressure"] - before_row["dropped_global_backpressure"]
        if global_delta > 0:
            return ("global", global_delta)
        total_delta = after_row["dropped_backpressure"] - before_row["dropped_backpressure"]
        if total_delta > 0:
            return ("backpressure", total_delta)
        return ("backpressure", 0)

    def _wake_reason_label(pressure_class: str) -> str:
        normalized = str(pressure_class or "backpressure").strip().lower()
        if normalized == "quota":
            return "quota_backpressure"
        if normalized == "global":
            return "global_backpressure"
        return "backpressure"

    async def _track_wake_backpressure(
        *,
        kind: str,
        source: str,
        before: dict[str, Any],
        after: dict[str, Any],
    ) -> str:
        normalized_kind = str(kind or "unknown").strip() or "unknown"
        pressure_class, delta = _classify_wake_backpressure(normalized_kind, before=before, after=after)
        now = time.monotonic()
        event_at = _utc_now_iso()
        streak_key = f"{normalized_kind}:{pressure_class}"
        last_seen = float(wake_pressure_state["last_seen_monotonic"].get(streak_key, 0.0) or 0.0)
        streaks = wake_pressure_state["streaks"]
        if (now - last_seen) > 120.0:
            streaks[streak_key] = 0
        streaks[streak_key] = int(streaks.get(streak_key, 0) or 0) + 1
        streak = int(streaks[streak_key])
        wake_pressure_state["last_seen_monotonic"][streak_key] = now
        wake_pressure_state["event_count"] = int(wake_pressure_state.get("event_count", 0) or 0) + 1
        wake_pressure_state["last_kind"] = normalized_kind
        wake_pressure_state["last_reason"] = pressure_class
        wake_pressure_state["last_event_at"] = event_at
        wake_pressure_state["events_by_kind"][normalized_kind] = int(wake_pressure_state["events_by_kind"].get(normalized_kind, 0) or 0) + 1
        wake_pressure_state["events_by_reason"][pressure_class] = int(wake_pressure_state["events_by_reason"].get(pressure_class, 0) or 0) + 1

        pending_by_kind = after.get("pending_by_kind") if isinstance(after.get("pending_by_kind"), dict) else {}
        kind_limits = after.get("kind_limits") if isinstance(after.get("kind_limits"), dict) else {}
        summary = (
            f"{normalized_kind} wake {pressure_class} "
            f"delta={max(1, int(delta))} pending={int(pending_by_kind.get(normalized_kind, 0) or 0)} "
            f"limit={int(kind_limits.get(normalized_kind, 0) or 0)}"
        )
        wake_pressure_state["last_summary"] = summary

        wake_component = lifecycle.components.setdefault(
            "wake_pressure",
            {"enabled": True, "running": False, "last_error": "", "event_count": 0, "notice_count": 0, "last_kind": "", "last_reason": ""},
        )
        wake_component["enabled"] = True
        wake_component["running"] = False
        wake_component["last_error"] = ""
        wake_component["event_count"] = int(wake_pressure_state.get("event_count", 0) or 0)
        wake_component["notice_count"] = int(wake_pressure_state.get("notice_count", 0) or 0)
        wake_component["last_kind"] = normalized_kind
        wake_component["last_reason"] = pressure_class
        wake_component["last_event_at"] = event_at
        wake_component["events_by_kind"] = dict(wake_pressure_state["events_by_kind"])
        wake_component["events_by_reason"] = dict(wake_pressure_state["events_by_reason"])
        wake_component["last_summary"] = summary

        metadata = {
            "pressure_kind": normalized_kind,
            "pressure_class": pressure_class,
            "pressure_delta": max(1, int(delta)),
            "pressure_streak": streak,
            "pressure_source": source,
            "pending_by_kind": dict(pending_by_kind),
            "kind_limits": dict(kind_limits),
            "autonomy_wake": dict(after),
        }
        _record_autonomy_event(
            "autonomy",
            "wake_backpressure",
            pressure_class,
            summary=summary,
            metadata=metadata,
            event_at=event_at,
        )

        if streak >= 2 and now >= float(wake_pressure_notice_until.get(streak_key, 0.0) or 0.0):
            sent = await _send_autonomy_notice(
                "autonomy",
                "wake_backpressure",
                pressure_class,
                text=(
                    f"Autonomy notice: {normalized_kind} wakes throttled by {pressure_class} backpressure. "
                    f"streak={streak} pending={int(pending_by_kind.get(normalized_kind, 0) or 0)} "
                    f"limit={int(kind_limits.get(normalized_kind, 0) or 0)}."
                ),
                metadata=metadata,
                summary=f"notice sent for {normalized_kind} wake {pressure_class}",
                event_at=event_at,
            )
            wake_pressure_notice_until[streak_key] = now + 120.0
            if sent:
                wake_pressure_state["notice_count"] = int(wake_pressure_state.get("notice_count", 0) or 0) + 1
                wake_pressure_state["last_notice_at"] = event_at
                wake_component["notice_count"] = int(wake_pressure_state.get("notice_count", 0) or 0)
        return pressure_class

    async def _send_autonomy_notice(
        source: str,
        action: str,
        status: str,
        *,
        text: str,
        metadata: dict[str, Any] | None = None,
        summary: str = "",
        event_at: str = "",
    ) -> bool:
        return await _send_autonomy_notice_helper(
            source=source,
            action=action,
            status=status,
            text=text,
            memory_store=getattr(runtime.engine, "memory", None),
            channels=runtime.channels,
            autonomy_log=runtime.autonomy_log,
            metadata=metadata,
            summary=summary,
            event_at=event_at,
            preferred_channel="telegram",
            cache=_LATEST_MEMORY_ROUTE_CACHE,
            cache_ttl_s=LATEST_MEMORY_ROUTE_CACHE_TTL_S,
        )
        return True
    memory_quality_cache = _build_memory_quality_cache()

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
        row["last_session_id"] = str(status.get("last_session_id", "") or "")
        return status

    async def _run_startup_bootstrap_cycle() -> dict[str, Any]:
        status = _refresh_bootstrap_component()
        if not bool(status.get("pending", False)):
            return {"attempted": False, "status": "skipped", "reason": "not_pending"}

        row = lifecycle.components.setdefault(
            "bootstrap",
            {"enabled": True, "running": False, "pending": False, "last_status": "", "last_error": ""},
        )
        row["enabled"] = True
        row["running"] = True
        row["pending"] = True
        row["last_error"] = ""
        bind_event("bootstrap.lifecycle", session="bootstrap:system").info("bootstrap startup cycle begin")

        result = await _run_bootstrap_cycle(runtime)
        _refresh_bootstrap_component()
        bind_event("bootstrap.lifecycle", session="bootstrap:system").info(
            "bootstrap startup cycle finished status={} reason={}",
            str(result.get("status", "") or "unknown"),
            str(result.get("reason", "") or ""),
        )
        return result

    def _background_task_snapshot(
        task: asyncio.Task[Any] | None,
        *,
        running: bool,
        last_error: str = "",
    ) -> tuple[str, str]:
        if task is None:
            return ("missing" if running else "stopped", last_error)
        if task.cancelled():
            return ("cancelled", last_error)
        if not task.done():
            return ("running", last_error)
        try:
            exc = task.exception()
        except asyncio.CancelledError:
            return ("cancelled", last_error)
        if exc is not None:
            return ("failed", str(exc))
        return ("done", last_error)

    def _refresh_runtime_components() -> None:
        self_evolution_state, self_evolution_error = _background_task_snapshot(
            self_evolution_task,
            running=self_evolution_running,
            last_error=str(self_evolution_runner_state.get("last_error", "") or ""),
        )
        lifecycle.components.setdefault("self_evolution", {"enabled": False, "running": False, "last_error": "disabled"})[
            "enabled"
        ] = bool(self_evolution_runner_state.get("enabled", False))
        lifecycle.mark_component(
            "self_evolution",
            running=bool(self_evolution_runner_state.get("enabled", False) and self_evolution_state == "running"),
            error=(
                self_evolution_error
                or (
                    str(self_evolution_runner_state.get("activation_reason", "") or "disabled")
                    if not self_evolution_runner_state.get("enabled", False)
                    else ""
                )
            ),
        )

        channels_dispatcher_status = runtime.channels.dispatcher_diagnostics()
        lifecycle.components.setdefault("channels_dispatcher", {"enabled": True, "running": False, "last_error": ""})[
            "enabled"
        ] = bool(channels_dispatcher_status.get("enabled", True))
        lifecycle.mark_component(
            "channels_dispatcher",
            running=bool(channels_dispatcher_status.get("enabled", True) and channels_dispatcher_status.get("running", False)),
            error=(
                str(channels_dispatcher_status.get("last_error", "") or "")
                or ("disabled" if not channels_dispatcher_status.get("enabled", True) else "")
            ),
        )

        channels_recovery_status = runtime.channels.recovery_diagnostics()
        lifecycle.components.setdefault("channels_recovery", {"enabled": True, "running": False, "last_error": ""})[
            "enabled"
        ] = bool(channels_recovery_status.get("enabled", True))
        lifecycle.mark_component(
            "channels_recovery",
            running=bool(channels_recovery_status.get("enabled", True) and channels_recovery_status.get("running", False)),
            error=(
                str(channels_recovery_status.get("last_error", "") or "")
                or ("disabled" if not channels_recovery_status.get("enabled", True) else "")
            ),
        )

        heartbeat_status = runtime.heartbeat.status()
        lifecycle.mark_component(
            "heartbeat",
            running=bool(heartbeat_status.get("running", False)),
            error=str(heartbeat_status.get("last_error", "") or ""),
        )

        autonomy_status = runtime.autonomy.status() if runtime.autonomy is not None else {
            "running": False,
            "enabled": False,
            "last_error": "disabled",
        }
        lifecycle.components.setdefault("autonomy", {"enabled": False, "running": False, "last_error": "disabled"})[
            "enabled"
        ] = bool(autonomy_status.get("enabled", False))
        lifecycle.mark_component(
            "autonomy",
            running=bool(autonomy_status.get("running", False)),
            error=(str(autonomy_status.get("last_error", "") or "") or ("disabled" if not autonomy_status.get("enabled", False) else "")),
        )

        cron_status = runtime.cron.status()
        lifecycle.mark_component(
            "cron",
            running=bool(cron_status.get("running", False)),
            error=str(cron_status.get("last_error", "") or ""),
        )

        autonomy_wake_status = runtime.autonomy_wake.status()
        lifecycle.mark_component(
            "autonomy_wake",
            running=bool(autonomy_wake_status.get("running", False)),
            error=str(autonomy_wake_status.get("last_error", "") or ""),
        )

        skills_watcher_status = runtime.skills_loader.watcher_status()
        lifecycle.mark_component(
            "skills_watcher",
            running=bool(skills_watcher_status.get("running", False)),
            error=str(skills_watcher_status.get("last_error", "") or ""),
        )

        subagent_maintenance_state_name, subagent_maintenance_error = _background_task_snapshot(
            subagent_maintenance_task,
            running=subagent_maintenance_running,
            last_error=str(subagent_maintenance_state.get("last_error", "") or ""),
        )
        lifecycle.mark_component(
            "subagent_maintenance",
            running=subagent_maintenance_state_name == "running",
            error=subagent_maintenance_error,
        )

        proactive_state, proactive_error = _background_task_snapshot(
            proactive_task,
            running=proactive_running,
            last_error=str(proactive_runner_state.get("last_error", "") or ""),
        )
        lifecycle.mark_component(
            "proactive_monitor",
            running=proactive_state == "running",
            error=proactive_error,
        )

        tuning_state, tuning_error = _background_task_snapshot(
            tuning_task,
            running=tuning_running,
            last_error=str(tuning_runner_state.get("last_error", "") or ""),
        )
        lifecycle.mark_component(
            "memory_quality_tuning",
            running=tuning_state == "running",
            error=tuning_error,
        )

        supervisor_status = runtime.supervisor.status() if runtime.supervisor is not None else {"running": False, "last_error": ""}
        lifecycle.mark_component(
            "supervisor",
            running=bool(supervisor_status.get("running", False)),
            error=str(supervisor_status.get("last_error", "") or ""),
        )

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
        before = runtime.autonomy_wake.status()
        decision = await runtime.autonomy_wake.submit(
            kind="heartbeat",
            key="heartbeat:loop",
            priority=10,
            payload={},
            fallback_result=fallback,
        )
        normalized = HeartbeatDecision.from_result(decision)
        if normalized.reason == "wake_backpressure":
            pressure_class = await _track_wake_backpressure(
                kind="heartbeat",
                source="heartbeat",
                before=before,
                after=runtime.autonomy_wake.status(),
            )
            normalized.reason = f"wake_{_wake_reason_label(pressure_class)}"
        return normalized

    async def _submit_cron_wake(job) -> str | None:
        before = runtime.autonomy_wake.status()
        result = await runtime.autonomy_wake.submit(
            kind="cron",
            key=f"cron:{job.id}",
            priority=50,
            payload={"job": job},
            fallback_result="cron_backpressure_skipped",
        )
        after = runtime.autonomy_wake.status()
        coalesced_delta = _wake_metric_delta(before, after, "cron", "coalesced")
        if coalesced_delta > 0:
            _record_wake_policy_event(
                state=cron_wake_state,
                source="cron",
                kind="cron",
                action="delayed",
                reason="coalesced",
                summary=f"cron wake delayed by coalesced pending run job_id={job.id}",
                metadata={
                    "job_id": str(job.id),
                    "job_name": str(getattr(job, "name", "") or ""),
                    "coalesced_delta": int(coalesced_delta),
                    "autonomy_wake": dict(after),
                },
            )
        if result == "cron_backpressure_skipped":
            pressure_class = await _track_wake_backpressure(
                kind="cron",
                source="cron",
                before=before,
                after=after,
            )
            _record_wake_policy_event(
                state=cron_wake_state,
                source="cron",
                kind="cron",
                action="discarded",
                reason=pressure_class,
                summary=f"cron wake discarded by {pressure_class} policy job_id={job.id}",
                metadata={
                    "job_id": str(job.id),
                    "job_name": str(getattr(job, "name", "") or ""),
                    "autonomy_wake": dict(after),
                },
            )
            return f"cron_{_wake_reason_label(pressure_class)}_skipped"
        cron_wake_state["last_result"] = str(result or "")
        return result

    async def _submit_proactive_wake() -> dict[str, Any]:
        fallback = {
            "status": "wake_backpressure",
            "scanned": 0,
            "delivered": 0,
            "failed": 0,
            "next_step_sent": False,
            "error": "",
        }
        before = runtime.autonomy_wake.status()
        response = await runtime.autonomy_wake.submit(
            kind="proactive",
            key="proactive:memory_monitor",
            priority=30,
            payload={},
            fallback_result=fallback,
        )
        after = runtime.autonomy_wake.status()
        if isinstance(response, dict):
            normalized = dict(response)
            coalesced_delta = _wake_metric_delta(before, after, "proactive", "coalesced")
            if coalesced_delta > 0:
                _record_wake_policy_event(
                    state=proactive_runner_state,
                    source="proactive",
                    kind="proactive",
                    action="delayed",
                    reason="coalesced",
                    summary="proactive wake delayed by coalesced pending run",
                    metadata={
                        "coalesced_delta": int(coalesced_delta),
                        "autonomy_wake": dict(after),
                    },
                )
            if str(normalized.get("status", "") or "").strip().lower() == "wake_backpressure":
                pressure_class = await _track_wake_backpressure(
                    kind="proactive",
                    source="proactive",
                    before=before,
                    after=after,
                )
                normalized["status"] = f"wake_{_wake_reason_label(pressure_class)}"
                normalized["pressure_class"] = pressure_class
                _record_wake_policy_event(
                    state=proactive_runner_state,
                    source="proactive",
                    kind="proactive",
                    action="discarded",
                    reason=pressure_class,
                    summary=f"proactive wake discarded by {pressure_class} policy",
                    metadata={
                        "autonomy_wake": dict(after),
                    },
                )
            return normalized
        return fallback

    control_handlers = GatewayControlHandlers(
        auth_guard=auth_guard,
        diagnostics_require_auth=cfg.gateway.diagnostics.require_auth,
        runtime=runtime,
        heartbeat_enabled=bool(cfg.gateway.heartbeat.enabled),
        memory_doctor_fn=memory_doctor_snapshot,
        memory_quality_fn=memory_quality_snapshot,
        memory_snapshot_create_fn=memory_snapshot_create,
        memory_snapshot_rollback_fn=memory_snapshot_rollback,
        submit_heartbeat_wake=_submit_heartbeat_wake,
        submit_proactive_wake=_submit_proactive_wake,
        self_evolution_runner_state=self_evolution_runner_state,
    )
    webhook_handlers = GatewayWebhookHandlers(
        config=cfg,
        runtime=runtime,
        telegram_max_body_bytes=TELEGRAM_WEBHOOK_MAX_BODY_BYTES,
        whatsapp_max_body_bytes=WHATSAPP_WEBHOOK_MAX_BODY_BYTES,
    )

    async def _send_channel_recovery_notice(payload: dict[str, Any]) -> None:
        normalized_channel = str(payload.get("channel", "") or "").strip()
        status = str(payload.get("status", "") or "").strip() or "unknown"
        reason = str(payload.get("reason", "") or "").strip()
        error = str(payload.get("error", "") or "").strip()
        event_at = str(payload.get("at", "") or "").strip()
        if normalized_channel:
            _record_autonomy_event(
                "channels",
                "channel_recovery",
                status,
                summary=f"channel {normalized_channel} {status}",
                metadata={
                    "channel": normalized_channel,
                    "reason": reason,
                    "error": error,
                },
                event_at=event_at,
            )
        text = f"Autonomy notice: channel {normalized_channel} {status}."
        if reason:
            text += f" reason={reason}."
        if error and status != "recovered":
            text += f" error={error}."
        await _send_autonomy_notice(
            "channels",
            "channel_recovery",
            status,
            text=text,
            metadata={
                "source": "channel_recovery",
                "recovery_channel": normalized_channel,
                "recovery_status": status,
                "recovery_reason": reason,
                "recovery_error": error,
            },
            summary=f"notice sent for channel {normalized_channel} {status}",
            event_at=event_at,
        )

    runtime.channels.set_recovery_notifier(_send_channel_recovery_notice)

    def _is_internal_session_id(session_id: str) -> bool:
        normalized = str(session_id or "").strip().lower()
        return normalized.startswith("heartbeat:") or normalized.startswith("autonomy:") or normalized.startswith("bootstrap:")

    def _is_hatch_session_id(session_id: str) -> bool:
        normalized = str(session_id or "").strip().lower()
        configured = str(build_dashboard_handoff(runtime.config).get("hatch_session_id", "hatch:operator") or "hatch:operator").strip().lower()
        return normalized == configured or normalized.startswith("hatch:")

    def _finalize_bootstrap_for_user_turn(session_id: str) -> None:
        if _is_internal_session_id(session_id):
            _refresh_bootstrap_component()
            return

        status = _bootstrap_status_snapshot()
        if not bool(status.get("pending", False)):
            _refresh_bootstrap_component()
            return

        if not _is_hatch_session_id(session_id):
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
        return _utc_now_iso_helper()

    def _control_plane_payload(server_time: str | None = None) -> ControlPlaneResponse:
        now = server_time or _utc_now_iso()
        _refresh_runtime_components()
        _refresh_bootstrap_component()
        return ControlPlaneResponse(
            **_build_control_plane_payload(
                ready=bool(lifecycle.ready),
                phase=str(lifecycle.phase),
                contract_version=GATEWAY_CONTRACT_VERSION,
                server_time=now,
                components=dict(lifecycle.components),
                auth_payload=_control_plane_auth_payload(auth_guard=auth_guard),
                memory_proactive_enabled=bool(runtime.memory_monitor is not None),
            )
        )

    def _parse_iso(value: str) -> dt.datetime | None:
        return _parse_iso_timestamp(value)

    def _semantic_metrics_from_payload(payload: Any) -> dict[str, Any]:
        return _semantic_metrics_from_payload_helper(payload)

    def _reasoning_layer_metrics_from_payload(payload: Any) -> dict[str, Any]:
        return _reasoning_layer_metrics_from_payload_helper(payload)

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
            await _run_memory_quality_tuning_tick_helper(
                runtime=runtime,
                now=dt.datetime.now(dt.timezone.utc),
                tuning_runner_state=tuning_runner_state,
                collect_memory_quality_inputs=_collect_memory_quality_inputs,
                parse_iso=_parse_iso,
                plan_tuning_action=_plan_tuning_action_helper,
                resolve_notify_variant=_resolve_tuning_notify_variant,
                resolve_backfill_limit=_resolve_tuning_backfill_limit,
                resolve_snapshot_tag=_resolve_tuning_snapshot_tag,
                build_tuning_action_entry=_build_tuning_action_entry_helper,
                record_tuning_runner_action=_record_tuning_runner_action_helper,
                build_tuning_patch=_build_tuning_patch_helper,
                resolve_tuning_layer=_resolve_tuning_layer,
                send_autonomy_notice=_send_autonomy_notice,
                record_autonomy_event=_record_autonomy_event,
                tuning_loop_interval_seconds=tuning_loop_interval_seconds,
                tuning_loop_timeout_seconds=tuning_loop_timeout_seconds,
                tuning_degrading_streak_threshold=tuning_degrading_streak_threshold,
                tuning_recent_actions_limit=tuning_recent_actions_limit,
                tuning_loop_cooldown_seconds=tuning_loop_cooldown_seconds,
                tuning_actions_per_hour_cap=tuning_actions_per_hour_cap,
                tuning_error_backoff_seconds=tuning_error_backoff_seconds,
                log_warning=lambda exc: bind_event("memory.quality.tuning").warning("tuning tick failed error={}", exc),
            )

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

        proactive_task = asyncio.create_task(
            _run_proactive_monitor_loop_helper(
                state=proactive_runner_state,
                stop_event=proactive_stop_event,
                interval_seconds=proactive_interval_seconds,
                is_running=lambda: proactive_running,
                submit_proactive_wake=_submit_proactive_wake,
                utc_now_iso=_utc_now_iso,
                log_error=lambda exc: bind_event("proactive.lifecycle").error("proactive loop tick failed error={}", exc),
            )
        )
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

    async def _start_self_evolution() -> None:
        nonlocal self_evolution_task, self_evolution_running
        if runtime.self_evolution is None:
            return
        status = runtime.self_evolution.status()
        self_evolution_runner_state["enabled"] = bool(status.get("background_enabled", status.get("enabled", False)))
        self_evolution_runner_state["cooldown_seconds"] = float(getattr(runtime.self_evolution, "cooldown_s", 3600.0))
        self_evolution_runner_state["activation_mode"] = str(status.get("activation_mode", "") or "")
        self_evolution_runner_state["activation_reason"] = str(status.get("activation_reason", "") or "")
        self_evolution_runner_state["enabled_for_sessions"] = list(status.get("enabled_for_sessions", []) or [])
        self_evolution_runner_state["autonomy_session_id"] = str(status.get("autonomy_session_id", "") or "")
        if not self_evolution_runner_state["enabled"]:
            self_evolution_running = False
            self_evolution_runner_state["running"] = False
            lifecycle.mark_component(
                "self_evolution",
                running=False,
                error=str(self_evolution_runner_state.get("activation_reason", "") or "disabled"),
            )
            return
        if self_evolution_task is not None and not self_evolution_task.done():
            self_evolution_running = True
            self_evolution_runner_state["running"] = True
            return

        self_evolution_stop_event.clear()
        self_evolution_running = True
        self_evolution_runner_state["running"] = True
        self_evolution_runner_state["last_error"] = ""
        bind_event("self_evolution.lifecycle").info("self_evolution loop starting")

        async def _evo_loop() -> None:
            await _run_self_evolution_loop_helper(
                self_evolution=runtime.self_evolution,
                state=self_evolution_runner_state,
                stop_event=self_evolution_stop_event,
                utc_now_iso=_utc_now_iso,
                log_error=lambda exc: bind_event("self_evolution.lifecycle").error("self_evolution tick failed error={}", exc),
            )

        self_evolution_task = asyncio.create_task(_evo_loop())
        lifecycle.mark_component("self_evolution", running=True)
        bind_event("self_evolution.lifecycle").info("self_evolution loop started")

    async def _stop_self_evolution() -> None:
        nonlocal self_evolution_task, self_evolution_running
        self_evolution_running = False
        self_evolution_stop_event.set()
        self_evolution_runner_state["running"] = False
        if self_evolution_task is not None:
            self_evolution_task.cancel()
            try:
                await self_evolution_task
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                self_evolution_runner_state["last_error"] = str(exc)
                bind_event("self_evolution.lifecycle").error("self_evolution stop failed error={}", exc)
            self_evolution_task = None
        lifecycle.mark_component(
            "self_evolution",
            running=False,
            error=(
                str(self_evolution_runner_state.get("activation_reason", "") or "disabled")
                if not self_evolution_runner_state.get("enabled", False)
                else str(self_evolution_runner_state.get("last_error", "") or "")
            ),
        )
        bind_event("self_evolution.lifecycle").info("self_evolution loop stopped")

    async def _start_subagent_maintenance() -> None:
        nonlocal subagent_maintenance_task, subagent_maintenance_running, subagent_maintenance_interval_seconds
        subagent_maintenance_interval_seconds = max(1.0, float(runtime.engine.subagents.maintenance_interval_seconds()))
        subagent_maintenance_state["interval_seconds"] = subagent_maintenance_interval_seconds
        if subagent_maintenance_task is not None and not subagent_maintenance_task.done():
            subagent_maintenance_running = True
            subagent_maintenance_state["running"] = True
            return

        subagent_maintenance_stop_event.clear()
        subagent_maintenance_running = True
        subagent_maintenance_state["running"] = True
        subagent_maintenance_state["last_error"] = ""
        bind_event("subagents.lifecycle").info(
            "subagent maintenance loop starting interval_s={}",
            subagent_maintenance_interval_seconds,
        )

        async def _maintenance_loop() -> None:
            await _run_subagent_maintenance_loop_helper(
                engine=runtime.engine,
                state=subagent_maintenance_state,
                stop_event=subagent_maintenance_stop_event,
                interval_seconds=subagent_maintenance_interval_seconds,
                utc_now_iso=_utc_now_iso,
                log_warning=lambda exc: bind_event("subagents.lifecycle").warning("subagent maintenance tick failed error={}", exc),
            )

        subagent_maintenance_task = asyncio.create_task(_maintenance_loop())
        lifecycle.mark_component("subagent_maintenance", running=True)
        bind_event("subagents.lifecycle").info("subagent maintenance loop started")

    async def _stop_subagent_maintenance() -> None:
        nonlocal subagent_maintenance_task, subagent_maintenance_running
        subagent_maintenance_running = False
        subagent_maintenance_stop_event.set()
        subagent_maintenance_state["running"] = False
        if subagent_maintenance_task is None:
            return
        subagent_maintenance_task.cancel()
        try:
            await subagent_maintenance_task
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            subagent_maintenance_state["last_error"] = str(exc)
            bind_event("subagents.lifecycle").error("subagent maintenance stop failed error={}", exc)
        subagent_maintenance_task = None
        bind_event("subagents.lifecycle").info("subagent maintenance loop stopped")

    async def _run_job_dispatch(job: Any) -> str:
        """Worker function dispatched for each job by kind."""
        kind = str(getattr(job, "kind", "") or "").strip()
        payload = dict(getattr(job, "payload", {}) or {})
        session_id = str(getattr(job, "session_id", "") or "").strip() or "jobs:system"
        payload_channel = str(payload.get("channel", "") or "").strip() or None
        raw_chat_id = payload.get("chat_id")
        if raw_chat_id is None:
            raw_chat_id = payload.get("target")
        payload_chat_id = None
        if isinstance(raw_chat_id, (str, int)) and not isinstance(raw_chat_id, bool):
            payload_chat_id = str(raw_chat_id).strip() or None
        raw_runtime_metadata = payload.get("runtime_metadata")
        payload_runtime_metadata = dict(raw_runtime_metadata) if isinstance(raw_runtime_metadata, dict) and raw_runtime_metadata else None
        if kind == "agent_run":
            task_text = str(payload.get("task", "") or "").strip()
            if not task_text:
                raise ValueError("agent_run job missing 'task' in payload")
            timeout_s = float(payload.get("timeout_s", 120.0) or 120.0)
            result = await _run_engine_with_timeout(
                engine=runtime.engine,
                session_id=session_id,
                user_text=task_text,
                timeout_s=timeout_s,
                channel=payload_channel,
                chat_id=payload_chat_id,
                runtime_metadata=payload_runtime_metadata,
            )
            return str(getattr(result, "text", "") or "").strip() or "ok"
        if kind == "skill_exec":
            skill_name = str(payload.get("skill", "") or "").strip()
            if not skill_name:
                raise ValueError("skill_exec job missing 'skill' in payload")
            skill_content = runtime.skills_loader.load_skill_content(skill_name)
            if skill_content is None:
                raise ValueError(f"skill not found: {skill_name}")
            task_text = str(payload.get("task", "") or "").strip() or f"Execute skill: {skill_name}"
            timeout_s = float(payload.get("timeout_s", 120.0) or 120.0)
            combined_text = f"Skill context:\n{skill_content}\n\nTask: {task_text}"
            result = await _run_engine_with_timeout(
                engine=runtime.engine,
                session_id=session_id,
                user_text=combined_text,
                timeout_s=timeout_s,
                channel=payload_channel,
                chat_id=payload_chat_id,
                runtime_metadata=payload_runtime_metadata,
            )
            return str(getattr(result, "text", "") or "").strip() or "ok"
        raise ValueError(f"unsupported job kind: {kind!r} — use agent_run, skill_exec, or custom")

    async def _start_job_workers() -> None:
        nonlocal job_workers_started
        if runtime.job_queue is None:
            return
        if job_workers_started:
            status = runtime.job_queue.worker_status()
            if status.get("running", False):
                return
        runtime.job_queue.start(_run_job_dispatch)
        job_workers_started = True
        lifecycle.mark_component("job_workers", running=True)
        bind_event("jobs.lifecycle").info(
            "job workers started concurrency={}",
            runtime.job_queue._concurrency,
        )

    async def _stop_job_workers() -> None:
        nonlocal job_workers_started
        if runtime.job_queue is None:
            return
        job_workers_started = False
        await runtime.job_queue.stop()
        lifecycle.mark_component("job_workers", running=False)
        bind_event("jobs.lifecycle").info("job workers stopped")

    runtime.autonomy = AutonomyService(
        enabled=bool(cfg.gateway.autonomy.enabled),
        interval_s=float(cfg.gateway.autonomy.interval_s or 900),
        cooldown_s=float(cfg.gateway.autonomy.cooldown_s or 300),
        timeout_s=float(cfg.gateway.autonomy.timeout_s or 45.0),
        max_queue_backlog=int(cfg.gateway.autonomy.max_queue_backlog or 200),
        session_id=str(cfg.gateway.autonomy.session_id or "autonomy:system"),
        snapshot_callback=_autonomy_snapshot_payload,
        run_callback=_run_autonomy_tick,
    )

    async def _supervisor_incident_checks() -> list[SupervisorIncident]:
        return await _collect_supervisor_incidents_helper(
            incident_cls=SupervisorIncident,
            cfg=cfg,
            runtime=runtime,
            self_evolution_task=self_evolution_task,
            self_evolution_running=self_evolution_running,
            self_evolution_runner_state=self_evolution_runner_state,
            subagent_maintenance_task=subagent_maintenance_task,
            subagent_maintenance_running=subagent_maintenance_running,
            subagent_maintenance_state=subagent_maintenance_state,
            proactive_task=proactive_task,
            proactive_running=proactive_running,
            proactive_runner_state=proactive_runner_state,
            tuning_task=tuning_task,
            tuning_running=tuning_running,
            tuning_runner_state=tuning_runner_state,
            background_task_snapshot=_background_task_snapshot,
            provider_telemetry_snapshot=_provider_telemetry_snapshot,
        )

    async def _handle_supervisor_incident(incident: SupervisorIncident) -> None:
        await _handle_supervisor_incident_helper(
            incident=incident,
            notice_until=supervisor_incident_notice_until,
            cooldown_s=max(30.0, float(cfg.gateway.supervisor.cooldown_s or 0.0)),
            now_monotonic=time.monotonic,
            record_autonomy_event=_record_autonomy_event,
            send_autonomy_notice=_send_autonomy_notice,
        )

    async def _recover_supervised_component(component: str, reason: str) -> bool:
        bind_event("supervisor.recover").warning("runtime recover component={} reason={}", component, reason)
        async def _recover_self_evolution() -> bool:
            await _start_self_evolution()
            _refresh_runtime_components()
            self_evolution_state, _self_evolution_error = _background_task_snapshot(
                self_evolution_task,
                running=self_evolution_running,
                last_error=str(self_evolution_runner_state.get("last_error", "") or ""),
            )
            return bool(self_evolution_runner_state.get("enabled", False) and self_evolution_state == "running")

        async def _recover_channels_dispatcher() -> bool:
            await runtime.channels.start_dispatcher_loop()
            _refresh_runtime_components()
            return bool(runtime.channels.dispatcher_diagnostics().get("running", False))

        async def _recover_channels_recovery() -> bool:
            await runtime.channels.start_recovery_supervisor()
            _refresh_runtime_components()
            return bool(runtime.channels.recovery_diagnostics().get("running", False))

        async def _recover_heartbeat() -> bool:
            await runtime.heartbeat.start(_submit_heartbeat_wake)
            _refresh_runtime_components()
            return bool(runtime.heartbeat.status().get("running", False))

        async def _recover_cron() -> bool:
            await runtime.cron.start(_submit_cron_wake)
            _refresh_runtime_components()
            return bool(runtime.cron.status().get("running", False))

        async def _recover_autonomy_wake() -> bool:
            await runtime.autonomy_wake.start(_dispatch_autonomy_wake)
            _refresh_runtime_components()
            return bool(runtime.autonomy_wake.status().get("running", False))

        async def _recover_autonomy() -> bool:
            if runtime.autonomy is not None:
                await runtime.autonomy.start()
                _refresh_runtime_components()
                return bool(runtime.autonomy.status().get("running", False))
            return False

        async def _recover_skills_watcher() -> bool:
            await runtime.skills_loader.start_watcher()
            _refresh_runtime_components()
            return bool(runtime.skills_loader.watcher_status().get("running", False))

        async def _recover_subagent_maintenance() -> bool:
            await _start_subagent_maintenance()
            _refresh_runtime_components()
            maintenance_state, _maintenance_error = _background_task_snapshot(
                subagent_maintenance_task,
                running=subagent_maintenance_running,
                last_error=str(subagent_maintenance_state.get("last_error", "") or ""),
            )
            return maintenance_state == "running"

        async def _recover_proactive_monitor() -> bool:
            await _start_proactive_monitor()
            _refresh_runtime_components()
            proactive_state, _proactive_error = _background_task_snapshot(
                proactive_task,
                running=proactive_running,
                last_error=str(proactive_runner_state.get("last_error", "") or ""),
            )
            return proactive_state == "running"

        async def _recover_memory_quality_tuning() -> bool:
            await _start_memory_quality_tuning()
            _refresh_runtime_components()
            tuning_state, _tuning_error = _background_task_snapshot(
                tuning_task,
                running=tuning_running,
                last_error=str(tuning_runner_state.get("last_error", "") or ""),
            )
            return tuning_state == "running"

        async def _recover_job_workers() -> bool:
            if runtime.job_queue is not None:
                await _start_job_workers()
                _refresh_runtime_components()
                return bool(runtime.job_queue.worker_status().get("running", False))
            return False

        return await _recover_supervised_component_helper(
            component=component,
            reason=reason,
            recoverers={
                "self_evolution": _recover_self_evolution,
                "channels_dispatcher": _recover_channels_dispatcher,
                "channels_recovery": _recover_channels_recovery,
                "heartbeat": _recover_heartbeat,
                "cron": _recover_cron,
                "autonomy_wake": _recover_autonomy_wake,
                "autonomy": _recover_autonomy,
                "skills_watcher": _recover_skills_watcher,
                "subagent_maintenance": _recover_subagent_maintenance,
                "proactive_monitor": _recover_proactive_monitor,
                "memory_quality_tuning": _recover_memory_quality_tuning,
                "job_workers": _recover_job_workers,
            },
            record_autonomy_event=_record_autonomy_event,
            send_autonomy_notice=_send_autonomy_notice,
        )

    supervisor_component_policies = {
        "self_evolution": SupervisorComponentPolicy(max_recoveries=4, budget_window_s=3600.0),
        "channels_dispatcher": SupervisorComponentPolicy(max_recoveries=8, budget_window_s=3600.0),
        "channels_recovery": SupervisorComponentPolicy(max_recoveries=8, budget_window_s=3600.0),
        "heartbeat": SupervisorComponentPolicy(max_recoveries=12, budget_window_s=3600.0),
        "cron": SupervisorComponentPolicy(max_recoveries=8, budget_window_s=3600.0),
        "autonomy_wake": SupervisorComponentPolicy(max_recoveries=16, budget_window_s=3600.0),
        "autonomy": SupervisorComponentPolicy(max_recoveries=8, budget_window_s=3600.0),
        "skills_watcher": SupervisorComponentPolicy(max_recoveries=6, budget_window_s=3600.0),
        "subagent_maintenance": SupervisorComponentPolicy(max_recoveries=8, budget_window_s=3600.0),
        "proactive_monitor": SupervisorComponentPolicy(max_recoveries=6, budget_window_s=3600.0),
        "memory_quality_tuning": SupervisorComponentPolicy(max_recoveries=4, budget_window_s=3600.0),
        "job_workers": SupervisorComponentPolicy(max_recoveries=8, budget_window_s=3600.0),
    }

    runtime.supervisor = RuntimeSupervisor(
        interval_s=cfg.gateway.supervisor.interval_s,
        cooldown_s=cfg.gateway.supervisor.cooldown_s,
        incident_checks=_supervisor_incident_checks,
        recover=_recover_supervised_component,
        on_incident=_handle_supervisor_incident,
        component_policies=supervisor_component_policies,
    )

    async def _resume_recoverable_subagents() -> dict[str, Any]:
        component = lifecycle.components.setdefault(
            "subagent_replay",
            {
                "enabled": True,
                "running": False,
                "last_error": "",
                "replayed": 0,
                "replayed_groups": 0,
                "failed": 0,
                "failed_groups": 0,
                "last_group_ids": [],
                "last_run_iso": "",
            },
        )
        return await _resume_recoverable_subagents_helper(
            component=component,
            engine=runtime.engine,
            record_autonomy_event=_record_autonomy_event,
            send_autonomy_notice=_send_autonomy_notice,
            log_warning=lambda *args: bind_event("gateway.subagents").warning(*args),
            log_info=lambda *args: bind_event("gateway.subagents").info(*args),
            now_iso=lambda: dt.datetime.now(dt.timezone.utc).isoformat(),
        )

    async def _start_subsystems() -> None:
        await _start_subsystems_helper(
            cfg=cfg,
            runtime=runtime,
            lifecycle=lifecycle,
            dispatch_autonomy_wake=_dispatch_autonomy_wake,
            submit_cron_wake=_submit_cron_wake,
            submit_heartbeat_wake=_submit_heartbeat_wake,
            start_subagent_maintenance=_start_subagent_maintenance,
            stop_subagent_maintenance=_stop_subagent_maintenance,
            start_job_workers=_start_job_workers,
            stop_job_workers=_stop_job_workers,
            start_proactive_monitor=_start_proactive_monitor,
            stop_proactive_monitor=_stop_proactive_monitor,
            start_memory_quality_tuning=_start_memory_quality_tuning,
            stop_memory_quality_tuning=_stop_memory_quality_tuning,
            start_self_evolution=_start_self_evolution,
            stop_self_evolution=_stop_self_evolution,
            resume_recoverable_subagents=_resume_recoverable_subagents,
            run_startup_bootstrap_cycle=_run_startup_bootstrap_cycle,
            record_autonomy_event=_record_autonomy_event,
            send_autonomy_notice=_send_autonomy_notice,
        )

    async def _stop_subsystems() -> None:
        await _stop_subsystems_helper(
            cfg=cfg,
            runtime=runtime,
            lifecycle=lifecycle,
            stop_subagent_maintenance=_stop_subagent_maintenance,
            stop_proactive_monitor=_stop_proactive_monitor,
            stop_memory_quality_tuning=_stop_memory_quality_tuning,
            stop_self_evolution=_stop_self_evolution,
        )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        lifecycle.phase = "starting"
        lifecycle.ready = False
        bind_event("gateway.lifecycle").info("gateway startup begin host={} port={}", cfg.gateway.host, cfg.gateway.port)
        bus_connect = getattr(runtime.bus, "connect", None)
        if callable(bus_connect):
            await bus_connect()
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
            drain_turn_persistence = getattr(runtime.engine, "drain_turn_persistence", None)
            if callable(drain_turn_persistence):
                await drain_turn_persistence()
            await _stop_subsystems()
            bus_close = getattr(runtime.bus, "close", None)
            if callable(bus_close):
                await bus_close()
            lifecycle.phase = "stopped"
            bind_event("gateway.lifecycle").info("gateway shutdown complete")

    app = FastAPI(title="ClawLite Gateway", version="1.0.0", lifespan=lifespan)
    app.state.runtime = runtime
    app.state.lifecycle = lifecycle
    app.state.auth_guard = auth_guard
    app.state.http_telemetry = http_telemetry
    app.state.ws_telemetry = ws_telemetry
    rate_limit_cfg = cfg.gateway.rate_limit
    gateway_rate_limiter = GatewayRateLimiter(
        enabled=bool(rate_limit_cfg.enabled),
        window_s=float(rate_limit_cfg.window_s),
        chat_requests_per_window=int(rate_limit_cfg.chat_requests_per_window),
        ws_chat_requests_per_window=int(rate_limit_cfg.ws_chat_requests_per_window),
        exempt_loopback=bool(rate_limit_cfg.exempt_loopback),
    )
    app.state.gateway_rate_limiter = gateway_rate_limiter
    telegram_webhook_path = _normalize_webhook_path(cfg.channels.telegram.webhook_path)
    whatsapp_webhook_path = _normalize_webhook_path(
        getattr(cfg.channels.whatsapp, "webhook_path", "/api/webhooks/whatsapp"),
        default="/api/webhooks/whatsapp",
    )

    @app.middleware("http")
    async def _http_telemetry_middleware(request: Request, call_next):
        request_id = _normalize_request_id(request.headers.get(_REQUEST_ID_HEADER_NAME, ""))
        request.state.request_id = request_id
        started_at = time.perf_counter()
        await http_telemetry.start(method=request.method, path=request.url.path, request_id=request_id)
        status_code = 500
        try:
            response = await call_next(request)
            status_code = int(getattr(response, "status_code", 500) or 500)
            response.headers[_REQUEST_ID_HEADER_NAME] = request_id
            return response
        except HTTPException as exc:
            status_code = int(exc.status_code)
            raise
        except Exception:
            status_code = 500
            raise
        finally:
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            await http_telemetry.finish(
                status_code=status_code,
                latency_ms=elapsed_ms,
                request_id=request_id,
                method=request.method,
                path=request.url.path,
            )
            if status_code >= 400:
                bind_event("gateway.http").warning(
                    "http request failed method={} path={} status={} request_id={}",
                    request.method,
                    request.url.path,
                    status_code,
                    request_id,
                )

    @app.exception_handler(HTTPException)
    async def _http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail
        request_id = _request_id_from_request(request)
        detail_text = str(detail or "").strip() if isinstance(detail, str) else "http_error"
        await http_telemetry.record_error(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status_code=exc.status_code,
            code=detail_text if isinstance(detail, str) else "http_error",
            message=detail_text,
        )
        if isinstance(detail, str):
            payload: dict[str, Any] = {
                "error": detail,
                "status": exc.status_code,
                "code": detail,
                "request_id": request_id,
            }
        else:
            payload = {
                "error": "http_error",
                "status": exc.status_code,
                "code": "http_error",
                "detail": detail,
                "request_id": request_id,
            }
        return JSONResponse(
            status_code=exc.status_code,
            content=payload,
            headers={_REQUEST_ID_HEADER_NAME: request_id},
        )

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, _: Exception) -> JSONResponse:
        request_id = _request_id_from_request(request)
        await http_telemetry.record_error(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status_code=500,
            code="internal_server_error",
            message="internal_server_error",
        )
        payload = {
            "error": "internal_server_error",
            "status": 500,
            "code": "internal_server_error",
            "request_id": request_id,
        }
        return JSONResponse(
            status_code=500,
            content=payload,
            headers={_REQUEST_ID_HEADER_NAME: request_id},
        )

    def _parse_failover_cooling_down(raw: str) -> str:
        parts: list[str] = []
        for item in str(raw or "").split(","):
            text = str(item or "").strip()
            if not text:
                continue
            model, sep, remaining_raw = text.rpartition(":")
            if not sep:
                parts.append(text)
                continue
            try:
                remaining_s = float(remaining_raw)
            except ValueError:
                parts.append(text)
                continue
            label = model.strip() or text
            parts.append(f"{label} ({remaining_s:.1f}s)")
        return ", ".join(parts[:4])

    def _active_provider_context() -> tuple[str, str]:
        provider_obj = getattr(runtime.engine, "provider", None)
        active_model = str(
            getattr(provider_obj, "model", "") or getattr(runtime.engine, "provider_model", "") or cfg.agents.defaults.model or cfg.provider.model
        ).strip()
        active_provider = str(getattr(provider_obj, "provider_name", "") or "").strip().lower().replace("-", "_")
        if not active_provider:
            active_provider = detect_provider_name(active_model)
        if active_provider == "failover" and active_model:
            active_provider = detect_provider_name(active_model)
        return active_provider, active_model

    def _provider_guidance_tail(provider_name: str, active_model: str) -> str:
        normalized_provider = str(provider_name or "").strip().lower().replace("-", "_")
        profile = provider_profile(normalized_provider)
        recommended_model = default_provider_model(normalized_provider)
        tail_parts: list[str] = []
        if recommended_model and recommended_model != active_model:
            tail_parts.append(f"Recommended model: {recommended_model}.")
        if profile.onboarding_hint:
            tail_parts.append(f"Hint: {profile.onboarding_hint}")
        if not tail_parts:
            return ""
        return " " + " ".join(tail_parts)

    def _provider_error_payload(exc: RuntimeError) -> tuple[int, str]:
        message = str(exc)
        active_provider, active_model = _active_provider_context()
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
                f"Missing API key for provider '{provider}'. Set CLAWLITE_LITELLM_API_KEY or the provider-specific key."
                + _provider_guidance_tail(provider, active_model),
            )
        if message.startswith("provider_auth_error:"):
            provider = message.rsplit(":", 1)[-1]
            return (
                502,
                f"Authentication failed for provider '{provider}'. Review the configured key and re-authenticate if needed."
                + _provider_guidance_tail(provider, active_model),
            )
        if message.startswith("provider_config_error:missing_base_url:"):
            provider = message.rsplit(":", 1)[-1]
            return (
                400,
                f"Missing base URL for provider '{provider}'. Configure CLAWLITE_LITELLM_BASE_URL."
                + _provider_guidance_tail(provider, active_model),
            )
        if message.startswith("provider_config_error:ollama_unreachable:"):
            base_url = message.partition("provider_config_error:ollama_unreachable:")[2].strip()
            suffix = f" em {base_url}" if base_url else ""
            return (503, f"Local Ollama runtime is unavailable{suffix}. Start 'ollama serve' and confirm port 11434.")
        if message.startswith("provider_config_error:ollama_model_missing:"):
            model_name = message.partition("provider_config_error:ollama_model_missing:")[2].strip() or active_model
            return (400, f"Local model '{model_name}' is not loaded in Ollama. Run 'ollama pull {model_name}'.")
        if message.startswith("provider_config_error:vllm_unreachable:"):
            base_url = message.partition("provider_config_error:vllm_unreachable:")[2].strip()
            suffix = f" em {base_url}" if base_url else ""
            return (503, f"Local vLLM runtime is unavailable{suffix}. Start the server and confirm the configured base URL.")
        if message.startswith("provider_config_error:vllm_model_missing:"):
            model_name = message.partition("provider_config_error:vllm_model_missing:")[2].strip() or active_model
            return (400, f"Model '{model_name}' was not found in vLLM. Serve the model on the server or adjust the configuration.")
        if message.startswith("provider_config_error:"):
            provider_label = active_provider or "active"
            return (
                400,
                f"Invalid configuration for provider '{provider_label}'. Review the model, base URL, and API key."
                + _provider_guidance_tail(provider_label, active_model),
            )
        if message.startswith("provider_failover_cooldown:all_candidates_cooling_down:"):
            detail = message.partition("provider_failover_cooldown:all_candidates_cooling_down:")[2]
            formatted = _parse_failover_cooling_down(detail)
            suffix = f" Cooling candidates: {formatted}." if formatted else ""
            return (503, f"All failover provider candidates are temporarily in cooldown.{suffix}")
        if message.startswith("provider_circuit_open:"):
            _, _, raw = message.partition("provider_circuit_open:")
            provider, _, cooldown_raw = raw.partition(":")
            provider_name = provider.strip() or "unknown"
            cooldown_hint = ""
            try:
                cooldown_hint = f" Wait about {float(cooldown_raw):.1f}s before trying again."
            except ValueError:
                cooldown_hint = ""
            return (
                503,
                f"Provider '{provider_name}' entered protection mode after consecutive failures.{cooldown_hint}"
                + _provider_guidance_tail(provider_name, active_model),
            )
        if provider_http_code == "400":
            provider_label = active_provider or "remote"
            hint = provider_http_detail or "Review the provider model, API key, and base URL."
            return (
                400,
                f"Invalid request to provider '{provider_label}' (400). {hint}" + _provider_guidance_tail(provider_label, active_model),
            )
        if provider_http_code in {"401", "403"}:
            provider_label = active_provider or "remote"
            return (
                502,
                f"Authentication failed for provider '{provider_label}' (HTTP {provider_http_code}). Review CLAWLITE_MODEL and CLAWLITE_LITELLM_API_KEY."
                + (f" Detail: {provider_http_detail}" if provider_http_detail else "")
                + _provider_guidance_tail(provider_label, active_model),
            )
        if provider_http_code == "429" or message == "provider_429_exhausted":
            provider_label = active_provider or "remote"
            if is_quota_429_error(message):
                detail = f" Detail: {provider_http_detail}" if provider_http_detail else ""
                return (
                    429,
                    f"Quota or billing has been exhausted for provider '{provider_label}'.{detail}"
                    + _provider_guidance_tail(provider_label, active_model),
                )
            return (
                429,
                f"Provider '{provider_label}' is rate-limiting requests. Try again shortly."
                + _provider_guidance_tail(provider_label, active_model),
            )
        if provider_http_code:
            provider_label = active_provider or "remote"
            detail = f" Detail: {provider_http_detail}" if provider_http_detail else ""
            return (
                502,
                f"Provider '{provider_label}' failed (HTTP {provider_http_code}).{detail}"
                + _provider_guidance_tail(provider_label, active_model),
            )
        if message.startswith("provider_network_error:"):
            provider_label = active_provider or "remote"
            return (
                503,
                f"Provider '{provider_label}' is currently unavailable (network error)." + _provider_guidance_tail(provider_label, active_model),
            )
        if message.startswith("codex_http_error:401"):
            return (502, "Authentication failed for Codex (401). Run the Codex OAuth login flow again.")
        if message == "codex_auth_error:missing_access_token":
            return (
                400,
                "Missing Codex OAuth token. Run 'clawlite provider login openai-codex' to authenticate.",
            )
        if message.startswith("codex_auth_error:401"):
            return (
                502,
                "Codex OAuth session is invalid or expired (401). Run 'clawlite provider login openai-codex' again.",
            )
        if message.startswith("codex_http_error:429") or message == "codex_429_exhausted":
            return (429, "Codex is rate-limiting requests. Try again shortly.")
        if message.startswith("codex_http_error:"):
            code = message.split(":", 1)[1]
            return (502, f"Codex failed (HTTP {code}).")
        if message.startswith("codex_network_error:"):
            return (503, "Codex is currently unavailable (network error).")
        return (500, "Internal failure while processing the request.")

    @app.get("/health")
    async def health(request: Request) -> dict[str, Any]:
        return await status_handlers.health(request)

    @app.get("/health/config")
    async def health_config(request: Request) -> dict[str, Any]:
        return await status_handlers.health_config(request)

    @app.get("/health/tools")
    async def health_tools(request: Request) -> dict[str, Any]:
        return await status_handlers.health_tools(request)

    @app.get("/health/providers")
    async def health_providers(request: Request) -> dict[str, Any]:
        return await status_handlers.health_providers(request)

    @app.get("/metrics/providers")
    async def metrics_providers(request: Request) -> dict[str, Any]:
        return await status_handlers.metrics_providers(request)

    def _dashboard_state_payload() -> dict[str, Any]:
        generated_at = _utc_now_iso()
        control_plane = _control_plane_payload(server_time=generated_at)
        return _dashboard_state_payload_runtime(
            runtime=runtime,
            contract_version=GATEWAY_CONTRACT_VERSION,
            generated_at=generated_at,
            control_plane=control_plane,
            control_plane_to_dict=_control_plane_to_dict,
            recent_dashboard_sessions_payload=_recent_dashboard_sessions_payload,
            dashboard_channels_summary_payload=_dashboard_channels_summary_payload,
            dashboard_cron_summary_payload=_dashboard_cron_summary_payload,
            dashboard_self_evolution_summary_payload=_dashboard_self_evolution_summary_payload,
            dashboard_memory_summary_payload=_dashboard_memory_summary_payload,
            operator_channel_summary=_operator_channel_summary,
            provider_telemetry_snapshot=_provider_telemetry_snapshot,
            provider_autonomy_snapshot=_provider_autonomy_snapshot,
            build_dashboard_handoff=build_dashboard_handoff,
            memory_profile_snapshot_fn=memory_profile_snapshot,
            memory_suggest_snapshot_fn=memory_suggest_snapshot,
            memory_version_snapshot_fn=memory_version_snapshot,
            ws_snapshot_payload=ws_telemetry.snapshot_nowait,
            self_evolution_runner_state=self_evolution_runner_state,
            dashboard_state_payload_builder=_dashboard_state_payload_builder,
        )

    async def _diagnostics_response_payload() -> DiagnosticsResponse:
        generated_at = _utc_now_iso()
        _refresh_runtime_components()
        payload = await _diagnostics_payload_builder(
            cfg=cfg,
            runtime=runtime,
            contract_version=GATEWAY_CONTRACT_VERSION,
            generated_at=generated_at,
            started_monotonic=started_monotonic,
            control_plane_payload=_control_plane_payload(generated_at),
            bootstrap_payload=_bootstrap_status_snapshot(),
            memory_quality_cache=memory_quality_cache,
            collect_memory_analysis_metrics=_collect_memory_analysis_metrics,
            engine_memory_payloads=_engine_memory_payloads,
            engine_memory_quality_payload=_engine_memory_quality_payload,
            engine_memory_integration_payload=_engine_memory_integration_payload,
            provider_telemetry_snapshot=_provider_telemetry_snapshot,
            memory_monitor_payload=_memory_monitor_payload,
            http_snapshot=http_telemetry.snapshot,
            ws_snapshot=ws_telemetry.snapshot,
            proactive_runner_state=proactive_runner_state,
            cron_wake_state=cron_wake_state,
            subagent_maintenance_state=subagent_maintenance_state,
            tuning_runner_state=tuning_runner_state,
            self_evolution_runner_state=self_evolution_runner_state,
        )
        return DiagnosticsResponse(**payload)

    status_handlers = GatewayStatusHandlers(
        auth_guard=auth_guard,
        diagnostics_require_auth=cfg.gateway.diagnostics.require_auth,
        cfg=cfg,
        runtime=runtime,
        lifecycle=lifecycle,
        status_payload_fn=lambda: _control_plane_payload(),
        dashboard_state_payload_fn=_dashboard_state_payload,
        diagnostics_payload_fn=_diagnostics_response_payload,
        token_payload_fn=lambda: {
            "token_configured": bool(auth_guard.token),
            "token_masked": _mask_secret(auth_guard.token),
            "mode": auth_guard.mode,
            "header_name": auth_guard.header_name,
            "query_param": auth_guard.query_param,
            "dashboard_handoff_enabled": bool(auth_guard.token),
            "dashboard_handoff_header_name": auth_guard.dashboard_handoff_header_name,
            "dashboard_handoff_query_param": auth_guard.dashboard_handoff_query_param,
            "dashboard_session_enabled": bool(auth_guard.dashboard_sessions) and bool(auth_guard.token),
            "dashboard_session_header_name": auth_guard.dashboard_session_header_name,
            "dashboard_session_query_param": auth_guard.dashboard_session_query_param,
            "dashboard_client_header_name": auth_guard.dashboard_client_header_name,
            "dashboard_client_query_param": auth_guard.dashboard_client_query_param,
        },
        dashboard_session_payload_fn=lambda **payload: (
            (
                lambda record, bootstrap_kind, client_id: {
                    "ok": True,
                    "token_type": "dashboard_session",
                    "bootstrap_kind": bootstrap_kind,
                    "session_token": record.token,
                    "expires_at": dashboard_session_expiry_iso(record),
                    "expires_in_s": auth_guard.dashboard_sessions.ttl_seconds if auth_guard.dashboard_sessions is not None else 0,
                    "header_name": auth_guard.dashboard_session_header_name,
                    "query_param": auth_guard.dashboard_session_query_param,
                    "client_header_name": auth_guard.dashboard_client_header_name,
                    "client_query_param": auth_guard.dashboard_client_query_param,
                    "client_id": client_id,
                    "handoff_header_name": auth_guard.dashboard_handoff_header_name,
                    "handoff_query_param": auth_guard.dashboard_handoff_query_param,
                }
            )(
                payload.get("record"),
                str(payload.get("bootstrap_kind") or ""),
                str(payload.get("client_id") or ""),
            )
            if auth_guard.dashboard_sessions is not None and auth_guard.token and payload.get("record") is not None
            else {"ok": False, "error": "dashboard_session_disabled"}
        ),
    )
    websocket_handlers = GatewayWebSocketHandlers(
        auth_guard=auth_guard,
        diagnostics_require_auth=cfg.gateway.diagnostics.require_auth,
        runtime=runtime,
        lifecycle=lifecycle,
        ws_telemetry=ws_telemetry,
        contract_version=GATEWAY_CONTRACT_VERSION,
        rate_limiter=gateway_rate_limiter,
        run_engine_with_timeout_fn=lambda session_id, user_text, **context: _run_engine_with_timeout(
            engine=runtime.engine,
            session_id=session_id,
            user_text=user_text,
            timeout_s=GATEWAY_CHAT_WS_ENGINE_TIMEOUT_S,
            **context,
        ),
        stream_engine_with_timeout_fn=lambda session_id, user_text, **context: _stream_engine_with_timeout(
            engine=runtime.engine,
            session_id=session_id,
            user_text=user_text,
            timeout_s=GATEWAY_CHAT_WS_ENGINE_TIMEOUT_S,
            **context,
        ),
        provider_error_payload_fn=_provider_error_payload,
        finalize_bootstrap_for_user_turn_fn=_finalize_bootstrap_for_user_turn,
        control_plane_payload_fn=_control_plane_payload,
        control_plane_to_dict_fn=_control_plane_to_dict,
        build_tools_catalog_payload_fn=build_tools_catalog_payload,
        parse_include_schema_flag_fn=parse_include_schema_flag,
        utc_now_iso_fn=_utc_now_iso,
        coalesce_enabled=cfg.gateway.websocket.coalesce_enabled,
        coalesce_min_chars=cfg.gateway.websocket.coalesce_min_chars,
        coalesce_max_chars=cfg.gateway.websocket.coalesce_max_chars,
        coalesce_profile=cfg.gateway.websocket.coalesce_profile,
    )
    request_handlers = GatewayRequestHandlers(
        auth_guard=auth_guard,
        diagnostics_require_auth=cfg.gateway.diagnostics.require_auth,
        runtime=runtime,
        dashboard_asset_root=_DASHBOARD_ASSET_ROOT,
        dashboard_bootstrap_token=_DASHBOARD_BOOTSTRAP_TOKEN,
        run_engine_with_timeout_fn=lambda session_id, user_text, **context: _run_engine_with_timeout(
            engine=runtime.engine,
            session_id=session_id,
            user_text=user_text,
            timeout_s=GATEWAY_CHAT_WS_ENGINE_TIMEOUT_S,
            **context,
        ),
        provider_error_payload_fn=_provider_error_payload,
        finalize_bootstrap_for_user_turn_fn=_finalize_bootstrap_for_user_turn,
        build_tools_catalog_payload_fn=build_tools_catalog_payload,
        parse_include_schema_flag_fn=parse_include_schema_flag,
        control_plane_payload_fn=_control_plane_payload,
        dashboard_asset_text_fn=_dashboard_asset_text,
        render_root_dashboard_html_fn=_render_root_dashboard_html,
    )

    @app.get("/v1/status", response_model=ControlPlaneResponse)
    async def status(request: Request) -> ControlPlaneResponse:
        return await status_handlers.status(request)

    @app.get("/api/status", response_model=ControlPlaneResponse)
    async def api_status(request: Request) -> ControlPlaneResponse:
        return await status_handlers.status(request, allow_dashboard_session=True)

    @app.get("/v1/dashboard/state")
    async def dashboard_state(request: Request) -> dict[str, Any]:
        return await status_handlers.dashboard_state(request)

    @app.get("/api/dashboard/state")
    async def api_dashboard_state(request: Request) -> dict[str, Any]:
        return await status_handlers.dashboard_state(request, allow_dashboard_session=True)

    @app.get("/v1/diagnostics", response_model=DiagnosticsResponse)
    async def diagnostics(request: Request) -> DiagnosticsResponse:
        return await status_handlers.diagnostics(request)

    @app.get("/api/diagnostics", response_model=DiagnosticsResponse)
    async def api_diagnostics(request: Request) -> DiagnosticsResponse:
        return await status_handlers.diagnostics(request, allow_dashboard_session=True)

    @app.post("/api/dashboard/session")
    async def api_dashboard_session(request: Request) -> dict[str, Any]:
        return await status_handlers.dashboard_session(request)

    @app.post("/v1/control/channels/replay")
    async def channels_replay(request: Request, payload: ChannelReplayRequest | None = None) -> dict[str, Any]:
        return await control_handlers.channels_replay(request, payload or ChannelReplayRequest())

    @app.post("/api/channels/replay")
    async def api_channels_replay(request: Request, payload: ChannelReplayRequest | None = None) -> dict[str, Any]:
        return await control_handlers.channels_replay(request, payload or ChannelReplayRequest())

    @app.post("/v1/control/channels/recover")
    async def channels_recover(request: Request, payload: ChannelRecoverRequest | None = None) -> dict[str, Any]:
        return await control_handlers.channels_recover(request, payload or ChannelRecoverRequest())

    @app.post("/api/channels/recover")
    async def api_channels_recover(request: Request, payload: ChannelRecoverRequest | None = None) -> dict[str, Any]:
        return await control_handlers.channels_recover(request, payload or ChannelRecoverRequest())

    @app.post("/v1/control/channels/inbound-replay")
    async def channels_inbound_replay(
        request: Request, payload: ChannelInboundReplayRequest | None = None
    ) -> dict[str, Any]:
        return await control_handlers.channels_inbound_replay(request, payload or ChannelInboundReplayRequest())

    @app.post("/api/channels/inbound-replay")
    async def api_channels_inbound_replay(
        request: Request, payload: ChannelInboundReplayRequest | None = None
    ) -> dict[str, Any]:
        return await control_handlers.channels_inbound_replay(request, payload or ChannelInboundReplayRequest())

    @app.post("/v1/control/channels/telegram/refresh")
    async def telegram_refresh(request: Request, payload: TelegramRefreshRequest | None = None) -> dict[str, Any]:
        return await control_handlers.telegram_refresh(request, payload or TelegramRefreshRequest())

    @app.post("/api/channels/telegram/refresh")
    async def api_telegram_refresh(request: Request, payload: TelegramRefreshRequest | None = None) -> dict[str, Any]:
        return await control_handlers.telegram_refresh(request, payload or TelegramRefreshRequest())

    @app.post("/v1/control/channels/telegram/pairing/approve")
    async def telegram_pairing_approve(
        request: Request, payload: TelegramPairingApproveRequest | None = None
    ) -> dict[str, Any]:
        return await control_handlers.telegram_pairing_approve(request, payload or TelegramPairingApproveRequest())

    @app.post("/api/channels/telegram/pairing/approve")
    async def api_telegram_pairing_approve(
        request: Request, payload: TelegramPairingApproveRequest | None = None
    ) -> dict[str, Any]:
        return await control_handlers.telegram_pairing_approve(request, payload or TelegramPairingApproveRequest())

    @app.post("/v1/control/channels/telegram/pairing/reject")
    async def telegram_pairing_reject(
        request: Request, payload: TelegramPairingRejectRequest | None = None
    ) -> dict[str, Any]:
        return await control_handlers.telegram_pairing_reject(request, payload or TelegramPairingRejectRequest())

    @app.post("/api/channels/telegram/pairing/reject")
    async def api_telegram_pairing_reject(
        request: Request, payload: TelegramPairingRejectRequest | None = None
    ) -> dict[str, Any]:
        return await control_handlers.telegram_pairing_reject(request, payload or TelegramPairingRejectRequest())

    @app.post("/v1/control/channels/telegram/pairing/revoke")
    async def telegram_pairing_revoke(
        request: Request, payload: TelegramPairingRevokeRequest | None = None
    ) -> dict[str, Any]:
        return await control_handlers.telegram_pairing_revoke(request, payload or TelegramPairingRevokeRequest())

    @app.post("/api/channels/telegram/pairing/revoke")
    async def api_telegram_pairing_revoke(
        request: Request, payload: TelegramPairingRevokeRequest | None = None
    ) -> dict[str, Any]:
        return await control_handlers.telegram_pairing_revoke(request, payload or TelegramPairingRevokeRequest())

    @app.post("/v1/control/channels/telegram/offset/commit")
    async def telegram_offset_commit(
        request: Request, payload: TelegramOffsetCommitRequest | None = None
    ) -> dict[str, Any]:
        return await control_handlers.telegram_offset_commit(request, payload or TelegramOffsetCommitRequest())

    @app.post("/api/channels/telegram/offset/commit")
    async def api_telegram_offset_commit(
        request: Request, payload: TelegramOffsetCommitRequest | None = None
    ) -> dict[str, Any]:
        return await control_handlers.telegram_offset_commit(request, payload or TelegramOffsetCommitRequest())

    @app.post("/v1/control/channels/telegram/offset/sync")
    async def telegram_offset_sync(
        request: Request, payload: TelegramOffsetSyncRequest | None = None
    ) -> dict[str, Any]:
        return await control_handlers.telegram_offset_sync(request, payload or TelegramOffsetSyncRequest())

    @app.post("/api/channels/telegram/offset/sync")
    async def api_telegram_offset_sync(
        request: Request, payload: TelegramOffsetSyncRequest | None = None
    ) -> dict[str, Any]:
        return await control_handlers.telegram_offset_sync(request, payload or TelegramOffsetSyncRequest())

    @app.post("/v1/control/channels/telegram/offset/reset")
    async def telegram_offset_reset(
        request: Request, payload: TelegramOffsetResetRequest | None = None
    ) -> dict[str, Any]:
        return await control_handlers.telegram_offset_reset(request, payload or TelegramOffsetResetRequest())

    @app.post("/api/channels/telegram/offset/reset")
    async def api_telegram_offset_reset(
        request: Request, payload: TelegramOffsetResetRequest | None = None
    ) -> dict[str, Any]:
        return await control_handlers.telegram_offset_reset(request, payload or TelegramOffsetResetRequest())

    @app.post("/v1/control/provider/recover")
    async def provider_recover(request: Request, payload: ProviderRecoverRequest | None = None) -> dict[str, Any]:
        return await control_handlers.provider_recover(request, payload or ProviderRecoverRequest())

    @app.post("/api/provider/recover")
    async def api_provider_recover(request: Request, payload: ProviderRecoverRequest | None = None) -> dict[str, Any]:
        return await control_handlers.provider_recover(request, payload or ProviderRecoverRequest())

    @app.post("/v1/control/autonomy/wake")
    async def autonomy_wake(request: Request, payload: AutonomyWakeRequest | None = None) -> dict[str, Any]:
        return await control_handlers.autonomy_wake(request, payload or AutonomyWakeRequest())

    @app.post("/api/autonomy/wake")
    async def api_autonomy_wake(request: Request, payload: AutonomyWakeRequest | None = None) -> dict[str, Any]:
        return await control_handlers.autonomy_wake(request, payload or AutonomyWakeRequest())

    @app.post("/v1/control/memory/suggest/refresh")
    async def memory_suggest_refresh(
        request: Request, payload: MemorySuggestRefreshRequest | None = None
    ) -> dict[str, Any]:
        return await control_handlers.memory_suggest_refresh(request, payload or MemorySuggestRefreshRequest())

    @app.post("/api/memory/suggest/refresh")
    async def api_memory_suggest_refresh(
        request: Request, payload: MemorySuggestRefreshRequest | None = None
    ) -> dict[str, Any]:
        return await control_handlers.memory_suggest_refresh(request, payload or MemorySuggestRefreshRequest())

    @app.post("/v1/control/memory/doctor")
    async def memory_doctor(
        request: Request, payload: MemoryDoctorRequest | None = None
    ) -> dict[str, Any]:
        return await control_handlers.memory_doctor(request, payload or MemoryDoctorRequest())

    @app.post("/api/memory/doctor")
    async def api_memory_doctor(
        request: Request, payload: MemoryDoctorRequest | None = None
    ) -> dict[str, Any]:
        return await control_handlers.memory_doctor(request, payload or MemoryDoctorRequest())

    @app.post("/v1/control/memory/quality")
    async def memory_quality(
        request: Request, payload: MemoryQualityRequest | None = None
    ) -> dict[str, Any]:
        return await control_handlers.memory_quality(request, payload or MemoryQualityRequest())

    @app.post("/api/memory/quality")
    async def api_memory_quality(
        request: Request, payload: MemoryQualityRequest | None = None
    ) -> dict[str, Any]:
        return await control_handlers.memory_quality(request, payload or MemoryQualityRequest())

    @app.post("/v1/control/skills/refresh")
    async def skills_refresh(
        request: Request, payload: SkillsRefreshRequest | None = None
    ) -> dict[str, Any]:
        return await control_handlers.skills_refresh(request, payload or SkillsRefreshRequest())

    @app.post("/api/skills/refresh")
    async def api_skills_refresh(
        request: Request, payload: SkillsRefreshRequest | None = None
    ) -> dict[str, Any]:
        return await control_handlers.skills_refresh(request, payload or SkillsRefreshRequest())

    @app.post("/v1/control/skills/sync")
    async def skills_sync(
        request: Request, payload: SkillsSyncRequest | None = None
    ) -> dict[str, Any]:
        return await control_handlers.skills_sync(request, payload or SkillsSyncRequest())

    @app.post("/api/skills/sync")
    async def api_skills_sync(
        request: Request, payload: SkillsSyncRequest | None = None
    ) -> dict[str, Any]:
        return await control_handlers.skills_sync(request, payload or SkillsSyncRequest())

    @app.post("/v1/control/skills/doctor")
    async def skills_doctor(
        request: Request, payload: SkillsDoctorRequest | None = None
    ) -> dict[str, Any]:
        return await control_handlers.skills_doctor(request, payload or SkillsDoctorRequest())

    @app.post("/api/skills/doctor")
    async def api_skills_doctor(
        request: Request, payload: SkillsDoctorRequest | None = None
    ) -> dict[str, Any]:
        return await control_handlers.skills_doctor(request, payload or SkillsDoctorRequest())

    @app.post("/v1/control/skills/validate")
    async def skills_validate(
        request: Request, payload: SkillsValidateRequest | None = None
    ) -> dict[str, Any]:
        return await control_handlers.skills_validate(request, payload or SkillsValidateRequest())

    @app.post("/api/skills/validate")
    async def api_skills_validate(
        request: Request, payload: SkillsValidateRequest | None = None
    ) -> dict[str, Any]:
        return await control_handlers.skills_validate(request, payload or SkillsValidateRequest())

    @app.get("/v1/control/skills/managed")
    async def skills_managed(request: Request, status: str = "", query: str = "") -> dict[str, Any]:
        return await control_handlers.skills_managed(request, status=status, query=query)

    @app.get("/api/skills/managed")
    async def api_skills_managed(request: Request, status: str = "", query: str = "") -> dict[str, Any]:
        return await control_handlers.skills_managed(request, status=status, query=query)

    @app.post("/v1/control/memory/snapshot/create")
    async def memory_snapshot_create_route(
        request: Request, payload: MemorySnapshotCreateRequest | None = None
    ) -> dict[str, Any]:
        return await control_handlers.memory_snapshot_create(request, payload or MemorySnapshotCreateRequest())

    @app.post("/api/memory/snapshot/create")
    async def api_memory_snapshot_create(
        request: Request, payload: MemorySnapshotCreateRequest | None = None
    ) -> dict[str, Any]:
        return await control_handlers.memory_snapshot_create(request, payload or MemorySnapshotCreateRequest())

    @app.post("/v1/control/memory/snapshot/rollback")
    async def memory_snapshot_rollback_route(
        request: Request, payload: MemorySnapshotRollbackRequest | None = None
    ) -> dict[str, Any]:
        return await control_handlers.memory_snapshot_rollback(request, payload or MemorySnapshotRollbackRequest())

    @app.post("/api/memory/snapshot/rollback")
    async def api_memory_snapshot_rollback(
        request: Request, payload: MemorySnapshotRollbackRequest | None = None
    ) -> dict[str, Any]:
        return await control_handlers.memory_snapshot_rollback(request, payload or MemorySnapshotRollbackRequest())

    @app.post("/v1/control/channels/discord/refresh")
    async def discord_refresh(
        request: Request, payload: DiscordRefreshRequest | None = None
    ) -> dict[str, Any]:
        return await control_handlers.discord_refresh(request, payload or DiscordRefreshRequest())

    @app.post("/api/channels/discord/refresh")
    async def api_discord_refresh(
        request: Request, payload: DiscordRefreshRequest | None = None
    ) -> dict[str, Any]:
        return await control_handlers.discord_refresh(request, payload or DiscordRefreshRequest())

    @app.post("/v1/control/supervisor/recover")
    async def supervisor_recover(request: Request, payload: SupervisorRecoverRequest | None = None) -> dict[str, Any]:
        return await control_handlers.supervisor_recover(request, payload or SupervisorRecoverRequest())

    @app.post("/api/supervisor/recover")
    async def api_supervisor_recover(request: Request, payload: SupervisorRecoverRequest | None = None) -> dict[str, Any]:
        return await control_handlers.supervisor_recover(request, payload or SupervisorRecoverRequest())

    @app.post("/v1/control/heartbeat/trigger")
    async def trigger_heartbeat(request: Request) -> dict[str, Any]:
        return await control_handlers.heartbeat_trigger(request)

    @app.get("/v1/self-evolution/status")
    async def self_evolution_status(request: Request) -> dict[str, Any]:
        return await control_handlers.self_evolution_status(request)

    @app.post("/v1/self-evolution/trigger")
    async def self_evolution_trigger(request: Request) -> dict[str, Any]:
        return await control_handlers.self_evolution_trigger(request)

    @app.post("/v1/chat", response_model=ChatResponse)
    async def chat(req: ChatRequest, request: Request) -> ChatResponse:
        if blocked := await _http_chat_rate_limit_response(
            request=request,
            auth_guard=auth_guard,
            rate_limiter=gateway_rate_limiter,
        ):
            return blocked
        return ChatResponse(**(await request_handlers.chat(req, request)))

    @app.post("/api/message", response_model=ChatResponse)
    async def api_message(req: ChatRequest, request: Request) -> ChatResponse:
        if blocked := await _http_chat_rate_limit_response(
            request=request,
            auth_guard=auth_guard,
            rate_limiter=gateway_rate_limiter,
            allow_dashboard_session=True,
        ):
            return blocked
        return ChatResponse(**(await request_handlers.chat(req, request, allow_dashboard_session=True)))

    @app.get("/v1/tools/catalog")
    async def tools_catalog(request: Request) -> dict[str, Any]:
        return await request_handlers.tools_catalog(request)

    @app.get("/api/tools/catalog")
    async def api_tools_catalog(request: Request) -> dict[str, Any]:
        return await request_handlers.tools_catalog(request, allow_dashboard_session=True)

    @app.get("/v1/tools/approvals")
    async def tools_approvals(
        request: Request,
        status: str = "pending",
        session_id: str = "",
        channel: str = "",
        tool: str = "",
        rule: str = "",
        include_grants: bool = False,
        limit: int = 50,
    ) -> dict[str, Any]:
        return await request_handlers.tools_approvals(
            request,
            status=status,
            session_id=session_id,
            channel=channel,
            tool=tool,
            rule=rule,
            include_grants=include_grants,
            limit=limit,
        )

    @app.get("/api/tools/approvals")
    async def api_tools_approvals(
        request: Request,
        status: str = "pending",
        session_id: str = "",
        channel: str = "",
        tool: str = "",
        rule: str = "",
        include_grants: bool = False,
        limit: int = 50,
    ) -> dict[str, Any]:
        return await request_handlers.tools_approvals(
            request,
            status=status,
            session_id=session_id,
            channel=channel,
            tool=tool,
            rule=rule,
            include_grants=include_grants,
            limit=limit,
        )

    @app.post("/v1/tools/approvals/{request_id}/approve")
    async def tools_approval_approve(
        request_id: str,
        request: Request,
        payload: ToolApprovalReviewRequest | None = None,
    ) -> dict[str, Any]:
        return await request_handlers.tools_approval_review(
            request,
            request_id=request_id,
            decision="approved",
            actor=str((payload or ToolApprovalReviewRequest()).actor or ""),
            note=str((payload or ToolApprovalReviewRequest()).note or ""),
        )

    @app.post("/api/tools/approvals/{request_id}/approve")
    async def api_tools_approval_approve(
        request_id: str,
        request: Request,
        payload: ToolApprovalReviewRequest | None = None,
    ) -> dict[str, Any]:
        return await request_handlers.tools_approval_review(
            request,
            request_id=request_id,
            decision="approved",
            actor=str((payload or ToolApprovalReviewRequest()).actor or ""),
            note=str((payload or ToolApprovalReviewRequest()).note or ""),
        )

    @app.post("/v1/tools/approvals/{request_id}/reject")
    async def tools_approval_reject(
        request_id: str,
        request: Request,
        payload: ToolApprovalReviewRequest | None = None,
    ) -> dict[str, Any]:
        return await request_handlers.tools_approval_review(
            request,
            request_id=request_id,
            decision="rejected",
            actor=str((payload or ToolApprovalReviewRequest()).actor or ""),
            note=str((payload or ToolApprovalReviewRequest()).note or ""),
        )

    @app.post("/api/tools/approvals/{request_id}/reject")
    async def api_tools_approval_reject(
        request_id: str,
        request: Request,
        payload: ToolApprovalReviewRequest | None = None,
    ) -> dict[str, Any]:
        return await request_handlers.tools_approval_review(
            request,
            request_id=request_id,
            decision="rejected",
            actor=str((payload or ToolApprovalReviewRequest()).actor or ""),
            note=str((payload or ToolApprovalReviewRequest()).note or ""),
        )

    @app.post("/v1/tools/grants/revoke")
    async def tools_grants_revoke(
        request: Request,
        payload: ToolGrantRevokeRequest | None = None,
    ) -> dict[str, Any]:
        body = payload or ToolGrantRevokeRequest()
        return await request_handlers.tools_grants_revoke(
            request,
            session_id=str(body.session_id or ""),
            channel=str(body.channel or ""),
            rule=str(body.rule or ""),
        )

    @app.post("/api/tools/grants/revoke")
    async def api_tools_grants_revoke(
        request: Request,
        payload: ToolGrantRevokeRequest | None = None,
    ) -> dict[str, Any]:
        body = payload or ToolGrantRevokeRequest()
        return await request_handlers.tools_grants_revoke(
            request,
            session_id=str(body.session_id or ""),
            channel=str(body.channel or ""),
            rule=str(body.rule or ""),
        )

    @app.get("/api/token")
    async def api_token(request: Request) -> dict[str, Any]:
        return await status_handlers.api_token(request, allow_dashboard_session=True)

    app.add_api_route(telegram_webhook_path, webhook_handlers.telegram, methods=["POST"])
    app.add_api_route(whatsapp_webhook_path, webhook_handlers.whatsapp, methods=["POST"])

    @app.post("/v1/cron/add")
    async def cron_add(req: CronAddRequest, request: Request) -> dict[str, Any]:
        return await request_handlers.cron_add(req, request)

    @app.get("/v1/cron/status")
    async def cron_status(request: Request) -> dict[str, Any]:
        return await request_handlers.cron_status(request=request)

    @app.get("/v1/cron/list")
    async def cron_list(request: Request, session_id: str = "") -> dict[str, Any]:
        return await request_handlers.cron_list(session_id=session_id, request=request)

    @app.get("/v1/cron/{job_id}")
    async def cron_get(job_id: str, request: Request, session_id: str = "") -> dict[str, Any]:
        return await request_handlers.cron_get(job_id=job_id, session_id=session_id, request=request)

    @app.post("/v1/cron/{job_id}/enable")
    async def cron_enable(job_id: str, request: Request, payload: CronToggleRequest | None = None) -> dict[str, Any]:
        body = payload or CronToggleRequest()
        return await request_handlers.cron_toggle(
            job_id=job_id,
            enabled=True,
            session_id=str(body.session_id or ""),
            request=request,
        )

    @app.post("/v1/cron/{job_id}/disable")
    async def cron_disable(job_id: str, request: Request, payload: CronToggleRequest | None = None) -> dict[str, Any]:
        body = payload or CronToggleRequest()
        return await request_handlers.cron_toggle(
            job_id=job_id,
            enabled=False,
            session_id=str(body.session_id or ""),
            request=request,
        )

    @app.delete("/v1/cron/{job_id}")
    async def cron_remove(job_id: str, request: Request) -> dict[str, Any]:
        return await request_handlers.cron_remove(job_id=job_id, request=request)

    @app.websocket("/v1/ws")
    async def ws_chat(socket: WebSocket) -> None:
        await websocket_handlers.handle(socket, path_label="/v1/ws")

    @app.websocket("/ws")
    async def ws_chat_alias(socket: WebSocket) -> None:
        await websocket_handlers.handle(socket, path_label="/ws", allow_dashboard_session=True)

    @app.get(f"{_DASHBOARD_ASSET_ROOT}/dashboard.css")
    async def dashboard_css() -> Response:
        return await request_handlers.dashboard_css()

    @app.get(f"{_DASHBOARD_ASSET_ROOT}/dashboard.js")
    async def dashboard_js() -> Response:
        return await request_handlers.dashboard_js()

    @app.get("/", response_class=HTMLResponse)
    async def root() -> HTMLResponse:
        return await request_handlers.root()

    return app


def run_gateway(
    host: str | None = None,
    port: int | None = None,
    *,
    config: AppConfig | None = None,
    config_path: str | None = None,
    config_profile: str | None = None,
) -> None:
    if config_path is not None or config_profile is not None:
        cfg = load_config(config_path, profile=config_profile)
    else:
        cfg = config or load_config()
    app = create_app(cfg, config_path=config_path, config_profile=config_profile)
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
