from __future__ import annotations

import asyncio
from pathlib import Path

from clawlite.core.subagent import SubagentLimitError, SubagentManager, SubagentRun


async def _runner(_session_id: str, task: str) -> str:
    return f"done:{task}"


def test_subagent_manager_spawn_and_list() -> None:
    async def _scenario() -> None:
        mgr = SubagentManager()
        run = await mgr.spawn(session_id="s1", task="t1", runner=_runner)
        await asyncio.sleep(0)
        runs = mgr.list_runs(session_id="s1")
        assert runs
        assert runs[0].run_id == run.run_id

    asyncio.run(_scenario())


def test_subagent_manager_queue_limits_and_session_quota(tmp_path: Path) -> None:
    async def _scenario() -> None:
        gate = asyncio.Event()

        async def _slow_runner(_session_id: str, task: str) -> str:
            await gate.wait()
            return f"done:{task}"

        mgr = SubagentManager(
            state_path=tmp_path / "state",
            max_concurrent_runs=1,
            max_queued_runs=1,
            per_session_quota=2,
        )

        first = await mgr.spawn(session_id="s1", task="t1", runner=_slow_runner)
        second = await mgr.spawn(session_id="s1", task="t2", runner=_slow_runner)

        assert first.status == "running"
        assert second.status == "queued"

        try:
            await mgr.spawn(session_id="s1", task="t3", runner=_slow_runner)
            raise AssertionError("expected SubagentLimitError for per-session quota")
        except SubagentLimitError:
            pass

        try:
            await mgr.spawn(session_id="s2", task="t4", runner=_slow_runner)
            raise AssertionError("expected SubagentLimitError for queue cap")
        except SubagentLimitError:
            pass

        gate.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        runs = {row.task: row.status for row in mgr.list_runs(session_id="s1")}
        assert runs["t1"] == "done"
        assert runs["t2"] == "done"

    asyncio.run(_scenario())


def test_subagent_manager_restores_resumable_state(tmp_path: Path) -> None:
    async def _scenario() -> None:
        blocker = asyncio.Event()

        async def _blocking_runner(_session_id: str, task: str) -> str:
            await blocker.wait()
            return f"done:{task}"

        state_path = tmp_path / "state"
        mgr = SubagentManager(state_path=state_path, max_concurrent_runs=1)
        run = await mgr.spawn(session_id="s1", task="long", runner=_blocking_runner)

        restored_mgr = SubagentManager(state_path=state_path, max_concurrent_runs=1)
        restored = restored_mgr.list_runs(session_id="s1")[0]
        assert restored.run_id == run.run_id
        assert restored.status == "interrupted"
        assert restored.metadata.get("resumable") is True

        assert mgr.cancel(run.run_id) is True
        await asyncio.sleep(0)

        async def _resume_runner(_session_id: str, task: str) -> str:
            return f"resumed:{task}"

        resumed = await restored_mgr.resume(run_id=run.run_id, runner=_resume_runner)
        assert resumed.status in {"running", "queued"}
        await asyncio.sleep(0)

        final = restored_mgr.list_runs(session_id="s1")[0]
        assert final.status == "done"
        assert final.result == "resumed:long"
        assert int(final.metadata.get("resume_attempts", 0)) >= 1

    asyncio.run(_scenario())


def test_list_completed_unsynthesized_filters_status_and_metadata(tmp_path: Path) -> None:
    state_path = tmp_path / "state"
    mgr = SubagentManager(state_path=state_path)
    mgr._runs = {
        "done-unsynth": SubagentRun(
            run_id="done-unsynth",
            session_id="s1",
            task="task-a",
            status="done",
            result="ok",
            finished_at="2026-03-05T10:00:00+00:00",
            metadata={},
        ),
        "error-unsynth": SubagentRun(
            run_id="error-unsynth",
            session_id="s1",
            task="task-b",
            status="error",
            error="boom",
            finished_at="2026-03-05T10:05:00+00:00",
            metadata={},
        ),
        "done-synth": SubagentRun(
            run_id="done-synth",
            session_id="s1",
            task="task-c",
            status="done",
            result="already",
            finished_at="2026-03-05T10:10:00+00:00",
            metadata={"synthesized": True},
        ),
        "running": SubagentRun(
            run_id="running",
            session_id="s1",
            task="task-d",
            status="running",
            metadata={},
        ),
        "other-session": SubagentRun(
            run_id="other-session",
            session_id="s2",
            task="task-e",
            status="done",
            metadata={},
        ),
    }

    rows = mgr.list_completed_unsynthesized("s1")
    assert [row.run_id for row in rows] == ["done-unsynth", "error-unsynth"]


def test_mark_synthesized_persists_across_reload(tmp_path: Path) -> None:
    state_path = tmp_path / "state"
    mgr = SubagentManager(state_path=state_path)
    mgr._runs = {
        "r1": SubagentRun(
            run_id="r1",
            session_id="s1",
            task="task-a",
            status="done",
            result="ok",
            finished_at="2026-03-05T10:00:00+00:00",
            metadata={},
        )
    }
    mgr._save_state()

    updated = mgr.mark_synthesized(["r1"], digest_id="dig-01")
    assert updated == 1

    reloaded = SubagentManager(state_path=state_path)
    run = reloaded.list_runs(session_id="s1")[0]
    assert run.metadata.get("synthesized") is True
    assert str(run.metadata.get("synthesized_at", "")).strip()
    assert run.metadata.get("synthesized_digest_id") == "dig-01"
