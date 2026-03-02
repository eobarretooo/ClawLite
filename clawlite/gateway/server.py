from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from clawlite.bus.queue import MessageQueue
from clawlite.channels.manager import ChannelManager
from clawlite.config.loader import load_config
from clawlite.config.schema import AppConfig
from clawlite.core.engine import AgentEngine
from clawlite.core.memory import MemoryStore
from clawlite.core.prompt import PromptBuilder
from clawlite.core.skills import SkillsLoader
from clawlite.providers import build_provider
from clawlite.scheduler.cron import CronService
from clawlite.scheduler.heartbeat import HeartbeatService
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
from clawlite.workspace.loader import WorkspaceLoader


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


@dataclass(slots=True)
class RuntimeContainer:
    config: AppConfig
    bus: MessageQueue
    engine: AgentEngine
    channels: ChannelManager
    cron: CronService
    heartbeat: HeartbeatService
    workspace: WorkspaceLoader


class _CronAPI:
    def __init__(self, service: CronService) -> None:
        self.service = service

    async def add_job(self, *, session_id: str, expression: str, prompt: str) -> str:
        return await self.service.add_job(session_id=session_id, expression=expression, prompt=prompt)

    def list_jobs(self, *, session_id: str) -> list[dict[str, Any]]:
        return self.service.list_jobs(session_id=session_id)


class _MessageAPI:
    def __init__(self, manager: ChannelManager) -> None:
        self.manager = manager

    async def send(self, *, channel: str, target: str, text: str) -> str:
        return await self.manager.send(channel=channel, target=target, text=text)


def _provider_config(config: AppConfig) -> dict[str, Any]:
    return {
        "model": config.provider.model,
        "providers": {
            "litellm": {
                "base_url": config.provider.litellm_base_url,
                "api_key": config.provider.litellm_api_key,
            }
        },
    }


def build_runtime(config: AppConfig) -> RuntimeContainer:
    workspace = WorkspaceLoader(workspace_path=config.workspace_path)
    workspace.bootstrap()

    provider = build_provider(_provider_config(config))
    cron = CronService(store_path=Path(config.state_path) / "cron_jobs.json")
    heartbeat = HeartbeatService(interval_seconds=config.scheduler.heartbeat_interval_seconds)

    tools = ToolRegistry()
    tools.register(ExecTool())
    tools.register(ReadFileTool())
    tools.register(WriteFileTool())
    tools.register(EditFileTool())
    tools.register(ListDirTool())
    tools.register(WebFetchTool())
    tools.register(WebSearchTool())
    tools.register(CronTool(_CronAPI(cron)))
    tools.register(MCPTool())
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
    )

    async def _subagent_runner(session_id: str, task: str) -> str:
        result = await engine.run(session_id=session_id, user_text=task)
        return result.text

    tools.register(SpawnTool(engine.subagents, _subagent_runner))

    bus = MessageQueue()
    channels = ChannelManager(bus=bus, engine=engine)
    tools.register(MessageTool(_MessageAPI(channels)))

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
    result = await runtime.engine.run(session_id=job.session_id, user_text=job.payload.prompt)
    channel = job.payload.channel.strip() or job.session_id.split(":", 1)[0]
    target = job.payload.target.strip() or job.session_id.split(":", 1)[-1]
    if channel and target:
        try:
            await runtime.channels.send(channel=channel, target=target, text=result.text)
        except Exception:
            return "cron_send_skipped"
    return result.text


async def _run_heartbeat(runtime: RuntimeContainer) -> str | None:
    heartbeat_prompt = "heartbeat: check pending tasks and send proactive updates when needed"
    session_id = "heartbeat:system"
    result = await runtime.engine.run(session_id=session_id, user_text=heartbeat_prompt)
    return result.text


def create_app(config: AppConfig | None = None) -> FastAPI:
    cfg = config or load_config()
    runtime = build_runtime(cfg)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await runtime.channels.start(cfg.to_dict())
        await runtime.cron.start(lambda job: _route_cron_job(runtime, job))
        await runtime.heartbeat.start(lambda: _run_heartbeat(runtime))
        try:
            yield
        finally:
            await runtime.heartbeat.stop()
            await runtime.cron.stop()
            await runtime.channels.stop()

    app = FastAPI(title="ClawLite Gateway", version="1.0.0", lifespan=lifespan)
    app.state.runtime = runtime

    def _provider_error_payload(exc: RuntimeError) -> tuple[int, str]:
        message = str(exc)
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
        if message.startswith("provider_http_error:401"):
            return (
                502,
                "Falha de autenticacao no provedor (401). Verifique CLAWLITE_MODEL e CLAWLITE_LITELLM_API_KEY.",
            )
        if message.startswith("provider_http_error:429") or message == "provider_429_exhausted":
            return (429, "Limite de requisicoes no provedor. Tente novamente em instantes.")
        if message.startswith("provider_http_error:"):
            code = message.split(":", 1)[1]
            return (502, f"Falha no provedor remoto (HTTP {code}).")
        if message.startswith("provider_network_error:"):
            return (503, "Provedor remoto indisponivel no momento (erro de rede).")
        if message.startswith("codex_http_error:401"):
            return (502, "Falha de autenticacao no Codex (401). Refaça login OAuth do provedor Codex.")
        if message.startswith("codex_http_error:429") or message == "codex_429_exhausted":
            return (429, "Limite de requisicoes no Codex. Tente novamente em instantes.")
        if message.startswith("codex_http_error:"):
            code = message.split(":", 1)[1]
            return (502, f"Falha no Codex (HTTP {code}).")
        if message.startswith("codex_network_error:"):
            return (503, "Codex indisponivel no momento (erro de rede).")
        return (500, "Falha interna ao processar a solicitacao.")

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "ok": True,
            "channels": runtime.channels.status(),
            "queue": runtime.bus.stats(),
        }

    @app.post("/v1/chat", response_model=ChatResponse)
    async def chat(req: ChatRequest) -> ChatResponse:
        if not req.session_id.strip() or not req.text.strip():
            raise HTTPException(status_code=400, detail="session_id and text are required")
        try:
            out = await runtime.engine.run(session_id=req.session_id, user_text=req.text)
        except RuntimeError as exc:
            status_code, detail = _provider_error_payload(exc)
            raise HTTPException(status_code=status_code, detail=detail)
        return ChatResponse(text=out.text, model=out.model)

    @app.post("/v1/cron/add")
    async def cron_add(req: CronAddRequest) -> dict[str, str]:
        job_id = await runtime.cron.add_job(
            session_id=req.session_id,
            expression=req.expression,
            prompt=req.prompt,
            name=req.name,
        )
        return {"id": job_id}

    @app.get("/v1/cron/list")
    async def cron_list(session_id: str) -> dict[str, Any]:
        return {"jobs": runtime.cron.list_jobs(session_id=session_id)}

    @app.delete("/v1/cron/{job_id}")
    async def cron_remove(job_id: str) -> dict[str, bool]:
        return {"ok": runtime.cron.remove_job(job_id)}

    @app.websocket("/v1/ws")
    async def ws_chat(socket: WebSocket) -> None:
        await socket.accept()
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
                    await socket.send_json({"error": detail, "status_code": status_code})
                    continue
                await socket.send_json({"text": out.text, "model": out.model})
        except WebSocketDisconnect:
            return

    return app


def run_gateway(host: str | None = None, port: int | None = None) -> None:
    cfg = load_config()
    app = create_app(cfg)
    uvicorn.run(
        app,
        host=host or cfg.gateway.host,
        port=port or int(cfg.gateway.port),
        access_log=False,
        log_level="warning",
    )


app = create_app()


if __name__ == "__main__":
    run_gateway()
