from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse

from clawlite.config.settings import load_config, save_config
from clawlite.gateway.utils import _check_bearer, _log

router = APIRouter()


@router.get("/api/channels/status")
def api_channels_status(authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    cfg = load_config()
    channels_cfg = cfg.get("channels", {})
    result: list[dict[str, Any]] = []
    for name, ch_cfg in channels_cfg.items():
        if not isinstance(ch_cfg, dict):
            continue
        enabled = bool(ch_cfg.get("enabled", False))
        has_token = bool(ch_cfg.get("token") or ch_cfg.get("accounts"))
        result.append({
            "channel": name,
            "enabled": enabled,
            "configured": has_token,
            "stt_enabled": bool(ch_cfg.get("stt_enabled", False)),
            "tts_enabled": bool(ch_cfg.get("tts_enabled", False)),
        })
    return JSONResponse({"ok": True, "channels": result})


@router.put("/api/channels/config")
def api_channels_config_save(payload: dict[str, Any], authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    cfg = load_config()
    channels = payload.get("channels", {})
    if not isinstance(channels, dict):
        raise HTTPException(status_code=400, detail="Campo 'channels' deve ser objeto")

    clean_channels: dict[str, dict[str, Any]] = {}
    for name, raw in channels.items():
        if not isinstance(raw, dict):
            continue
        clean_channels[str(name)] = {
            "enabled": bool(raw.get("enabled", False)),
            "token": str(raw.get("token", "")).strip(),
            "account": str(raw.get("account", "")).strip(),
            "stt_enabled": bool(raw.get("stt_enabled", False)),
            "tts_enabled": bool(raw.get("tts_enabled", False)),
        }
    cfg["channels"] = clean_channels
    save_config(cfg)
    _log("channels.updated", data={"count": len(clean_channels)})
    return JSONResponse({"ok": True, "channels": clean_channels})


@router.post("/api/dashboard/config/apply")
def api_dashboard_config_apply(payload: dict[str, Any], authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    cfg = load_config()
    dry_run = bool(payload.get("dry_run", False))

    model = str(payload.get("model", cfg.get("model", ""))).strip()
    if not model:
        raise HTTPException(status_code=400, detail="Model obrigatório")

    channels = payload.get("channels", cfg.get("channels", {}))
    if not isinstance(channels, dict):
        raise HTTPException(status_code=400, detail="Campo 'channels' inválido")

    sanitized_channels: dict[str, dict[str, Any]] = {}
    for name, raw in channels.items():
        if not isinstance(raw, dict):
            continue
        sanitized_channels[str(name)] = {
            "enabled": bool(raw.get("enabled", False)),
            "token": str(raw.get("token", "")).strip(),
            "account": str(raw.get("account", "")).strip(),
            "stt_enabled": bool(raw.get("stt_enabled", False)),
            "tts_enabled": bool(raw.get("tts_enabled", False)),
        }

    pending_cfg = dict(cfg)
    pending_cfg["model"] = model
    pending_cfg["channels"] = sanitized_channels

    if not dry_run:
        save_config(pending_cfg)
        _log("config.applied", data={"model": model, "channels": len(sanitized_channels)})
    else:
        _log("config.apply.dry_run", data={"model": model, "channels": len(sanitized_channels)})

    return JSONResponse(
        {
            "ok": True,
            "dry_run": dry_run,
            "settings": {
                "model": model,
                "channels": sanitized_channels,
            },
            "message": "validação concluída" if dry_run else "config aplicada",
        }
    )


@router.post("/api/dashboard/config/restart")
def api_dashboard_config_restart(payload: dict[str, Any] | None = None, authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    mode = "safe"
    if isinstance(payload, dict):
        mode = str(payload.get("mode", "safe")).strip() or "safe"
    _log("gateway.restart.requested", data={"mode": mode})
    return JSONResponse(
        {
            "ok": True,
            "mode": mode,
            "performed": False,
            "message": "Restart seguro registrado (noop no runtime embutido)",
        }
    )
