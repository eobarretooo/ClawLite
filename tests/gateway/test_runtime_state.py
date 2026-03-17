from __future__ import annotations

from clawlite.gateway.runtime_state import (
    build_cron_wake_state,
    build_memory_quality_cache,
    build_proactive_runner_state,
    build_self_evolution_runner_state,
    build_subagent_maintenance_state,
    build_tuning_runner_state,
    build_wake_pressure_state,
)


def test_runtime_state_builders_shape_default_payloads() -> None:
    proactive = build_proactive_runner_state(enabled=True, interval_seconds=30)
    wake = build_wake_pressure_state()
    cron = build_cron_wake_state()
    tuning = build_tuning_runner_state(
        enabled=True,
        interval_seconds=60,
        timeout_seconds=45.0,
        cooldown_seconds=300,
        actions_per_hour_cap=20,
    )
    self_evo = build_self_evolution_runner_state(enabled=False, cooldown_seconds=0.0)
    subagents = build_subagent_maintenance_state(interval_seconds=15.0)
    cache = build_memory_quality_cache()

    assert proactive["enabled"] is True
    assert proactive["interval_seconds"] == 30
    assert proactive["policy_by_action"] == {}
    assert wake["events_by_kind"] == {}
    assert cron["recent_policy_events"] == []
    assert tuning["actions_per_hour_cap"] == 20
    assert tuning["last_action_metadata"] == {}
    assert self_evo["enabled"] is False
    assert subagents["last_result"] == {}
    assert cache == {"fingerprint": "", "payload": None}
