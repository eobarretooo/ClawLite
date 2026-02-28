from __future__ import annotations

import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse

from clawlite.config.settings import CONFIG_DIR, load_config, save_config
from clawlite.core.model_catalog import get_model_or_default, list_models
from clawlite.core.rbac import ROLE_SCOPES, get_audit_log, set_tool_policy
from clawlite.gateway.state import LOG_RING, STARTED_AT, chat_connections, connections, log_connections
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
    return JSONResponse(
        {
            "ok": True,
            "gateway": cfg.get("gateway", {}),
            "skills": cfg.get("skills", []),
            "connections": len(connections) + len(chat_connections) + len(log_connections),
        }
    )


@router.get("/api/dashboard/bootstrap")
def api_dashboard_bootstrap(authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    cfg = load_config()
    settings = _load_dashboard_settings()
    model_key = str(cfg.get("model", "openai/gpt-4o-mini"))
    model_meta = get_model_or_default(model_key)

    return JSONResponse(
        {
            "ok": True,
            "status": {
                "online": True,
                "uptime_seconds": int((datetime.now(timezone.utc) - STARTED_AT).total_seconds()),
                "model": model_key,
                "connections": len(connections) + len(chat_connections) + len(log_connections),
            },
            "settings": {
                "model": model_key,
                "channels": cfg.get("channels", {}),
                "hooks": settings.get("hooks", {"pre": "", "post": ""}),
                "theme": settings.get("theme", "dark"),
            },
            "model_metadata": {
                "provider": model_meta.provider,
                "display_name": model_meta.display_name,
                "context_window": model_meta.context_window,
                "max_output_tokens": model_meta.max_output_tokens,
                "api_format": model_meta.api_format,
            },
        }
    )


@router.get("/api/dashboard/settings")
def api_dashboard_get_settings(authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    cfg = load_config()
    settings = _load_dashboard_settings()
    return JSONResponse(
        {
            "ok": True,
            "settings": {
                "model": cfg.get("model", "openai/gpt-4o-mini"),
                "channels": cfg.get("channels", {}),
                "hooks": settings.get("hooks", {"pre": "", "post": ""}),
                "theme": settings.get("theme", "dark"),
            },
        }
    )


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
    return JSONResponse(
        {
            "ok": True,
            "settings": {
                "model": model,
                "channels": cfg.get("channels", {}),
                "hooks": dashboard_settings["hooks"],
                "theme": theme,
            },
        }
    )


@router.get("/api/dashboard/status")
def api_dashboard_status(authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    cfg = load_config()
    return JSONResponse(
        {
            "ok": True,
            "online": True,
            "uptime_seconds": int((datetime.now(timezone.utc) - STARTED_AT).total_seconds()),
            "model": cfg.get("model", "unknown"),
            "connections": len(connections) + len(chat_connections) + len(log_connections),
        }
    )


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


@router.get("/api/models/catalog")
def api_models_catalog(
    authorization: str | None = Header(default=None),
    provider: str = Query(default=""),
) -> JSONResponse:
    _check_bearer(authorization)
    items = []
    for entry in list_models(provider=provider):
        items.append(
            {
                "key": f"{entry.provider}/{entry.id}",
                "id": entry.id,
                "provider": entry.provider,
                "display_name": entry.display_name,
                "context_window": entry.context_window,
                "max_output_tokens": entry.max_output_tokens,
                "api_format": entry.api_format,
                "deprecated": entry.deprecated,
                "cost": {
                    "input": entry.cost.input,
                    "output": entry.cost.output,
                    "cache_read": entry.cost.cache_read,
                },
                "capabilities": {
                    "text": entry.capabilities.text,
                    "image_input": entry.capabilities.image_input,
                    "tool_calling": entry.capabilities.tool_calling,
                    "streaming": entry.capabilities.streaming,
                    "reasoning": entry.capabilities.reasoning,
                    "json_mode": entry.capabilities.json_mode,
                },
            }
        )
    return JSONResponse({"ok": True, "provider": provider or "all", "models": items})


@router.get("/api/security/rbac")
def api_security_rbac(authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    cfg = load_config()
    security_cfg = cfg.get("security", {}) if isinstance(cfg.get("security"), dict) else {}
    policies = security_cfg.get("tool_policies", {}) if isinstance(security_cfg.get("tool_policies"), dict) else {}
    roles = {role.value: sorted(scope.value for scope in scopes) for role, scopes in ROLE_SCOPES.items()}
    return JSONResponse({"ok": True, "roles": roles, "tool_policies": policies})


@router.get("/api/security/tool-audit")
def api_security_tool_audit(
    authorization: str | None = Header(default=None),
    limit: int = Query(default=50, ge=1, le=500),
) -> JSONResponse:
    _check_bearer(authorization)
    return JSONResponse({"ok": True, "entries": get_audit_log(limit=limit)})


@router.put("/api/security/tool-policy")
def api_security_tool_policy(payload: dict[str, Any], authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    tool_name = str(payload.get("tool_name", "")).strip()
    policy = str(payload.get("policy", "")).strip().lower()
    if not tool_name:
        raise HTTPException(status_code=400, detail="tool_name e obrigatorio")
    if policy not in {"allow", "review", "deny"}:
        raise HTTPException(status_code=400, detail="policy invalida: use allow|review|deny")
    set_tool_policy(tool_name, policy)
    _log("security.tool_policy.updated", data={"tool_name": tool_name, "policy": policy})
    return JSONResponse({"ok": True, "tool_name": tool_name, "policy": policy})
