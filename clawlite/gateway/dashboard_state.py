from __future__ import annotations

import datetime as dt
from typing import Any


def dashboard_preview(value: Any, *, max_chars: int = 140) -> str:
    text = " ".join(str(value or "").strip().split())
    if len(text) <= max_chars:
        return text
    return f"{text[: max(1, max_chars - 3)]}..."


def recent_dashboard_sessions(*, sessions: Any, subagents: Any, limit: int = 8) -> dict[str, Any]:
    paths = sorted(
        sessions.root.glob("*.jsonl"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    rows: list[dict[str, Any]] = []
    for path in paths[: max(1, int(limit or 1))]:
        session_id = sessions._restore_session_id(path.stem)
        history = sessions.read(session_id, limit=1)
        last_message = history[-1] if history else {}
        session_runs = subagents.list_runs(session_id=session_id)
        active_runs = subagents.list_runs(session_id=session_id, active_only=True)
        subagent_statuses: dict[str, int] = {}
        for run in session_runs:
            subagent_statuses[run.status] = subagent_statuses.get(run.status, 0) + 1
        rows.append(
            {
                "session_id": session_id,
                "last_role": str(last_message.get("role", "") or ""),
                "last_preview": dashboard_preview(last_message.get("content", "")),
                "active_subagents": len(active_runs),
                "subagent_statuses": dict(sorted(subagent_statuses.items())),
                "updated_at": dt.datetime.fromtimestamp(path.stat().st_mtime, tz=dt.timezone.utc).isoformat(),
            }
        )
    return {
        "count": len(paths),
        "items": rows,
    }


def dashboard_channels_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for name, payload in sorted(snapshot.items()):
        row = dict(payload) if isinstance(payload, dict) else {"status": payload}
        state_label = str(
            row.get("status")
            or row.get("worker_state")
            or row.get("mode")
            or ("enabled" if bool(row.get("enabled", False)) else "disabled")
        )
        items.append(
            {
                "name": name,
                "enabled": bool(row.get("enabled", False)),
                "state": state_label,
                "summary": dashboard_preview(row, max_chars=180),
            }
        )
    return {
        "count": len(items),
        "items": items,
    }


def dashboard_cron_summary(*, cron: Any, limit: int = 8) -> dict[str, Any]:
    jobs = cron.list_jobs()
    enabled_count = sum(1 for row in jobs if bool(row.get("enabled", False)))
    status_counts: dict[str, int] = {}
    for row in jobs:
        status = str(row.get("last_status", "") or "idle").strip() or "idle"
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "status": cron.status(),
        "count": len(jobs),
        "enabled_count": enabled_count,
        "disabled_count": max(0, len(jobs) - enabled_count),
        "status_counts": dict(sorted(status_counts.items())),
        "jobs": jobs[: max(1, int(limit or 1))],
    }


def dashboard_self_evolution_summary(*, evolution: Any, runner_state: dict[str, Any]) -> dict[str, Any]:
    if evolution is None:
        return {"enabled": False, "status": {}, "runner": {}}
    return {
        "enabled": bool(evolution.enabled),
        "status": evolution.status(),
        "runner": dict(runner_state),
    }


def dashboard_state_payload(
    *,
    contract_version: str,
    generated_at: str,
    control_plane: Any,
    control_plane_to_dict: Any,
    queue_payload: dict[str, Any],
    sessions_payload: dict[str, Any],
    channels_payload: dict[str, Any],
    channels_dispatcher_payload: dict[str, Any],
    channels_delivery_payload: dict[str, Any],
    channels_inbound_payload: dict[str, Any],
    channels_recovery_payload: dict[str, Any],
    discord_payload: dict[str, Any],
    telegram_payload: dict[str, Any],
    cron_payload: dict[str, Any],
    heartbeat_payload: dict[str, Any],
    ws_payload: dict[str, Any] | None = None,
    subagents_payload: dict[str, Any],
    supervisor_payload: dict[str, Any],
    skills_payload: dict[str, Any],
    workspace_payload: dict[str, Any],
    handoff_payload: dict[str, Any],
    onboarding_payload: dict[str, Any],
    bootstrap_payload: dict[str, Any],
    memory_payload: dict[str, Any],
    provider_telemetry_payload: dict[str, Any],
    provider_autonomy_payload: dict[str, Any],
    self_evolution_payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "contract_version": contract_version,
        "generated_at": generated_at,
        "control_plane": control_plane_to_dict(control_plane),
        "queue": queue_payload,
        "sessions": sessions_payload,
        "channels": channels_payload,
        "channels_dispatcher": channels_dispatcher_payload,
        "channels_delivery": channels_delivery_payload,
        "channels_inbound": channels_inbound_payload,
        "channels_recovery": channels_recovery_payload,
        "discord": discord_payload,
        "telegram": telegram_payload,
        "cron": cron_payload,
        "heartbeat": heartbeat_payload,
        "ws": dict(ws_payload or {}),
        "subagents": subagents_payload,
        "supervisor": supervisor_payload,
        "skills": skills_payload,
        "workspace": workspace_payload,
        "handoff": handoff_payload,
        "onboarding": onboarding_payload,
        "bootstrap": bootstrap_payload,
        "memory": memory_payload,
        "provider": {
            "telemetry": provider_telemetry_payload,
            "autonomy": provider_autonomy_payload,
        },
        "self_evolution": self_evolution_payload,
    }


def operator_channel_summary(channel: Any) -> dict[str, Any]:
    operator_status = getattr(channel, "operator_status", None)
    if channel is None or not callable(operator_status):
        return {"available": False}
    try:
        payload = operator_status()
    except Exception as exc:
        return {"last_error": str(exc), "available": False}
    if isinstance(payload, dict):
        return {"available": True, **payload}
    return {"available": True}
