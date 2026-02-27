from __future__ import annotations

import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from clawlite.runtime.battery import effective_poll_seconds, get_battery_mode
from clawlite.runtime.voice import send_telegram_audio_reply, synthesize_tts

DB_DIR = Path.home() / ".clawlite"
DB_PATH = DB_DIR / "multiagent.db"
POLL_SECONDS = 2.0


@dataclass
class WorkerRow:
    id: int
    channel: str
    chat_id: str
    thread_id: str
    label: str
    command_template: str
    enabled: int
    pid: int | None
    status: str
    created_at: float
    updated_at: float


def _now() -> float:
    return time.time()


def _conn() -> sqlite3.Connection:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=3000")
    return conn


def init_db() -> None:
    with _conn() as c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS workers (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              channel TEXT NOT NULL,
              chat_id TEXT NOT NULL,
              thread_id TEXT NOT NULL DEFAULT '',
              label TEXT NOT NULL,
              command_template TEXT NOT NULL,
              enabled INTEGER NOT NULL DEFAULT 1,
              pid INTEGER,
              status TEXT NOT NULL DEFAULT 'stopped',
              created_at REAL NOT NULL,
              updated_at REAL NOT NULL,
              UNIQUE(channel, chat_id, thread_id, label)
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              channel TEXT NOT NULL,
              chat_id TEXT NOT NULL,
              thread_id TEXT NOT NULL DEFAULT '',
              label TEXT NOT NULL,
              payload TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'queued',
              result TEXT,
              worker_id INTEGER,
              created_at REAL NOT NULL,
              updated_at REAL NOT NULL
            )
            """
        )


def _pid_state(pid: int) -> str | None:
    """Return Linux process state letter from /proc/<pid>/status (e.g. R/S/Z).

    Returns None when unavailable (non-Linux, permission denied, missing proc entry).
    """
    try:
        with open(f"/proc/{pid}/status", "r", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("State:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        return parts[1].upper()
                    return None
    except OSError:
        return None
    return None


def _is_pid_running(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False

    # Zombie/defunct process must be treated as unhealthy so recovery can restart.
    state = _pid_state(pid)
    if state == "Z":
        return False
    return True


def _row_to_worker(row: sqlite3.Row) -> WorkerRow:
    return WorkerRow(**dict(row))


def upsert_worker(
    channel: str,
    chat_id: str,
    thread_id: str,
    label: str,
    command_template: str,
    enabled: bool = True,
) -> int:
    init_db()
    ts = _now()
    with _conn() as c:
        c.execute(
            """
            INSERT INTO workers (channel, chat_id, thread_id, label, command_template, enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(channel, chat_id, thread_id, label)
            DO UPDATE SET command_template=excluded.command_template,
                          enabled=excluded.enabled,
                          updated_at=excluded.updated_at
            """,
            (channel, chat_id, thread_id or "", label, command_template, 1 if enabled else 0, ts, ts),
        )
        row = c.execute(
            "SELECT id FROM workers WHERE channel=? AND chat_id=? AND thread_id=? AND label=?",
            (channel, chat_id, thread_id or "", label),
        ).fetchone()
    return int(row["id"])


def list_workers() -> list[WorkerRow]:
    init_db()
    with _conn() as c:
        rows = c.execute("SELECT * FROM workers ORDER BY channel, chat_id, thread_id, label").fetchall()
    out: list[WorkerRow] = []
    for row in rows:
        item = dict(row)
        if item.get("pid") and not _is_pid_running(item["pid"]):
            item["pid"] = None
            item["status"] = "stopped"
        out.append(WorkerRow(**item))
    return out


def _set_worker_runtime(worker_id: int, pid: int | None, status: str, enabled: int | None = None) -> None:
    with _conn() as c:
        if enabled is None:
            c.execute(
                "UPDATE workers SET pid=?, status=?, updated_at=? WHERE id=?",
                (pid, status, _now(), worker_id),
            )
        else:
            c.execute(
                "UPDATE workers SET pid=?, status=?, enabled=?, updated_at=? WHERE id=?",
                (pid, status, enabled, _now(), worker_id),
            )


def _get_worker(worker_id: int) -> WorkerRow:
    with _conn() as c:
        row = c.execute("SELECT * FROM workers WHERE id=?", (worker_id,)).fetchone()
    if not row:
        raise ValueError(f"worker {worker_id} não encontrado")
    return _row_to_worker(row)


def start_worker(worker_id: int) -> int:
    init_db()
    worker = _get_worker(worker_id)
    if worker.pid and _is_pid_running(worker.pid):
        return worker.pid

    cmd = [sys.executable, "-m", "clawlite.cli", "agents", "worker", "--worker-id", str(worker_id)]
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    _set_worker_runtime(worker_id, proc.pid, "running", enabled=1)
    return int(proc.pid)


def stop_worker(worker_id: int) -> bool:
    worker = _get_worker(worker_id)
    pid = worker.pid
    if pid and _is_pid_running(pid):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    _set_worker_runtime(worker_id, None, "stopped", enabled=0)
    return True


def recover_workers() -> list[int]:
    init_db()
    with _conn() as c:
        rows = c.execute("SELECT id, pid, enabled FROM workers").fetchall()
    restarted: list[int] = []
    for row in rows:
        if int(row["enabled"]) != 1:
            continue
        if _is_pid_running(row["pid"]):
            continue
        wid = int(row["id"])
        try:
            start_worker(wid)
            restarted.append(wid)
        except Exception:
            # keep MVP resilient: skip broken worker and continue
            pass
    return restarted


def enqueue_task(channel: str, chat_id: str, thread_id: str, label: str, payload: dict[str, Any]) -> int:
    init_db()
    ts = _now()
    with _conn() as c:
        row = c.execute(
            "SELECT id FROM workers WHERE channel=? AND chat_id=? AND thread_id=? AND label=? AND enabled=1",
            (channel, chat_id, thread_id or "", label),
        ).fetchone()
        if not row:
            raise ValueError(f"Nenhum worker ativo para {channel}/{chat_id}/{thread_id}/{label}")
        c.execute(
            """
            INSERT INTO tasks (channel, chat_id, thread_id, label, payload, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (channel, chat_id, thread_id or "", label, json.dumps(payload, ensure_ascii=False), ts, ts),
        )
        task_id = c.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    return int(task_id)


def _next_task(worker: WorkerRow) -> sqlite3.Row | None:
    with _conn() as c:
        row = c.execute(
            """
            SELECT * FROM tasks
            WHERE status='queued' AND channel=? AND chat_id=? AND thread_id=? AND label=?
            ORDER BY id ASC
            LIMIT 1
            """,
            (worker.channel, worker.chat_id, worker.thread_id, worker.label),
        ).fetchone()
    return row


def _claim_task(task_id: int, worker_id: int) -> bool:
    with _conn() as c:
        cur = c.execute(
            "UPDATE tasks SET status='running', worker_id=?, updated_at=? WHERE id=? AND status='queued'",
            (worker_id, _now(), task_id),
        )
    return cur.rowcount == 1


def _finish_task(task_id: int, ok: bool, result: str) -> None:
    with _conn() as c:
        c.execute(
            "UPDATE tasks SET status=?, result=?, updated_at=? WHERE id=?",
            ("done" if ok else "failed", result[:4000], _now(), task_id),
        )


def _render_command(template: str, payload: dict[str, Any]) -> str:
    merged = {
        "text": payload.get("text", ""),
        "label": payload.get("label", ""),
        "chat_id": payload.get("chat_id", ""),
        "thread_id": payload.get("thread_id", ""),
        "channel": payload.get("channel", "telegram"),
    }
    return template.format(**merged)


def worker_loop(worker_id: int) -> None:
    init_db()
    worker = _get_worker(worker_id)
    _set_worker_runtime(worker_id, os.getpid(), "running")

    while True:
        worker = _get_worker(worker_id)
        if worker.enabled != 1:
            _set_worker_runtime(worker_id, None, "stopped")
            return

        poll_sleep = effective_poll_seconds(POLL_SECONDS)
        row = _next_task(worker)
        if not row:
            time.sleep(poll_sleep)
            continue

        task_id = int(row["id"])
        if not _claim_task(task_id, worker_id):
            continue

        payload = json.loads(row["payload"])
        try:
            command = _render_command(worker.command_template, payload)
            proc = subprocess.run(command, shell=True, capture_output=True, text=True)
            out = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
            ok = proc.returncode == 0

            # Resposta em áudio opcional para Telegram
            if ok and payload.get("reply_in_audio") and payload.get("channel") == "telegram":
                ch_cfg = payload.get("channel_cfg") or {}
                audio_path = synthesize_tts(out.strip() or "Resposta concluída.", ch_cfg)
                send_telegram_audio_reply(
                    telegram_token=str(ch_cfg.get("token", "")),
                    chat_id=str(payload.get("chat_id", "")),
                    audio_path=audio_path,
                    caption="Resposta em áudio",
                )

            _finish_task(task_id, ok, out.strip())
        except Exception as exc:
            _finish_task(task_id, False, f"worker error: {exc}")

        if get_battery_mode().get("enabled", False):
            time.sleep(poll_sleep)


def format_workers_table(rows: list[WorkerRow]) -> str:
    if not rows:
        return "(sem workers)"
    lines = ["id | canal | chat | thread | label | status | pid"]
    for r in rows:
        status = r.status
        pid = r.pid if (r.pid and _is_pid_running(r.pid)) else "-"
        lines.append(f"{r.id} | {r.channel} | {r.chat_id} | {r.thread_id or '-'} | {r.label} | {status} | {pid}")
    return "\n".join(lines)


def task_status(limit: int = 20) -> str:
    init_db()
    with _conn() as c:
        rows = c.execute(
            "SELECT id, channel, chat_id, thread_id, label, status, worker_id, updated_at FROM tasks ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    if not rows:
        return "(sem tasks)"
    lines = ["task | canal | chat | thread | label | status | worker"]
    for r in rows:
        lines.append(
            f"{r['id']} | {r['channel']} | {r['chat_id']} | {r['thread_id'] or '-'} | {r['label']} | {r['status']} | {r['worker_id'] or '-'}"
        )
    return "\n".join(lines)
