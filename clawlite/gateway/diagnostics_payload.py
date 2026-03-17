from __future__ import annotations

import time
from typing import Any, Awaitable, Callable


def diagnostics_environment_payload(
    *,
    include_config: bool,
    workspace_path: str,
    state_path: str,
    provider_model: str,
) -> dict[str, Any]:
    if not include_config:
        return {}
    return {
        "workspace_path": workspace_path,
        "state_path": state_path,
        "provider_model": provider_model,
    }


async def diagnostics_engine_payload(
    *,
    runtime: Any,
    generated_at: str,
    memory_quality_cache: dict[str, Any],
    collect_memory_analysis_metrics: Callable[[], Awaitable[tuple[dict[str, Any], dict[str, Any]]]],
    engine_memory_payloads: Callable[..., dict[str, Any]],
    engine_memory_quality_payload: Callable[..., Awaitable[dict[str, Any]]],
    engine_memory_integration_payload: Callable[..., dict[str, Any]],
    provider_telemetry_snapshot: Callable[[Any], dict[str, Any]],
    include_provider_telemetry: bool,
) -> dict[str, Any]:
    retrieval_metrics_snapshot = runtime.engine.retrieval_metrics_snapshot()
    turn_metrics_snapshot = runtime.engine.turn_metrics_snapshot()
    memory_store = getattr(runtime.engine, "memory", None)
    engine_payload: dict[str, Any] = {
        "retrieval_metrics": retrieval_metrics_snapshot,
        "turn_metrics": turn_metrics_snapshot,
        "skills": runtime.skills_loader.diagnostics_report(),
    }
    engine_payload.update(engine_memory_payloads(memory_store=memory_store))
    engine_payload["memory_quality"] = await engine_memory_quality_payload(
        memory_store=memory_store,
        retrieval_metrics_snapshot=retrieval_metrics_snapshot,
        turn_metrics_snapshot=turn_metrics_snapshot,
        generated_at=generated_at,
        memory_quality_cache=memory_quality_cache,
        collect_memory_analysis_metrics=collect_memory_analysis_metrics,
    )
    engine_payload["memory_integration"] = engine_memory_integration_payload(memory_store=memory_store)
    if include_provider_telemetry:
        engine_payload["provider"] = provider_telemetry_snapshot(runtime.engine.provider)
    return engine_payload


async def diagnostics_payload(
    *,
    cfg: Any,
    runtime: Any,
    contract_version: str,
    generated_at: str,
    started_monotonic: float,
    control_plane_payload: dict[str, Any],
    bootstrap_payload: dict[str, Any],
    memory_quality_cache: dict[str, Any],
    collect_memory_analysis_metrics: Callable[[], Awaitable[tuple[dict[str, Any], dict[str, Any]]]],
    engine_memory_payloads: Callable[..., dict[str, Any]],
    engine_memory_quality_payload: Callable[..., Awaitable[dict[str, Any]]],
    engine_memory_integration_payload: Callable[..., dict[str, Any]],
    provider_telemetry_snapshot: Callable[[Any], dict[str, Any]],
    memory_monitor_payload: Callable[..., dict[str, Any]],
    http_snapshot: Callable[[], Awaitable[dict[str, Any]]],
    ws_snapshot: Callable[[], Awaitable[dict[str, Any]]],
    proactive_runner_state: dict[str, Any],
    cron_wake_state: dict[str, Any],
    subagent_maintenance_state: dict[str, Any],
    tuning_runner_state: dict[str, Any],
    self_evolution_runner_state: dict[str, Any],
) -> dict[str, Any]:
    environment = diagnostics_environment_payload(
        include_config=bool(cfg.gateway.diagnostics.include_config),
        workspace_path=str(cfg.workspace_path),
        state_path=str(cfg.state_path),
        provider_model=str(cfg.agents.defaults.model),
    )
    engine_payload = await diagnostics_engine_payload(
        runtime=runtime,
        generated_at=generated_at,
        memory_quality_cache=memory_quality_cache,
        collect_memory_analysis_metrics=collect_memory_analysis_metrics,
        engine_memory_payloads=engine_memory_payloads,
        engine_memory_quality_payload=engine_memory_quality_payload,
        engine_memory_integration_payload=engine_memory_integration_payload,
        provider_telemetry_snapshot=provider_telemetry_snapshot,
        include_provider_telemetry=bool(cfg.gateway.diagnostics.include_provider_telemetry),
    )
    monitor_payload = memory_monitor_payload(
        memory_monitor=runtime.memory_monitor,
        proactive_runner_state=proactive_runner_state,
    )
    cron_payload = dict(runtime.cron.status())
    cron_payload["wake_policy"] = dict(cron_wake_state)
    subagent_payload = dict(runtime.engine.subagents.status())
    subagent_payload["runner"] = dict(subagent_maintenance_state)
    self_evolution_payload = runtime.self_evolution.status() if runtime.self_evolution is not None else {}
    self_evolution_payload["runner"] = dict(self_evolution_runner_state)

    return {
        "schema_version": "2026-03-02",
        "contract_version": contract_version,
        "generated_at": generated_at,
        "uptime_s": max(0, int(time.monotonic() - started_monotonic)),
        "control_plane": control_plane_payload,
        "queue": runtime.bus.stats(),
        "channels": runtime.channels.status(),
        "channels_dispatcher": runtime.channels.dispatcher_diagnostics(),
        "channels_delivery": runtime.channels.delivery_diagnostics(),
        "channels_inbound": runtime.channels.inbound_diagnostics(),
        "channels_recovery": runtime.channels.recovery_diagnostics(),
        "cron": cron_payload,
        "heartbeat": runtime.heartbeat.status(),
        "autonomy": runtime.autonomy.status() if runtime.autonomy is not None else {},
        "supervisor": runtime.supervisor.status() if runtime.supervisor is not None else {},
        "autonomy_wake": runtime.autonomy_wake.status(),
        "autonomy_log": runtime.autonomy_log.snapshot(),
        "subagents": subagent_payload,
        "bootstrap": bootstrap_payload,
        "workspace": runtime.workspace.runtime_health(),
        "memory_monitor": monitor_payload,
        "memory_quality_tuning": dict(tuning_runner_state),
        "engine": engine_payload,
        "environment": environment,
        "http": await http_snapshot(),
        "ws": await ws_snapshot(),
        "self_evolution": self_evolution_payload,
    }


__all__ = [
    "diagnostics_engine_payload",
    "diagnostics_environment_payload",
    "diagnostics_payload",
]
