from __future__ import annotations

import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header
from fastapi.responses import HTMLResponse, JSONResponse

from clawlite.config.settings import CONFIG_DIR, load_config, save_config
from clawlite.gateway.state import STARTED_AT, chat_connections, connections, log_connections, LOG_RING
from clawlite.gateway.utils import (
    _check_bearer,
    _load_dashboard_settings,
    _log,
    _save_dashboard_settings,
    _skills_dir,
    _token,
    _version,
)

router = APIRouter()


@router.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "ok": True,
        "service": "clawlite-gateway",
        "uptime_seconds": int((datetime.now(timezone.utc) - STARTED_AT).total_seconds()),
        "connections": len(connections) + len(chat_connections) + len(log_connections),
    }


@router.get("/")
def root() -> HTMLResponse:
    # Need to get dashboard.html from parent folder
    html = (Path(__file__).parent.parent / "dashboard.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@router.get("/dashboard")
def dashboard() -> HTMLResponse:
    html = (Path(__file__).parent.parent / "dashboard.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@router.post("/api/dashboard/auth")
def api_dashboard_auth(payload: dict[str, Any]) -> JSONResponse:
    import secrets
    token = str(payload.get("token", "")).strip()
    ok = secrets.compare_digest(token, _token())
    return JSONResponse({"ok": ok})


@router.get("/api/status")
def api_status(authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    cfg = load_config()
    return JSONResponse({
        "ok": True,
        "gateway": cfg.get("gateway", {}),
        "skills": cfg.get("skills", []),
        "connections": len(connections) + len(chat_connections) + len(log_connections),
    })


@router.get("/api/dashboard/bootstrap")
def api_dashboard_bootstrap(authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    cfg = load_config()
    settings = _load_dashboard_settings()
    return JSONResponse({
        "ok": True,
        "status": {
            "online": True,
            "uptime_seconds": int((datetime.now(timezone.utc) - STARTED_AT).total_seconds()),
            "model": cfg.get("model", "unknown"),
            "connections": len(connections) + len(chat_connections) + len(log_connections),
        },
        "settings": {
            "model": cfg.get("model", "openai/gpt-4o-mini"),
            "channels": cfg.get("channels", {}),
            "hooks": settings.get("hooks", {"pre": "", "post": ""}),
            "theme": settings.get("theme", "dark"),
        },
    })


@router.get("/api/dashboard/settings")
def api_dashboard_get_settings(authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    cfg = load_config()
    settings = _load_dashboard_settings()
    return JSONResponse({
        "ok": True,
        "settings": {
            "model": cfg.get("model", "openai/gpt-4o-mini"),
            "channels": cfg.get("channels", {}),
            "hooks": settings.get("hooks", {"pre": "", "post": ""}),
            "theme": settings.get("theme", "dark"),
        },
    })


@router.put("/api/dashboard/settings")
def api_dashboard_save_settings(payload: dict[str, Any], authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    cfg = load_config()
    model = str(payload.get("model", cfg.get("model", ""))).strip() or cfg.get("model", "openai/gpt-4o-mini")
    channels = payload.get("channels", cfg.get("channels", {}))
    hooks = payload.get("hooks", _load_dashboard_settings().get("hooks", {"pre": "", "post": ""}))
    theme = str(payload.get("theme", "dark") or "dark")

    cfg["model"] = model
    if isinstance(channels, dict):
        cfg["channels"] = channels
    save_config(cfg)

    dashboard_settings = _load_dashboard_settings()
    dashboard_settings["hooks"] = hooks if isinstance(hooks, dict) else {"pre": "", "post": ""}
    dashboard_settings["theme"] = theme
    _save_dashboard_settings(dashboard_settings)

    _log("settings.updated", data={"model": model})
    return JSONResponse({"ok": True, "settings": {"model": model, "channels": cfg.get("channels", {}), "hooks": dashboard_settings["hooks"], "theme": theme}})


@router.get("/api/dashboard/status")
def api_dashboard_status(authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    cfg = load_config()
    return JSONResponse({
        "ok": True,
        "online": True,
        "uptime_seconds": int((datetime.now(timezone.utc) - STARTED_AT).total_seconds()),
        "model": cfg.get("model", "unknown"),
        "connections": len(connections) + len(chat_connections) + len(log_connections),
    })


@router.get("/api/dashboard/debug")
def api_dashboard_debug(authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    return JSONResponse(
        {
            "ok": True,
            "debug": {
                "version": _version(),
                "python": sys.version.split(" ")[0],
                "platform": platform.platform(),
                "cwd": str(Path.cwd()),
                "home": str(Path.home()),
                "config_dir": str(CONFIG_DIR),
                "skills_dir": str(_skills_dir()),
                "logs_in_ring": len(LOG_RING),
                "uptime_seconds": int((datetime.now(timezone.utc) - STARTED_AT).total_seconds()),
            },
        }
    )
