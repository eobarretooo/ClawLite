from __future__ import annotations

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from clawlite.config.settings import load_config
from clawlite.gateway.routes import admin, agents, channels, cron, mcp, pairing, sessions, skills, websockets, workspace, webhooks
from clawlite.gateway.utils import _log

import contextlib

@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    from clawlite.runtime.autonomy import runtime as autonomy_runtime

    await autonomy_runtime.start()
    app.state.autonomy_runtime = autonomy_runtime
    yield
    await autonomy_runtime.stop()

# Main FastAPI App Setup
app = FastAPI(title="ClawLite Gateway", version="0.3.0", lifespan=lifespan)

# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include all modular routers
app.include_router(admin.router)
app.include_router(agents.router)
app.include_router(channels.router)
app.include_router(cron.router)
app.include_router(mcp.router)
app.include_router(pairing.router)
app.include_router(sessions.router)
app.include_router(skills.router)
app.include_router(websockets.router)
app.include_router(workspace.router)
app.include_router(webhooks.router)


def run_gateway(host: str | None = None, port: int | None = None) -> None:
    """Run the ClawLite gateway server."""
    cfg = load_config()
    h_raw = host if host is not None else cfg.get("gateway", {}).get("host", "0.0.0.0")
    h = str(h_raw).strip() or "0.0.0.0"

    p_raw = port if port is not None else cfg.get("gateway", {}).get("port", 8787)
    try:
        p = int(p_raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            "Configuração inválida do gateway: 'port' deve ser inteiro entre 1 e 65535."
        ) from exc
    if p < 1 or p > 65535:
        raise RuntimeError(
            f"Configuração inválida do gateway: porta {p} fora do intervalo 1..65535."
        )

    _log("gateway.started", data={"host": h, "port": p})

    try:
        uvicorn.run(
            app,
            host=h,
            port=p,
            access_log=False,
            log_level="warning",
        )
    except OSError as exc:
        raise RuntimeError(
            f"Falha ao iniciar gateway em {h}:{p}. Verifique porta em uso/permissão. Detalhe: {exc}"
        ) from exc


# Exports para compatibilidade com a suite de testes existente
from clawlite.gateway.utils import _token, _log
from clawlite.gateway import state
from clawlite.core.agent import run_task_with_meta
from clawlite.skills.marketplace import update_skills

LOG_RING = state.LOG_RING
connections = state.connections
chat_connections = state.chat_connections
log_connections = state.log_connections
