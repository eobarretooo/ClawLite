from __future__ import annotations

from typing import Any


def build_proactive_runner_state(*, enabled: bool, interval_seconds: int) -> dict[str, Any]:
    return {
        "enabled": bool(enabled),
        "running": False,
        "interval_seconds": int(interval_seconds),
        "ticks": 0,
        "success_count": 0,
        "error_count": 0,
        "backpressure_count": 0,
        "backpressure_by_reason": {},
        "delivered_count": 0,
        "replayed_count": 0,
        "last_trigger": "",
        "last_backpressure_reason": "",
        "last_result": "",
        "last_error": "",
        "last_run_iso": "",
        "policy_event_count": 0,
        "delayed_count": 0,
        "discarded_count": 0,
        "policy_by_action": {},
        "policy_by_reason": {},
        "last_policy_action": "",
        "last_policy_reason": "",
        "last_policy_at": "",
        "recent_policy_events": [],
    }


def build_wake_pressure_state() -> dict[str, Any]:
    return {
        "enabled": True,
        "event_count": 0,
        "notice_count": 0,
        "events_by_kind": {},
        "events_by_reason": {},
        "streaks": {},
        "last_seen_monotonic": {},
        "last_kind": "",
        "last_reason": "",
        "last_summary": "",
        "last_event_at": "",
        "last_notice_at": "",
    }


def build_cron_wake_state() -> dict[str, Any]:
    return {
        "enabled": True,
        "policy_event_count": 0,
        "delayed_count": 0,
        "discarded_count": 0,
        "policy_by_action": {},
        "policy_by_reason": {},
        "last_policy_action": "",
        "last_policy_reason": "",
        "last_policy_at": "",
        "last_result": "",
        "recent_policy_events": [],
    }


def build_tuning_runner_state(
    *,
    enabled: bool,
    interval_seconds: int,
    timeout_seconds: float,
    cooldown_seconds: int,
    actions_per_hour_cap: int,
) -> dict[str, Any]:
    return {
        "enabled": bool(enabled),
        "running": False,
        "interval_seconds": int(interval_seconds),
        "timeout_seconds": float(timeout_seconds),
        "cooldown_seconds": int(cooldown_seconds),
        "actions_per_hour_cap": int(actions_per_hour_cap),
        "ticks": 0,
        "success_count": 0,
        "error_count": 0,
        "action_count": 0,
        "last_result": "",
        "last_error": "",
        "last_run_iso": "",
        "next_run_iso": "",
        "last_action": "",
        "last_action_status": "",
        "last_action_reason": "",
        "actions_by_layer": {},
        "actions_by_playbook": {},
        "actions_by_action": {},
        "action_status_by_layer": {},
        "last_action_metadata": {},
    }


def build_self_evolution_runner_state(*, enabled: bool, cooldown_seconds: float) -> dict[str, Any]:
    return {
        "enabled": bool(enabled),
        "running": False,
        "cooldown_seconds": float(cooldown_seconds),
        "ticks": 0,
        "success_count": 0,
        "error_count": 0,
        "last_result": "",
        "last_error": "",
        "last_run_iso": "",
    }


def build_subagent_maintenance_state(*, interval_seconds: float) -> dict[str, Any]:
    return {
        "enabled": True,
        "running": False,
        "interval_seconds": float(interval_seconds),
        "ticks": 0,
        "success_count": 0,
        "error_count": 0,
        "last_result": {},
        "last_error": "",
        "last_run_iso": "",
    }


def build_memory_quality_cache() -> dict[str, Any]:
    return {"fingerprint": "", "payload": None}


__all__ = [
    "build_cron_wake_state",
    "build_memory_quality_cache",
    "build_proactive_runner_state",
    "build_self_evolution_runner_state",
    "build_subagent_maintenance_state",
    "build_tuning_runner_state",
    "build_wake_pressure_state",
]
