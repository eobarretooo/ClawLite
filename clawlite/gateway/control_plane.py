from __future__ import annotations

import datetime as dt
from typing import Any


def utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def control_plane_auth_payload(*, auth_guard: Any) -> dict[str, Any]:
    dashboard_sessions = getattr(auth_guard, "dashboard_sessions", None)
    return {
        "posture": auth_guard.posture(),
        "mode": auth_guard.mode,
        "allow_loopback_without_auth": auth_guard.allow_loopback_without_auth,
        "protect_health": auth_guard.protect_health,
        "token_configured": bool(auth_guard.token),
        "header_name": auth_guard.header_name,
        "query_param": auth_guard.query_param,
        "dashboard_session_enabled": bool(dashboard_sessions) and bool(auth_guard.token),
        "dashboard_session_header_name": getattr(auth_guard, "dashboard_session_header_name", ""),
        "dashboard_session_query_param": getattr(auth_guard, "dashboard_session_query_param", ""),
    }


def build_control_plane_payload(
    *,
    ready: bool,
    phase: str,
    contract_version: str,
    server_time: str,
    components: dict[str, Any],
    auth_payload: dict[str, Any],
    memory_proactive_enabled: bool,
) -> dict[str, Any]:
    return {
        "ready": bool(ready),
        "phase": str(phase),
        "contract_version": str(contract_version),
        "server_time": str(server_time),
        "components": dict(components),
        "auth": dict(auth_payload),
        "memory_proactive_enabled": bool(memory_proactive_enabled),
    }


def parse_iso_timestamp(value: str) -> dt.datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def semantic_metrics_from_payload(payload: Any) -> dict[str, Any]:
    semantic_raw = payload.get("semantic", {}) if isinstance(payload, dict) else {}
    if not isinstance(semantic_raw, dict):
        semantic_raw = {}
    return {
        "enabled": bool(semantic_raw.get("enabled", False)),
        "coverage_ratio": float(semantic_raw.get("coverage_ratio", 0.0) or 0.0),
        "missing_records": int(semantic_raw.get("missing_records", 0) or 0),
        "total_records": int(semantic_raw.get("total_records", 0) or 0),
    }


def reasoning_layer_metrics_from_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}

    reasoning_raw = payload.get("reasoning_layers")
    if reasoning_raw is None:
        reasoning_raw = payload.get("reasoningLayers")
    if reasoning_raw is None:
        reasoning_raw = payload.get("layers")

    reasoning_payload: dict[str, Any] = {}
    if isinstance(reasoning_raw, dict) and reasoning_raw:
        reasoning_payload["reasoning_layers"] = dict(reasoning_raw)

    confidence_raw = payload.get("confidence")
    if isinstance(confidence_raw, dict) and confidence_raw:
        reasoning_payload["confidence"] = dict(confidence_raw)

    return reasoning_payload


__all__ = [
    "build_control_plane_payload",
    "control_plane_auth_payload",
    "parse_iso_timestamp",
    "reasoning_layer_metrics_from_payload",
    "semantic_metrics_from_payload",
    "utc_now_iso",
]
