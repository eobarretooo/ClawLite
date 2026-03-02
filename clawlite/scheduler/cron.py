from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from loguru import logger

from clawlite.scheduler.types import CronJob, CronPayload, CronSchedule
from clawlite.utils.logging import setup_logging

setup_logging()

try:
    from croniter import croniter
except Exception:  # pragma: no cover
    croniter = None


JobCallback = Callable[[CronJob], Awaitable[str | None]]


class CronService:
    def __init__(self, store_path: str | Path | None = None) -> None:
        self.path = Path(store_path) if store_path else (Path.home() / ".clawlite" / "state" / "cron_jobs.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._jobs: dict[str, CronJob] = {}
        self._task: asyncio.Task[Any] | None = None
        self._on_job: JobCallback | None = None
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        if not isinstance(data, list):
            return
        for row in data:
            try:
                schedule = CronSchedule(**row["schedule"])
                payload = CronPayload(**row["payload"])
                job = CronJob(
                    id=row["id"],
                    name=row["name"],
                    session_id=row["session_id"],
                    schedule=schedule,
                    payload=payload,
                    enabled=bool(row.get("enabled", True)),
                    next_run_iso=str(row.get("next_run_iso", "")),
                    last_run_iso=str(row.get("last_run_iso", "")),
                )
            except Exception:
                continue
            self._jobs[job.id] = job
        if self._jobs:
            logger.info("cron jobs loaded count={} path={}", len(self._jobs), self.path)

    def _save(self) -> None:
        items = [asdict(job) for job in self._jobs.values()]
        self.path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _compute_next(schedule: CronSchedule, now: datetime) -> datetime | None:
        if schedule.kind == "every":
            seconds = max(1, int(schedule.every_seconds or 1))
            return now + timedelta(seconds=seconds)
        if schedule.kind == "at":
            if not schedule.run_at_iso:
                return None
            try:
                dt = datetime.fromisoformat(schedule.run_at_iso)
            except ValueError:
                return None
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        if schedule.kind == "cron":
            if croniter is None:
                raise RuntimeError("croniter is required for cron expressions")
            if not schedule.cron_expr.strip():
                return None
            return croniter(schedule.cron_expr, now).get_next(datetime)
        return None

    async def start(self, on_job: JobCallback) -> None:
        self._on_job = on_job
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._loop())
        logger.info("cron service started path={}", self.path)

    async def stop(self) -> None:
        if self._task is None:
            return
        logger.info("cron service stopping")
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        logger.info("cron service stopped")

    async def _loop(self) -> None:
        while True:
            now = self._now()
            changed = False
            for job in self._jobs.values():
                if not job.enabled:
                    continue
                if not job.next_run_iso:
                    next_dt = self._compute_next(job.schedule, now)
                    job.next_run_iso = next_dt.isoformat() if next_dt else ""
                    changed = True
                if not job.next_run_iso:
                    continue
                next_run = datetime.fromisoformat(job.next_run_iso)
                if next_run.tzinfo is None:
                    next_run = next_run.replace(tzinfo=timezone.utc)
                if next_run > now:
                    continue
                if self._on_job is not None:
                    logger.info("cron job executing id={} session={} name={}", job.id, job.session_id, job.name)
                    try:
                        await self._on_job(job)
                        logger.info("cron job executed id={} session={}", job.id, job.session_id)
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        logger.error("cron job failed id={} session={} error={}", job.id, job.session_id, exc)
                job.last_run_iso = now.isoformat()
                after = self._compute_next(job.schedule, now)
                # one-shot jobs (at) disable after first run
                if job.schedule.kind == "at":
                    job.enabled = False
                    job.next_run_iso = ""
                else:
                    job.next_run_iso = after.isoformat() if after else ""
                changed = True
            if changed:
                self._save()
            await asyncio.sleep(1)

    def list_jobs(self, *, session_id: str | None = None) -> list[dict[str, Any]]:
        rows = list(self._jobs.values())
        if session_id:
            rows = [item for item in rows if item.session_id == session_id]
        return [asdict(item) for item in sorted(rows, key=lambda j: j.name)]

    async def add_job(self, *, session_id: str, expression: str, prompt: str, name: str = "") -> str:
        schedule = self._parse_expression(expression)
        now = self._now()
        next_run = self._compute_next(schedule, now)
        job_id = uuid.uuid4().hex
        job = CronJob(
            id=job_id,
            name=name or f"job-{job_id[:8]}",
            session_id=session_id,
            schedule=schedule,
            payload=CronPayload(prompt=prompt),
            next_run_iso=next_run.isoformat() if next_run else "",
        )
        self._jobs[job_id] = job
        self._save()
        logger.info(
            "cron job created id={} session={} schedule_kind={} name={}",
            job_id,
            session_id,
            schedule.kind,
            job.name,
        )
        return job_id

    def remove_job(self, job_id: str) -> bool:
        existed = job_id in self._jobs
        self._jobs.pop(job_id, None)
        if existed:
            self._save()
            logger.info("cron job removed id={}", job_id)
        return existed

    @staticmethod
    def _parse_expression(expression: str) -> CronSchedule:
        expr = expression.strip()
        if expr.startswith("every "):
            raw = expr.split(" ", 1)[1].strip().lower()
            if raw.endswith("s"):
                raw = raw[:-1]
            return CronSchedule(kind="every", every_seconds=max(1, int(raw)))
        if expr.startswith("at "):
            return CronSchedule(kind="at", run_at_iso=expr.split(" ", 1)[1].strip())
        return CronSchedule(kind="cron", cron_expr=expr)
