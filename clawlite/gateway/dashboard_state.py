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


def dashboard_channel_posture_summary(
    *,
    queue_payload: dict[str, Any],
    channels_dispatcher_payload: dict[str, Any],
    channels_delivery_payload: dict[str, Any],
    channels_inbound_payload: dict[str, Any],
    channels_recovery_payload: dict[str, Any],
) -> dict[str, Any]:
    queue = dict(queue_payload or {}) if isinstance(queue_payload, dict) else {}
    dispatcher = dict(channels_dispatcher_payload or {}) if isinstance(channels_dispatcher_payload, dict) else {}
    delivery = dict(channels_delivery_payload or {}) if isinstance(channels_delivery_payload, dict) else {}
    inbound = dict(channels_inbound_payload or {}) if isinstance(channels_inbound_payload, dict) else {}
    recovery = dict(channels_recovery_payload or {}) if isinstance(channels_recovery_payload, dict) else {}
    total = dict(delivery.get("total") or {}) if isinstance(delivery.get("total"), dict) else {}
    inbound_persistence = dict(inbound.get("persistence") or {}) if isinstance(inbound.get("persistence"), dict) else {}
    recovery_total = dict(recovery.get("total") or {}) if isinstance(recovery.get("total"), dict) else {}

    outbound_size = max(0, int(queue.get("outbound_size", 0) or 0))
    dead_letter_size = max(0, int(queue.get("dead_letter_size", 0) or 0))
    inbound_pending = max(0, int(inbound_persistence.get("pending", 0) or 0))
    dispatcher_enabled = bool(dispatcher.get("enabled", True))
    dispatcher_running = bool(dispatcher.get("running", False))
    dispatcher_task_state = str(dispatcher.get("task_state", "unknown") or "unknown").strip().lower() or "unknown"
    dispatcher_error = str(dispatcher.get("last_error", "") or "").strip()
    dispatcher_active_tasks = max(0, int(dispatcher.get("active_tasks", 0) or 0))
    dispatcher_active_sessions = max(0, int(dispatcher.get("active_sessions", 0) or 0))
    recovery_enabled = bool(recovery.get("enabled", True))
    recovery_running = bool(recovery.get("running", False))
    recovery_task_state = str(recovery.get("task_state", "unknown") or "unknown").strip().lower() or "unknown"
    recovery_error = str(recovery.get("last_error", "") or "").strip()
    recovery_success = max(0, int(recovery_total.get("success", 0) or 0))
    recovery_failures = max(0, int(recovery_total.get("failures", 0) or 0))
    recovery_cooldown_skips = max(0, int(recovery_total.get("skipped_cooldown", 0) or 0))
    delivery_confirmed = max(0, int(total.get("delivery_confirmed", total.get("success", 0)) or 0))
    delivery_failed_final = max(0, int(total.get("delivery_failed_final", total.get("failures", 0)) or 0))
    dead_lettered = max(0, int(total.get("dead_lettered", 0) or 0))

    if dispatcher_error:
        dispatcher_posture = "error"
    elif not dispatcher_enabled:
        dispatcher_posture = "disabled"
    elif not dispatcher_running:
        dispatcher_posture = "stopped"
    elif dispatcher_active_tasks > 0 or dispatcher_active_sessions > 0:
        dispatcher_posture = "busy"
    else:
        dispatcher_posture = "steady"

    if recovery_error:
        recovery_posture = "error"
    elif not recovery_enabled:
        recovery_posture = "disabled"
    elif not recovery_running:
        recovery_posture = "stopped"
    elif recovery_failures > 0 or recovery_cooldown_skips > 0:
        recovery_posture = "recovering"
    else:
        recovery_posture = "steady"

    if dead_letter_size > 0:
        queue_posture = "dead_letter_backlog"
    elif outbound_size > 0 or inbound_pending > 0:
        queue_posture = "queued"
    else:
        queue_posture = "clear"

    if dispatcher_error:
        summary_posture = "dispatcher_error"
        summary_tone = "danger"
        operator_hint = "Channel dispatcher reported an error; inspect diagnostics or run channel recovery before replaying more work."
    elif dispatcher_enabled and not dispatcher_running:
        summary_posture = "dispatcher_stopped"
        summary_tone = "danger"
        operator_hint = "Channel dispatcher is stopped while enabled; restart channel recovery to restore delivery flow."
    elif recovery_error:
        summary_posture = "recovery_error"
        summary_tone = "danger"
        operator_hint = "Channel recovery loop reported an error; inspect the recovery supervisor before retrying failed deliveries."
    elif recovery_enabled and not recovery_running:
        summary_posture = "recovery_stopped"
        summary_tone = "warn"
        operator_hint = "Channel recovery loop is not running, so failed workers will not self-heal until it is restarted."
    elif dead_letter_size > 0:
        summary_posture = "dead_letter_backlog"
        summary_tone = "warn"
        operator_hint = "Dead letters are pending; replay or inspect the failing channel before more messages accumulate."
    elif recovery_failures > 0 or recovery_cooldown_skips > 0:
        summary_posture = "recovering"
        summary_tone = "warn"
        operator_hint = "Recent channel recovery activity is still in progress; watch cooldown skips and repeated failures."
    elif outbound_size > 0 or inbound_pending > 0 or dispatcher_active_tasks > 0:
        summary_posture = "busy"
        summary_tone = "ok"
        operator_hint = "Channel delivery is active; queue and replay activity are currently moving through the dispatcher."
    else:
        summary_posture = "healthy"
        summary_tone = "ok"
        operator_hint = "Channel delivery and recovery loops look steady."

    return {
        "summary_posture": summary_posture,
        "summary_tone": summary_tone,
        "operator_hint": operator_hint,
        "queue_posture": queue_posture,
        "dispatcher_posture": dispatcher_posture,
        "recovery_posture": recovery_posture,
        "queue": {
            "outbound_size": outbound_size,
            "dead_letter_size": dead_letter_size,
            "inbound_pending": inbound_pending,
        },
        "delivery": {
            "delivery_confirmed": delivery_confirmed,
            "delivery_failed_final": delivery_failed_final,
            "dead_lettered": dead_lettered,
        },
        "dispatcher": {
            "enabled": dispatcher_enabled,
            "running": dispatcher_running,
            "task_state": dispatcher_task_state,
            "active_tasks": dispatcher_active_tasks,
            "active_sessions": dispatcher_active_sessions,
            "last_error": dispatcher_error,
        },
        "recovery": {
            "enabled": recovery_enabled,
            "running": recovery_running,
            "task_state": recovery_task_state,
            "success": recovery_success,
            "failures": recovery_failures,
            "skipped_cooldown": recovery_cooldown_skips,
            "last_error": recovery_error,
        },
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


def _dashboard_field(payload: Any, key: str, default: Any = None) -> Any:
    if isinstance(payload, dict):
        return payload.get(key, default)
    return getattr(payload, key, default)


def _runtime_policy_session_ids(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        raw_values = [values]
    else:
        try:
            raw_values = list(values)
        except TypeError:
            raw_values = [values]
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in raw_values:
        item = str(raw or "").strip()
        if not item or item in seen:
            continue
        normalized.append(item)
        seen.add(item)
    return normalized


def _runtime_policy_config_snapshot(config: Any) -> dict[str, Any]:
    gateway = _dashboard_field(config, "gateway")
    autonomy = _dashboard_field(gateway, "autonomy")
    enabled = bool(_dashboard_field(autonomy, "self_evolution_enabled", False))
    require_approval = bool(_dashboard_field(autonomy, "self_evolution_require_approval", False))
    enabled_for_sessions = _runtime_policy_session_ids(
        _dashboard_field(autonomy, "self_evolution_enabled_for_sessions", [])
    )
    autonomy_session_id = str(_dashboard_field(autonomy, "session_id", "") or "").strip()
    if not enabled:
        activation_scope = "disabled"
    elif enabled_for_sessions:
        activation_scope = "session_canary"
    else:
        activation_scope = "global"
    return {
        "enabled": enabled,
        "require_approval": require_approval,
        "activation_scope": activation_scope,
        "enabled_for_sessions": enabled_for_sessions,
        "enabled_for_sessions_count": len(enabled_for_sessions),
        "enabled_for_sessions_sample": enabled_for_sessions[:3],
        "autonomy_session_id": autonomy_session_id,
    }


def _runtime_policy_effective_enabled(evolution_status: dict[str, Any], evolution_runner: dict[str, Any]) -> bool:
    return bool(
        evolution_status.get("enabled", False)
        or evolution_status.get("background_enabled", False)
        or evolution_runner.get("enabled", False)
    )


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

    evolution_enabled = _runtime_policy_effective_enabled(evolution_status, evolution_runner)
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
            "enabled": evolution_enabled,
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


def dashboard_runtime_policy_summary(*, self_evolution_payload: dict[str, Any], config: Any = None) -> dict[str, Any]:
    self_evolution = dict(self_evolution_payload or {}) if isinstance(self_evolution_payload, dict) else {}
    evolution_status = dict(self_evolution.get("status") or {}) if isinstance(self_evolution.get("status"), dict) else {}
    evolution_runner = dict(self_evolution.get("runner") or {}) if isinstance(self_evolution.get("runner"), dict) else {}
    config_snapshot = _runtime_policy_config_snapshot(config)

    evolution_enabled = _runtime_policy_effective_enabled(evolution_status, evolution_runner)
    background_enabled = bool(evolution_status.get("background_enabled", False))
    require_approval = bool(evolution_status.get("require_approval", False))
    activation_scope = str(evolution_status.get("activation_mode", "") or evolution_runner.get("activation_mode", "") or "").strip()
    activation_reason = str(
        evolution_status.get("activation_reason", "") or evolution_runner.get("activation_reason", "") or ""
    ).strip()
    enabled_for_sessions = _runtime_policy_session_ids(
        evolution_status.get("enabled_for_sessions", []) or evolution_runner.get("enabled_for_sessions", []) or []
    )
    autonomy_session_id = str(
        evolution_status.get("autonomy_session_id", "") or evolution_runner.get("autonomy_session_id", "") or ""
    ).strip()
    last_review_status = str(evolution_status.get("last_review_status", "") or "").strip()
    cooldown_remaining_s = round(_runtime_posture_number(evolution_status.get("cooldown_remaining_s")), 3)
    runner_enabled = bool(evolution_runner.get("enabled", False))

    if not evolution_enabled:
        activation_scope = "disabled"
    elif not activation_scope:
        activation_scope = "session_canary" if enabled_for_sessions else "global"

    if not evolution_enabled:
        approval_mode = "disabled"
        policy_posture = "manual_only"
        policy_tone = "warn"
        policy_block = activation_reason or "disabled_by_config"
        current_session_allowed = False
        policy_hint = "Background self-evolution is disabled; only explicit/manual runs can proceed."
    else:
        approval_mode = "approval_required" if require_approval else "direct_commit"
        current_session_allowed = not enabled_for_sessions or (
            bool(autonomy_session_id) and autonomy_session_id in enabled_for_sessions
        )
        if activation_reason:
            policy_posture = "blocked"
            policy_tone = "warn"
            policy_block = activation_reason
            if activation_reason == "autonomy_session_not_allowlisted":
                policy_hint = (
                    f"Current autonomy session {autonomy_session_id or 'unbound'} is outside the canary allowlist."
                )
            else:
                policy_hint = f"Runtime policy is currently blocked by {activation_reason}."
        elif activation_scope == "session_canary":
            policy_posture = "session_canary"
            policy_tone = "warn"
            policy_block = ""
            policy_hint = (
                f"Canary policy restricts background self-evolution to {len(enabled_for_sessions)} allowlisted session(s)."
            )
        elif approval_mode == "approval_required":
            policy_posture = "approval_required"
            policy_tone = "warn"
            policy_block = ""
            policy_hint = "Runtime policy requires approval before merge."
        else:
            policy_posture = "direct_commit"
            policy_tone = "ok"
            policy_block = ""
            policy_hint = "Runtime policy allows direct commits; monitor recent outcomes before widening scope."

    configured_scope = str(config_snapshot.get("activation_scope", "disabled") or "disabled")
    configured_allowlist = _runtime_policy_session_ids(config_snapshot.get("enabled_for_sessions", []))
    configured_session_id = str(config_snapshot.get("autonomy_session_id", "") or "").strip()
    configured_enabled = bool(config_snapshot.get("enabled", False))
    configured_require_approval = bool(config_snapshot.get("require_approval", False))

    effective_snapshot = {
        "enabled": evolution_enabled,
        "background_enabled": background_enabled,
        "runner_enabled": runner_enabled,
        "require_approval": require_approval,
        "activation_scope": activation_scope,
        "enabled_for_sessions_count": len(enabled_for_sessions),
        "enabled_for_sessions_sample": enabled_for_sessions[:3],
        "autonomy_session_id": autonomy_session_id,
        "current_session_allowed": current_session_allowed,
    }

    if configured_enabled != evolution_enabled:
        drift_posture = "engine_mismatch"
        drift_tone = "danger"
        drift_reason = "enabled_mismatch"
        drift_hint = "Configured self-evolution enablement no longer matches the effective runtime state."
    elif configured_require_approval != require_approval:
        drift_posture = "approval_mismatch"
        drift_tone = "warn"
        drift_reason = "approval_mode_mismatch"
        drift_hint = "Configured approval policy differs from the effective runtime review gate."
    elif configured_scope != activation_scope:
        drift_posture = "scope_mismatch"
        drift_tone = "warn"
        drift_reason = "activation_scope_mismatch"
        drift_hint = "Configured activation scope differs from the effective runtime policy scope."
    elif sorted(configured_allowlist) != sorted(enabled_for_sessions):
        drift_posture = "allowlist_mismatch"
        drift_tone = "warn"
        drift_reason = "allowlist_mismatch"
        drift_hint = "Configured canary allowlist differs from the effective runtime allowlist."
    elif configured_session_id and autonomy_session_id and configured_session_id != autonomy_session_id:
        drift_posture = "session_mismatch"
        drift_tone = "warn"
        drift_reason = "autonomy_session_mismatch"
        drift_hint = "Configured autonomy session differs from the session bound to self-evolution."
    elif configured_enabled and background_enabled and not runner_enabled:
        drift_posture = "runner_mismatch"
        drift_tone = "warn"
        drift_reason = "background_runner_disabled"
        drift_hint = "Runtime policy is enabled, but the background self-evolution runner is not marked active."
    elif policy_posture == "blocked":
        drift_posture = "aligned_blocked"
        drift_tone = "warn"
        drift_reason = policy_block or activation_reason or "runtime_blocked"
        drift_hint = "Configured policy matches runtime state, but the current runtime context is still blocked."
    else:
        drift_posture = "aligned"
        drift_tone = "ok"
        drift_reason = ""
        drift_hint = "Configured policy and effective runtime policy are aligned."

    return {
        "approval_mode": approval_mode,
        "activation_scope": activation_scope,
        "policy_posture": policy_posture,
        "policy_tone": policy_tone,
        "policy_block": policy_block,
        "policy_hint": policy_hint,
        "self_evolution": {
            "enabled": evolution_enabled,
            "background_enabled": background_enabled,
            "require_approval": require_approval,
            "activation_scope": activation_scope,
            "activation_reason": activation_reason,
            "autonomy_session_id": autonomy_session_id,
            "enabled_for_sessions_count": len(enabled_for_sessions),
            "enabled_for_sessions_sample": enabled_for_sessions[:3],
            "current_session_allowed": current_session_allowed,
            "last_review_status": last_review_status,
            "cooldown_remaining_s": cooldown_remaining_s,
        },
        "drift": {
            "posture": drift_posture,
            "tone": drift_tone,
            "reason": drift_reason,
            "hint": drift_hint,
            "configured": config_snapshot,
            "effective": effective_snapshot,
        },
    }


def dashboard_provider_health_summary(
    *,
    provider_telemetry_payload: dict[str, Any],
    provider_autonomy_payload: dict[str, Any],
    provider_status_payload: dict[str, Any],
) -> dict[str, Any]:
    telemetry = dict(provider_telemetry_payload or {}) if isinstance(provider_telemetry_payload, dict) else {}
    autonomy = dict(provider_autonomy_payload or {}) if isinstance(provider_autonomy_payload, dict) else {}
    status = dict(provider_status_payload or {}) if isinstance(provider_status_payload, dict) else {}
    summary = dict(telemetry.get("summary") or {}) if isinstance(telemetry.get("summary"), dict) else {}
    live_probe = dict(status.get("last_live_probe") or {}) if isinstance(status.get("last_live_probe"), dict) else {}
    capability = (
        dict(status.get("last_capability_probe") or {})
        if isinstance(status.get("last_capability_probe"), dict)
        else {}
    )

    provider_name = str(
        status.get("provider")
        or status.get("selected_provider")
        or autonomy.get("provider")
        or telemetry.get("provider")
        or ""
    ).strip()
    transport = str(status.get("transport") or summary.get("transport") or "").strip()
    active_model = str(status.get("active_model") or status.get("model") or "").strip()
    base_url = str(status.get("base_url") or "").strip()
    active_matches_selected = bool(status.get("active_matches_selected", False))
    summary_state = str(summary.get("state", autonomy.get("state", "healthy")) or "healthy").strip().lower()
    suppression_reason = str(
        autonomy.get("suppression_reason") or summary.get("suppression_reason") or ""
    ).strip().lower()
    suppression_backoff_s = round(_runtime_posture_number(autonomy.get("suppression_backoff_s")), 3)
    last_error_class = str(autonomy.get("last_error_class") or "").strip().lower()

    if not provider_name:
        health_posture = "unconfigured"
        health_tone = "warn"
        operator_hint = "No provider route is configured yet."
    elif status.get("ok") is False:
        health_posture = "status_error"
        health_tone = "danger"
        operator_hint = str(status.get("error") or "Provider status failed to load.").strip()
    elif summary_state == "circuit_open":
        health_posture = "circuit_open"
        health_tone = "danger"
        operator_hint = str(
            autonomy.get("suppression_hint")
            or "Provider recovery is blocked by an open circuit; wait for cooldown or recover the route."
        ).strip()
    elif suppression_reason in {"auth", "quota", "config"}:
        health_posture = "suppressed"
        health_tone = "danger"
        operator_hint = str(
            autonomy.get("suppression_hint")
            or f"Provider is suppressed by {suppression_reason}; fix the route before retrying."
        ).strip()
    elif live_probe and live_probe.get("ok") is False:
        health_posture = "probe_error"
        health_tone = "danger"
        operator_hint = str(
            live_probe.get("error") or "The latest cached live probe failed for the active provider route."
        ).strip()
    elif live_probe and (
        not active_matches_selected
        or not bool(live_probe.get("matches_current_model", False))
        or not bool(live_probe.get("matches_current_base_url", False))
    ):
        health_posture = "cache_stale"
        health_tone = "warn"
        operator_hint = "Cached probe posture no longer matches the active provider route."
    elif capability and bool(capability.get("checked", False)) and not bool(capability.get("current_model_listed", False)):
        health_posture = "model_not_listed"
        health_tone = "warn"
        operator_hint = "The active model is not present in the latest cached remote model list."
    elif summary_state in {"cooldown", "degraded"}:
        health_posture = summary_state
        health_tone = "warn"
        operator_hint = str(
            autonomy.get("suppression_hint")
            or (summary.get("hints", [""]) or [""])[0]
            or "Provider recovery is still in progress."
        ).strip()
    elif not live_probe:
        health_posture = "probe_missing"
        health_tone = "warn"
        operator_hint = "No cached live probe is recorded yet for the selected provider."
    elif not capability:
        health_posture = "capability_missing"
        health_tone = "warn"
        operator_hint = "No cached capability summary is recorded yet for the selected provider."
    else:
        health_posture = "healthy"
        health_tone = "ok"
        operator_hint = str(
            (summary.get("hints", [""]) or [""])[0] or "Cached provider route and capability posture look steady."
        ).strip()

    probe_posture = "missing"
    if live_probe:
        if live_probe.get("ok") is False:
            probe_posture = "error"
        elif bool(live_probe.get("matches_current_model", False)) and bool(live_probe.get("matches_current_base_url", False)):
            probe_posture = "matched"
        else:
            probe_posture = "stale"

    capability_posture = "missing"
    if capability:
        if not bool(capability.get("checked", False)):
            capability_posture = "unknown"
        elif bool(capability.get("current_model_listed", False)):
            capability_posture = "listed"
        else:
            capability_posture = "model_not_listed"

    return {
        "provider": provider_name,
        "transport": transport,
        "health_posture": health_posture,
        "health_tone": health_tone,
        "operator_hint": operator_hint,
        "route": {
            "selected_provider": str(status.get("selected_provider") or provider_name),
            "active_provider": str(status.get("active_provider") or ""),
            "active_model": active_model,
            "base_url": base_url,
            "base_url_source": str(status.get("base_url_source") or ""),
            "active_matches_selected": active_matches_selected,
        },
        "probe": {
            "recorded": bool(live_probe),
            "posture": probe_posture,
            "transport": str(live_probe.get("transport") or transport or ""),
            "checked_at": str(live_probe.get("checked_at") or ""),
            "ok": bool(live_probe.get("ok", False)) if live_probe else False,
            "status_code": int(live_probe.get("status_code", 0) or 0) if live_probe else 0,
            "error": str(live_probe.get("error") or ""),
            "matches_current_model": bool(live_probe.get("matches_current_model", False)) if live_probe else False,
            "matches_current_base_url": bool(live_probe.get("matches_current_base_url", False)) if live_probe else False,
        },
        "capability": {
            "recorded": bool(capability),
            "posture": capability_posture,
            "detail": str(capability.get("detail") or ""),
            "checked_at": str(capability.get("checked_at") or ""),
            "current_model_listed": bool(capability.get("current_model_listed", False)) if capability else False,
            "matched_model": str(capability.get("matched_model") or ""),
            "listed_model_count": int(capability.get("listed_model_count", 0) or 0) if capability else 0,
            "listed_model_sample": list(capability.get("listed_model_sample", []) or [])[:5] if capability else [],
        },
        "autonomy": {
            "state": summary_state,
            "suppression_reason": suppression_reason,
            "suppression_backoff_s": suppression_backoff_s,
            "last_error_class": last_error_class,
        },
    }


def dashboard_provider_budget_summary(
    *,
    provider_telemetry_payload: dict[str, Any],
    provider_autonomy_payload: dict[str, Any],
    provider_status_payload: dict[str, Any],
) -> dict[str, Any]:
    telemetry = dict(provider_telemetry_payload or {}) if isinstance(provider_telemetry_payload, dict) else {}
    autonomy = dict(provider_autonomy_payload or {}) if isinstance(provider_autonomy_payload, dict) else {}
    status = dict(provider_status_payload or {}) if isinstance(provider_status_payload, dict) else {}
    summary = dict(telemetry.get("summary") or {}) if isinstance(telemetry.get("summary"), dict) else {}
    counters = dict(telemetry.get("counters") or {}) if isinstance(telemetry.get("counters"), dict) else {}

    provider_name = str(
        status.get("active_provider")
        or status.get("selected_provider")
        or status.get("provider")
        or autonomy.get("provider")
        or telemetry.get("provider")
        or ""
    ).strip()
    transport = str(status.get("transport") or summary.get("transport") or "").strip()
    active_model = str(status.get("active_model") or status.get("model") or telemetry.get("model") or "").strip()
    summary_state = str(summary.get("state") or autonomy.get("state") or "healthy").strip().lower() or "healthy"
    suppression_reason = str(autonomy.get("suppression_reason") or summary.get("suppression_reason") or "").strip().lower()
    last_error_class = str(
        autonomy.get("last_error_class")
        or telemetry.get("last_error_class")
        or counters.get("last_error_class")
        or ""
    ).strip().lower()
    suppression_backoff_s = round(
        _runtime_posture_number(autonomy.get("suppression_backoff_s") or autonomy.get("cooldown_remaining_s")),
        3,
    )
    rate_limit_errors = max(0, int(counters.get("rate_limit_errors", 0) or 0))
    auth_errors = max(0, int(counters.get("auth_errors", 0) or 0))
    http_errors = max(0, int(counters.get("http_errors", 0) or 0))
    requests = max(0, int(counters.get("requests", 0) or 0))
    successes = max(0, int(counters.get("successes", 0) or 0))
    summary_hints = list(summary.get("hints", []) or []) if isinstance(summary.get("hints"), list) else []
    first_hint = str(summary_hints[0] or "").strip() if summary_hints else ""

    quota_signaled = suppression_reason == "quota" or last_error_class == "quota"
    rate_limit_signaled = suppression_reason == "rate_limit" or last_error_class == "rate_limit"
    non_budget_reason = ""
    for candidate in (suppression_reason, last_error_class, summary_state):
        normalized = str(candidate or "").strip().lower()
        if normalized and normalized not in {"healthy", "ready", "ok"}:
            non_budget_reason = normalized
            break

    if not provider_name:
        budget_posture = "unconfigured"
        budget_tone = "warn"
        operator_hint = "No provider route is configured yet."
    elif status.get("ok") is False:
        budget_posture = "unknown"
        budget_tone = "warn"
        operator_hint = str(status.get("error") or "Provider status failed to load.").strip()
    elif quota_signaled:
        budget_posture = "quota_exhausted"
        budget_tone = "danger"
        operator_hint = str(
            autonomy.get("suppression_hint")
            or first_hint
            or "Provider quota or billing appears exhausted; restore credits or switch the route."
        ).strip()
    elif rate_limit_signaled:
        budget_posture = "rate_limited"
        budget_tone = "warn"
        operator_hint = str(
            autonomy.get("suppression_hint")
            or first_hint
            or "Provider is rate-limited; wait for the window or switch the route."
        ).strip()
    elif non_budget_reason:
        non_budget_messages = {
            "auth": "Current provider issue is authentication-related, not quota-related.",
            "config": "Current provider issue is configuration-related, not quota-related.",
            "network": "Current provider issue is network-related, not quota-related.",
            "http_transient": "Current provider issue is transient HTTP failure, not quota-related.",
            "retry_exhausted": "Current provider issue is retry exhaustion, not quota-related.",
            "cooldown": "Provider is cooling down, but no quota or rate-limit signal is active.",
            "degraded": "Provider is degraded, but no quota or rate-limit signal is active.",
            "circuit_open": "Provider recovery is waiting on circuit cooldown, not quota or billing.",
        }
        budget_posture = "non_budget_block"
        budget_tone = "warn"
        non_budget_prefix = non_budget_messages.get(non_budget_reason) or f"Current provider issue is {non_budget_reason}, not quota-related."
        trailing_hint = str(autonomy.get("suppression_hint") or first_hint or "").strip()
        operator_hint = non_budget_prefix if not trailing_hint else f"{non_budget_prefix} {trailing_hint}"
    else:
        budget_posture = "clear"
        budget_tone = "ok"
        operator_hint = first_hint or "No quota or rate-limit pressure is visible in current provider telemetry."

    quota_posture = "unknown"
    if provider_name:
        quota_posture = "exhausted" if quota_signaled else "clear"
    rate_limit_posture = "unknown"
    if provider_name:
        rate_limit_posture = "limited" if rate_limit_signaled else "clear"

    return {
        "provider": provider_name,
        "transport": transport,
        "budget_posture": budget_posture,
        "budget_tone": budget_tone,
        "operator_hint": operator_hint,
        "route": {
            "selected_provider": str(status.get("selected_provider") or status.get("provider") or provider_name),
            "active_provider": str(status.get("active_provider") or ""),
            "active_model": active_model,
        },
        "quota": {
            "posture": quota_posture,
            "suppression_reason": suppression_reason,
            "last_error_class": last_error_class,
            "backoff_s": suppression_backoff_s if quota_signaled else 0.0,
        },
        "rate_limit": {
            "posture": rate_limit_posture,
            "error_count": rate_limit_errors,
            "suppression_reason": suppression_reason,
            "last_error_class": last_error_class,
            "backoff_s": suppression_backoff_s if rate_limit_signaled else 0.0,
        },
        "telemetry": {
            "summary_state": summary_state,
            "requests": requests,
            "successes": successes,
            "auth_errors": auth_errors,
            "rate_limit_errors": rate_limit_errors,
            "http_errors": http_errors,
            "last_error_class": last_error_class,
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
    channels_posture_payload: dict[str, Any],
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
    provider_health_payload: dict[str, Any],
    provider_budget_payload: dict[str, Any],
    self_evolution_payload: dict[str, Any],
    runtime_posture_payload: dict[str, Any],
    runtime_policy_payload: dict[str, Any],
) -> dict[str, Any]:
    channels_summary = dict(channels_payload or {}) if isinstance(channels_payload, dict) else {}
    channels_summary["posture"] = dict(channels_posture_payload or {}) if isinstance(channels_posture_payload, dict) else {}
    return {
        "contract_version": contract_version,
        "generated_at": generated_at,
        "control_plane": control_plane_to_dict(control_plane),
        "queue": queue_payload,
        "sessions": sessions_payload,
        "channels": channels_summary,
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
            "health": provider_health_payload,
            "budget": provider_budget_payload,
        },
        "self_evolution": self_evolution_payload,
        "runtime": {
            "posture": runtime_posture_payload,
            "policy": runtime_policy_payload,
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
