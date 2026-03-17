from __future__ import annotations

from typing import Any, Callable


async def collect_supervisor_incidents(
    *,
    incident_cls: type,
    cfg: Any,
    runtime: Any,
    self_evolution_task: Any,
    self_evolution_running: bool,
    self_evolution_runner_state: dict[str, Any],
    subagent_maintenance_task: Any,
    subagent_maintenance_running: bool,
    subagent_maintenance_state: dict[str, Any],
    proactive_task: Any,
    proactive_running: bool,
    proactive_runner_state: dict[str, Any],
    tuning_task: Any,
    tuning_running: bool,
    tuning_runner_state: dict[str, Any],
    background_task_snapshot: Callable[..., tuple[str, str]],
    provider_telemetry_snapshot: Callable[[Any], dict[str, Any]],
) -> list[Any]:
    incidents: list[Any] = []

    if self_evolution_runner_state.get("enabled", False):
        self_evolution_state, _self_evolution_error = background_task_snapshot(
            self_evolution_task,
            running=self_evolution_running,
            last_error=str(self_evolution_runner_state.get("last_error", "") or ""),
        )
        if self_evolution_state != "running":
            incidents.append(
                incident_cls(component="self_evolution", reason=f"self_evolution_{self_evolution_state}")
            )

    channels_dispatcher_status = runtime.channels.dispatcher_diagnostics()
    if channels_dispatcher_status.get("enabled", True) and not channels_dispatcher_status.get("running", False):
        worker_state = str(channels_dispatcher_status.get("task_state", "stopped") or "stopped")
        incidents.append(incident_cls(component="channels_dispatcher", reason=f"channels_dispatcher_{worker_state}"))

    channels_recovery_status = runtime.channels.recovery_diagnostics()
    if channels_recovery_status.get("enabled", True) and not channels_recovery_status.get("running", False):
        worker_state = str(channels_recovery_status.get("task_state", "stopped") or "stopped")
        incidents.append(incident_cls(component="channels_recovery", reason=f"channels_recovery_{worker_state}"))

    if cfg.gateway.heartbeat.enabled:
        heartbeat_status = runtime.heartbeat.status()
        if not heartbeat_status.get("running", False):
            worker_state = str(heartbeat_status.get("worker_state", "stopped") or "stopped")
            incidents.append(incident_cls(component="heartbeat", reason=f"heartbeat_{worker_state}"))

    cron_status = runtime.cron.status()
    if not cron_status.get("running", False):
        worker_state = str(cron_status.get("worker_state", "stopped") or "stopped")
        incidents.append(incident_cls(component="cron", reason=f"cron_{worker_state}"))

    autonomy_wake_status = runtime.autonomy_wake.status()
    if not autonomy_wake_status.get("running", False):
        worker_state = str(autonomy_wake_status.get("worker_state", "stopped") or "stopped")
        incidents.append(incident_cls(component="autonomy_wake", reason=f"autonomy_wake_{worker_state}"))

    if cfg.gateway.autonomy.enabled and runtime.autonomy is not None:
        autonomy_status = runtime.autonomy.status()
        if not autonomy_status.get("running", False):
            worker_state = str(autonomy_status.get("worker_state", "stopped") or "stopped")
            incidents.append(incident_cls(component="autonomy", reason=f"autonomy_{worker_state}"))

    subagent_maintenance_state_name, _subagent_maintenance_error = background_task_snapshot(
        subagent_maintenance_task,
        running=subagent_maintenance_running,
        last_error=str(subagent_maintenance_state.get("last_error", "") or ""),
    )
    if subagent_maintenance_state_name != "running":
        incidents.append(
            incident_cls(
                component="subagent_maintenance",
                reason=f"subagent_maintenance_{subagent_maintenance_state_name}",
            )
        )

    skills_watcher_status = runtime.skills_loader.watcher_status()
    if not skills_watcher_status.get("running", False):
        watcher_state = str(skills_watcher_status.get("task_state", "stopped") or "stopped")
        incidents.append(incident_cls(component="skills_watcher", reason=f"skills_watcher_{watcher_state}"))

    if runtime.memory_monitor is not None:
        proactive_state, _proactive_error = background_task_snapshot(
            proactive_task,
            running=proactive_running,
            last_error=str(proactive_runner_state.get("last_error", "") or ""),
        )
        if proactive_state != "running":
            incidents.append(incident_cls(component="proactive_monitor", reason=f"proactive_monitor_{proactive_state}"))

    if cfg.gateway.autonomy.tuning_loop_enabled:
        tuning_state, _tuning_error = background_task_snapshot(
            tuning_task,
            running=tuning_running,
            last_error=str(tuning_runner_state.get("last_error", "") or ""),
        )
        if tuning_state != "running":
            incidents.append(incident_cls(component="memory_quality_tuning", reason=f"memory_quality_tuning_{tuning_state}"))

    if runtime.job_queue is not None:
        job_status = runtime.job_queue.worker_status()
        if not job_status.get("running", False):
            workers_alive = int(job_status.get("workers_alive", 0) or 0)
            workers_total = int(job_status.get("workers_total", 0) or 0)
            reason = f"job_workers_dead:{workers_alive}/{workers_total}"
            incidents.append(incident_cls(component="job_workers", reason=reason))

    if cfg.gateway.autonomy.enabled and runtime.autonomy is not None:
        autonomy_status = runtime.autonomy.status()
        consecutive_errors = int(autonomy_status.get("consecutive_error_count", 0) or 0)
        no_progress_streak = int(autonomy_status.get("no_progress_streak", 0) or 0)
        if consecutive_errors >= 5:
            incidents.append(
                incident_cls(
                    component="autonomy_stuck",
                    reason=f"autonomy_consecutive_errors:{consecutive_errors}",
                    recoverable=False,
                )
            )
        elif no_progress_streak >= 3:
            incidents.append(
                incident_cls(
                    component="autonomy_stuck",
                    reason=f"autonomy_no_progress_streak:{no_progress_streak}",
                    recoverable=False,
                )
            )

    provider_telemetry = provider_telemetry_snapshot(runtime.engine.provider)
    provider_summary = provider_telemetry.get("summary", {}) if isinstance(provider_telemetry, dict) else {}
    provider_state = str(provider_summary.get("state", "") or "").strip().lower()
    provider_name = str(provider_telemetry.get("provider", "") or "provider").strip().lower() or "provider"
    if provider_state in {"circuit_open", "cooldown"}:
        incidents.append(
            incident_cls(
                component="provider",
                reason=f"provider_{provider_state}:{provider_name}",
                recoverable=False,
            )
        )

    return incidents


__all__ = ["collect_supervisor_incidents"]
