from __future__ import annotations

import asyncio

from clawlite.runtime.supervisor import RuntimeSupervisor, SupervisorComponentPolicy, SupervisorIncident


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def monotonic(self) -> float:
        return self.now


def test_supervisor_heartbeat_recovery_then_cooldown_skip() -> None:
    clock = _Clock()
    calls = {"recover": 0}

    async def _checks() -> list[SupervisorIncident]:
        return [SupervisorIncident(component="heartbeat", reason="heartbeat_down", recoverable=True)]

    async def _recover(component: str, reason: str) -> bool:
        assert component == "heartbeat"
        assert reason == "heartbeat_down"
        calls["recover"] += 1
        return True

    async def _scenario() -> None:
        supervisor = RuntimeSupervisor(
            interval_s=20,
            cooldown_s=30,
            incident_checks=_checks,
            recover=_recover,
            now_monotonic=clock.monotonic,
        )
        await supervisor.run_once()
        await supervisor.run_once()
        status = supervisor.status()
        assert status["incident_count"] == 2
        assert status["recovery_attempts"] == 1
        assert status["recovery_success"] == 1
        assert status["recovery_skipped_cooldown"] == 1
        assert status["component_incidents"]["heartbeat"] == 2
        assert "heartbeat" in status["cooldown_active"]
        assert calls["recover"] == 1

    asyncio.run(_scenario())


def test_supervisor_cron_down_recovery_counters() -> None:
    clock = _Clock()

    async def _checks() -> list[SupervisorIncident]:
        return [SupervisorIncident(component="cron", reason="cron_down", recoverable=True)]

    async def _recover(component: str, reason: str) -> bool:
        assert component == "cron"
        assert reason == "cron_down"
        return True

    async def _scenario() -> None:
        supervisor = RuntimeSupervisor(
            interval_s=20,
            cooldown_s=30,
            incident_checks=_checks,
            recover=_recover,
            now_monotonic=clock.monotonic,
        )
        await supervisor.run_once()
        status = supervisor.status()
        assert status["incident_count"] == 1
        assert status["recovery_attempts"] == 1
        assert status["recovery_success"] == 1
        assert status["recovery_failures"] == 0
        assert status["component_incidents"]["cron"] == 1

    asyncio.run(_scenario())


def test_supervisor_provider_circuit_open_tracks_incident_without_recovery() -> None:
    clock = _Clock()
    notifications: list[tuple[str, str]] = []

    async def _checks() -> list[SupervisorIncident]:
        return [SupervisorIncident(component="provider", reason="circuit_open", recoverable=False)]

    async def _recover(_component: str, _reason: str) -> bool:
        raise AssertionError("recover should not be called for non-recoverable incidents")

    async def _on_incident(incident: SupervisorIncident) -> None:
        notifications.append((incident.component, incident.reason))

    async def _scenario() -> None:
        supervisor = RuntimeSupervisor(
            interval_s=20,
            cooldown_s=30,
            incident_checks=_checks,
            recover=_recover,
            on_incident=_on_incident,
            now_monotonic=clock.monotonic,
        )
        await supervisor.run_once()
        status = supervisor.status()
        assert status["incident_count"] == 1
        assert status["recovery_attempts"] == 0
        assert status["recovery_success"] == 0
        assert status["component_incidents"]["provider"] == 1
        assert status["last_incident"]["component"] == "provider"
        assert status["last_incident"]["reason"] == "circuit_open"
        assert notifications == [("provider", "circuit_open")]

    asyncio.run(_scenario())


def test_supervisor_component_budget_limits_recovery_attempts_per_window() -> None:
    clock = _Clock()
    calls = {"recover": 0}

    async def _checks() -> list[SupervisorIncident]:
        return [SupervisorIncident(component="heartbeat", reason="heartbeat_down", recoverable=True)]

    async def _recover(component: str, reason: str) -> bool:
        assert component == "heartbeat"
        assert reason == "heartbeat_down"
        calls["recover"] += 1
        return True

    async def _scenario() -> None:
        supervisor = RuntimeSupervisor(
            interval_s=20,
            cooldown_s=0,
            incident_checks=_checks,
            recover=_recover,
            component_policies={
                "heartbeat": SupervisorComponentPolicy(cooldown_s=0, max_recoveries=1, budget_window_s=60),
            },
            now_monotonic=clock.monotonic,
        )

        await supervisor.run_once()
        await supervisor.run_once()
        status = supervisor.status()
        heartbeat = status["component_recovery"]["heartbeat"]

        assert calls["recover"] == 1
        assert status["recovery_attempts"] == 1
        assert status["recovery_success"] == 1
        assert status["recovery_skipped_budget"] == 1
        assert heartbeat["recovery_attempts"] == 1
        assert heartbeat["recovery_success"] == 1
        assert heartbeat["recovery_skipped_budget"] == 1
        assert heartbeat["max_recoveries"] == 1
        assert heartbeat["budget_window_s"] == 60.0
        assert heartbeat["budget_remaining"] == 0

        clock.now += 61.0
        await supervisor.run_once()
        refreshed = supervisor.status()["component_recovery"]["heartbeat"]

        assert calls["recover"] == 2
        assert refreshed["recovery_attempts"] == 2
        assert refreshed["recovery_success"] == 2
        assert refreshed["budget_remaining"] == 0

    asyncio.run(_scenario())


def test_supervisor_component_specific_cooldown_overrides_global_cooldown() -> None:
    clock = _Clock()
    calls = {"recover": 0}

    async def _checks() -> list[SupervisorIncident]:
        return [SupervisorIncident(component="cron", reason="cron_down", recoverable=True)]

    async def _recover(component: str, reason: str) -> bool:
        assert component == "cron"
        assert reason == "cron_down"
        calls["recover"] += 1
        return True

    async def _scenario() -> None:
        supervisor = RuntimeSupervisor(
            interval_s=20,
            cooldown_s=30,
            incident_checks=_checks,
            recover=_recover,
            component_policies={
                "cron": SupervisorComponentPolicy(cooldown_s=5, max_recoveries=0, budget_window_s=60),
            },
            now_monotonic=clock.monotonic,
        )

        await supervisor.run_once()
        clock.now += 6.0
        await supervisor.run_once()
        status = supervisor.status()
        cron = status["component_recovery"]["cron"]

        assert calls["recover"] == 2
        assert status["recovery_attempts"] == 2
        assert status["recovery_skipped_cooldown"] == 0
        assert cron["cooldown_s"] == 5.0
        assert cron["recovery_attempts"] == 2
        assert cron["recovery_success"] == 2
        assert cron["budget_remaining"] is None

    asyncio.run(_scenario())


def test_supervisor_run_once_handles_check_exceptions() -> None:
    clock = _Clock()

    async def _checks() -> list[SupervisorIncident]:
        raise RuntimeError("tick_boom")

    async def _scenario() -> None:
        supervisor = RuntimeSupervisor(
            interval_s=20,
            cooldown_s=30,
            incident_checks=_checks,
            now_monotonic=clock.monotonic,
        )
        await supervisor.run_once()
        await supervisor.run_once()
        status = supervisor.status()
        assert status["ticks"] == 2
        assert status["consecutive_error_count"] == 2
        assert "tick_boom" in status["last_error"]

    asyncio.run(_scenario())


def test_supervisor_start_restarts_when_previous_task_crashed() -> None:
    async def _scenario() -> None:
        supervisor = RuntimeSupervisor(interval_s=60, cooldown_s=30)

        async def _crash() -> None:
            raise RuntimeError("supervisor_worker_crash")

        crashed_task = asyncio.create_task(_crash())
        try:
            await crashed_task
        except RuntimeError:
            pass

        supervisor._task = crashed_task
        supervisor._running = True

        await supervisor.start()
        replacement_task = supervisor._task

        assert replacement_task is not None
        assert replacement_task is not crashed_task
        assert not replacement_task.done()

        await supervisor.stop()

    asyncio.run(_scenario())


def test_supervisor_start_is_idempotent_with_healthy_running_task() -> None:
    async def _scenario() -> None:
        supervisor = RuntimeSupervisor(interval_s=60, cooldown_s=30)
        await supervisor.start()
        first_task = supervisor._task

        await supervisor.start()

        assert supervisor._task is first_task

        await supervisor.stop()

    asyncio.run(_scenario())
