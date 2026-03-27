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


def _runtime_posture_number(value: Any, *, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _runtime_posture_severity(label: Any) -> tuple[int, str]:
    normalized = str(label or "").strip()
    if normalized in {"error", "provider_backoff"}:
        return 3, "danger"
    if normalized in {"busy", "no_progress_backoff", "disabled", "cooldown", "stopped", "approval_required"}:
        return 2, "warn"
    if normalized in {"running", "ready", "idle", "direct_commit"}:
        return 1, "ok"
    return 0, "danger"


def dashboard_runtime_posture_summary(
    *,
    autonomy_payload: dict[str, Any],
    autonomy_wake_payload: dict[str, Any],
    supervisor_payload: dict[str, Any],
    self_evolution_payload: dict[str, Any],
) -> dict[str, Any]:
    autonomy = dict(autonomy_payload or {}) if isinstance(autonomy_payload, dict) else {}
    autonomy_wake = dict(autonomy_wake_payload or {}) if isinstance(autonomy_wake_payload, dict) else {}
    supervisor = dict(supervisor_payload or {}) if isinstance(supervisor_payload, dict) else {}
    self_evolution = dict(self_evolution_payload or {}) if isinstance(self_evolution_payload, dict) else {}
    evolution_status = dict(self_evolution.get("status") or {}) if isinstance(self_evolution.get("status"), dict) else {}
    evolution_runner = dict(self_evolution.get("runner") or {}) if isinstance(self_evolution.get("runner"), dict) else {}

    autonomy_enabled = bool(autonomy.get("enabled", False))
    autonomy_running = bool(autonomy.get("running", False))
    autonomy_error = str(autonomy.get("last_error", "") or "").strip()
    autonomy_cooldown = max(0.0, _runtime_posture_number(autonomy.get("cooldown_remaining_s")))
    provider_backoff = max(0.0, _runtime_posture_number(autonomy.get("provider_backoff_remaining_s")))
    no_progress_backoff = max(0.0, _runtime_posture_number(autonomy.get("no_progress_backoff_remaining_s")))

    if not autonomy_enabled:
        autonomy_posture = "disabled"
    elif autonomy_error and not autonomy_running:
        autonomy_posture = "error"
    elif no_progress_backoff > 0.0:
        autonomy_posture = "no_progress_backoff"
    elif provider_backoff > 0.0:
        autonomy_posture = "provider_backoff"
    elif autonomy_cooldown > 0.0:
        autonomy_posture = "cooldown"
    elif autonomy_running:
        autonomy_posture = "running"
    else:
        autonomy_posture = "idle"

    wake_running = bool(autonomy_wake.get("running", False))
    wake_error = str(autonomy_wake.get("last_error", "") or "").strip()
    wake_queue_depth = max(0, int(autonomy_wake.get("queue_depth", 0) or 0))
    wake_pending = max(0, int(autonomy_wake.get("pending_count", 0) or 0))
    if wake_error and not wake_running:
        wake_posture = "error"
    elif wake_running and (wake_queue_depth > 0 or wake_pending > 0):
        wake_posture = "busy"
    elif wake_running:
        wake_posture = "ready"
    else:
        wake_posture = "stopped"

    evolution_enabled = bool(
        evolution_status.get("enabled", False)
        or evolution_status.get("background_enabled", False)
        or evolution_runner.get("enabled", False)
    )
    activation_mode = str(evolution_status.get("activation_mode", "") or evolution_runner.get("activation_mode", "") or "").strip()
    enabled_for_sessions = list(evolution_status.get("enabled_for_sessions", []) or evolution_runner.get("enabled_for_sessions", []) or [])
    last_review_status = str(evolution_status.get("last_review_status", "") or "").strip()

    if not evolution_enabled:
        approval_posture = "disabled"
    elif bool(evolution_status.get("require_approval", False)):
        approval_posture = "approval_required"
    else:
        approval_posture = "direct_commit"

    summary_posture = autonomy_posture
    summary_tone = _runtime_posture_severity(summary_posture)[1]
    for candidate in (wake_posture, approval_posture):
        candidate_severity, candidate_tone = _runtime_posture_severity(candidate)
        current_severity, _ = _runtime_posture_severity(summary_posture)
        if candidate_severity > current_severity:
            summary_posture = candidate
            summary_tone = candidate_tone

    if autonomy_posture == "disabled":
        operator_hint = "Autonomy loop is disabled; use a manual wake when you want proactive work."
    elif autonomy_posture == "no_progress_backoff":
        operator_hint = "Autonomy is paused by the no-progress guard; inspect provider/runtime context before forcing another wake."
    elif autonomy_posture == "provider_backoff":
        operator_hint = "Provider backoff is suppressing autonomy; recover the provider or wait for cooldown."
    elif wake_posture == "busy":
        operator_hint = "The wake coordinator already has pending work; let it drain before queueing another nudge."
    elif evolution_enabled and activation_mode == "session_canary" and enabled_for_sessions:
        operator_hint = f"Self-evolution is canary-gated to {len(enabled_for_sessions)} session(s)."
    elif evolution_enabled and approval_posture == "approval_required":
        operator_hint = "Self-evolution requires operator approval before merge."
    elif evolution_enabled and approval_posture == "direct_commit":
        operator_hint = "Self-evolution is configured for direct commit; monitor recent outcomes before widening scope."
    else:
        operator_hint = "Runtime posture looks steady."

    return {
        "autonomy_posture": autonomy_posture,
        "wake_posture": wake_posture,
        "approval_posture": approval_posture,
        "summary_posture": summary_posture,
        "summary_tone": summary_tone,
        "operator_hint": operator_hint,
        "autonomy": {
            "enabled": autonomy_enabled,
            "running": autonomy_running,
            "worker_state": str(autonomy.get("worker_state", "") or ""),
            "session_id": str(autonomy.get("session_id", "") or ""),
            "cooldown_remaining_s": round(autonomy_cooldown, 3),
            "provider_backoff_remaining_s": round(provider_backoff, 3),
            "provider_backoff_reason": str(autonomy.get("provider_backoff_reason", "") or ""),
            "provider_backoff_provider": str(autonomy.get("provider_backoff_provider", "") or ""),
            "no_progress_backoff_remaining_s": round(no_progress_backoff, 3),
            "no_progress_reason": str(autonomy.get("no_progress_reason", "") or ""),
            "no_progress_streak": int(autonomy.get("no_progress_streak", 0) or 0),
            "last_error": autonomy_error,
            "last_result_excerpt": str(autonomy.get("last_result_excerpt", "") or ""),
        },
        "autonomy_wake": {
            "running": wake_running,
            "worker_state": str(autonomy_wake.get("worker_state", "") or ""),
            "queue_depth": wake_queue_depth,
            "pending_count": wake_pending,
            "dropped_backpressure": int(autonomy_wake.get("dropped_backpressure", 0) or 0),
            "dropped_quota": int(autonomy_wake.get("dropped_quota", 0) or 0),
            "last_error": wake_error,
        },
        "self_evolution": {
            "enabled": bool(evolution_status.get("enabled", False)),
            "background_enabled": bool(evolution_status.get("background_enabled", False)),
            "activation_mode": activation_mode,
            "activation_reason": str(
                evolution_status.get("activation_reason", "") or evolution_runner.get("activation_reason", "") or ""
            ),
            "enabled_for_sessions_count": len(enabled_for_sessions),
            "autonomy_session_id": str(
                evolution_status.get("autonomy_session_id", "") or evolution_runner.get("autonomy_session_id", "") or ""
            ),
            "require_approval": bool(evolution_status.get("require_approval", False)),
            "cooldown_remaining_s": round(_runtime_posture_number(evolution_status.get("cooldown_remaining_s")), 3),
            "last_review_status": last_review_status,
            "last_outcome": str(evolution_status.get("last_outcome", "") or ""),
        },
        "supervisor": {
            "worker_state": str(supervisor.get("worker_state", "") or ""),
            "incident_count": int(supervisor.get("incident_count", 0) or 0),
            "consecutive_error_count": int(supervisor.get("consecutive_error_count", 0) or 0),
        },
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
    provider_status_payload: dict[str, Any],
    self_evolution_payload: dict[str, Any],
    runtime_posture_payload: dict[str, Any],
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
            "status": provider_status_payload,
        },
        "self_evolution": self_evolution_payload,
        "runtime": {
            "posture": runtime_posture_payload,
        },
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
