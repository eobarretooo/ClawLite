from __future__ import annotations

from typing import Any, Callable


def _dashboard_handoff_payload(*, runtime: Any, build_dashboard_handoff: Callable[[Any], dict[str, Any]]) -> dict[str, Any]:
    try:
        return build_dashboard_handoff(runtime.config, include_sensitive=False)
    except TypeError:
        return build_dashboard_handoff(runtime.config)


def dashboard_channels_summary(*, runtime: Any, dashboard_channels_summary_payload: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
    return dashboard_channels_summary_payload(runtime.channels.status())


def dashboard_cron_summary(*, runtime: Any, dashboard_cron_summary_payload: Callable[..., dict[str, Any]], limit: int = 8) -> dict[str, Any]:
    return dashboard_cron_summary_payload(cron=runtime.cron, limit=limit)


def dashboard_self_evolution_summary(
    *,
    runtime: Any,
    runner_state: dict[str, Any],
    dashboard_self_evolution_summary_payload: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    return dashboard_self_evolution_summary_payload(
        evolution=runtime.self_evolution,
        runner_state=runner_state,
    )


def dashboard_runtime_posture_summary(
    *,
    runtime: Any,
    self_evolution_payload: dict[str, Any],
    dashboard_runtime_posture_summary_payload: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    return dashboard_runtime_posture_summary_payload(
        autonomy_payload=runtime.autonomy.status() if runtime.autonomy is not None else {},
        autonomy_wake_payload=runtime.autonomy_wake.status(),
        supervisor_payload=runtime.supervisor.status() if runtime.supervisor is not None else {},
        self_evolution_payload=self_evolution_payload,
    )


def dashboard_runtime_policy_summary(
    *,
    runtime: Any,
    self_evolution_payload: dict[str, Any],
    dashboard_runtime_policy_summary_payload: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    del runtime
    return dashboard_runtime_policy_summary_payload(
        self_evolution_payload=self_evolution_payload,
    )


def dashboard_provider_health_summary(
    *,
    provider_telemetry_payload: dict[str, Any],
    provider_autonomy_payload: dict[str, Any],
    provider_status_payload: dict[str, Any],
    dashboard_provider_health_summary_payload: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    return dashboard_provider_health_summary_payload(
        provider_telemetry_payload=provider_telemetry_payload,
        provider_autonomy_payload=provider_autonomy_payload,
        provider_status_payload=provider_status_payload,
    )


def dashboard_memory_summary(
    *,
    runtime: Any,
    memory_profile_snapshot_fn: Callable[..., dict[str, Any]],
    memory_suggest_snapshot_fn: Callable[..., dict[str, Any]],
    memory_version_snapshot_fn: Callable[..., dict[str, Any]],
    dashboard_memory_summary_payload: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    return dashboard_memory_summary_payload(
        memory_monitor=runtime.memory_monitor,
        memory_store=runtime.engine.memory,
        config=runtime.config,
        memory_profile_snapshot_fn=memory_profile_snapshot_fn,
        memory_suggest_snapshot_fn=memory_suggest_snapshot_fn,
        memory_version_snapshot_fn=memory_version_snapshot_fn,
    )


def dashboard_operator_summary(*, runtime: Any, channel_name: str, operator_channel_summary: Callable[[Any], dict[str, Any]]) -> dict[str, Any]:
    return operator_channel_summary(runtime.channels.get_channel(channel_name))


def dashboard_state_payload(
    *,
    runtime: Any,
    contract_version: str,
    generated_at: str,
    control_plane: Any,
    control_plane_to_dict: Callable[[Any], dict[str, Any]],
    recent_dashboard_sessions_payload: Callable[..., dict[str, Any]],
    dashboard_channels_summary_payload: Callable[[dict[str, Any]], dict[str, Any]],
    dashboard_cron_summary_payload: Callable[..., dict[str, Any]],
    dashboard_self_evolution_summary_payload: Callable[..., dict[str, Any]],
    dashboard_runtime_posture_summary_payload: Callable[..., dict[str, Any]],
    dashboard_runtime_policy_summary_payload: Callable[..., dict[str, Any]],
    dashboard_provider_health_summary_payload: Callable[..., dict[str, Any]],
    dashboard_memory_summary_payload: Callable[..., dict[str, Any]],
    operator_channel_summary: Callable[[Any], dict[str, Any]],
    provider_telemetry_snapshot: Callable[[Any], dict[str, Any]],
    provider_autonomy_snapshot: Callable[..., dict[str, Any]],
    provider_status_payload_fn: Callable[[], dict[str, Any]],
    build_dashboard_handoff: Callable[[Any], dict[str, Any]],
    memory_profile_snapshot_fn: Callable[..., dict[str, Any]],
    memory_suggest_snapshot_fn: Callable[..., dict[str, Any]],
    memory_version_snapshot_fn: Callable[..., dict[str, Any]],
    ws_snapshot_payload: Callable[[], dict[str, Any]] = lambda: {},
    self_evolution_runner_state: dict[str, Any],
    dashboard_state_payload_builder: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    provider_telemetry = provider_telemetry_snapshot(runtime.engine.provider)
    provider_autonomy = provider_autonomy_snapshot(provider=runtime.engine.provider)
    provider_status = provider_status_payload_fn()
    provider_health = dashboard_provider_health_summary(
        provider_telemetry_payload=provider_telemetry,
        provider_autonomy_payload=provider_autonomy,
        provider_status_payload=provider_status if isinstance(provider_status, dict) else {},
        dashboard_provider_health_summary_payload=dashboard_provider_health_summary_payload,
    )
    self_evolution_payload = dashboard_self_evolution_summary(
        runtime=runtime,
        runner_state=self_evolution_runner_state,
        dashboard_self_evolution_summary_payload=dashboard_self_evolution_summary_payload,
    )
    runtime_posture_payload = dashboard_runtime_posture_summary(
        runtime=runtime,
        self_evolution_payload=self_evolution_payload,
        dashboard_runtime_posture_summary_payload=dashboard_runtime_posture_summary_payload,
    )
    runtime_policy_payload = dashboard_runtime_policy_summary(
        runtime=runtime,
        self_evolution_payload=self_evolution_payload,
        dashboard_runtime_policy_summary_payload=dashboard_runtime_policy_summary_payload,
    )
    skills = runtime.skills_loader.diagnostics_report()
    return dashboard_state_payload_builder(
        contract_version=contract_version,
        generated_at=generated_at,
        control_plane=control_plane,
        control_plane_to_dict=control_plane_to_dict,
        queue_payload=runtime.bus.stats(),
        sessions_payload=recent_dashboard_sessions_payload(
            sessions=runtime.engine.sessions,
            subagents=runtime.engine.subagents,
            limit=8,
        ),
        channels_payload=dashboard_channels_summary(runtime=runtime, dashboard_channels_summary_payload=dashboard_channels_summary_payload),
        channels_dispatcher_payload=runtime.channels.dispatcher_diagnostics(),
        channels_delivery_payload=runtime.channels.delivery_diagnostics(),
        channels_inbound_payload=runtime.channels.inbound_diagnostics(),
        channels_recovery_payload=runtime.channels.recovery_diagnostics(),
        discord_payload=dashboard_operator_summary(runtime=runtime, channel_name="discord", operator_channel_summary=operator_channel_summary),
        telegram_payload=dashboard_operator_summary(runtime=runtime, channel_name="telegram", operator_channel_summary=operator_channel_summary),
        cron_payload=dashboard_cron_summary(runtime=runtime, dashboard_cron_summary_payload=dashboard_cron_summary_payload),
        heartbeat_payload=runtime.heartbeat.status(),
        ws_payload=ws_snapshot_payload(),
        subagents_payload=runtime.engine.subagents.status(),
        supervisor_payload=runtime.supervisor.status() if runtime.supervisor is not None else {},
        skills_payload=skills,
        workspace_payload=runtime.workspace.runtime_health(),
        handoff_payload=_dashboard_handoff_payload(runtime=runtime, build_dashboard_handoff=build_dashboard_handoff),
        onboarding_payload=runtime.workspace.onboarding_status(),
        bootstrap_payload=runtime.workspace.bootstrap_status(),
        memory_payload=dashboard_memory_summary(
            runtime=runtime,
            memory_profile_snapshot_fn=memory_profile_snapshot_fn,
            memory_suggest_snapshot_fn=memory_suggest_snapshot_fn,
            memory_version_snapshot_fn=memory_version_snapshot_fn,
            dashboard_memory_summary_payload=dashboard_memory_summary_payload,
        ),
        provider_telemetry_payload=provider_telemetry,
        provider_autonomy_payload=provider_autonomy,
        provider_status_payload=provider_status if isinstance(provider_status, dict) else {},
        provider_health_payload=provider_health if isinstance(provider_health, dict) else {},
        self_evolution_payload=self_evolution_payload,
        runtime_posture_payload=runtime_posture_payload if isinstance(runtime_posture_payload, dict) else {},
        runtime_policy_payload=runtime_policy_payload if isinstance(runtime_policy_payload, dict) else {},
    )


__all__ = [
    "dashboard_channels_summary",
    "dashboard_cron_summary",
    "dashboard_memory_summary",
    "dashboard_operator_summary",
    "dashboard_provider_health_summary",
    "dashboard_runtime_policy_summary",
    "dashboard_runtime_posture_summary",
    "dashboard_self_evolution_summary",
    "dashboard_state_payload",
]
