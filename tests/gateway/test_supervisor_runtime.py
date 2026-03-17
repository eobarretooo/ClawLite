from __future__ import annotations

import asyncio
from types import SimpleNamespace

from clawlite.runtime import SupervisorIncident
from clawlite.gateway.supervisor_runtime import collect_supervisor_incidents


def test_collect_supervisor_incidents_reports_component_and_provider_failures() -> None:
    async def _scenario() -> None:
        cfg = SimpleNamespace(
            gateway=SimpleNamespace(
                heartbeat=SimpleNamespace(enabled=True),
                autonomy=SimpleNamespace(enabled=True, tuning_loop_enabled=True),
            )
        )
        runtime = SimpleNamespace(
            channels=SimpleNamespace(
                dispatcher_diagnostics=lambda: {"enabled": True, "running": False, "task_state": "crashed"},
                recovery_diagnostics=lambda: {"enabled": True, "running": True, "task_state": "running"},
            ),
            heartbeat=SimpleNamespace(status=lambda: {"running": False, "worker_state": "stopped"}),
            cron=SimpleNamespace(status=lambda: {"running": True, "worker_state": "running"}),
            autonomy_wake=SimpleNamespace(status=lambda: {"running": False, "worker_state": "stopped"}),
            autonomy=SimpleNamespace(status=lambda: {"running": True, "consecutive_error_count": 6, "no_progress_streak": 0}),
            skills_loader=SimpleNamespace(watcher_status=lambda: {"running": False, "task_state": "failed"}),
            memory_monitor=object(),
            job_queue=SimpleNamespace(worker_status=lambda: {"running": False, "workers_alive": 0, "workers_total": 2}),
            engine=SimpleNamespace(provider=object()),
        )

        self_evolution_task = object()
        subagent_maintenance_task = object()
        proactive_task = object()
        tuning_task = object()

        def _snapshot(task: object | None, *, running: bool, last_error: str) -> tuple[str, str]:
            del running, last_error
            mapping = {
                self_evolution_task: ("failed", "boom"),
                subagent_maintenance_task: ("running", ""),
                proactive_task: ("stopped", ""),
                tuning_task: ("running", ""),
            }
            return mapping.get(task, ("running", ""))

        incidents = await collect_supervisor_incidents(
            incident_cls=SupervisorIncident,
            cfg=cfg,
            runtime=runtime,
            self_evolution_task=self_evolution_task,
            self_evolution_running=False,
            self_evolution_runner_state={"enabled": True, "last_error": "boom"},
            subagent_maintenance_task=subagent_maintenance_task,
            subagent_maintenance_running=True,
            subagent_maintenance_state={"last_error": ""},
            proactive_task=proactive_task,
            proactive_running=False,
            proactive_runner_state={"last_error": ""},
            tuning_task=tuning_task,
            tuning_running=True,
            tuning_runner_state={"last_error": ""},
            background_task_snapshot=_snapshot,
            provider_telemetry_snapshot=lambda provider: {"provider": "failover", "summary": {"state": "circuit_open"}},
        )

        components = {(item.component, item.reason) for item in incidents}
        assert ("self_evolution", "self_evolution_failed") in components
        assert ("channels_dispatcher", "channels_dispatcher_crashed") in components
        assert ("heartbeat", "heartbeat_stopped") in components
        assert ("autonomy_wake", "autonomy_wake_stopped") in components
        assert ("skills_watcher", "skills_watcher_failed") in components
        assert ("proactive_monitor", "proactive_monitor_stopped") in components
        assert ("job_workers", "job_workers_dead:0/2") in components
        assert ("autonomy_stuck", "autonomy_consecutive_errors:6") in components
        assert ("provider", "provider_circuit_open:failover") in components

    asyncio.run(_scenario())
