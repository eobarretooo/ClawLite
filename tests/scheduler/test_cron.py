from __future__ import annotations

import asyncio
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
