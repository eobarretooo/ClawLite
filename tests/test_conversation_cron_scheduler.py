from __future__ import annotations

import time

from clawlite.runtime import conversation_cron as cron_mod
from clawlite.runtime.conversation_cron import ConversationCronScheduler, CronRunResult


def test_scheduler_run_pending_once_calls_runtime(monkeypatch) -> None:
    called = {"count": 0}

    def fake_run_cron_jobs(*, job_id=None, run_all=False):
        called["count"] += 1
        assert job_id is None
        assert run_all is False
        return [CronRunResult(job_id=1, status="enqueued", task_id=10, message="ok")]

    monkeypatch.setattr(cron_mod, "run_cron_jobs", fake_run_cron_jobs)

    scheduler = ConversationCronScheduler(poll_interval_s=5.0)
    rows = scheduler.run_pending_once()

    assert called["count"] == 1
    assert len(rows) == 1
    assert rows[0].job_id == 1


def test_start_cron_scheduler_thread_runs_once_and_stops(monkeypatch) -> None:
    called = {"count": 0}

    def fake_run_cron_jobs(*, job_id=None, run_all=False):
        called["count"] += 1
        return []

    monkeypatch.setattr(cron_mod, "run_cron_jobs", fake_run_cron_jobs)

    scheduler = cron_mod.start_cron_scheduler_thread(poll_interval_s=0.1)

    # O loop dispara imediatamente antes do primeiro wait().
    timeout_at = time.time() + 0.5
    while called["count"] == 0 and time.time() < timeout_at:
        time.sleep(0.01)

    scheduler.stop()

    assert called["count"] >= 1
