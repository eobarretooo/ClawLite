from __future__ import annotations

import asyncio

from clawlite.runtime.autonomy import AutonomyService


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def monotonic(self) -> float:
        return self.now


def test_autonomy_backlog_skip_increments_counter_and_skips_callback() -> None:
    clock = _Clock()
    calls = {"run": 0}

    async def _snapshot() -> dict[str, dict[str, int]]:
        return {
            "queue": {"outbound_size": 5, "dead_letter_size": 6},
            "supervisor": {"running": True, "incident_count": 0, "consecutive_error_count": 0},
            "channels": {"enabled_count": 1, "running_count": 1},
        }

    async def _run(_snapshot_payload: dict[str, object]) -> str:
        calls["run"] += 1
        return "should_not_run"

    async def _scenario() -> None:
        service = AutonomyService(
            enabled=True,
            interval_s=10,
            cooldown_s=30,
            timeout_s=5,
            max_queue_backlog=10,
            snapshot_callback=_snapshot,
            run_callback=_run,
            now_monotonic=clock.monotonic,
        )
        status = await service.run_once(force=False)
        assert status["ticks"] == 1
        assert status["run_attempts"] == 0
        assert status["skipped_backlog"] == 1
        assert calls["run"] == 0

    asyncio.run(_scenario())


def test_autonomy_success_updates_excerpt_and_cooldown_skip() -> None:
    clock = _Clock()
    calls = {"run": 0}

    async def _snapshot() -> dict[str, dict[str, int]]:
        return {
            "queue": {"outbound_size": 0, "dead_letter_size": 0},
            "supervisor": {"running": True, "incident_count": 0, "consecutive_error_count": 0},
            "channels": {"enabled_count": 1, "running_count": 1},
        }

    async def _run(_snapshot_payload: dict[str, object]) -> str:
        calls["run"] += 1
        return "AUTONOMY_IDLE"

    async def _scenario() -> None:
        service = AutonomyService(
            enabled=True,
            interval_s=10,
            cooldown_s=30,
            timeout_s=5,
            max_queue_backlog=10,
            snapshot_callback=_snapshot,
            run_callback=_run,
            now_monotonic=clock.monotonic,
        )
        first = await service.run_once(force=False)
        assert first["run_attempts"] == 1
        assert first["run_success"] == 1
        assert first["run_failures"] == 0
        assert first["worker_state"] == "stopped"
        assert first["last_result_excerpt"] == "AUTONOMY_IDLE"
        assert first["consecutive_error_count"] == 0

        second = await service.run_once(force=False)
        assert second["run_attempts"] == 1
        assert second["skipped_cooldown"] == 1
        assert calls["run"] == 1

    asyncio.run(_scenario())


def test_autonomy_failed_run_updates_failure_counters_and_error() -> None:
    clock = _Clock()

    async def _snapshot() -> dict[str, dict[str, int]]:
        return {
            "queue": {"outbound_size": 0, "dead_letter_size": 0},
            "supervisor": {"running": True, "incident_count": 0, "consecutive_error_count": 0},
            "channels": {"enabled_count": 1, "running_count": 1},
        }

    async def _run(_snapshot_payload: dict[str, object]) -> str:
        raise RuntimeError("autonomy_boom")

    async def _scenario() -> None:
        service = AutonomyService(
            enabled=True,
            interval_s=10,
            cooldown_s=0,
            timeout_s=5,
            max_queue_backlog=10,
            snapshot_callback=_snapshot,
            run_callback=_run,
            now_monotonic=clock.monotonic,
        )
        status = await service.run_once(force=False)
        assert status["run_attempts"] == 1
        assert status["run_success"] == 0
        assert status["run_failures"] == 1
        assert status["consecutive_error_count"] == 1
        assert "autonomy_boom" in status["last_error"]

    asyncio.run(_scenario())


def test_autonomy_provider_backoff_skips_until_window_expires() -> None:
    clock = _Clock()
    calls = {"run": 0}

    async def _snapshot() -> dict[str, dict[str, object]]:
        return {
            "queue": {"outbound_size": 0, "dead_letter_size": 0},
            "supervisor": {"running": True, "incident_count": 0, "consecutive_error_count": 0},
            "channels": {"enabled_count": 1, "running_count": 1},
            "provider": {
                "provider": "failover",
                "state": "cooldown",
                "cooldown_remaining_s": 45.0,
                "last_error_class": "rate_limit",
                "suppression_reason": "cooldown",
                "suppression_backoff_s": 45.0,
                "suppression_hint": "provider cooldown active",
            },
        }

    async def _run(_snapshot_payload: dict[str, object]) -> str:
        calls["run"] += 1
        if calls["run"] == 1:
            raise RuntimeError("autonomy_provider_backoff:failover:cooldown:45")
        return "AUTONOMY_IDLE"

    async def _scenario() -> None:
        service = AutonomyService(
            enabled=True,
            interval_s=10,
            cooldown_s=0,
            timeout_s=5,
            max_queue_backlog=10,
            snapshot_callback=_snapshot,
            run_callback=_run,
            now_monotonic=clock.monotonic,
        )

        first = await service.run_once(force=False)
        assert first["run_attempts"] == 1
        assert first["run_failures"] == 1
        assert first["last_error_kind"] == "provider_backoff"
        assert first["provider_backoff_reason"] == "cooldown"
        assert first["provider_backoff_provider"] == "failover"
        assert first["provider_backoff_remaining_s"] == 45.0
        assert first["last_snapshot"]["provider"]["suppression_reason"] == "cooldown"
        assert first["last_snapshot"]["provider"]["suppression_backoff_s"] == 45.0

        second = await service.run_once(force=False)
        assert second["run_attempts"] == 1
        assert second["skipped_provider_backoff"] == 1
        assert calls["run"] == 1

        clock.now += 46.0
        third = await service.run_once(force=False)
        assert third["run_attempts"] == 2
        assert third["run_success"] == 1
        assert third["last_error_kind"] == ""
        assert third["provider_backoff_remaining_s"] == 0.0
        assert calls["run"] == 2

    asyncio.run(_scenario())


def test_autonomy_start_restarts_when_previous_task_crashed() -> None:
    async def _scenario() -> None:
        service = AutonomyService(enabled=True, interval_s=60)

        async def _crash() -> None:
            raise RuntimeError("autonomy_worker_crash")

        crashed_task = asyncio.create_task(_crash())
        try:
            await crashed_task
        except RuntimeError:
            pass

        service._task = crashed_task
        service._running = True

        await service.start()
        replacement_task = service._task

        assert replacement_task is not None
        assert replacement_task is not crashed_task
        assert not replacement_task.done()

        await service.stop()

    asyncio.run(_scenario())


def test_autonomy_start_is_idempotent_with_healthy_running_task() -> None:
    async def _scenario() -> None:
        service = AutonomyService(enabled=True, interval_s=60)
        await service.start()
        first_task = service._task

        await service.start()

        assert service._task is first_task

        await service.stop()

    asyncio.run(_scenario())
