from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from datetime import timedelta
from pathlib import Path

import pytest

from clawlite.scheduler.cron import CronService


def test_cron_service_add_and_run(tmp_path: Path) -> None:
    async def _scenario() -> None:
        store = tmp_path / "cron.json"
        service = CronService(store)
        seen: list[str] = []

        async def _on_job(job):
            seen.append(job.payload.prompt)
            return "ok"

        await service.add_job(session_id="s1", expression="every 1", prompt="ping")
        await service.start(_on_job)
        await asyncio.sleep(1.3)
        await service.stop()

        assert seen
        jobs = service.list_jobs(session_id="s1")
        assert jobs
        assert jobs[0]["expression"] == "every 1"
        assert jobs[0]["timezone"] == "UTC"

    asyncio.run(_scenario())


def test_cron_service_enable_disable_and_manual_run(tmp_path: Path) -> None:
    async def _scenario() -> None:
        store = tmp_path / "cron.json"
        service = CronService(store)
        seen: list[str] = []

        async def _on_job(job):
            seen.append(job.id)
            return "ran"

        job_id = await service.add_job(session_id="s1", expression="every 60", prompt="ping")
        assert service.enable_job(job_id, enabled=False) is True
        assert service.enable_job("missing", enabled=True) is False

        try:
            await service.run_job(job_id, on_job=_on_job)
            raise AssertionError("expected disabled error")
        except RuntimeError as exc:
            assert str(exc) == "cron_job_disabled"

        out = await service.run_job(job_id, on_job=_on_job, force=True)
        assert out == "ran"
        assert seen == [job_id]

    asyncio.run(_scenario())


def test_cron_service_run_once_is_auto_removed_in_loop(tmp_path: Path) -> None:
    async def _scenario() -> None:
        service = CronService(tmp_path / "cron.json")
        completed = asyncio.Event()

        async def _on_job(_job):
            completed.set()
            return "ok"

        job_id = await service.add_job(
            session_id="s1",
            expression="every 1",
            prompt="single shot",
            metadata={"run_once": True},
        )

        await service.start(_on_job)
        await asyncio.wait_for(completed.wait(), timeout=3.0)
        await asyncio.sleep(0.1)
        await service.stop()

        assert service.get_job(job_id) is None

    asyncio.run(_scenario())


def test_cron_service_run_once_is_auto_removed_in_manual_run(tmp_path: Path) -> None:
    async def _scenario() -> None:
        service = CronService(tmp_path / "cron.json")

        async def _on_job(_job):
            return "ok"

        job_id = await service.add_job(
            session_id="s1",
            expression="every 60",
            prompt="manual single shot",
            metadata={"run_once": True},
        )

        out = await service.run_job(job_id, on_job=_on_job)
        assert out == "ok"
        assert service.get_job(job_id) is None

    asyncio.run(_scenario())


def test_cron_service_timezone_validation_and_next_run(tmp_path: Path) -> None:
    async def _scenario() -> None:
        store = tmp_path / "cron.json"
        service = CronService(store, default_timezone="America/Sao_Paulo")

        try:
            await service.add_job(
                session_id="s1",
                expression="*/5 * * * *",
                prompt="ping",
                timezone_name="Invalid/Timezone",
            )
            raise AssertionError("expected invalid timezone error")
        except ValueError as exc:
            assert "unknown timezone" in str(exc)

        if service._compute_next.__globals__.get("croniter") is not None:
            job_id = await service.add_job(
                session_id="s1",
                expression="*/5 * * * *",
                prompt="ping",
                timezone_name="America/New_York",
            )

            row = service.list_jobs(session_id="s1")[0]
            assert row["id"] == job_id
            assert row["schedule"]["timezone"] == "America/New_York"
            assert row["timezone"] == "America/New_York"
            assert row["next_run_iso"]
        else:
            pytest.skip("croniter not installed in test environment")

        at_id = await service.add_job(
            session_id="s1",
            expression="at 2030-01-01T10:00:00",
            prompt="one shot",
            timezone_name="America/New_York",
        )
        at_row = [item for item in service.list_jobs(session_id="s1") if item["id"] == at_id][0]
        assert at_row["next_run_iso"].startswith("2030-01-01T15:00:00")

    asyncio.run(_scenario())


def test_cron_loop_survives_callback_failure_and_tracks_job_health(tmp_path: Path) -> None:
    async def _scenario() -> None:
        service = CronService(tmp_path / "cron.json")
        completed = asyncio.Event()
        call_count = 0

        async def _on_job(job):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("callback failed")
            completed.set()
            return "ok"

        job_id = await service.add_job(session_id="s1", expression="every 1", prompt="ping")
        await service.start(_on_job)
        await asyncio.wait_for(completed.wait(), timeout=3.0)

        async def _wait_for_committed_run() -> None:
            deadline = asyncio.get_running_loop().time() + 1.0
            while asyncio.get_running_loop().time() < deadline:
                current = service.get_job(job_id)
                if current is not None and current.run_count >= 2:
                    return
                await asyncio.sleep(0.01)
            raise AssertionError("timed out waiting for committed cron run")

        await _wait_for_committed_run()

        status_running = service.status()
        job = service.get_job(job_id)
        assert status_running["running"] is True
        assert job is not None
        assert job.run_count >= 2
        assert job.last_status == "success"
        assert job.consecutive_failures == 0
        assert status_running["job_failure_count"] >= 1
        assert status_running["job_success_count"] >= 1

        await service.stop()

    asyncio.run(_scenario())


def test_cron_start_restarts_when_previous_task_crashed(tmp_path: Path) -> None:
    async def _scenario() -> None:
        service = CronService(tmp_path / "cron.json")

        async def _crash() -> None:
            raise RuntimeError("cron_worker_crash")

        async def _on_job(_job):
            return "ok"

        crashed_task = asyncio.create_task(_crash())
        try:
            await crashed_task
        except RuntimeError:
            pass

        service._task = crashed_task
        crashed_status = service.status()
        assert crashed_status["running"] is False
        assert crashed_status["worker_state"] == "failed"
        assert "cron_worker_crash" in crashed_status["last_error"]

        await service.start(_on_job)
        replacement_task = service._task

        assert replacement_task is not None
        assert replacement_task is not crashed_task
        assert not replacement_task.done()
        assert service.status()["worker_state"] == "running"

        await service.stop()

    asyncio.run(_scenario())


def test_cron_loop_times_out_slow_callback_and_keeps_processing(tmp_path: Path) -> None:
    async def _scenario() -> None:
        service = CronService(tmp_path / "cron.json", callback_timeout_seconds=0.05)
        fast_ran = asyncio.Event()

        slow_job_id = await service.add_job(session_id="s1", expression="every 1", prompt="slow", name="slow")
        await service.add_job(session_id="s1", expression="every 1", prompt="fast", name="fast")

        async def _on_job(job):
            if job.name == "slow":
                await asyncio.sleep(0.2)
                return "slow"
            fast_ran.set()
            return "fast"

        await service.start(_on_job)
        await asyncio.wait_for(fast_ran.wait(), timeout=4.0)

        async def _wait_for_slow_timeout() -> None:
            deadline = asyncio.get_running_loop().time() + 2.0
            while asyncio.get_running_loop().time() < deadline:
                slow_job = service.get_job(slow_job_id)
                if slow_job is not None and slow_job.last_status == "failed":
                    return
                await asyncio.sleep(0.02)
            raise AssertionError("timed out waiting for slow job timeout")

        await _wait_for_slow_timeout()
        status = service.status()
        slow_job = service.get_job(slow_job_id)

        assert status["running"] is True
        assert status["job_failure_count"] >= 1
        assert status["job_success_count"] >= 1
        assert slow_job is not None
        assert slow_job.last_status == "failed"
        assert "callback_timeout" in slow_job.last_error

        await service.stop()

    asyncio.run(_scenario())


def test_cron_manual_run_applies_callback_timeout(tmp_path: Path) -> None:
    async def _scenario() -> None:
        service = CronService(tmp_path / "cron.json", callback_timeout_seconds=0.05)
        job_id = await service.add_job(session_id="s1", expression="every 60", prompt="manual timeout")

        async def _slow(_job):
            await asyncio.sleep(0.2)
            return "late"

        with pytest.raises(TimeoutError, match="callback_timeout"):
            await service.run_job(job_id, on_job=_slow, force=True)

        job = service.get_job(job_id)
        status = service.status()

        assert job is not None
        assert job.last_status == "failed"
        assert "callback_timeout" in job.last_error
        assert status["job_failure_count"] >= 1

    asyncio.run(_scenario())


def test_cron_schedule_failure_isolated_per_job(monkeypatch, tmp_path: Path) -> None:
    async def _scenario() -> None:
        service = CronService(tmp_path / "cron.json")
        ok_ran = asyncio.Event()

        async def _on_job(job):
            if job.name == "ok":
                ok_ran.set()
            return "ok"

        bad_job_id = await service.add_job(session_id="s1", expression="every 9", prompt="bad", name="bad")
        await service.add_job(session_id="s1", expression="every 1", prompt="ok", name="ok")
        bad_job = service.get_job(bad_job_id)
        assert bad_job is not None
        bad_job.next_run_iso = ""

        original_compute_next = service._compute_next

        def _compute_next_with_failure(schedule, now):
            if schedule.kind == "every" and int(schedule.every_seconds or 0) == 9:
                raise ValueError("schedule exploded")
            return original_compute_next(schedule, now)

        monkeypatch.setattr(service, "_compute_next", _compute_next_with_failure)

        await service.start(_on_job)
        await asyncio.wait_for(ok_ran.wait(), timeout=3.0)
        bad_job = service.get_job(bad_job_id)
        status = service.status()

        assert status["running"] is True
        assert status["schedule_error_count"] >= 1
        assert bad_job is not None
        assert bad_job.last_status == "schedule_error"
        assert bad_job.consecutive_failures >= 1
        assert "schedule exploded" in bad_job.last_error

        await service.stop()

    asyncio.run(_scenario())


def test_cron_save_retry_diagnostics_and_persisted_store(monkeypatch, tmp_path: Path) -> None:
    async def _scenario() -> None:
        store = tmp_path / "cron.json"
        service = CronService(store)

        original_replace = os.replace
        calls = {"count": 0}

        def _flaky_replace(src, dst):
            calls["count"] += 1
            if calls["count"] == 1:
                raise OSError("replace failed once")
            return original_replace(src, dst)

        monkeypatch.setattr("clawlite.scheduler.cron.os.replace", _flaky_replace)

        job_id = await service.add_job(session_id="s1", expression="every 60", prompt="persist me")
        status = service.status()
        assert status["save_retries"] >= 1
        assert status["save_failures"] >= 1
        assert status["save_success"] >= 1

        rows = json.loads(store.read_text(encoding="utf-8"))
        assert any(str(row.get("id", "")) == job_id for row in rows)

        reloaded = CronService(store)
        listed = reloaded.list_jobs(session_id="s1")
        assert listed and listed[0]["id"] == job_id

    asyncio.run(_scenario())


def test_cron_write_rows_durable_path_calls_replace_and_fsync(monkeypatch, tmp_path: Path) -> None:
    service = CronService(tmp_path / "cron.json")
    rows = [{"id": "job-1", "name": "job"}]

    original_replace = os.replace
    fsync_calls: list[int] = []
    replace_calls: list[tuple[str, str]] = []

    def _tracked_fsync(fd: int) -> None:
        fsync_calls.append(fd)

    def _tracked_replace(src, dst) -> None:
        replace_calls.append((str(src), str(dst)))
        original_replace(src, dst)

    monkeypatch.setattr("clawlite.scheduler.cron.os.fsync", _tracked_fsync)
    monkeypatch.setattr("clawlite.scheduler.cron.os.replace", _tracked_replace)

    service._write_rows_unlocked(rows)

    assert len(replace_calls) == 1
    replaced_src, replaced_dst = replace_calls[0]
    assert replaced_dst == str(service.path)
    assert replaced_src.endswith(".tmp")
    assert len(fsync_calls) >= 2

    persisted = json.loads(service.path.read_text(encoding="utf-8"))
    assert persisted == rows


def test_cron_multi_instance_claims_due_job_once(tmp_path: Path) -> None:
    async def _scenario() -> None:
        store = tmp_path / "cron.json"
        initializer = CronService(store)
        await initializer.add_job(
            session_id="s1",
            expression="every 1",
            prompt="once",
            metadata={"run_once": True},
        )

        service_a = CronService(store, lease_seconds=30)
        service_b = CronService(store, lease_seconds=30)
        executed: list[str] = []
        completed = asyncio.Event()

        async def _on_job(job):
            executed.append(job.id)
            await asyncio.sleep(0.2)
            completed.set()
            return "ok"

        await service_a.start(_on_job)
        await service_b.start(_on_job)
        await asyncio.wait_for(completed.wait(), timeout=4.0)
        await asyncio.sleep(0.3)
        await service_a.stop()
        await service_b.stop()

        assert executed
        assert len(executed) == 1

    asyncio.run(_scenario())


def test_cron_stale_lease_is_recovered(tmp_path: Path) -> None:
    async def _scenario() -> None:
        store = tmp_path / "cron.json"
        initializer = CronService(store)
        await initializer.add_job(
            session_id="s1",
            expression="every 1",
            prompt="recover stale",
            metadata={"run_once": True},
        )

        payload = json.loads(store.read_text(encoding="utf-8"))
        assert isinstance(payload, list)
        assert payload
        stale_now = initializer._now()
        payload[0]["next_run_iso"] = (stale_now - timedelta(seconds=1)).isoformat()
        payload[0]["lease_token"] = "stale-token"
        payload[0]["lease_owner"] = "dead-instance"
        payload[0]["lease_claimed_iso"] = (stale_now - timedelta(seconds=90)).isoformat()
        payload[0]["lease_expires_iso"] = (stale_now - timedelta(seconds=30)).isoformat()
        store.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        recovering = CronService(store, lease_seconds=30)
        ran = asyncio.Event()

        async def _on_job(_job):
            ran.set()
            return "ok"

        await recovering.start(_on_job)
        await asyncio.wait_for(ran.wait(), timeout=4.0)
        await asyncio.sleep(0.2)
        await recovering.stop()

        status = recovering.status()
        assert status["lease_stale_recovered"] >= 1

    asyncio.run(_scenario())


def test_cron_loop_claim_path_does_not_block_event_loop(monkeypatch, tmp_path: Path) -> None:
    async def _scenario() -> None:
        service = CronService(tmp_path / "cron.json")
        job_id = await service.add_job(session_id="s1", expression="every 60", prompt="slow-claim")
        job = service.get_job(job_id)
        assert job is not None
        job.next_run_iso = (service._now() - timedelta(seconds=1)).isoformat()
        service._save()

        original_claim = service._try_claim_due_job
        claim_started = threading.Event()
        claim_finished = threading.Event()
        ticker_steps = 0
        executed = asyncio.Event()

        def _slow_claim(job_id: str, now):
            claim_started.set()
            time.sleep(0.3)
            try:
                return original_claim(job_id, now)
            finally:
                claim_finished.set()

        async def _on_job(_job):
            executed.set()
            return "ok"

        async def _ticker() -> int:
            nonlocal ticker_steps
            while not claim_started.is_set():
                await asyncio.sleep(0.01)
            while not claim_finished.is_set():
                ticker_steps += 1
                await asyncio.sleep(0.01)
            return ticker_steps

        monkeypatch.setattr(service, "_try_claim_due_job", _slow_claim)

        ticker_task = asyncio.create_task(_ticker())
        await service.start(_on_job)
        await asyncio.wait_for(executed.wait(), timeout=4.0)
        await asyncio.wait_for(ticker_task, timeout=2.0)
        await service.stop()

        assert ticker_steps > 0

    asyncio.run(_scenario())
