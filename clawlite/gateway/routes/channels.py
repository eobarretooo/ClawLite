from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse

from clawlite.channels.manager import manager
from clawlite.config.settings import load_config, save_config
from clawlite.gateway.utils import _check_bearer, _log

router = APIRouter()


def _normalize_accounts(value: Any) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if not isinstance(value, list):
        return rows
    for entry in value:
        if not isinstance(entry, dict):
            continue
        account = str(entry.get("account") or entry.get("name") or "").strip()
        token = str(entry.get("token", "")).strip()
        if not account and not token:
            continue
        row: dict[str, str] = {
            "account": account,
            "token": token,
        }
        if entry.get("app_token") is not None:
            row["app_token"] = str(entry.get("app_token", "")).strip()
        if entry.get("phone_number_id") is not None:
            row["phone_number_id"] = str(entry.get("phone_number_id", "")).strip()
        rows.append(row)
    return rows


def _normalize_allow_from(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _sanitize_channel(name: str, raw: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {
        "enabled": bool(raw.get("enabled", False)),
        "token": str(raw.get("token", "")).strip(),
        "account": str(raw.get("account", "")).strip(),
        "accounts": _normalize_accounts(raw.get("accounts", [])),
        "allowFrom": _normalize_allow_from(raw.get("allowFrom", [])),
        "allowChannels": _normalize_allow_from(raw.get("allowChannels", [])),
        "stt_enabled": bool(raw.get("stt_enabled", False)),
        "tts_enabled": bool(raw.get("tts_enabled", False)),
    }
    if "stt_model" in raw:
        clean["stt_model"] = str(raw.get("stt_model", "")).strip()
    if "stt_language" in raw:
        clean["stt_language"] = str(raw.get("stt_language", "")).strip()
    if "tts_provider" in raw:
        clean["tts_provider"] = str(raw.get("tts_provider", "")).strip()
    if "tts_model" in raw:
        clean["tts_model"] = str(raw.get("tts_model", "")).strip()
    if "tts_voice" in raw:
        clean["tts_voice"] = str(raw.get("tts_voice", "")).strip()
    if "tts_default_reply" in raw:
        clean["tts_default_reply"] = bool(raw.get("tts_default_reply", False))

    channel = str(name).strip().lower()
    if channel == "telegram":
        clean["chat_id"] = str(raw.get("chat_id", "")).strip()
    elif channel == "discord":
        clean["guild_id"] = str(raw.get("guild_id", "")).strip()
    elif channel == "slack":
        clean["workspace"] = str(raw.get("workspace", "")).strip()
        clean["app_token"] = str(raw.get("app_token") or raw.get("socket_mode_token") or "").strip()
    elif channel == "whatsapp":
        clean["phone"] = str(raw.get("phone", "")).strip()
        clean["phone_number_id"] = str(raw.get("phone_number_id", "")).strip()
    elif channel == "googlechat":
        clean["serviceAccountFile"] = str(raw.get("serviceAccountFile", "")).strip()
        if "serviceAccount" in raw:
            clean["serviceAccount"] = raw.get("serviceAccount")
        if "serviceAccountRef" in raw:
            clean["serviceAccountRef"] = raw.get("serviceAccountRef")
        clean["botUser"] = str(raw.get("botUser", "")).strip()
        clean["webhookPath"] = str(raw.get("webhookPath", "/api/webhooks/googlechat")).strip() or "/api/webhooks/googlechat"
        clean["requireMention"] = bool(raw.get("requireMention", True))
        dm_raw = raw.get("dm", {})
        if isinstance(dm_raw, dict):
            clean["dm"] = {
                "policy": str(dm_raw.get("policy", "pairing")).strip() or "pairing",
                "allowFrom": _normalize_allow_from(dm_raw.get("allowFrom", [])),
            }
    elif channel == "irc":
        clean["host"] = str(raw.get("host", "")).strip()
        raw_port = raw.get("port", 6697)
        try:
            clean["port"] = int(raw_port)
        except (TypeError, ValueError):
            clean["port"] = 6697
        clean["tls"] = bool(raw.get("tls", True))
        clean["nick"] = str(raw.get("nick", "clawlite-bot")).strip() or "clawlite-bot"
        clean["channels"] = _normalize_allow_from(raw.get("channels", []))
        clean["relay_url"] = str(raw.get("relay_url") or raw.get("relayUrl") or "").strip()
        clean["requireMention"] = bool(raw.get("requireMention", True))
    elif channel == "signal":
        clean["account"] = str(raw.get("account", "")).strip()
        clean["cliPath"] = str(raw.get("cliPath") or raw.get("cli_path") or "signal-cli").strip()
        clean["httpUrl"] = str(raw.get("httpUrl") or raw.get("http_url") or "").strip()
    elif channel == "imessage":
        clean["cliPath"] = str(raw.get("cliPath") or raw.get("cli_path") or "imsg").strip()
        clean["service"] = str(raw.get("service", "auto")).strip().lower()
    elif channel == "teams":
        clean["tenant"] = str(raw.get("tenant", "")).strip()

    return clean


def _channel_configured(channel_name: str, ch_cfg: dict[str, Any], account_count: int) -> bool:
    base_token = str(ch_cfg.get("token", "")).strip()
    if channel_name in {"telegram", "whatsapp", "discord", "teams"}:
        return bool(base_token or account_count > 0)
    if channel_name == "slack":
        account_rows = _normalize_accounts(ch_cfg.get("accounts", []))
        has_account_app_token = any(str(row.get("app_token", "")).strip() for row in account_rows)
        return bool(
            (base_token or account_count > 0)
            and (
                str(ch_cfg.get("app_token") or ch_cfg.get("socket_mode_token") or "").strip()
                or has_account_app_token
            )
        )
    if channel_name == "googlechat":
        return bool(
            str(ch_cfg.get("serviceAccountFile", "")).strip()
            or ch_cfg.get("serviceAccount")
            or ch_cfg.get("serviceAccountRef")
        )
    if channel_name == "irc":
        return bool(str(ch_cfg.get("host", "")).strip() and str(ch_cfg.get("nick", "")).strip())
    if channel_name == "signal":
        return bool(
            str(ch_cfg.get("account", "")).strip()
            or str(ch_cfg.get("httpUrl", "") or ch_cfg.get("http_url", "")).strip()
        )
    if channel_name == "imessage":
        return bool(str(ch_cfg.get("cliPath", "")).strip() or str(ch_cfg.get("cli_path", "")).strip())
    return bool(base_token or account_count > 0)


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
        channel_name = str(name).strip().lower()
        account_count = len(_normalize_accounts(ch_cfg.get("accounts", [])))
        has_token = _channel_configured(channel_name, ch_cfg, account_count)
        instance_prefix = f"{channel_name}:"
        online_instances = sum(
            1
            for key in manager.active_channels.keys()
            if key == channel_name or key.startswith(instance_prefix)
        )
        result.append({
            "channel": name,
            "enabled": enabled,
            "configured": has_token,
            "instances_online": online_instances,
            "accounts_configured": account_count,
            "stt_enabled": bool(ch_cfg.get("stt_enabled", False)),
            "tts_enabled": bool(ch_cfg.get("tts_enabled", False)),
        })
    return JSONResponse({"ok": True, "channels": result})


@router.get("/api/channels/instances")
def api_channels_instances(
    authorization: str | None = Header(default=None),
    channel: str = "",
) -> JSONResponse:
    _check_bearer(authorization)
    rows = manager.describe_instances(channel_name=channel)
    return JSONResponse({"ok": True, "instances": rows})


@router.post("/api/channels/reconnect")
async def api_channels_reconnect(
    payload: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    _check_bearer(authorization)
    channel = str(payload.get("channel", "")).strip().lower()
    if not channel:
        raise HTTPException(status_code=400, detail="Campo 'channel' é obrigatório")
    result = await manager.reconnect_channel(channel)
    _log("channels.reconnected", data={"channel": channel, "started": len(result.get("started", []))})
    return JSONResponse({"ok": True, **result})


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
        clean_channels[str(name)] = _sanitize_channel(str(name), raw)
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
        sanitized_channels[str(name)] = _sanitize_channel(str(name), raw)

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
