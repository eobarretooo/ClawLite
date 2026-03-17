from __future__ import annotations

import datetime as dt
from typing import Any, Callable


def count_recent_tuning_actions(
    recent_actions: list[dict[str, Any]],
    *,
    now: dt.datetime,
    parse_iso: Callable[[str], dt.datetime | None],
    ignored_statuses: set[str] | frozenset[str],
) -> int:
    one_hour_ago = now - dt.timedelta(hours=1)
    action_events_last_hour = 0
    for entry in recent_actions:
        if not isinstance(entry, dict):
            continue
        status = str(entry.get("status", "") or "")
        if status in ignored_statuses:
            continue
        at_dt = parse_iso(str(entry.get("at", "") or ""))
        if at_dt is None or at_dt < one_hour_ago:
            continue
        action_events_last_hour += 1
    return action_events_last_hour


def build_tuning_action_entry(
    *,
    action: str,
    status: str,
    reason: str,
    at: str,
    metadata: dict[str, Any],
) -> dict[str, Any] | None:
    if not str(action or "").strip():
        return None
    return {
        "action": str(action or ""),
        "status": str(status or ""),
        "reason": str(reason or ""),
        "at": str(at or ""),
        "metadata": dict(metadata),
    }


def record_tuning_runner_action(
    state: dict[str, Any],
    *,
    weakest_layer: str,
    action: str,
    playbook_id: str,
    action_status: str,
    action_metadata: dict[str, Any],
    resolve_tuning_layer: Callable[[str], str],
) -> None:
    if not str(action or "").strip():
        return
    layer_key = resolve_tuning_layer(weakest_layer)
    actions_by_layer = state.setdefault("actions_by_layer", {})
    actions_by_layer[layer_key] = int(actions_by_layer.get(layer_key, 0) or 0) + 1

    actions_by_playbook = state.setdefault("actions_by_playbook", {})
    if playbook_id:
        actions_by_playbook[playbook_id] = int(actions_by_playbook.get(playbook_id, 0) or 0) + 1

    actions_by_action = state.setdefault("actions_by_action", {})
    actions_by_action[action] = int(actions_by_action.get(action, 0) or 0) + 1

    status_by_layer = state.setdefault("action_status_by_layer", {})
    layer_status_raw = status_by_layer.get(layer_key, {})
    layer_status = dict(layer_status_raw) if isinstance(layer_status_raw, dict) else {}
    layer_status[action_status] = int(layer_status.get(action_status, 0) or 0) + 1
    status_by_layer[layer_key] = layer_status
    state["last_action_metadata"] = dict(action_metadata)


def build_tuning_patch(
    *,
    degrading_streak: int,
    now_iso: str,
    interval_seconds: float,
    action_entry: dict[str, Any] | None,
) -> dict[str, Any]:
    patch: dict[str, Any] = {
        "degrading_streak": int(degrading_streak),
        "last_run_at": str(now_iso or ""),
        "next_run_at": (dt.datetime.fromisoformat(now_iso) + dt.timedelta(seconds=interval_seconds)).isoformat(timespec="seconds"),
        "last_error": "",
    }
    if action_entry is None:
        return patch
    patch["last_action"] = action_entry.get("action", "")
    patch["last_action_status"] = action_entry.get("status", "")
    patch["last_reason"] = action_entry.get("reason", "")
    patch["recent_actions"] = [action_entry]
    if action_entry.get("status", "") not in {"cooldown_skipped", "rate_limited"}:
        patch["last_action_at"] = action_entry.get("at", "")
    return patch


__all__ = [
    "build_tuning_action_entry",
    "build_tuning_patch",
    "count_recent_tuning_actions",
    "record_tuning_runner_action",
]
