from __future__ import annotations

from typing import Any


OUTBOUND_HEALTH_THRESHOLDS: dict[str, float | int] = {
    # Thresholds solicitados explicitamente para latência outbound.
    "latency_warning_s": 5.0,
    "latency_error_s": 15.0,
    "consecutive_failures_warning": 3,
    "consecutive_failures_error": 5,
    "circuit_open_cooldown_warning_s": 5.0,
    "circuit_open_cooldown_error_s": 15.0,
    "circuit_blocked_warning_count": 1,
    "circuit_blocked_error_count": 5,
}

_SEVERITY_RANK = {"ok": 0, "warning": 1, "error": 2}


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _max_level(current: str, incoming: str) -> str:
    return incoming if _SEVERITY_RANK.get(incoming, 0) > _SEVERITY_RANK.get(current, 0) else current


def _threshold_check(
    *,
    check_id: str,
    label: str,
    value: float,
    warning_gt: float,
    error_gt: float,
) -> dict[str, Any]:
    level = "ok"
    decision = "pass"
    if value > error_gt:
        level = "error"
        decision = f"fail: {label} ({value:.3f}) > {error_gt:.3f}"
    elif value > warning_gt:
        level = "warning"
        decision = f"warn: {label} ({value:.3f}) > {warning_gt:.3f}"
    return {
        "id": check_id,
        "label": label,
        "value": value,
        "warning_gt": warning_gt,
        "error_gt": error_gt,
        "level": level,
        "decision": decision,
    }


def evaluate_outbound_health(outbound: dict[str, Any] | None) -> dict[str, Any]:
    metrics = outbound if isinstance(outbound, dict) else {}
    policy = dict(OUTBOUND_HEALTH_THRESHOLDS)
    checks: list[dict[str, Any]] = []
    overall = "ok"

    last_latency = max(
        _to_float(metrics.get("last_attempt_latency_s"), 0.0),
        _to_float(metrics.get("avg_attempt_latency_s"), 0.0),
    )
    latency_check = _threshold_check(
        check_id="latency",
        label="send latency (s)",
        value=last_latency,
        warning_gt=float(policy["latency_warning_s"]),
        error_gt=float(policy["latency_error_s"]),
    )
    checks.append(latency_check)
    overall = _max_level(overall, str(latency_check["level"]))

    consecutive_failures = _to_int(metrics.get("circuit_consecutive_failures"), 0)
    failure_check = _threshold_check(
        check_id="consecutive_failures",
        label="consecutive failures",
        value=float(consecutive_failures),
        warning_gt=float(policy["consecutive_failures_warning"]),
        error_gt=float(policy["consecutive_failures_error"]),
    )
    checks.append(failure_check)
    overall = _max_level(overall, str(failure_check["level"]))

    blocked_count = _to_int(metrics.get("circuit_blocked_count"), 0)
    blocked_check = _threshold_check(
        check_id="circuit_blocked",
        label="circuit blocked sends",
        value=float(blocked_count),
        warning_gt=float(policy["circuit_blocked_warning_count"]),
        error_gt=float(policy["circuit_blocked_error_count"]),
    )
    checks.append(blocked_check)
    overall = _max_level(overall, str(blocked_check["level"]))

    circuit_state = str(metrics.get("circuit_state", "closed")).strip().lower() or "closed"
    if circuit_state == "open":
        cooldown_remaining = _to_float(metrics.get("circuit_cooldown_remaining_s"), 0.0)
        open_check = _threshold_check(
            check_id="circuit_open_cooldown",
            label="circuit open cooldown (s)",
            value=cooldown_remaining,
            warning_gt=float(policy["circuit_open_cooldown_warning_s"]),
            error_gt=float(policy["circuit_open_cooldown_error_s"]),
        )
        if open_check["level"] == "ok":
            open_check["level"] = "warning"
            open_check["decision"] = (
                f"warn: circuit open (cooldown remaining {cooldown_remaining:.3f}s)"
            )
        checks.append(open_check)
        overall = _max_level(overall, str(open_check["level"]))
    elif circuit_state == "half_open":
        half_open_check = {
            "id": "circuit_half_open",
            "label": "circuit half-open",
            "value": 1.0,
            "warning_gt": 0.0,
            "error_gt": 1e9,
            "level": "warning",
            "decision": "warn: circuit em recuperação (half-open)",
        }
        checks.append(half_open_check)
        overall = _max_level(overall, "warning")

    return {
        "level": overall,
        "pass": overall != "error",
        "policy": policy,
        "checks": checks,
    }

