from __future__ import annotations

import asyncio
from types import SimpleNamespace

from clawlite.gateway.background_runners import (
    run_proactive_monitor_loop,
    run_self_evolution_loop,
)


def test_run_proactive_monitor_loop_tracks_backpressure_and_counts() -> None:
    async def _scenario() -> None:
        state: dict[str, object] = {}
        stop_event = asyncio.Event()

        async def _submit() -> dict[str, object]:
            stop_event.set()
            return {
                "status": "wake_coalesced_backpressure",
                "pressure_class": "coalesced",
                "delivered": 2,
                "replayed": 1,
            }

        await run_proactive_monitor_loop(
            state=state,
            stop_event=stop_event,
            interval_seconds=60,
            is_running=lambda: True,
            submit_proactive_wake=_submit,
            utc_now_iso=lambda: "2026-03-17T12:00:00+00:00",
            log_error=lambda exc: None,
        )

        assert state["ticks"] == 1
        assert state["last_trigger"] == "startup"
        assert state["backpressure_count"] == 1
        assert state["backpressure_by_reason"] == {"coalesced": 1}
        assert state["delivered_count"] == 2
        assert state["replayed_count"] == 1
        assert state["last_result"] == "wake_coalesced_backpressure"

    asyncio.run(_scenario())


def test_run_self_evolution_loop_updates_runner_state() -> None:
    async def _scenario() -> None:
        state: dict[str, object] = {}
        stop_event = asyncio.Event()

        class _FakeSelfEvolution:
            cooldown_s = 9999.0

            async def run_once(self) -> dict[str, str]:
                stop_event.set()
                return {"last_outcome": "applied"}

        await run_self_evolution_loop(
            self_evolution=_FakeSelfEvolution(),
            state=state,
            stop_event=stop_event,
            utc_now_iso=lambda: "2026-03-17T12:00:00+00:00",
            log_error=lambda exc: None,
        )

        assert state["ticks"] == 1
        assert state["success_count"] == 1
        assert state["last_result"] == "applied"
        assert state["last_error"] == ""
        assert state["last_run_iso"] == "2026-03-17T12:00:00+00:00"

    asyncio.run(_scenario())
