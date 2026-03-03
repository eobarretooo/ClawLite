from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel

from clawlite.bus.queue import MessageQueue
from clawlite.channels.manager import ChannelManager
from clawlite.config.loader import load_config
from clawlite.config.schema import AppConfig
from clawlite.core.engine import AgentEngine, LoopDetectionSettings
from clawlite.core.memory import MemoryStore
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
from clawlite.tools.registry import ToolRegistry
from clawlite.tools.skill import SkillTool
from clawlite.tools.spawn import SpawnTool
from clawlite.tools.web import WebFetchTool, WebSearchTool
from clawlite.utils.logging import bind_event, setup_logging
from clawlite.workspace.loader import WorkspaceLoader

setup_logging()


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
    components: dict[str, Any]
    auth: dict[str, Any]


class DiagnosticsResponse(BaseModel):
    schema_version: str
    control_plane: ControlPlaneResponse
    queue: dict[str, int]
    channels: dict[str, Any]
    cron: dict[str, Any]
    heartbeat: dict[str, Any]
    environment: dict[str, Any] = {}


@dataclass(slots=True)
class RuntimeContainer:
    config: AppConfig
    bus: MessageQueue
    engine: AgentEngine
    channels: ChannelManager
    cron: CronService
    heartbeat: HeartbeatService
    workspace: WorkspaceLoader


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
        mode = str(auth_cfg.mode or "off").strip().lower()
        if mode not in {"off", "optional", "required"}:
            mode = "off"
        return cls(
            mode=mode,
            token=str(auth_cfg.token or "").strip(),
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

    async def send(self, *, channel: str, target: str, text: str) -> str:
        return await self.manager.send(channel=channel, target=target, text=text)


def _provider_config(config: AppConfig) -> dict[str, Any]:
    active_model = str(config.agents.defaults.model or config.provider.model).strip() or config.provider.model
    provider_name = detect_provider_name(active_model)
    selected = getattr(config.providers, provider_name, None)
    selected_api_key = selected.api_key if selected is not None else ""
    selected_api_base = selected.api_base if selected is not None else ""

    return {
        "model": active_model,
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

    tools = ToolRegistry()
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

    sessions = SessionStore(root=Path(config.state_path) / "sessions")
    memory = MemoryStore(db_path=Path(config.state_path) / "memory.jsonl")
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
    return HeartbeatDecision.from_result(result.text)


def create_app(config: AppConfig | None = None) -> FastAPI:
    cfg = config or load_config()
    runtime = build_runtime(cfg)
    auth_guard = GatewayAuthGuard.from_config(cfg)
    if auth_guard.mode == "required" and not auth_guard.token:
        raise RuntimeError("gateway_auth_required_but_token_missing")
    if auth_guard.mode == "off" and not GatewayAuthGuard._is_loopback(cfg.gateway.host):
        bind_event("gateway.auth").warning("gateway running on non-loopback host without auth host={}", cfg.gateway.host)
    lifecycle = GatewayLifecycleState()
    lifecycle.components["heartbeat"]["enabled"] = bool(cfg.gateway.heartbeat.enabled)

    def _control_plane_payload() -> ControlPlaneResponse:
        return ControlPlaneResponse(
            ready=bool(lifecycle.ready),
            phase=str(lifecycle.phase),
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

    @app.exception_handler(HTTPException)
    async def _http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail
        if isinstance(detail, str):
            payload: dict[str, Any] = {"error": detail, "status": exc.status_code}
        else:
            payload = {"error": "http_error", "status": exc.status_code, "detail": detail}
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
                f"Missing API key for provider '{provider}'. Set CLAWLITE_LITELLM_API_KEY or the provider-specific key.",
            )
        if message.startswith("provider_config_error:missing_base_url:"):
            provider = message.rsplit(":", 1)[-1]
            return (
                400,
                f"Missing base URL for provider '{provider}'. Configure CLAWLITE_LITELLM_BASE_URL.",
            )
        if message.startswith("provider_config_error:"):
            return (400, "Invalid provider configuration. Review model, base URL, and API key.")
        if provider_http_code == "400":
            hint = provider_http_detail or "Check provider model, API key, and base URL."
            return (400, f"Invalid request to provider (400). {hint}")
        if provider_http_code == "401":
            return (
                502,
                "Provider authentication failed (401). Check CLAWLITE_MODEL and CLAWLITE_LITELLM_API_KEY."
                + (f" Detail: {provider_http_detail}" if provider_http_detail else ""),
            )
        if provider_http_code == "429" or message == "provider_429_exhausted":
            return (429, "Provider rate limit reached. Try again shortly.")
        if provider_http_code:
            detail = f" Detail: {provider_http_detail}" if provider_http_detail else ""
            return (502, f"Remote provider failure (HTTP {provider_http_code}).{detail}")
        if message.startswith("provider_network_error:"):
            return (503, "Remote provider is currently unavailable (network error).")
        if message.startswith("codex_http_error:401"):
            return (502, "Codex authentication failed (401). Re-authenticate OAuth for the Codex provider.")
        if message.startswith("codex_http_error:429") or message == "codex_429_exhausted":
            return (429, "Codex rate limit reached. Try again shortly.")
        if message.startswith("codex_http_error:"):
            code = message.split(":", 1)[1]
            return (502, f"Codex failure (HTTP {code}).")
        if message.startswith("codex_network_error:"):
            return (503, "Codex is currently unavailable (network error).")
        return (500, "Internal failure while processing the request.")

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

    @app.get("/v1/status", response_model=ControlPlaneResponse)
    async def status(request: Request) -> ControlPlaneResponse:
        auth_guard.check_http(request=request, scope="control", diagnostics_auth=cfg.gateway.diagnostics.require_auth)
        return _control_plane_payload()

    @app.get("/v1/diagnostics", response_model=DiagnosticsResponse)
    async def diagnostics(request: Request) -> DiagnosticsResponse:
        if not cfg.gateway.diagnostics.enabled:
            raise HTTPException(status_code=404, detail="diagnostics_disabled")
        auth_guard.check_http(request=request, scope="diagnostics", diagnostics_auth=cfg.gateway.diagnostics.require_auth)
        environment: dict[str, Any] = {}
        if cfg.gateway.diagnostics.include_config:
            environment = {
                "workspace_path": cfg.workspace_path,
                "state_path": cfg.state_path,
                "provider_model": cfg.agents.defaults.model,
            }
        return DiagnosticsResponse(
            schema_version="2026-03-02",
            control_plane=_control_plane_payload(),
            queue=runtime.bus.stats(),
            channels=runtime.channels.status(),
            cron=runtime.cron.status(),
            heartbeat=runtime.heartbeat.status(),
            environment=environment,
        )

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

    @app.post("/v1/chat", response_model=ChatResponse)
    async def chat(req: ChatRequest, request: Request) -> ChatResponse:
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
        bind_event("gateway.chat", session=req.session_id).info("chat response generated model={}", out.model)
        return ChatResponse(text=out.text, model=out.model)

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

    @app.websocket("/v1/ws")
    async def ws_chat(socket: WebSocket) -> None:
        if not await auth_guard.check_ws(socket=socket, scope="control", diagnostics_auth=cfg.gateway.diagnostics.require_auth):
            return
        await socket.accept()
        bind_event("gateway.ws", channel="ws").info("websocket client connected path=/v1/ws")
        try:
            while True:
                payload = await socket.receive_json()
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
                await socket.send_json({"text": out.text, "model": out.model})
                bind_event("gateway.ws", session=session_id, channel="ws").debug("websocket response sent model={}", out.model)
        except WebSocketDisconnect:
            bind_event("gateway.ws", channel="ws").info("websocket client disconnected path=/v1/ws")
            return

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
