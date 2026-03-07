from __future__ import annotations

import asyncio
import contextlib
import json
import os
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable
from zoneinfo import ZoneInfo

from loguru import logger

from clawlite.scheduler.types import CronJob, CronPayload, CronSchedule
from clawlite.utils.logging import bind_event, setup_logging

try:
    import fcntl
except Exception:  # pragma: no cover
    fcntl = None

try:
    from croniter import croniter
except Exception:  # pragma: no cover
    croniter = None


JobCallback = Callable[[CronJob], Awaitable[str | None]]
DEFAULT_CALLBACK_TIMEOUT_SECONDS = 300.0


class CronService:
    _LOOP_SLEEP_MIN_SECONDS = 0.05
    _LOOP_SLEEP_MAX_SECONDS = 5.0

    def __init__(
        self,
        store_path: str | Path | None = None,
        default_timezone: str = "UTC",
        lease_seconds: int = 30,
        callback_timeout_seconds: float = DEFAULT_CALLBACK_TIMEOUT_SECONDS,
    ) -> None:
        setup_logging()
        self.path = Path(store_path) if store_path else (Path.home() / ".clawlite" / "state" / "cron_jobs.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_path = self.path.with_name(f"{self.path.name}.lock")
        self._jobs: dict[str, CronJob] = {}
        self._task: asyncio.Task[Any] | None = None
        self._on_job: JobCallback | None = None
        self.default_timezone = self._normalize_timezone(default_timezone)
        self._instance_id = uuid.uuid4().hex
        self._lease_seconds = max(5, int(lease_seconds or 30))
        self._callback_timeout_seconds = max(0.1, float(callback_timeout_seconds or DEFAULT_CALLBACK_TIMEOUT_SECONDS))
        self._diag: dict[str, int | str] = {
            "load_attempts": 0,
            "load_success": 0,
            "load_failures": 0,
            "save_attempts": 0,
            "save_retries": 0,
            "save_failures": 0,
            "save_success": 0,
            "job_success_count": 0,
            "job_failure_count": 0,
            "schedule_error_count": 0,
            "lease_claimed": 0,
            "lease_skipped_active": 0,
            "lease_stale_recovered": 0,
            "lease_released_on_stop": 0,
            "lease_finalize_mismatch": 0,
            "lease_finalize_missing": 0,
            "last_load_error": "",
            "last_save_error": "",
        }
        self._load()

    def _task_snapshot(self) -> tuple[str, str]:
        task = self._task
        if task is None:
            return ("stopped", "")
        if task.cancelled():
            return ("cancelled", "")
        if not task.done():
            return ("running", "")
        try:
            exc = task.exception()
        except asyncio.CancelledError:
            return ("cancelled", "")
        if exc is not None:
            return ("failed", str(exc))
        return ("done", "")

    @staticmethod
    def _normalize_timezone(value: str | None) -> str:
        candidate = (value or "UTC").strip() or "UTC"
        try:
            ZoneInfo(candidate)
        except Exception as exc:
            raise ValueError(f"unknown timezone '{candidate}'") from exc
        return candidate

    def _load(self) -> None:
        self._diag["load_attempts"] = int(self._diag.get("load_attempts", 0) or 0) + 1
        try:
            with self._store_lock():
                self._jobs = self._read_jobs_unlocked()
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            self._diag["load_failures"] = int(self._diag.get("load_failures", 0) or 0) + 1
            self._diag["last_load_error"] = str(exc)
            bind_event("cron.state").error("cron load failed path={} error={}", self.path, exc)
            return
        self._diag["load_success"] = int(self._diag.get("load_success", 0) or 0) + 1
        self._diag["last_load_error"] = ""
        if self._jobs:
            logger.info("cron jobs loaded count={} path={}", len(self._jobs), self.path)

    def _save(self) -> None:
        items = [asdict(job) for job in self._jobs.values()]
        for attempt in range(2):
            self._diag["save_attempts"] = int(self._diag.get("save_attempts", 0) or 0) + 1
            if attempt > 0:
                self._diag["save_retries"] = int(self._diag.get("save_retries", 0) or 0) + 1
            try:
                with self._store_lock():
                    self._write_rows_unlocked(items)
            except OSError as exc:
                self._diag["save_failures"] = int(self._diag.get("save_failures", 0) or 0) + 1
                self._diag["last_save_error"] = str(exc)
                bind_event("cron.state").error("cron save failed attempt={} path={} error={}", attempt + 1, self.path, exc)
                if attempt == 0:
                    continue
                return
            self._diag["save_success"] = int(self._diag.get("save_success", 0) or 0) + 1
            self._diag["last_save_error"] = ""
            return

    async def _save_async(self) -> None:
        await asyncio.to_thread(self._save)

    @contextlib.contextmanager
    def _store_lock(self):
        fd: int | None = None
        lock_file = None
        try:
            lock_file = self._lock_path.open("a+", encoding="utf-8")
            fd = lock_file.fileno()
            if fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            if fd is not None and fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_UN)
            if lock_file is not None:
                lock_file.close()

    def _read_rows_unlocked(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and isinstance(raw.get("jobs"), list):
            rows = raw["jobs"]
        elif isinstance(raw, list):
            rows = raw
        else:
            raise ValueError("invalid_payload")
        out: list[dict[str, Any]] = []
        for row in rows:
            if isinstance(row, dict):
                out.append(row)
        return out

    def _read_jobs_unlocked(self) -> dict[str, CronJob]:
        jobs: dict[str, CronJob] = {}
        for row in self._read_rows_unlocked():
            job = self._job_from_row(row)
            if job is not None:
                jobs[job.id] = job
        return jobs

    def _write_rows_unlocked(self, rows: list[dict[str, Any]]) -> None:
        payload = json.dumps(rows, ensure_ascii=False, indent=2)
        tmp_path = self.path.with_name(f"{self.path.name}.{os.getpid()}.tmp")
        with tmp_path.open("w", encoding="utf-8") as tmp_file:
            tmp_file.write(payload)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        os.replace(tmp_path, self.path)
        dir_fd: int | None = None
        try:
            dir_fd = os.open(self.path.parent, os.O_RDONLY)
            os.fsync(dir_fd)
        except OSError:
            pass
        finally:
            if dir_fd is not None:
                os.close(dir_fd)

    def _job_from_row(self, row: dict[str, Any]) -> CronJob | None:
        try:
            schedule = CronSchedule(**row["schedule"])
            schedule.timezone = self._normalize_timezone(schedule.timezone or self.default_timezone)
            payload = CronPayload(**row["payload"])
            return CronJob(
                id=row["id"],
                name=row["name"],
                session_id=row["session_id"],
                schedule=schedule,
                payload=payload,
                enabled=bool(row.get("enabled", True)),
                next_run_iso=str(row.get("next_run_iso", "")),
                last_run_iso=str(row.get("last_run_iso", "")),
                last_status=str(row.get("last_status", "idle") or "idle"),
                last_error=str(row.get("last_error", "") or ""),
                consecutive_failures=int(row.get("consecutive_failures", 0) or 0),
                run_count=int(row.get("run_count", 0) or 0),
                lease_token=str(row.get("lease_token", "") or ""),
                lease_owner=str(row.get("lease_owner", "") or ""),
                lease_expires_iso=str(row.get("lease_expires_iso", "") or ""),
                lease_claimed_iso=str(row.get("lease_claimed_iso", "") or ""),
            )
        except Exception:
            return None

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _compute_next(schedule: CronSchedule, now: datetime) -> datetime | None:
        tz_name = (schedule.timezone or "UTC").strip() or "UTC"
        tz = ZoneInfo(tz_name)
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
                dt = dt.replace(tzinfo=tz)
            return dt.astimezone(timezone.utc)
        if schedule.kind == "cron":
            if croniter is None:
                raise RuntimeError("croniter is required for cron expressions")
            if not schedule.cron_expr.strip():
                return None
            base = now.astimezone(tz)
            next_local = croniter(schedule.cron_expr, base).get_next(datetime)
            if next_local.tzinfo is None:
                next_local = next_local.replace(tzinfo=tz)
            return next_local.astimezone(timezone.utc)
        return None

    async def start(self, on_job: JobCallback) -> None:
        self._on_job = on_job
        if self._task is not None:
            task_state, _task_error = self._task_snapshot()
            if task_state in {"failed", "cancelled", "done"}:
                self._task = None
            else:
                return
        self._task = asyncio.create_task(self._loop())
        logger.info("cron service started path={}", self.path)

    async def stop(self) -> None:
        if self._task is None:
            return
        bind_event("cron.lifecycle").info("cron service stopping")
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        released = await asyncio.to_thread(self._release_owned_leases)
        if released:
            bind_event("cron.lifecycle").warning("cron stop released_owned_leases count={}", released)
        bind_event("cron.lifecycle").info("cron service stopped")

    def status(self) -> dict[str, Any]:
        task_state, task_error = self._task_snapshot()
        return {
            "running": task_state == "running",
            "worker_state": task_state,
            "jobs": len(self._jobs),
            "store_path": str(self.path),
            "default_timezone": self.default_timezone,
            "load_attempts": int(self._diag.get("load_attempts", 0) or 0),
            "load_success": int(self._diag.get("load_success", 0) or 0),
            "load_failures": int(self._diag.get("load_failures", 0) or 0),
            "save_attempts": int(self._diag.get("save_attempts", 0) or 0),
            "save_retries": int(self._diag.get("save_retries", 0) or 0),
            "save_failures": int(self._diag.get("save_failures", 0) or 0),
            "save_success": int(self._diag.get("save_success", 0) or 0),
            "job_success_count": int(self._diag.get("job_success_count", 0) or 0),
            "job_failure_count": int(self._diag.get("job_failure_count", 0) or 0),
            "schedule_error_count": int(self._diag.get("schedule_error_count", 0) or 0),
            "lease_claimed": int(self._diag.get("lease_claimed", 0) or 0),
            "lease_skipped_active": int(self._diag.get("lease_skipped_active", 0) or 0),
            "lease_stale_recovered": int(self._diag.get("lease_stale_recovered", 0) or 0),
            "lease_released_on_stop": int(self._diag.get("lease_released_on_stop", 0) or 0),
            "lease_finalize_mismatch": int(self._diag.get("lease_finalize_mismatch", 0) or 0),
            "lease_finalize_missing": int(self._diag.get("lease_finalize_missing", 0) or 0),
            "last_load_error": str(self._diag.get("last_load_error", "") or ""),
            "last_save_error": str(self._diag.get("last_save_error", "") or ""),
            "last_error": task_error,
        }

    def _mark_schedule_error(self, job: CronJob, exc: Exception) -> None:
        job.last_status = "schedule_error"
        job.last_error = str(exc)
        job.consecutive_failures = int(job.consecutive_failures or 0) + 1
        self._diag["schedule_error_count"] = int(self._diag.get("schedule_error_count", 0) or 0) + 1
        bind_event("cron.job", session=job.session_id).error("cron schedule error id={} error={}", job.id, exc)

    @staticmethod
    def _normalize_datetime(value: str) -> datetime:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    def _is_lease_active(self, job: CronJob, now: datetime) -> bool:
        if not job.lease_token or not job.lease_expires_iso:
            return False
        try:
            expires = self._normalize_datetime(job.lease_expires_iso)
        except ValueError:
            return False
        return expires > now

    def _clear_lease(self, job: CronJob) -> None:
        job.lease_token = ""
        job.lease_owner = ""
        job.lease_expires_iso = ""
        job.lease_claimed_iso = ""

    def _release_owned_leases(self) -> int:
        released = 0
        with self._store_lock():
            jobs = self._read_jobs_unlocked()
            changed = False
            for job in jobs.values():
                if str(job.lease_owner or "") != self._instance_id or not str(job.lease_token or ""):
                    continue
                self._clear_lease(job)
                if not str(job.last_status or "").strip() or job.last_status == "idle":
                    job.last_status = "interrupted"
                job.last_error = "service_stopped_before_commit"
                jobs[job.id] = job
                released += 1
                changed = True
            if changed:
                self._write_rows_unlocked([asdict(item) for item in jobs.values()])
                self._jobs = jobs
            else:
                self._jobs = jobs
        if released:
            self._diag["lease_released_on_stop"] = int(self._diag.get("lease_released_on_stop", 0) or 0) + released
        return released

    def _try_claim_due_job(self, job_id: str, now: datetime) -> CronJob | None:
        token = uuid.uuid4().hex
        claimed: CronJob | None = None
        with self._store_lock():
            jobs = self._read_jobs_unlocked()
            job = jobs.get(job_id)
            if job is None:
                self._diag["lease_finalize_missing"] = int(self._diag.get("lease_finalize_missing", 0) or 0) + 1
                self._jobs = jobs
                return None
            if not job.enabled or not job.next_run_iso:
                self._jobs = jobs
                return None
            try:
                next_run = self._normalize_datetime(job.next_run_iso)
            except ValueError:
                self._jobs = jobs
                return None
            if next_run > now:
                self._jobs = jobs
                return None
            stale_recovered = False
            if self._is_lease_active(job, now):
                self._diag["lease_skipped_active"] = int(self._diag.get("lease_skipped_active", 0) or 0) + 1
                self._jobs = jobs
                return None
            if job.lease_token and job.lease_expires_iso:
                stale_recovered = True
            job.lease_token = token
            job.lease_owner = self._instance_id
            job.lease_claimed_iso = now.isoformat()
            job.lease_expires_iso = (now + timedelta(seconds=self._lease_seconds)).isoformat()
            jobs[job.id] = job
            self._write_rows_unlocked([asdict(item) for item in jobs.values()])
            self._jobs = jobs
            claimed = job
        self._diag["lease_claimed"] = int(self._diag.get("lease_claimed", 0) or 0) + 1
        if stale_recovered:
            self._diag["lease_stale_recovered"] = int(self._diag.get("lease_stale_recovered", 0) or 0) + 1
        return claimed

    def _commit_job_result(
        self,
        *,
        job_id: str,
        lease_token: str,
        now: datetime,
        callback_failed: bool,
        claimed_job: CronJob,
    ) -> bool:
        committed = False
        with self._store_lock():
            jobs = self._read_jobs_unlocked()
            job = jobs.get(job_id)
            if job is None:
                self._diag["lease_finalize_missing"] = int(self._diag.get("lease_finalize_missing", 0) or 0) + 1
                self._jobs = jobs
                return False
            if job.lease_token != lease_token:
                self._diag["lease_finalize_mismatch"] = int(self._diag.get("lease_finalize_mismatch", 0) or 0) + 1
                self._jobs = jobs
                return False
            job.last_status = claimed_job.last_status
            job.last_error = claimed_job.last_error
            job.consecutive_failures = int(claimed_job.consecutive_failures or 0)
            job.run_count = int(job.run_count or 0) + 1
            if callback_failed:
                try:
                    after_failed = self._compute_next(job.schedule, now)
                    job.next_run_iso = after_failed.isoformat() if after_failed else ""
                except Exception as exc:
                    self._mark_schedule_error(job, exc)
                    job.next_run_iso = ""
                self._clear_lease(job)
                jobs[job.id] = job
                self._write_rows_unlocked([asdict(item) for item in jobs.values()])
                self._jobs = jobs
                return True
            job.last_run_iso = now.isoformat()
            run_once = bool(job.payload.metadata.get("run_once"))
            if run_once:
                jobs.pop(job.id, None)
                bind_event("cron.job", session=job.session_id).info("cron job auto-removed after run_once id={}", job.id)
                self._write_rows_unlocked([asdict(item) for item in jobs.values()])
                self._jobs = jobs
                return True
            try:
                after = self._compute_next(job.schedule, now)
            except Exception as exc:
                self._mark_schedule_error(job, exc)
                after = None
            if job.schedule.kind == "at":
                job.enabled = False
                job.next_run_iso = ""
            else:
                job.next_run_iso = after.isoformat() if after else ""
            self._clear_lease(job)
            jobs[job.id] = job
            self._write_rows_unlocked([asdict(item) for item in jobs.values()])
            self._jobs = jobs
            committed = True
        return committed

    def _compute_loop_sleep_seconds(self, now: datetime) -> float:
        nearest_delta: float | None = None
        for job in self._jobs.values():
            if not job.enabled or not job.next_run_iso:
                continue
            try:
                next_run = self._normalize_datetime(job.next_run_iso)
            except ValueError:
                continue
            delta_s = (next_run - now).total_seconds()
            if nearest_delta is None or delta_s < nearest_delta:
                nearest_delta = delta_s

        if nearest_delta is None:
            return self._LOOP_SLEEP_MAX_SECONDS

        bounded = max(self._LOOP_SLEEP_MIN_SECONDS, min(self._LOOP_SLEEP_MAX_SECONDS, nearest_delta))
        return float(bounded)

    async def _loop(self) -> None:
        while True:
            now = self._now()
            changed = False
            for job in list(self._jobs.values()):
                if not job.enabled:
                    continue
                if not job.next_run_iso:
                    try:
                        next_dt = self._compute_next(job.schedule, now)
                    except Exception as exc:
                        self._mark_schedule_error(job, exc)
                        changed = True
                        continue
                    job.next_run_iso = next_dt.isoformat() if next_dt else ""
                    changed = True
                if not job.next_run_iso:
                    continue
                try:
                    next_run = self._normalize_datetime(job.next_run_iso)
                except ValueError as exc:
                    self._mark_schedule_error(job, exc)
                    job.next_run_iso = ""
                    changed = True
                    continue
                if next_run > now:
                    continue
                claimed = await asyncio.to_thread(self._try_claim_due_job, job.id, now)
                if claimed is None:
                    continue
                callback_failed = False
                if self._on_job is not None:
                    logger.info("cron job executing id={} session={} name={}", claimed.id, claimed.session_id, claimed.name)
                    try:
                        await asyncio.wait_for(self._on_job(claimed), timeout=self._callback_timeout_seconds)
                        logger.info("cron job executed id={} session={}", claimed.id, claimed.session_id)
                        claimed.last_status = "success"
                        claimed.last_error = ""
                        claimed.consecutive_failures = 0
                        self._diag["job_success_count"] = int(self._diag.get("job_success_count", 0) or 0) + 1
                    except asyncio.CancelledError:
                        raise
                    except asyncio.TimeoutError:
                        callback_failed = True
                        claimed.last_status = "failed"
                        claimed.last_error = f"callback_timeout after {self._callback_timeout_seconds}s"
                        claimed.consecutive_failures = int(claimed.consecutive_failures or 0) + 1
                        self._diag["job_failure_count"] = int(self._diag.get("job_failure_count", 0) or 0) + 1
                        logger.error(
                            "cron job timed out id={} session={} timeout={}s",
                            claimed.id,
                            claimed.session_id,
                            self._callback_timeout_seconds,
                        )
                    except Exception as exc:
                        callback_failed = True
                        claimed.last_status = "failed"
                        claimed.last_error = str(exc)
                        claimed.consecutive_failures = int(claimed.consecutive_failures or 0) + 1
                        self._diag["job_failure_count"] = int(self._diag.get("job_failure_count", 0) or 0) + 1
                        logger.error("cron job failed id={} session={} error={}", claimed.id, claimed.session_id, exc)
                committed = await asyncio.to_thread(
                    self._commit_job_result,
                    job_id=claimed.id,
                    lease_token=claimed.lease_token,
                    now=now,
                    callback_failed=callback_failed,
                    claimed_job=claimed,
                )
                if not committed:
                    continue
            if changed:
                await asyncio.to_thread(self._save)
            sleep_seconds = self._compute_loop_sleep_seconds(self._now())
            await asyncio.sleep(sleep_seconds)

    def list_jobs(self, *, session_id: str | None = None) -> list[dict[str, Any]]:
        rows = list(self._jobs.values())
        if session_id:
            rows = [item for item in rows if item.session_id == session_id]
        out: list[dict[str, Any]] = []
        for item in sorted(rows, key=lambda j: j.name):
            row = asdict(item)
            row["expression"] = self._schedule_to_expression(item.schedule)
            row["timezone"] = item.schedule.timezone
            out.append(row)
        return out

    async def add_job(
        self,
        *,
        session_id: str,
        expression: str,
        prompt: str,
        name: str = "",
        timezone_name: str | None = None,
        channel: str = "",
        target: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        schedule = self._parse_expression(expression, timezone_name=timezone_name)
        now = self._now()
        next_run = self._compute_next(schedule, now)
        job_id = uuid.uuid4().hex
        job = CronJob(
            id=job_id,
            name=name or f"job-{job_id[:8]}",
            session_id=session_id,
            schedule=schedule,
            payload=CronPayload(prompt=prompt, channel=channel, target=target, metadata=metadata or {}),
            next_run_iso=next_run.isoformat() if next_run else "",
        )
        self._jobs[job_id] = job
        await self._save_async()
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
            bind_event("cron.job").info("cron job removed id={}", job_id)
        return existed

    def enable_job(self, job_id: str, *, enabled: bool) -> bool:
        job = self._jobs.get(job_id)
        if job is None:
            return False
        job.enabled = enabled
        if enabled and not job.next_run_iso:
            next_dt = self._compute_next(job.schedule, self._now())
            job.next_run_iso = next_dt.isoformat() if next_dt else ""
        self._save()
        bind_event("cron.job").info("cron job updated id={} enabled={}", job_id, enabled)
        return True

    def get_job(self, job_id: str) -> CronJob | None:
        return self._jobs.get(job_id)

    async def run_job(self, job_id: str, *, on_job: JobCallback | None = None, force: bool = False) -> str | None:
        job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(job_id)
        if not job.enabled and not force:
            raise RuntimeError("cron_job_disabled")
        callback = on_job or self._on_job
        if callback is None:
            raise RuntimeError("cron_job_callback_missing")
        job.run_count = int(job.run_count or 0) + 1
        try:
            out = await asyncio.wait_for(callback(job), timeout=self._callback_timeout_seconds)
            job.last_status = "success"
            job.last_error = ""
            job.consecutive_failures = 0
            self._diag["job_success_count"] = int(self._diag.get("job_success_count", 0) or 0) + 1
        except asyncio.TimeoutError as exc:
            timeout_error = f"callback_timeout after {self._callback_timeout_seconds}s"
            job.last_status = "failed"
            job.last_error = timeout_error
            job.consecutive_failures = int(job.consecutive_failures or 0) + 1
            self._clear_lease(job)
            self._diag["job_failure_count"] = int(self._diag.get("job_failure_count", 0) or 0) + 1
            await self._save_async()
            raise TimeoutError(timeout_error) from exc
        except Exception as exc:
            job.last_status = "failed"
            job.last_error = str(exc)
            job.consecutive_failures = int(job.consecutive_failures or 0) + 1
            self._clear_lease(job)
            self._diag["job_failure_count"] = int(self._diag.get("job_failure_count", 0) or 0) + 1
            await self._save_async()
            raise
        now = self._now()
        job.last_run_iso = now.isoformat()
        self._clear_lease(job)
        run_once = bool(job.payload.metadata.get("run_once"))
        if run_once:
            self._jobs.pop(job.id, None)
            await self._save_async()
            bind_event("cron.job", session=job.session_id).info("cron job manually auto-removed after run_once id={}", job.id)
            return out
        try:
            after = self._compute_next(job.schedule, now)
        except Exception as exc:
            self._mark_schedule_error(job, exc)
            after = None
        if job.schedule.kind == "at":
            job.enabled = False
            job.next_run_iso = ""
        else:
            job.next_run_iso = after.isoformat() if after else ""
        await self._save_async()
        bind_event("cron.job", session=job.session_id).info("cron job manually executed id={} enabled={}", job.id, job.enabled)
        return out

    def _schedule_to_expression(self, schedule: CronSchedule) -> str:
        if schedule.kind == "every":
            return f"every {max(1, int(schedule.every_seconds or 1))}"
        if schedule.kind == "at":
            return f"at {schedule.run_at_iso}"
        return schedule.cron_expr

    def _parse_expression(self, expression: str, *, timezone_name: str | None = None) -> CronSchedule:
        expr = expression.strip()
        tz_name = self._normalize_timezone(timezone_name or self.default_timezone)
        if expr.startswith("every "):
            raw = expr.split(" ", 1)[1].strip().lower()
            if raw.endswith("s"):
                raw = raw[:-1]
            return CronSchedule(kind="every", every_seconds=max(1, int(raw)), timezone=tz_name)
        if expr.startswith("at "):
            return CronSchedule(kind="at", run_at_iso=expr.split(" ", 1)[1].strip(), timezone=tz_name)
        return CronSchedule(kind="cron", cron_expr=expr, timezone=tz_name)
