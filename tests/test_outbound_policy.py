from __future__ import annotations

from clawlite.runtime.outbound_policy import evaluate_outbound_health


def test_outbound_policy_ok_when_metrics_under_threshold():
    health = evaluate_outbound_health(
        {
            "last_attempt_latency_s": 1.2,
            "avg_attempt_latency_s": 1.0,
            "circuit_consecutive_failures": 1,
            "circuit_blocked_count": 0,
            "circuit_state": "closed",
        }
    )
    assert health["level"] == "ok"
    assert health["pass"] is True


def test_outbound_policy_warning_when_latency_above_5s():
    health = evaluate_outbound_health(
        {
            "last_attempt_latency_s": 6.1,
            "circuit_consecutive_failures": 0,
            "circuit_blocked_count": 0,
            "circuit_state": "closed",
        }
    )
    assert health["level"] == "warning"
    assert health["pass"] is True
    latency_check = next(item for item in health["checks"] if item["id"] == "latency")
    assert latency_check["decision"].startswith("warn:")


def test_outbound_policy_error_when_latency_above_15s():
    health = evaluate_outbound_health(
        {
            "last_attempt_latency_s": 16.0,
            "circuit_consecutive_failures": 6,
            "circuit_blocked_count": 6,
            "circuit_state": "open",
            "circuit_cooldown_remaining_s": 20.0,
        }
    )
    assert health["level"] == "error"
    assert health["pass"] is False
    checks = {item["id"]: item for item in health["checks"]}
    assert checks["latency"]["level"] == "error"
    assert checks["consecutive_failures"]["level"] == "error"
    assert checks["circuit_blocked"]["level"] == "error"


def test_outbound_policy_open_circuit_stays_warning_even_without_high_cooldown():
    health = evaluate_outbound_health(
        {
            "last_attempt_latency_s": 1.0,
            "circuit_consecutive_failures": 0,
            "circuit_blocked_count": 0,
            "circuit_state": "open",
            "circuit_cooldown_remaining_s": 2.0,
        }
    )
    assert health["level"] == "warning"
    check = next(item for item in health["checks"] if item["id"] == "circuit_open_cooldown")
    assert check["level"] == "warning"
    assert check["decision"].startswith("warn:")
