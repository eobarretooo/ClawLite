"""Phase 5 supervisor integration tests — job workers and autonomy stuck detection."""
from __future__ import annotations

import asyncio
import pytest


@pytest.mark.asyncio
async def test_supervisor_detects_job_workers_dead():
    """Supervisor emits incident when job workers are not running."""
    from clawlite.jobs.queue import JobQueue
    from clawlite.runtime.supervisor import RuntimeSupervisor, SupervisorIncident

    job_queue = JobQueue(concurrency=1)
    incidents: list[SupervisorIncident] = []

    async def incident_checks() -> list[SupervisorIncident]:
        result = []
        status = job_queue.worker_status()
        if not status.get("running", False):
            workers_alive = int(status.get("workers_alive", 0))
            workers_total = int(status.get("workers_total", 0))
            result.append(SupervisorIncident(
                component="job_workers",
                reason=f"job_workers_dead:{workers_alive}/{workers_total}",
            ))
        return result

    async def on_incident(incident: SupervisorIncident) -> None:
        incidents.append(incident)

    supervisor = RuntimeSupervisor(
        interval_s=0.05,
        cooldown_s=0.0,
        incident_checks=incident_checks,
        on_incident=on_incident,
    )
    await supervisor.run_once()

    assert any(i.component == "job_workers" for i in incidents)
    assert supervisor.status()["incident_count"] >= 1


@pytest.mark.asyncio
async def test_supervisor_no_incident_when_job_workers_running():
    """Supervisor does not emit incident when job workers are alive."""
    from clawlite.jobs.queue import JobQueue
    from clawlite.runtime.supervisor import RuntimeSupervisor, SupervisorIncident

    job_queue = JobQueue(concurrency=1)
    incidents: list[SupervisorIncident] = []

    async def noop(job):
        return "ok"

    job_queue.start(noop)

    async def incident_checks() -> list[SupervisorIncident]:
        result = []
        status = job_queue.worker_status()
        if not status.get("running", False):
            result.append(SupervisorIncident(component="job_workers", reason="dead"))
        return result

    async def on_incident(incident: SupervisorIncident) -> None:
        incidents.append(incident)

    supervisor = RuntimeSupervisor(
        interval_s=0.05,
        cooldown_s=0.0,
        incident_checks=incident_checks,
        on_incident=on_incident,
    )
    await supervisor.run_once()
    await job_queue.stop()

    assert not any(i.component == "job_workers" for i in incidents)


@pytest.mark.asyncio
async def test_supervisor_recovers_job_workers():
    """Supervisor recovery handler restarts dead job workers."""
    from clawlite.jobs.queue import JobQueue
    from clawlite.runtime.supervisor import RuntimeSupervisor, SupervisorIncident

    job_queue = JobQueue(concurrency=1)
    recovery_called: list[str] = []

    async def noop(job):
        return "ok"

    async def incident_checks() -> list[SupervisorIncident]:
        status = job_queue.worker_status()
        if not status.get("running", False):
            return [SupervisorIncident(component="job_workers", reason="dead")]
        return []

    async def recover(component: str, reason: str) -> bool:
        if component == "job_workers":
            job_queue.start(noop)
            recovery_called.append(component)
            return job_queue.worker_status().get("running", False)
        return False

    supervisor = RuntimeSupervisor(
        interval_s=0.05,
        cooldown_s=0.0,
        incident_checks=incident_checks,
        recover=recover,
    )
    await supervisor.run_once()
    await job_queue.stop()

    assert "job_workers" in recovery_called
    assert supervisor.status()["recovery_success"] >= 1


@pytest.mark.asyncio
async def test_job_workers_started_on_queue_with_jobs():
    """Jobs submitted before start() execute after workers are started."""
    from clawlite.jobs.queue import JobQueue

    q = JobQueue(concurrency=1)
    j1 = q.submit("agent_run", {"val": "a"})
    j2 = q.submit("agent_run", {"val": "b"})

    assert q.worker_status()["running"] is False
    assert q.worker_status()["pending_jobs"] == 2

    async def worker(job):
        return f"done:{job.payload['val']}"

    q.start(worker)
    await asyncio.sleep(0.3)
    await q.stop()

    assert q.status(j1.id).status == "done"
    assert q.status(j2.id).status == "done"
