from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse

from clawlite.gateway.utils import _check_bearer
from clawlite.runtime.multiagent import bind_agent, create_agent, list_agent_bindings, list_agents

router = APIRouter()


@router.get("/api/agents")
def api_agents(authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    return JSONResponse({"ok": True, "agents": [a.__dict__ for a in list_agents()], "bindings": list_agent_bindings()})


@router.post("/api/agents")
def api_agents_create(payload: dict[str, Any], authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    try:
        agent_id = create_agent(
            str(payload.get("name", "")),
            channel=str(payload.get("channel", "telegram")),
            role=str(payload.get("role", "")),
            personality=str(payload.get("personality", "")),
            credentials=str(payload.get("token", "")),
            account=str(payload.get("account", "")),
            orchestrator=bool(payload.get("orchestrator", False)),
            tags=[str(t) for t in (payload.get("tags") or [])],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse({"ok": True, "id": agent_id})


@router.post("/api/agents/bind")
def api_agents_bind(payload: dict[str, Any], authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    try:
        agent_id = bind_agent(str(payload.get("agent", "")), channel=str(payload.get("channel", "")), account=str(payload.get("account", "")))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse({"ok": True, "agent_id": agent_id})
