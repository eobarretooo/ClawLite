from __future__ import annotations

from typing import Any, Callable


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
    dashboard_memory_summary_payload: Callable[..., dict[str, Any]],
    operator_channel_summary: Callable[[Any], dict[str, Any]],
    provider_telemetry_snapshot: Callable[[Any], dict[str, Any]],
    provider_autonomy_snapshot: Callable[..., dict[str, Any]],
    build_dashboard_handoff: Callable[[Any], dict[str, Any]],
    memory_profile_snapshot_fn: Callable[..., dict[str, Any]],
    memory_suggest_snapshot_fn: Callable[..., dict[str, Any]],
    memory_version_snapshot_fn: Callable[..., dict[str, Any]],
    self_evolution_runner_state: dict[str, Any],
    dashboard_state_payload_builder: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    provider_telemetry = provider_telemetry_snapshot(runtime.engine.provider)
    provider_autonomy = provider_autonomy_snapshot(provider=runtime.engine.provider)
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
        subagents_payload=runtime.engine.subagents.status(),
        supervisor_payload=runtime.supervisor.status() if runtime.supervisor is not None else {},
        skills_payload=skills,
        workspace_payload=runtime.workspace.runtime_health(),
        handoff_payload=build_dashboard_handoff(runtime.config),
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
        self_evolution_payload=dashboard_self_evolution_summary(
            runtime=runtime,
            runner_state=self_evolution_runner_state,
            dashboard_self_evolution_summary_payload=dashboard_self_evolution_summary_payload,
        ),
    )


__all__ = [
    "dashboard_channels_summary",
    "dashboard_cron_summary",
    "dashboard_memory_summary",
    "dashboard_operator_summary",
    "dashboard_self_evolution_summary",
    "dashboard_state_payload",
]
