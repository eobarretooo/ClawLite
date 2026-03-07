from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
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


def test_subagent_manager_spawn_persists_custom_metadata(tmp_path: Path) -> None:
    async def _scenario() -> None:
        mgr = SubagentManager(state_path=tmp_path / "state")
        run = await mgr.spawn(
            session_id="s1",
            task="t1",
            runner=_runner,
            metadata={
                "target_session_id": "s1:subagent",
                "target_user_id": "u-1",
                "share_scope": "family",
            },
        )
        await asyncio.sleep(0)

        listed = mgr.list_runs(session_id="s1")
        assert listed
        assert listed[0].run_id == run.run_id
        assert listed[0].metadata["target_session_id"] == "s1:subagent"
        assert listed[0].metadata["target_user_id"] == "u-1"
        assert listed[0].metadata["share_scope"] == "family"

        reloaded = SubagentManager(state_path=tmp_path / "state")
        restored = reloaded.list_runs(session_id="s1")[0]
        assert restored.metadata["target_session_id"] == "s1:subagent"
        assert restored.metadata["target_user_id"] == "u-1"
        assert restored.metadata["share_scope"] == "family"

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

        assert await mgr.cancel_async(run.run_id) is True
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


def test_subagent_manager_enforces_retry_budget_on_resume(tmp_path: Path) -> None:
    async def _scenario() -> None:
        mgr = SubagentManager(state_path=tmp_path / "state", max_resume_attempts=1)
        expired_run = SubagentRun(
            run_id="r-budget",
            session_id="s1",
            task="retry task",
            status="interrupted",
            finished_at="2026-03-05T10:00:00+00:00",
            metadata={
                "resumable": True,
                "resume_attempts": 1,
                "resume_attempts_max": 1,
                "retry_budget_remaining": 0,
            },
        )
        mgr._runs[expired_run.run_id] = expired_run
        mgr._save_state()

        try:
            await mgr.resume(run_id=expired_run.run_id, runner=_runner)
            raise AssertionError("expected retry budget exhaustion")
        except ValueError as exc:
            assert "exhausted retry budget" in str(exc)

        run = mgr.list_runs(session_id="s1")[0]
        assert run.metadata["resumable"] is False
        assert run.metadata["retry_budget_remaining"] == 0

    asyncio.run(_scenario())


def test_subagent_manager_sweeps_expired_and_orphaned_runs(tmp_path: Path) -> None:
    async def _scenario() -> None:
        blocker = asyncio.Event()

        async def _blocking_runner(_session_id: str, task: str) -> str:
            await blocker.wait()
            return f"done:{task}"

        mgr = SubagentManager(
            state_path=tmp_path / "state",
            max_concurrent_runs=1,
            run_ttl_seconds=0.01,
            zombie_grace_seconds=0.0,
        )
        running = await mgr.spawn(session_id="s1", task="expire-me", runner=_blocking_runner)
        await asyncio.sleep(0.02)

        stale_iso = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()
        orphaned = SubagentRun(
            run_id="queued-orphan",
            session_id="s1",
            task="recover-me",
            status="queued",
            queued_at=stale_iso,
            updated_at=stale_iso,
            metadata={
                "resume_attempts": 0,
                "resume_attempts_max": 2,
                "retry_budget_remaining": 2,
                "resumable": False,
            },
        )
        mgr._runs[orphaned.run_id] = orphaned
        mgr._save_state()

        swept = await mgr.sweep_async()
        await asyncio.sleep(0)

        assert swept == {
            "expired": 1,
            "orphaned_running": 0,
            "orphaned_queued": 1,
        }

        rows = {row.run_id: row for row in mgr.list_runs(session_id="s1")}
        assert rows[running.run_id].status == "expired"
        assert rows[running.run_id].metadata["resumable"] is False
        assert "expired" in rows[running.run_id].error
        assert rows["queued-orphan"].status == "interrupted"
        assert rows["queued-orphan"].metadata["resumable"] is True
        assert rows["queued-orphan"].metadata["last_status_reason"] == "orphaned_queue_entry"

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


def test_subagent_manager_concurrent_spawn_cancel_and_synthesize(tmp_path: Path) -> None:
    async def _scenario() -> None:
        gate = asyncio.Event()

        async def _slow_runner(_session_id: str, task: str) -> str:
            await gate.wait()
            return f"done:{task}"

        mgr = SubagentManager(
            state_path=tmp_path / "state",
            max_concurrent_runs=1,
            max_queued_runs=64,
            per_session_quota=128,
        )

        initial_runs = [
            await mgr.spawn(session_id="race", task=f"task-{idx}", runner=_slow_runner)
            for idx in range(12)
        ]
        queued_run_ids = [run.run_id for run in initial_runs if run.status == "queued"]

        async def _spawn_more() -> None:
            for idx in range(12, 24):
                await mgr.spawn(session_id="race", task=f"task-{idx}", runner=_slow_runner)
                await asyncio.sleep(0)

        async def _cancel_some() -> None:
            for run_id in queued_run_ids[::2]:
                await mgr.cancel_async(run_id)
                await asyncio.sleep(0)

        async def _mark_synthesized_loop() -> None:
            run_ids = [run.run_id for run in initial_runs]
            for _ in range(8):
                await mgr.mark_synthesized_async(run_ids, digest_id="digest-race")
                await asyncio.sleep(0)

        await asyncio.gather(_spawn_more(), _cancel_some(), _mark_synthesized_loop())
        gate.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        runs = mgr.list_runs(session_id="race")
        run_ids = [run.run_id for run in runs]
        assert len(run_ids) == len(set(run_ids))

        queue_snapshot = list(mgr._queue)
        assert len(queue_snapshot) == len(set(queue_snapshot))
        assert all(run_id in mgr._runs for run_id in queue_snapshot)
        assert all(mgr._runs[run_id].status == "queued" for run_id in queue_snapshot)

        valid_statuses = {"queued", "running", "done", "error", "cancelled", "interrupted"}
        valid_statuses.add("expired")
        assert all(run.status in valid_statuses for run in runs)
        assert all(str(run.updated_at).strip() for run in runs)

    asyncio.run(_scenario())
