from __future__ import annotations

import asyncio
import datetime as dt
import json
import time
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
from clawlite.scheduler.cron import CronService
from clawlite.scheduler.heartbeat import HeartbeatDecision, HeartbeatService
from clawlite.session.store import SessionStore
from clawlite.tools.cron import CronTool
from clawlite.tools.exec import ExecTool
from clawlite.tools.files import EditFileTool, ListDirTool, ReadFileTool, WriteFileTool
from clawlite.tools.mcp import MCPTool
from clawlite.tools.message import MessageTool
from clawlite.tools.memory import MemoryAnalyzeTool, MemoryForgetTool, MemoryLearnTool, MemoryRecallTool
from clawlite.tools.registry import ToolRegistry
from clawlite.tools.skill import SkillTool
from clawlite.tools.spawn import SpawnTool
from clawlite.tools.web import WebFetchTool, WebSearchTool
from clawlite.utils.logging import bind_event, setup_logging
from clawlite.workspace.loader import WorkspaceLoader

setup_logging()


GATEWAY_CONTRACT_VERSION = "2026-03-04"
TELEGRAM_WEBHOOK_MAX_BODY_BYTES = 1024 * 1024


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
    bootstrap: dict[str, Any]
    memory_monitor: dict[str, Any] = {}
    engine: dict[str, Any] = {}
    environment: dict[str, Any] = {}
    http: dict[str, Any] = {}


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


@dataclass(slots=True)
class RuntimeContainer:
    config: AppConfig
    bus: MessageQueue
    engine: AgentEngine
    channels: ChannelManager
    cron: CronService
    heartbeat: HeartbeatService
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

    def check_http(self, *, request: Request, scope: str, diagnostics_auth: bool) -> None:
        client_host = request.client.host if request.client is not None else None
        should_require = self._require_for_scope(scope=scope, host=client_host, diagnostics_auth=diagnostics_auth)
        header_value = str(request.headers.get(self.header_name, "") or "")
        query_value = str(request.query_params.get(self.query_param, "") or "")
        supplied_token = self._extract_token(header_value=header_value, query_value=query_value)
        if should_require and (not self.token or supplied_token != self.token):
            raise HTTPException(status_code=401, detail="gateway_auth_required")
        if self.mode == "optional" and supplied_token and self.token and supplied_token != self.token:
            raise HTTPException(status_code=401, detail="gateway_auth_invalid")

    async def check_ws(self, *, socket: WebSocket, scope: str, diagnostics_auth: bool) -> bool:
        client_host = socket.client.host if socket.client is not None else None
        should_require = self._require_for_scope(scope=scope, host=client_host, diagnostics_auth=diagnostics_auth)
        header_value = str(socket.headers.get(self.header_name, "") or "")
        query_value = str(socket.query_params.get(self.query_param, "") or "")
        supplied_token = self._extract_token(header_value=header_value, query_value=query_value)
        if should_require and (not self.token or supplied_token != self.token):
            await socket.close(code=4401, reason="gateway_auth_required")
            return False
        if self.mode == "optional" and supplied_token and self.token and supplied_token != self.token:
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
    provider_name = detect_provider_name(active_model)
    selected = getattr(config.providers, provider_name, None)
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
        },
    }


def build_runtime(config: AppConfig) -> RuntimeContainer:
    bind_event("gateway.runtime").info("building runtime workspace={} state={}", config.workspace_path, config.state_path)
    workspace = WorkspaceLoader(workspace_path=config.workspace_path)
    workspace.bootstrap()
    workspace_path = Path(config.workspace_path).expanduser().resolve()

    provider = build_provider(_provider_config(config))
    cron = CronService(
        store_path=Path(config.state_path) / "cron_jobs.json",
        default_timezone=config.scheduler.timezone,
    )
    heartbeat = HeartbeatService(
        interval_seconds=config.gateway.heartbeat.interval_s,
        state_path=workspace_path / "memory" / "heartbeat-state.json",
    )

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
    tools.register(ReadFileTool(workspace_path=workspace_path, restrict_to_workspace=config.tools.restrict_to_workspace))
    tools.register(WriteFileTool(workspace_path=workspace_path, restrict_to_workspace=config.tools.restrict_to_workspace))
    tools.register(EditFileTool(workspace_path=workspace_path, restrict_to_workspace=config.tools.restrict_to_workspace))
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
    tools.register(SkillTool(loader=skills, registry=tools))

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
    memory_monitor = MemoryMonitor(memory) if bool(getattr(config.agents.defaults.memory, "proactive", False)) else None
    tools.register(MemoryRecallTool(memory))
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

    tools.register(SpawnTool(engine.subagents, _subagent_runner))

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
        workspace=workspace,
        memory_monitor=memory_monitor,
    )


async def _route_cron_job(runtime: RuntimeContainer, job) -> str | None:
    bind_event("cron.dispatch", session=job.session_id).info("cron dispatch start job_id={}", job.id)
    result = await runtime.engine.run(session_id=job.session_id, user_text=job.payload.prompt)
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


async def _run_heartbeat(runtime: RuntimeContainer) -> HeartbeatDecision:
    heartbeat_prompt = (
        "Read HEARTBEAT.md if it exists (workspace context). Follow it strictly. "
        "Do not infer or repeat old tasks from prior chats. "
        "If nothing needs attention, reply HEARTBEAT_OK."
    )
    session_id = "heartbeat:system"
    bind_event("heartbeat.tick", session="heartbeat:system").debug("heartbeat callback running")
    result = await runtime.engine.run(session_id=session_id, user_text=heartbeat_prompt)
    bind_event("heartbeat.tick", session="heartbeat:system").debug("heartbeat callback completed")
    decision = HeartbeatDecision.from_result(result.text)

    channels = getattr(runtime, "channels", None)
    memory_store = getattr(getattr(runtime, "engine", None), "memory", None)

    def _default_heartbeat_route() -> tuple[str, str]:
        return "cli", "profile"

    async def _latest_memory_route() -> tuple[str, str]:
        channel, target = _default_heartbeat_route()
        if memory_store is None or not hasattr(memory_store, "all"):
            return channel, target
        try:
            history_rows = await asyncio.to_thread(memory_store.all)
        except Exception:
            return channel, target
        latest_source = ""
        latest_stamp = dt.datetime.min.replace(tzinfo=dt.timezone.utc)
        for row in history_rows:
            source = str(getattr(row, "source", "") or "").strip()
            created_raw = str(getattr(row, "created_at", "") or "")
            try:
                created_at = dt.datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=dt.timezone.utc)
            except Exception:
                created_at = dt.datetime.min.replace(tzinfo=dt.timezone.utc)
            if source and created_at >= latest_stamp:
                latest_stamp = created_at
                latest_source = source
        if latest_source:
            return MemoryMonitor._delivery_route_from_source(latest_source)
        return channel, target

    if decision.action == "run" and decision.text:
        channel, target = await _latest_memory_route()
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

    monitor = getattr(runtime, "memory_monitor", None)
    if monitor is not None and channels is not None:
        try:
            suggestions = await monitor.scan()
        except Exception as exc:
            bind_event("heartbeat.memory", session="heartbeat:system").warning("memory monitor scan failed error={}", exc)
        else:
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
                    bind_event("heartbeat.memory", session="heartbeat:system").warning(
                        "memory suggestion delivery failed suggestion_id={} channel={} target={} error={}",
                        suggestion.suggestion_id,
                        suggestion.channel,
                        suggestion.target,
                        exc,
                    )
                    try:
                        monitor.mark_failed(suggestion, error=str(exc))
                    except Exception:
                        pass
                    continue
                try:
                    monitor.mark_delivered(suggestion)
                except Exception as exc:
                    bind_event("heartbeat.memory", session="heartbeat:system").warning(
                        "memory suggestion mark_delivered failed suggestion_id={} error={}",
                        suggestion.suggestion_id,
                        exc,
                    )

        try:
            channel = "cli"
            target = "profile"
            if memory_store is not None and hasattr(memory_store, "all"):
                try:
                    history_rows = await asyncio.to_thread(memory_store.all)
                except Exception:
                    history_rows = []
                latest_source = ""
                latest_stamp = dt.datetime.min.replace(tzinfo=dt.timezone.utc)
                for row in history_rows:
                    source = str(getattr(row, "source", "") or "").strip()
                    created_raw = str(getattr(row, "created_at", "") or "")
                    try:
                        created_at = dt.datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
                        if created_at.tzinfo is None:
                            created_at = created_at.replace(tzinfo=dt.timezone.utc)
                    except Exception:
                        created_at = dt.datetime.min.replace(tzinfo=dt.timezone.utc)
                    if source and created_at >= latest_stamp:
                        latest_stamp = created_at
                        latest_source = source
                if latest_source:
                    channel, target = MemoryMonitor._delivery_route_from_source(latest_source)

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
                            bind_event("heartbeat.memory", session="heartbeat:system").warning(
                                "next-step suggestion delivery failed channel={} target={} error={}",
                                suggestion.channel,
                                suggestion.target,
                                exc,
                            )
                            try:
                                monitor.mark_failed(suggestion, error=str(exc))
                            except Exception:
                                pass
                        else:
                            try:
                                monitor.mark_delivered(suggestion)
                            except Exception:
                                pass
        except Exception as exc:
            bind_event("heartbeat.memory", session="heartbeat:system").warning(
                "next-step proactive retrieval failed error={}",
                exc,
            )

    return decision


def create_app(config: AppConfig | None = None) -> FastAPI:
    cfg = config or load_config()
    runtime = build_runtime(cfg)
    auth_guard = GatewayAuthGuard.from_config(cfg)
    if auth_guard.mode == "required" and not auth_guard.token:
        raise RuntimeError("gateway_auth_required_but_token_missing")
    if auth_guard.mode == "off" and not GatewayAuthGuard._is_loopback(cfg.gateway.host):
        bind_event("gateway.auth").warning("gateway running on non-loopback host without auth host={}", cfg.gateway.host)
    lifecycle = GatewayLifecycleState()
    http_telemetry = HttpRequestTelemetry()
    started_monotonic = time.monotonic()
    lifecycle.components["heartbeat"]["enabled"] = bool(cfg.gateway.heartbeat.enabled)

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

    async def _start_subsystems() -> None:
        started: list[tuple[str, Any]] = []
        steps: list[tuple[str, Any, Any, bool]] = [
            ("channels", runtime.channels.start, runtime.channels.stop, True),
            ("cron", runtime.cron.start, runtime.cron.stop, True),
            ("heartbeat", runtime.heartbeat.start, runtime.heartbeat.stop, bool(cfg.gateway.heartbeat.enabled)),
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
                elif name == "cron":
                    await start_fn(lambda job: _route_cron_job(runtime, job))
                else:
                    await start_fn(lambda: _run_heartbeat(runtime))
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
            ("cron", runtime.cron.stop, True),
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
        engine_payload: dict[str, Any] = {
            "retrieval_metrics": runtime.engine.retrieval_metrics_snapshot(),
            "turn_metrics": runtime.engine.turn_metrics_snapshot(),
        }
        if cfg.gateway.diagnostics.include_provider_telemetry:
            engine_payload["provider"] = _provider_telemetry_snapshot(runtime.engine.provider)
        monitor_payload: dict[str, Any]
        if runtime.memory_monitor is None:
            monitor_payload = {"enabled": False}
        else:
            try:
                monitor_payload = dict(runtime.memory_monitor.telemetry())
            except Exception:
                monitor_payload = {}
            monitor_payload["enabled"] = True

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
            bootstrap=_bootstrap_status_snapshot(),
            memory_monitor=monitor_payload,
            engine=engine_payload,
            environment=environment,
            http=await http_telemetry.snapshot(),
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
        decision = await runtime.heartbeat.trigger_now(lambda: _run_heartbeat(runtime))
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
            out = await runtime.engine.run(session_id=req.session_id, user_text=req.text)
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
            if not supplied_secret or supplied_secret != expected_secret:
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
        removed = runtime.cron.remove_job(job_id)
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

        if not await auth_guard.check_ws(socket=socket, scope="control", diagnostics_auth=cfg.gateway.diagnostics.require_auth):
            return
        await socket.accept()
        bind_event("gateway.ws", channel="ws").info("websocket client connected path={}", path_label)
        try:
            while True:
                payload = await socket.receive_json()
                if not isinstance(payload, dict):
                    await socket.send_json({"error": "session_id and text are required"})
                    continue

                message_type = str(payload.get("type", "") or "").strip().lower()
                if message_type:
                    request_id = str(payload.get("request_id", "") or "").strip() or None
                    if message_type == "hello":
                        await socket.send_json(
                            {
                                "type": "ready",
                                "contract_version": GATEWAY_CONTRACT_VERSION,
                                "server_time": _utc_now_iso(),
                            }
                        )
                        continue
                    if message_type == "ping":
                        await socket.send_json({"type": "pong", "server_time": _utc_now_iso()})
                        continue
                    if message_type != "message":
                        await socket.send_json(
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
                        await socket.send_json(
                            _ws_envelope_error(
                                error="session_id and text are required",
                                status_code=400,
                                request_id=request_id,
                            )
                        )
                        continue

                    try:
                        out = await runtime.engine.run(session_id=session_id, user_text=text)
                    except RuntimeError as exc:
                        status_code, detail = _provider_error_payload(exc)
                        bind_event("gateway.ws", session=session_id, channel="ws").error(
                            "websocket request failed status={} detail={}",
                            status_code,
                            detail,
                        )
                        await socket.send_json(
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
                    await socket.send_json(response_payload)
                    bind_event("gateway.ws", session=session_id, channel="ws").debug(
                        "websocket response sent model={}",
                        out.model,
                    )
                    continue

                session_id = str(payload.get("session_id", "")).strip()
                text = str(payload.get("text", "")).strip()
                if not session_id or not text:
                    await socket.send_json({"error": "session_id and text are required"})
                    continue
                try:
                    out = await runtime.engine.run(session_id=session_id, user_text=text)
                except RuntimeError as exc:
                    status_code, detail = _provider_error_payload(exc)
                    bind_event("gateway.ws", session=session_id, channel="ws").error("websocket request failed status={} detail={}", status_code, detail)
                    await socket.send_json({"error": detail, "status_code": status_code})
                    continue
                _finalize_bootstrap_for_user_turn(session_id)
                await socket.send_json({"text": out.text, "model": out.model})
                bind_event("gateway.ws", session=session_id, channel="ws").debug("websocket response sent model={}", out.model)
        except WebSocketDisconnect:
            bind_event("gateway.ws", channel="ws").info("websocket client disconnected path={}", path_label)
            return

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


app = create_app()


if __name__ == "__main__":
    run_gateway()
