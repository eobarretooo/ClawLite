from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from clawlite.gateway.subagents_runtime import (
    resume_recoverable_subagents,
    run_subagent_maintenance_loop,
)


def test_run_subagent_maintenance_loop_updates_state_and_stops() -> None:
    async def _scenario() -> None:
        state: dict[str, object] = {}
        stop_event = asyncio.Event()

        class _Subagents:
            async def sweep_async(self) -> dict[str, int]:
                stop_event.set()
                return {"swept": 2}

        engine = SimpleNamespace(subagents=_Subagents())
        await run_subagent_maintenance_loop(
            engine=engine,
            state=state,
            stop_event=stop_event,
            interval_seconds=60.0,
            utc_now_iso=lambda: "2026-03-17T12:00:00+00:00",
            log_warning=lambda exc: None,
        )

        assert state["ticks"] == 1
        assert state["success_count"] == 1
        assert state["last_result"] == {"swept": 2}
        assert state["last_error"] == ""

    asyncio.run(_scenario())


def test_resume_recoverable_subagents_tracks_group_counts_and_notifies() -> None:
    async def _scenario() -> None:
        resumed: list[str] = []
        send_notice = AsyncMock(return_value="ok")
        recorded: list[tuple[tuple[object, ...], dict[str, object]]] = []
        component = {"enabled": False, "running": False, "last_error": ""}

        class _Subagents:
            def list_resumable_runs(self, limit: int = 128):
                del limit
                return [
                    SimpleNamespace(run_id="run-a", metadata={"last_status_reason": "manager_restart", "parallel_group_id": "grp-1"}),
                    SimpleNamespace(run_id="run-b", metadata={"last_status_reason": "orphaned_task", "parallel_group_id": "grp-1"}),
                ]

            async def resume(self, *, run_id: str, runner) -> None:
                del runner
                resumed.append(run_id)

        engine = SimpleNamespace(
            subagents=_Subagents(),
            _subagent_resume_runner_factory=lambda run: f"runner:{run.run_id}",
        )

        result = await resume_recoverable_subagents(
            component=component,
            engine=engine,
            record_autonomy_event=lambda *args, **kwargs: recorded.append((args, kwargs)),
            send_autonomy_notice=send_notice,
            log_warning=lambda *args: None,
            log_info=lambda *args: None,
            now_iso=lambda: "2026-03-17T12:00:00+00:00",
        )

        assert resumed == ["run-a", "run-b"]
        assert result == {"replayed": 2, "failed": 0}
        assert component["replayed"] == 2
        assert component["replayed_groups"] == 1
        assert component["last_group_ids"] == ["grp-1"]
        assert recorded[0][0][:3] == ("subagents", "startup_replay", "ok")
        assert send_notice.await_args.kwargs["metadata"]["replayed"] == 2

    asyncio.run(_scenario())
