from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

from clawlite.config.settings import load_config, save_config
from clawlite.skills.marketplace import (
    DEFAULT_DOWNLOAD_BASE_URL,
    SkillMarketplaceError,
    load_hub_manifest,
    publish_skill,
)

app = FastAPI(title="ClawLite Gateway", version="0.2.0")
connections: set[WebSocket] = set()
STARTED_AT = datetime.now(timezone.utc)


def _token() -> str:
    cfg = load_config()
    t = os.getenv("CLAWLITE_GATEWAY_TOKEN") or cfg.get("gateway", {}).get("token", "")
    if not t:
        t = secrets.token_urlsafe(24)
        cfg.setdefault("gateway", {})["token"] = t
        save_config(cfg)
    return t


def _check_bearer(auth: str | None) -> None:
    expected = _token()
    if not auth or not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    got = auth.removeprefix("Bearer ").strip()
    if got != expected:
        raise HTTPException(status_code=403, detail="Invalid token")


def _hub_manifest_path() -> Path:
    custom = os.getenv("CLAWLITE_HUB_MANIFEST")
    if custom:
        return Path(custom).expanduser()
    return Path.cwd() / "hub" / "marketplace" / "manifest.local.json"


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "clawlite-gateway",
        "uptime_seconds": int((datetime.now(timezone.utc) - STARTED_AT).total_seconds()),
        "connections": len(connections),
    }


@app.get("/dashboard")
def dashboard() -> HTMLResponse:
    html = Path(__file__).with_name("dashboard.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@app.get("/api/status")
def api_status(authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    cfg = load_config()
    return JSONResponse({
        "ok": True,
        "gateway": cfg.get("gateway", {}),
        "skills": cfg.get("skills", []),
        "connections": len(connections),
    })


@app.get("/api/hub/manifest")
def api_hub_manifest() -> JSONResponse:
    manifest = load_hub_manifest(_hub_manifest_path())
    return JSONResponse({"ok": True, "manifest": manifest})


@app.get("/api/hub/skills/{slug}")
def api_hub_skill(slug: str) -> JSONResponse:
    manifest = load_hub_manifest(_hub_manifest_path())
    for item in manifest.get("skills", []):
        if str(item.get("slug", "")).strip() == slug:
            return JSONResponse({"ok": True, "skill": item})
    raise HTTPException(status_code=404, detail="Skill not found")


@app.post("/api/hub/publish")
def api_hub_publish(payload: dict[str, Any], authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    try:
        result = publish_skill(
            payload.get("source_dir", ""),
            version=str(payload.get("version", "")).strip(),
            slug=payload.get("slug"),
            description=str(payload.get("description", "")),
            hub_dir=payload.get("hub_dir"),
            manifest_path=payload.get("manifest_path") or _hub_manifest_path(),
            download_base_url=str(payload.get("download_base_url", "")) or DEFAULT_DOWNLOAD_BASE_URL,
        )
    except SkillMarketplaceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse({"ok": True, "result": result})


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    token = websocket.query_params.get("token", "")
    if token != _token():
        await websocket.close(code=4403)
        return

    await websocket.accept()
    connections.add(websocket)
    await websocket.send_json({"type": "welcome", "service": "clawlite-gateway"})

    try:
        while True:
            msg = await websocket.receive_json()
            if msg.get("type") == "ping":
                await websocket.send_json({"type": "pong", "ts": datetime.now(timezone.utc).isoformat()})
            else:
                await websocket.send_json({"type": "echo", "payload": msg})
    except WebSocketDisconnect:
        pass
    finally:
        connections.discard(websocket)


def run_gateway(host: str | None = None, port: int | None = None) -> None:
    cfg = load_config()
    h = host or cfg.get("gateway", {}).get("host", "0.0.0.0")
    p = port or int(cfg.get("gateway", {}).get("port", 8787))
    uvicorn.run(app, host=h, port=p)
