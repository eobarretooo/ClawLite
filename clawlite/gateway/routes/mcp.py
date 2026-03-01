from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import JSONResponse

from clawlite.gateway.utils import _check_bearer
from clawlite.mcp import add_server, install_template, list_servers, remove_server, search_marketplace
from clawlite.mcp_server import handle_mcp_jsonrpc

router = APIRouter()


@router.post("/mcp")
def mcp_rpc(payload: dict[str, Any], authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    return JSONResponse(handle_mcp_jsonrpc(payload))


@router.get("/api/mcp/list")
def api_mcp_list(authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    rows = list_servers()
    return JSONResponse({"ok": True, "servers": rows})


@router.get("/api/mcp/config")
def api_mcp_config(authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    rows = list_servers()
    return JSONResponse({"ok": True, "servers": rows})


@router.post("/api/mcp/add")
def api_mcp_add(payload: dict[str, Any], authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    try:
        row = add_server(str(payload.get("name", "")), str(payload.get("url", "")))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse({"ok": True, "server": row})


@router.post("/api/mcp/remove")
def api_mcp_remove(payload: dict[str, Any], authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    try:
        removed = remove_server(str(payload.get("name", "")))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not removed:
        raise HTTPException(status_code=404, detail="Servidor MCP não encontrado")
    return JSONResponse({"ok": True, "removed": True})


@router.get("/api/mcp/search")
def api_mcp_search(q: str = Query(default=""), authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    return JSONResponse({"ok": True, "items": search_marketplace(q)})


@router.post("/api/mcp/install")
def api_mcp_install(payload: dict[str, Any], authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    name = str(payload.get("name", "")).strip()
    try:
        row = install_template(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse({"ok": True, "server": row})


@router.get("/api/mcp/status")
def api_mcp_status(authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    rows = list_servers()
    return JSONResponse(
        {
            "ok": True,
            "count": len(rows),
            "servers": [
                {
                    **row,
                    "status": "configured",
                    "connected": False,
                }
                for row in rows
            ],
        }
    )
