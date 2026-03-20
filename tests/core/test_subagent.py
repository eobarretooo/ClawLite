from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import clawlite.core.subagent as subagent_module
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


def test_subagent_manager_save_state_uses_durable_atomic_write(tmp_path: Path) -> None:
    mgr = SubagentManager(state_path=tmp_path / "state")
    mgr._runs["run-1"] = SubagentRun(
        run_id="run-1",
        session_id="s1",
        task="task-1",
        status="queued",
        metadata={"resume_attempts": 0, "resume_attempts_max": 2, "retry_budget_remaining": 2},
    )

    fsync_fds: list[int] = []
    real_fsync = subagent_module.os.fsync

    def _tracking_fsync(fd: int) -> None:
        fsync_fds.append(fd)
        real_fsync(fd)

    with patch("clawlite.core.subagent.os.fsync", side_effect=_tracking_fsync):
        mgr._save_state()

    payload = json.loads(mgr._state_file.read_text(encoding="utf-8"))
    assert payload["runs"][0]["run_id"] == "run-1"
    assert len(fsync_fds) >= 1
    assert not list(mgr._state_file.parent.glob("runs.json.tmp*"))


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


def test_subagent_manager_restart_clears_phantom_queue_entries(tmp_path: Path) -> None:
    async def _scenario() -> None:
        blocker = asyncio.Event()
        resumed_gate = asyncio.Event()

        async def _blocking_runner(_session_id: str, task: str) -> str:
            await blocker.wait()
            return f"done:{task}"

        async def _resumed_runner(_session_id: str, task: str) -> str:
            await resumed_gate.wait()
            return f"resumed:{task}"

        state_path = tmp_path / "state"
        mgr = SubagentManager(state_path=state_path, max_concurrent_runs=1, max_queued_runs=1)
        running = await mgr.spawn(session_id="s1", task="long-running", runner=_blocking_runner)
        queued = await mgr.spawn(session_id="s1", task="long-queued", runner=_blocking_runner)
        assert queued.status == "queued"

        restored_mgr = SubagentManager(state_path=state_path, max_concurrent_runs=1, max_queued_runs=1)
        assert list(restored_mgr._queue) == []

        resumed = await restored_mgr.spawn(session_id="s1", task="new-running", runner=_resumed_runner)
        assert resumed.status == "running"

        follow_up = await restored_mgr.spawn(session_id="s1", task="new-queued", runner=_resumed_runner)
        assert follow_up.status == "queued"
        assert list(restored_mgr._queue) == [follow_up.run_id]

        assert await mgr.cancel_async(running.run_id) is True
        assert await mgr.cancel_async(queued.run_id) is True
        await asyncio.sleep(0)
        assert await restored_mgr.cancel_async(resumed.run_id) is True
        assert await restored_mgr.cancel_async(follow_up.run_id) is True
        await asyncio.sleep(0)

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


def test_subagent_manager_resume_rejects_already_queued_run(tmp_path: Path) -> None:
    async def _scenario() -> None:
        blocker = asyncio.Event()

        async def _blocking_runner(_session_id: str, task: str) -> str:
            await blocker.wait()
            return f"done:{task}"

        mgr = SubagentManager(
            state_path=tmp_path / "state",
            max_concurrent_runs=1,
            max_queued_runs=4,
            max_resume_attempts=2,
        )
        active = await mgr.spawn(session_id="s1", task="active", runner=_blocking_runner)
        run = SubagentRun(
            run_id="resume-once",
            session_id="s1",
            task="retry-me",
            status="interrupted",
            finished_at="2026-03-05T10:00:00+00:00",
            metadata={
                "resumable": True,
                "resume_attempts": 0,
                "resume_attempts_max": 2,
                "retry_budget_remaining": 2,
            },
        )
        mgr._runs[run.run_id] = run

        queued = await mgr.resume(run_id=run.run_id, runner=_blocking_runner)
        assert queued.status == "queued"
        assert queued.metadata["resume_attempts"] == 1
        assert queued.metadata["retry_budget_remaining"] == 1
        assert list(mgr._queue) == [run.run_id]

        try:
            await mgr.resume(run_id=run.run_id, runner=_blocking_runner)
            raise AssertionError("expected queued run to be non-resumable")
        except ValueError as exc:
            assert "not resumable" in str(exc)

        current = mgr.get_run(run.run_id)
        assert current is not None
        assert current.metadata["resume_attempts"] == 1
        assert current.metadata["retry_budget_remaining"] == 1
        assert list(mgr._queue) == [run.run_id]

        assert await mgr.cancel_async(active.run_id) is True
        assert await mgr.cancel_async(run.run_id) is True
        await asyncio.sleep(0)

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
            run_ttl_seconds=0.05,
            zombie_grace_seconds=0.0,
        )
        running = await mgr.spawn(session_id="s1", task="expire-me", runner=_blocking_runner)
        await asyncio.sleep(0.08)

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
            "pruned_completed": 0,
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
        "interrupted-resumable": SubagentRun(
            run_id="interrupted-resumable",
            session_id="s1",
            task="task-f",
            status="interrupted",
            finished_at="2026-03-05T10:12:00+00:00",
            metadata={"resumable": True},
        ),
        "interrupted-final": SubagentRun(
            run_id="interrupted-final",
            session_id="s1",
            task="task-g",
            status="interrupted",
            finished_at="2026-03-05T10:13:00+00:00",
            metadata={"resumable": False},
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
    assert [row.run_id for row in rows] == ["done-unsynth", "error-unsynth", "interrupted-final"]


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


def test_subagent_resume_clears_stale_synthesis_metadata(tmp_path: Path) -> None:
    async def _scenario() -> None:
        blocker = asyncio.Event()

        async def _blocking_runner(_session_id: str, task: str) -> str:
            await blocker.wait()
            return f"done:{task}"

        mgr = SubagentManager(state_path=tmp_path / "state", max_concurrent_runs=1, max_resume_attempts=2)
        run = SubagentRun(
            run_id="r-synth-retry",
            session_id="s1",
            task="retry task",
            status="interrupted",
            finished_at="2026-03-05T10:00:00+00:00",
            metadata={
                "resumable": True,
                "resume_attempts": 0,
                "resume_attempts_max": 2,
                "retry_budget_remaining": 2,
                "synthesized": True,
                "synthesized_at": "2026-03-05T10:01:00+00:00",
                "synthesized_digest_id": "dig-old",
            },
        )
        mgr._runs[run.run_id] = run

        resumed = await mgr.resume(run_id=run.run_id, runner=_blocking_runner)
        assert resumed.status == "running"
        assert "synthesized" not in resumed.metadata
        assert "synthesized_at" not in resumed.metadata
        assert "synthesized_digest_id" not in resumed.metadata

        blocker.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        final = mgr.get_run(run.run_id)
        assert final is not None
        assert final.status == "done"
        assert "synthesized" not in final.metadata
        assert "synthesized_at" not in final.metadata
        assert "synthesized_digest_id" not in final.metadata

    asyncio.run(_scenario())


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


def test_subagent_manager_status_reports_maintenance_and_heartbeat(tmp_path: Path) -> None:
    async def _scenario() -> None:
        gate = asyncio.Event()

        async def _slow_runner(_session_id: str, task: str) -> str:
            await gate.wait()
            return f"done:{task}"

        mgr = SubagentManager(
            state_path=tmp_path / "state",
            max_concurrent_runs=1,
            run_ttl_seconds=60,
            zombie_grace_seconds=5,
        )
        run = await mgr.spawn(session_id="s1", task="long", runner=_slow_runner)

        before_heartbeat = str(run.metadata.get("heartbeat_at", "") or "")
        assert before_heartbeat

        await asyncio.sleep(0)
        swept = await mgr.sweep_async()
        current = mgr.get_run(run.run_id)
        assert current is not None
        after_heartbeat = str(current.metadata.get("heartbeat_at", "") or "")

        assert swept == {
            "expired": 0,
            "orphaned_running": 0,
            "orphaned_queued": 0,
            "pruned_completed": 0,
        }
        assert after_heartbeat
        assert after_heartbeat >= before_heartbeat

        status = mgr.status()
        assert status["run_count"] == 1
        assert status["running_count"] == 1
        assert status["queued_count"] == 0
        assert status["maintenance_interval_s"] == 5.0
        assert status["maintenance"]["sweep_runs"] >= 1
        assert status["maintenance"]["last_sweep_stats"] == swept
        assert status["maintenance"]["totals"] == swept

        gate.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        final = mgr.get_run(run.run_id)
        assert final is not None
        assert final.status == "done"
        assert str(final.metadata.get("heartbeat_at", "") or "") >= after_heartbeat

    asyncio.run(_scenario())


def test_orchestration_depth_increments_on_child_spawn() -> None:
    async def _scenario() -> None:
        mgr = SubagentManager(max_orchestration_depth=5)

        async def runner(sid: str, task: str) -> str:
            return "ok"

        run = await mgr.spawn(
            session_id="child",
            task="task",
            runner=runner,
            parent_session_id="parent",
        )
        await asyncio.sleep(0.1)
        assert run.metadata.get("orchestration_depth") == 1
        assert run.session_id.startswith("parent:sub:")

    asyncio.run(_scenario())


def test_orchestration_depth_blocks_at_max() -> None:
    async def _scenario() -> None:
        mgr = SubagentManager(max_orchestration_depth=2)

        async def runner(sid: str, task: str) -> str:
            return "ok"

        # Depth 1: parent -> child
        run1 = await mgr.spawn(
            session_id="c1",
            task="t",
            runner=runner,
            parent_session_id="parent",
        )
        await asyncio.sleep(0.1)
        assert run1.metadata.get("orchestration_depth") == 1

        # Depth 2: parent:sub:XX -> grandchild
        run2 = await mgr.spawn(
            session_id="c2",
            task="t",
            runner=runner,
            parent_session_id=run1.session_id,
        )
        await asyncio.sleep(0.1)
        assert run2.metadata.get("orchestration_depth") == 2

        # Depth 3: should be blocked
        try:
            await mgr.spawn(
                session_id="c3",
                task="t",
                runner=runner,
                parent_session_id=run2.session_id,
            )
            raise AssertionError("Should have raised SubagentLimitError")
        except SubagentLimitError as exc:
            assert "orchestration depth limit" in str(exc)

    asyncio.run(_scenario())


def test_orchestration_depth_zero_means_no_parent() -> None:
    async def _scenario() -> None:
        mgr = SubagentManager()

        async def runner(sid: str, task: str) -> str:
            return "ok"

        run = await mgr.spawn(session_id="s1", task="t", runner=runner)
        await asyncio.sleep(0.1)
        assert run.metadata.get("orchestration_depth") == 0

    asyncio.run(_scenario())


def test_orchestration_depth_unlimited_when_zero() -> None:
    """max_orchestration_depth=0 disables the guard."""
    async def _scenario() -> None:
        mgr = SubagentManager(max_orchestration_depth=0)

        async def runner(sid: str, task: str) -> str:
            return "ok"

        # Build a deep chain without hitting a limit
        parent_id = "root"
        for _ in range(10):
            run = await mgr.spawn(
                session_id="child",
                task="t",
                runner=runner,
                parent_session_id=parent_id,
            )
            await asyncio.sleep(0.05)
            parent_id = run.session_id
        # Should complete without error

    asyncio.run(_scenario())


def test_status_exposes_max_orchestration_depth() -> None:
    mgr = SubagentManager(max_orchestration_depth=3)
    assert mgr.status()["max_orchestration_depth"] == 3
