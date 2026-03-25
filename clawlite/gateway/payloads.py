from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any

from clawlite.providers.hints import provider_telemetry_summary


_SENSITIVE_KEY_MARKERS: tuple[str, ...] = (
    "api_key",
    "access_token",
    "token",
    "authorization",
    "auth",
    "credential",
    "credentials",
    "secret",
    "password",
)


def control_plane_to_dict(control_plane: Any) -> dict[str, Any]:
    if hasattr(control_plane, "model_dump"):
        payload = control_plane.model_dump()
        if isinstance(payload, dict):
            return payload
    if hasattr(control_plane, "dict"):
        payload = control_plane.dict()
        if isinstance(payload, dict):
            return payload
    if isinstance(control_plane, dict):
        return dict(control_plane)
    return {}


@lru_cache(maxsize=1)
def dashboard_asset_text(name: str) -> str:
    asset = resources.files("clawlite.dashboard").joinpath(name)
    return asset.read_text(encoding="utf-8")


def dashboard_bootstrap_payload(*, control_plane: Any, dashboard_asset_root: str) -> dict[str, Any]:
    control_plane_payload = control_plane_to_dict(control_plane)
    auth_payload = control_plane_payload.get("auth", {}) if isinstance(control_plane_payload, dict) else {}
    if not isinstance(auth_payload, dict):
        auth_payload = {}
    return {
        "brand": {
            "name": "ClawLite",
            "subtitle": "Gateway Dashboard",
        },
        "control_plane": control_plane_payload,
        "auth": dict(auth_payload),
        "paths": {
            "health": "/health",
            "dashboard_session": "/api/dashboard/session",
            "dashboard_state": "/api/dashboard/state",
            "status": "/api/status",
            "diagnostics": "/api/diagnostics",
            "message": "/api/message",
            "token": "/api/token",
            "tools": "/api/tools/catalog",
            "channels_replay": "/v1/control/channels/replay",
            "channels_recover": "/v1/control/channels/recover",
            "channels_inbound_replay": "/v1/control/channels/inbound-replay",
            "telegram_refresh": "/v1/control/channels/telegram/refresh",
            "telegram_pairing_approve": "/v1/control/channels/telegram/pairing/approve",
            "telegram_pairing_reject": "/v1/control/channels/telegram/pairing/reject",
            "telegram_pairing_revoke": "/v1/control/channels/telegram/pairing/revoke",
            "telegram_offset_commit": "/v1/control/channels/telegram/offset/commit",
            "telegram_offset_sync": "/v1/control/channels/telegram/offset/sync",
            "telegram_offset_reset": "/v1/control/channels/telegram/offset/reset",
            "discord_refresh": "/v1/control/channels/discord/refresh",
            "skills_refresh": "/v1/control/skills/refresh",
            "skills_sync": "/v1/control/skills/sync",
            "skills_doctor": "/v1/control/skills/doctor",
            "skills_validate": "/v1/control/skills/validate",
            "skills_managed": "/v1/control/skills/managed",
            "memory_doctor": "/v1/control/memory/doctor",
            "memory_suggest_refresh": "/v1/control/memory/suggest/refresh",
            "memory_snapshot_create": "/v1/control/memory/snapshot/create",
            "memory_snapshot_rollback": "/v1/control/memory/snapshot/rollback",
            "provider_recover": "/v1/control/provider/recover",
            "autonomy_wake": "/v1/control/autonomy/wake",
            "supervisor_recover": "/v1/control/supervisor/recover",
            "heartbeat_trigger": "/v1/control/heartbeat/trigger",
            "ws": "/ws",
        },
        "assets": {
            "css": f"{dashboard_asset_root}/dashboard.css",
            "js": f"{dashboard_asset_root}/dashboard.js",
        },
    }


def render_root_dashboard_html(
    *,
    control_plane: Any,
    dashboard_asset_root: str,
    dashboard_bootstrap_token: str,
) -> str:
    template = dashboard_asset_text("index.html")
    bootstrap = json.dumps(
        dashboard_bootstrap_payload(
            control_plane=control_plane,
            dashboard_asset_root=dashboard_asset_root,
        ),
        ensure_ascii=False,
    )
    return template.replace(dashboard_bootstrap_token, bootstrap)


def mask_secret(value: str, *, keep: int = 4) -> str:
    token = str(value or "").strip()
    if not token:
        return ""
    if len(token) <= keep:
        return "*" * len(token)
    return f"{'*' * max(3, len(token) - keep)}{token[-keep:]}"


def is_sensitive_telemetry_key(key: Any) -> bool:
    value = str(key or "").strip().lower()
    if not value:
        return False
    return any(marker in value for marker in _SENSITIVE_KEY_MARKERS)


def sanitize_telemetry_payload(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, nested in value.items():
            if is_sensitive_telemetry_key(key):
                continue
            sanitized[str(key)] = sanitize_telemetry_payload(nested)
        return sanitized
    if isinstance(value, list):
        return [sanitize_telemetry_payload(item) for item in value]
    return value


def provider_telemetry_snapshot(provider: Any) -> dict[str, Any]:
    minimal: dict[str, Any] = {
        "provider": str(getattr(provider, "provider_name", provider.__class__.__name__.lower()) or provider.__class__.__name__.lower()),
        "model": str(getattr(provider, "model", "") or ""),
        "diagnostics_available": False,
        "counters": {},
    }
    diagnostics_fn = getattr(provider, "diagnostics", None)
    if not callable(diagnostics_fn):
        return minimal
    try:
        raw = diagnostics_fn()
    except Exception:
        return minimal
    if not isinstance(raw, dict):
        return minimal

    telemetry = sanitize_telemetry_payload(raw)
    if not isinstance(telemetry, dict):
        return minimal
    telemetry.setdefault("provider", minimal["provider"])
    telemetry.setdefault("model", minimal["model"])
    telemetry["diagnostics_available"] = True
    if not isinstance(telemetry.get("counters"), dict):
        telemetry["counters"] = {}
    telemetry["summary"] = provider_telemetry_summary(telemetry)
    return telemetry


def autonomy_provider_suppression_hint(*, provider: str, reason: str) -> str:
    provider_name = str(provider or "provider").strip() or "provider"
    normalized_reason = str(reason or "").strip().lower()
    hints = {
        "auth": f"Provider {provider_name} needs valid credentials before autonomy should try again.",
        "quota": f"Provider {provider_name} appears out of quota or billing; restore credits or switch provider/model.",
        "rate_limit": f"Provider {provider_name} is rate-limited; wait for the limit window or use another provider.",
        "retry_exhausted": f"Provider {provider_name} exhausted retries; wait briefly before autonomy retries.",
        "network": f"Provider {provider_name} is unreachable; restore connectivity before autonomy retries.",
        "http_transient": f"Provider {provider_name} is seeing transient HTTP failures; let it recover before autonomy retries.",
        "circuit_open": f"Provider {provider_name} circuit breaker is open; autonomy will wait for cooldown.",
        "cooldown": f"Provider {provider_name} still has candidates cooling down; autonomy will wait before retrying.",
    }
    return hints.get(normalized_reason, "")


def provider_autonomy_snapshot(*, provider: Any, default_circuit_cooldown_s: float = 30.0) -> dict[str, Any]:
    telemetry = provider_telemetry_snapshot(provider)
    summary = telemetry.get("summary", {}) if isinstance(telemetry, dict) else {}
    counters = telemetry.get("counters", {}) if isinstance(telemetry, dict) else {}
    if not isinstance(summary, dict):
        summary = {}
    if not isinstance(counters, dict):
        counters = {}

    cooldown_candidates: list[float] = []
    for key in ("primary_cooldown_remaining_s", "fallback_cooldown_remaining_s"):
        try:
            value = float(counters.get(key, 0.0) or 0.0)
        except (TypeError, ValueError):
            value = 0.0
        if value > 0.0:
            cooldown_candidates.append(value)
    cooling_candidates = summary.get("cooling_candidates", []) if isinstance(summary.get("cooling_candidates"), list) else []
    for row in cooling_candidates:
        if not isinstance(row, dict):
            continue
        try:
            value = float(row.get("cooldown_remaining_s", 0.0) or 0.0)
        except (TypeError, ValueError):
            value = 0.0
        if value > 0.0:
            cooldown_candidates.append(value)

    state = str(summary.get("state", "healthy") or "healthy").strip().lower() or "healthy"
    provider_name = str(telemetry.get("provider", "") or "")
    last_error_class = str(telemetry.get("last_error_class", counters.get("last_error_class", "")) or "")
    summary_suppression_reason = str(summary.get("suppression_reason", "") or "").strip().lower()
    cooldown_remaining_s = max(cooldown_candidates, default=0.0)
    if state == "circuit_open" and cooldown_remaining_s <= 0.0:
        cooldown_remaining_s = max(0.0, float(default_circuit_cooldown_s or 0.0))

    suppression_reason = ""
    suppression_backoff_s = 0.0
    if state in {"circuit_open", "cooldown"}:
        suppression_reason = summary_suppression_reason or state
        suppression_backoff_s = cooldown_remaining_s
    else:
        synthetic_backoff_s = {
            "auth": 900.0,
            "quota": 1800.0,
            "rate_limit": 120.0,
            "retry_exhausted": 120.0,
            "network": 60.0,
            "http_transient": 60.0,
        }
        suppression_backoff_s = float(synthetic_backoff_s.get(last_error_class, 0.0) or 0.0)
        if suppression_backoff_s > 0.0:
            suppression_reason = last_error_class
    suppression_hint = autonomy_provider_suppression_hint(provider=provider_name, reason=suppression_reason)

    return {
        "provider": provider_name,
        "state": state,
        "cooldown_remaining_s": round(cooldown_remaining_s, 3),
        "last_error_class": last_error_class,
        "suppression_reason": suppression_reason,
        "suppression_backoff_s": round(suppression_backoff_s, 3),
        "suppression_hint": suppression_hint,
    }
