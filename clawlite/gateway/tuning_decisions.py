from __future__ import annotations

import datetime as dt
from typing import Any, Callable

from clawlite.gateway.tuning_policy import normalize_reasoning_layer, select_tuning_action_playbook
from clawlite.gateway.tuning_runtime import count_recent_tuning_actions


def plan_tuning_action(
    *,
    report: dict[str, Any],
    tuning_state: dict[str, Any],
    now: dt.datetime,
    parse_iso: Callable[[str], dt.datetime | None],
    degrading_streak_threshold: int,
    recent_actions_limit: int,
    cooldown_seconds: int,
    actions_per_hour_cap: int,
) -> dict[str, Any]:
    drift = str(report.get("drift", {}).get("assessment", "") or "")
    score = int(report.get("score", 0) or 0)
    reasoning_report = report.get("reasoning_layers", {})

    weakest_layer = ""
    if isinstance(reasoning_report, dict):
        weakest_layer = normalize_reasoning_layer(str(reasoning_report.get("weakest_layer", "") or ""))

    degrading_streak = int(tuning_state.get("degrading_streak", 0) or 0)
    if drift == "degrading":
        degrading_streak += 1
    else:
        degrading_streak = 0

    plan: dict[str, Any] = {
        "drift": drift,
        "score": score,
        "weakest_layer": weakest_layer,
        "degrading_streak": degrading_streak,
        "severity": "",
        "action": "",
        "playbook_id": "",
        "action_reason": "",
        "action_status": "noop",
        "action_metadata": {},
        "should_execute": False,
    }

    if drift != "degrading":
        return plan

    if degrading_streak >= (degrading_streak_threshold + 2) or score <= 40:
        severity = "high"
    elif degrading_streak >= degrading_streak_threshold:
        severity = "medium"
    else:
        severity = "low"

    action, playbook_id = select_tuning_action_playbook(
        severity=severity,
        weakest_layer=weakest_layer,
    )
    action_reason = f"quality_drift_{severity}:playbook_id={playbook_id}:severity={severity}"
    if weakest_layer:
        action_reason = f"{action_reason}:weakest_layer={weakest_layer}"

    action_metadata: dict[str, Any] = {
        "severity": severity,
        "playbook_id": playbook_id,
        "action_variant": f"{playbook_id}:{action}:v2",
    }
    if weakest_layer:
        action_metadata["weakest_layer"] = weakest_layer

    last_action_at = parse_iso(str(tuning_state.get("last_action_at", "") or ""))
    in_cooldown = (
        last_action_at is not None
        and cooldown_seconds > 0
        and (now - last_action_at).total_seconds() < float(cooldown_seconds)
    )

    recent_actions_raw = tuning_state.get("recent_actions", [])
    recent_actions = list(recent_actions_raw) if isinstance(recent_actions_raw, list) else []
    recent_actions = recent_actions[-recent_actions_limit:]
    action_events_last_hour = count_recent_tuning_actions(
        recent_actions,
        now=now,
        parse_iso=parse_iso,
        ignored_statuses=frozenset({"cooldown_skipped", "rate_limited", "noop"}),
    )

    action_status = "noop"
    should_execute = False
    if in_cooldown:
        action_status = "cooldown_skipped"
    elif action_events_last_hour >= actions_per_hour_cap:
        action_status = "rate_limited"
    else:
        should_execute = bool(action)

    plan.update(
        {
            "severity": severity,
            "action": action,
            "playbook_id": playbook_id,
            "action_reason": action_reason,
            "action_status": action_status,
            "action_metadata": action_metadata,
            "should_execute": should_execute,
        }
    )
    return plan


__all__ = ["plan_tuning_action"]
