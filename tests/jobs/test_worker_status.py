"""Tests for JobQueue.worker_status() — Phase 5 supervisor integration."""
from __future__ import annotations

import asyncio
import pytest


@pytest.fixture
def queue():
    from clawlite.jobs.queue import JobQueue
    return JobQueue(concurrency=2)


def test_worker_status_before_start(queue):
    status = queue.worker_status()
    assert status["running"] is False
    assert status["concurrency"] == 2
    assert status["workers_alive"] == 0
    assert status["workers_total"] == 0
    assert status["pending_jobs"] == 0
    assert status["running_jobs"] == 0


@pytest.mark.asyncio
async def test_worker_status_after_start(queue):
    async def noop(job):
        return "ok"

    queue.start(noop)
    status = queue.worker_status()
    assert status["running"] is True
    assert status["workers_alive"] == 2
    assert status["workers_total"] == 2
    await queue.stop()


@pytest.mark.asyncio
async def test_worker_status_after_stop(queue):
    async def noop(job):
        return "ok"

    queue.start(noop)
    await queue.stop()
    status = queue.worker_status()
    assert status["running"] is False
    assert status["workers_alive"] == 0


@pytest.mark.asyncio
async def test_worker_status_counts_pending_and_running():
    from clawlite.jobs.queue import JobQueue

    q = JobQueue(concurrency=1)
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_worker(job):
        started.set()
        await release.wait()
        return "done"

    j1 = q.submit("agent_run", {})
    j2 = q.submit("agent_run", {})
    q.start(slow_worker)

    # Wait for first job to start running
    await asyncio.wait_for(started.wait(), timeout=2.0)

    status = q.worker_status()
    assert status["running_jobs"] >= 1
    assert status["pending_jobs"] >= 1

    release.set()
    await q.stop()
