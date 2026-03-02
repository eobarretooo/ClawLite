from __future__ import annotations

import asyncio
from pathlib import Path

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

    asyncio.run(_scenario())
