from __future__ import annotations

import asyncio
import contextlib
from contextlib import contextmanager
import logging
import sqlite3
import threading
import time
from dataclasses import dataclass
from typing import Any, Iterator

from clawlite.runtime import multiagent
from clawlite.runtime.notifications import create_notification

logger = logging.getLogger(__name__)


@dataclass
class CronJobRow:
    id: int
    channel: str
    chat_id: str
    thread_id: str
    label: str
    name: str
    text: str
    interval_seconds: int
    enabled: int
    last_run_at: float | None
    next_run_at: float
    last_result: str
    created_at: float
    updated_at: float


@dataclass
class CronRunResult:
    job_id: int
    status: str
    task_id: int | None
    message: str


def _now() -> float:
    return time.time()


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    db_path = multiagent.current_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=3000")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_cron_db() -> None:
    multiagent.init_db()
    with _conn() as c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS conversation_cron_jobs (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              channel TEXT NOT NULL,
              chat_id TEXT NOT NULL,
              thread_id TEXT NOT NULL DEFAULT '',
              label TEXT NOT NULL,
              name TEXT NOT NULL,
              text TEXT NOT NULL,
              interval_seconds INTEGER NOT NULL,
              enabled INTEGER NOT NULL DEFAULT 1,
              last_run_at REAL,
              next_run_at REAL NOT NULL,
              last_result TEXT NOT NULL DEFAULT '',
              created_at REAL NOT NULL,
              updated_at REAL NOT NULL,
              UNIQUE(channel, chat_id, thread_id, label, name)
            )
            """
        )


def _row_to_job(row: sqlite3.Row) -> CronJobRow:
    return CronJobRow(**dict(row))


def add_cron_job(
    channel: str,
    chat_id: str,
    thread_id: str,
    label: str,
    name: str,
    text: str,
    interval_seconds: int,
    enabled: bool = True,
) -> int:
    init_cron_db()
    interval = int(interval_seconds)
    if interval <= 0:
        raise ValueError("interval_seconds deve ser maior que 0")

    ts = _now()
    with _conn() as c:
        c.execute(
            """
            INSERT INTO conversation_cron_jobs
            (channel, chat_id, thread_id, label, name, text, interval_seconds, enabled, next_run_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(channel, chat_id, thread_id, label, name)
            DO UPDATE SET text=excluded.text,
                          interval_seconds=excluded.interval_seconds,
                          enabled=excluded.enabled,
                          updated_at=excluded.updated_at
            """,
            (
                channel,
                chat_id,
                thread_id or "",
                label,
                name,
                text,
                interval,
                1 if enabled else 0,
                ts + interval,
                ts,
                ts,
            ),
        )
        row = c.execute(
            "SELECT id FROM conversation_cron_jobs WHERE channel=? AND chat_id=? AND thread_id=? AND label=? AND name=?",
            (channel, chat_id, thread_id or "", label, name),
        ).fetchone()
    return int(row["id"])


def list_cron_jobs(
    channel: str | None = None,
    chat_id: str | None = None,
    thread_id: str | None = None,
    label: str | None = None,
) -> list[CronJobRow]:
    init_cron_db()
    query = "SELECT * FROM conversation_cron_jobs"
    where: list[str] = []
    params: list[Any] = []

    if channel is not None:
        where.append("channel=?")
        params.append(channel)
    if chat_id is not None:
        where.append("chat_id=?")
        params.append(chat_id)
    if thread_id is not None:
        where.append("thread_id=?")
        params.append(thread_id)
    if label is not None:
        where.append("label=?")
        params.append(label)

    if where:
        query += " WHERE " + " AND ".join(where)
    query += " ORDER BY channel, chat_id, thread_id, label, name"

    with _conn() as c:
        rows = c.execute(query, tuple(params)).fetchall()
    return [_row_to_job(r) for r in rows]


def remove_cron_job(job_id: int) -> bool:
    init_cron_db()
    with _conn() as c:
        cur = c.execute("DELETE FROM conversation_cron_jobs WHERE id=?", (int(job_id),))
    return cur.rowcount == 1


def _select_runnable_jobs(job_id: int | None, run_all: bool, now_ts: float) -> list[CronJobRow]:
    if job_id is not None:
        with _conn() as c:
            row = c.execute("SELECT * FROM conversation_cron_jobs WHERE id=?", (int(job_id),)).fetchone()
        return [_row_to_job(row)] if row else []

    if run_all:
        with _conn() as c:
            rows = c.execute("SELECT * FROM conversation_cron_jobs WHERE enabled=1 ORDER BY id ASC").fetchall()
        return [_row_to_job(r) for r in rows]

    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM conversation_cron_jobs WHERE enabled=1 AND next_run_at <= ? ORDER BY id ASC",
            (now_ts,),
        ).fetchall()
    return [_row_to_job(r) for r in rows]


def run_cron_jobs(job_id: int | None = None, run_all: bool = False) -> list[CronRunResult]:
    init_cron_db()
    now_ts = _now()
    jobs = _select_runnable_jobs(job_id, run_all, now_ts)
    results: list[CronRunResult] = []

    for job in jobs:
        payload = {
            "channel": job.channel,
            "chat_id": job.chat_id,
            "thread_id": job.thread_id,
            "label": job.label,
            "text": job.text,
            "source": "cron",
            "cron_job_id": job.id,
            "cron_name": job.name,
        }

        status = "enqueued"
        task_id: int | None = None
        message = "ok"
        try:
            if job.channel == "system" and job.label == "skills" and job.name == "auto-update":
                from clawlite.skills.marketplace import run_runtime_auto_update

                run_result = run_runtime_auto_update(job.text)
                updated_count = len(run_result.get("updated", []))
                blocked_count = len(run_result.get("blocked", []))
                status = "executed"
                message = f"updated={updated_count}, blocked={blocked_count}"
                last_result = f"runtime:{message}"
            else:
                task_id = multiagent.enqueue_task(job.channel, job.chat_id, job.thread_id, job.label, payload)
                last_result = f"task:{task_id}"
        except Exception as exc:
            status = "failed"
            message = str(exc)
            last_result = f"error:{message}"

        next_run = now_ts + int(job.interval_seconds)
        with _conn() as c:
            c.execute(
                """
                UPDATE conversation_cron_jobs
                SET last_run_at=?, next_run_at=?, last_result=?, updated_at=?
                WHERE id=?
                """,
                (now_ts, next_run, last_result[:4000], now_ts, job.id),
            )

        dedupe_window = int(job.interval_seconds) if int(job.interval_seconds) > 0 else 60
        is_ok = status in {"enqueued", "executed"}
        create_notification(
            event=f"cron_{status}",
            message=(f"Cron job {job.name} -> {status} ({message})" if is_ok else f"Cron job {job.name} falhou: {message}"),
            priority=("low" if is_ok else "high"),
            dedupe_key=(f"cron:{status}:{job.id}" if is_ok else f"cron:failed:{job.id}:{message}"),
            dedupe_window_seconds=min(dedupe_window, 600),
            channel=job.channel,
            chat_id=job.chat_id,
            thread_id=job.thread_id,
            label=job.label,
            metadata={"cron_job_id": job.id, "task_id": task_id},
        )

        results.append(CronRunResult(job_id=job.id, status=status, task_id=task_id, message=message))

    return results


class ConversationCronScheduler:
    """Scheduler em loop para disparo automático de jobs cron."""

    def __init__(self, poll_interval_s: float = 5.0) -> None:
        try:
            interval = float(poll_interval_s)
        except (TypeError, ValueError):
            interval = 5.0
        self.poll_interval_s = max(1.0, interval)
        self._stop_event = threading.Event()
        self._run_lock = threading.Lock()

    def run_pending_once(self) -> list[CronRunResult]:
        """Executa apenas jobs devidos; evita sobreposição de execução."""
        if not self._run_lock.acquire(blocking=False):
            return []
        try:
            return run_cron_jobs(run_all=False)
        finally:
            self._run_lock.release()

    def start(self) -> None:
        logger.info("cron-scheduler: iniciado (poll_interval_s=%.1f)", self.poll_interval_s)
        while not self._stop_event.is_set():
            try:
                self.run_pending_once()
            except Exception as exc:
                logger.warning("cron-scheduler: erro no ciclo: %s", exc)
            self._stop_event.wait(self.poll_interval_s)
        logger.info("cron-scheduler: encerrado")

    def stop(self) -> None:
        self._stop_event.set()


def start_cron_scheduler_thread(poll_interval_s: float = 5.0) -> ConversationCronScheduler:
    """Inicia o scheduler cron em thread daemon."""
    scheduler = ConversationCronScheduler(poll_interval_s=poll_interval_s)
    thread = threading.Thread(target=scheduler.start, name="clawlite-cron-scheduler", daemon=True)
    thread.start()
    return scheduler


class AsyncConversationCronScheduler:
    """Versão assíncrona do scheduler cron para runtime principal."""

    def __init__(self, poll_interval_s: float = 5.0) -> None:
        try:
            interval = float(poll_interval_s)
        except (TypeError, ValueError):
            interval = 5.0
        self.poll_interval_s = max(1.0, interval)
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    async def run_pending_once(self) -> list[CronRunResult]:
        return await asyncio.to_thread(run_cron_jobs, run_all=False)

    async def _run_loop(self) -> None:
        logger.info("cron-scheduler(async): iniciado (poll_interval_s=%.1f)", self.poll_interval_s)
        while not self._stop_event.is_set():
            try:
                await self.run_pending_once()
            except Exception as exc:
                logger.warning("cron-scheduler(async): erro no ciclo: %s", exc)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.poll_interval_s)
            except asyncio.TimeoutError:
                pass
        logger.info("cron-scheduler(async): encerrado")

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop(), name="clawlite-cron-scheduler-async")

    async def stop(self) -> None:
        self._stop_event.set()
        task = self._task
        self._task = None
        if task is not None:
            with contextlib.suppress(Exception):
                await task


def format_cron_jobs_table(rows: list[CronJobRow]) -> str:
    if not rows:
        return "(sem cron jobs)"

    lines = ["id | canal | chat | thread | label | nome | intervalo(s) | enabled | próxima execução"]
    for item in rows:
        lines.append(
            f"{item.id} | {item.channel} | {item.chat_id} | {item.thread_id or '-'} | {item.label} | "
            f"{item.name} | {item.interval_seconds} | {item.enabled} | {int(item.next_run_at)}"
        )
    return "\n".join(lines)


def format_cron_run_results(rows: list[CronRunResult]) -> str:
    if not rows:
        return "(nenhum job executado)"

    lines = ["job | status | task | detalhe"]
    for item in rows:
        lines.append(f"{item.job_id} | {item.status} | {item.task_id or '-'} | {item.message}")
    return "\n".join(lines)
