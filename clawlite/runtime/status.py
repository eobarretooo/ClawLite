from __future__ import annotations

import socket
import sqlite3
from pathlib import Path

from clawlite.config.settings import load_config
from clawlite.runtime.conversation_cron import init_cron_db, list_cron_jobs
from clawlite.runtime.multiagent import DB_PATH, list_workers


def _port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        target = "127.0.0.1" if host in {"0.0.0.0", "::", ""} else host
        with socket.create_connection((target, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def _task_counts() -> tuple[int, int]:
    if not DB_PATH.exists():
        return (0, 0)
    with sqlite3.connect(DB_PATH) as c:
        queued = c.execute("SELECT COUNT(*) FROM tasks WHERE status='queued'").fetchone()[0]
        running = c.execute("SELECT COUNT(*) FROM tasks WHERE status='running'").fetchone()[0]
    return int(queued), int(running)


def runtime_status() -> str:
    cfg = load_config()
    gw = cfg.get("gateway", {})

    gateway_running = _port_open(str(gw.get("host", "0.0.0.0")), int(gw.get("port", 8787)))

    workers = list_workers()
    running_workers = [w for w in workers if w.status == "running" and w.pid]

    init_cron_db()
    jobs = list_cron_jobs()
    enabled_jobs = [j for j in jobs if j.enabled == 1]

    queued, running_tasks = _task_counts()

    reddit_cfg = cfg.get("web_tools", {}).get("reddit", {})
    reddit_enabled = bool(reddit_cfg.get("enabled") or cfg.get("reddit", {}).get("enabled"))
    state_file = Path.home() / ".clawlite" / "reddit_state.json"

    lines = [
        "📊 ClawLite Status",
        f"gateway: {'running ✅' if gateway_running else 'stopped ❌'} ({gw.get('host', '0.0.0.0')}:{gw.get('port', 8787)})",
        f"workers: {len(running_workers)}/{len(workers)} running",
        f"cron.jobs: {len(enabled_jobs)} enabled ({len(jobs)} total)",
        f"tasks.queue: {queued} queued / {running_tasks} running",
        f"reddit.monitor: {'enabled ✅' if reddit_enabled else 'disabled ❌'}",
        f"reddit.state_file: {'ok' if state_file.exists() else 'missing'}",
    ]
    return "\n".join(lines)
