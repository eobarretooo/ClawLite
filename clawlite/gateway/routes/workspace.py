from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import JSONResponse

from clawlite.config import settings as app_settings
from clawlite.config.settings import load_config
from clawlite.gateway.state import LOG_RING, STARTED_AT, chat_connections, connections, log_connections
from clawlite.gateway.utils import _check_bearer, _log

router = APIRouter()
_WORKSPACE_ALLOWED = {"SOUL.md", "USER.md", "HEARTBEAT.md", "BOOTSTRAP.md"}


def _workspace_dir() -> Path:
    return Path(app_settings.CONFIG_DIR) / "workspace"


@router.get("/api/learning/stats")
async def api_learning_stats(
    period: str = Query("all", pattern="^(today|week|month|all)$"),
    skill: str | None = Query(None),
):
    from clawlite.runtime.learning import get_stats, get_templates
    from clawlite.runtime.preferences import get_preferences

    stats = get_stats(period=period, skill=skill)
    stats["preferences"] = get_preferences()
    stats["templates_count"] = sum(len(v) for v in get_templates().values())
    return JSONResponse(stats)


@router.get("/api/metrics")
def api_metrics(authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    from clawlite.channels.manager import manager as channel_manager
    from clawlite.runtime import multiagent
    from contextlib import closing
    import sqlite3 as _sqlite3

    workers = multiagent.list_workers()
    running_workers = [w for w in workers if w.status == "running" and w.pid]

    queued_tasks = 0
    running_tasks = 0
    db_path = multiagent.current_db_path()
    if db_path.exists():
        try:
            with closing(_sqlite3.connect(db_path)) as c:
                queued_tasks = c.execute("SELECT COUNT(*) FROM tasks WHERE status='queued'").fetchone()[0]
                running_tasks = c.execute("SELECT COUNT(*) FROM tasks WHERE status='running'").fetchone()[0]
        except _sqlite3.Error:
            pass

    uptime_s = (datetime.now(timezone.utc) - STARTED_AT).total_seconds()
    total_logs = len(LOG_RING)
    error_logs = sum(1 for e in LOG_RING if e.get("level") == "error")
    warn_logs = sum(1 for e in LOG_RING if e.get("level") == "warn")
    outbound_by_channel = channel_manager.outbound_metrics()
    outbound_totals = {
        "sent_ok": 0,
        "retry_count": 0,
        "timeout_count": 0,
        "fallback_count": 0,
        "send_fail_count": 0,
        "dedupe_hits": 0,
    }
    for row in outbound_by_channel.values():
        if not isinstance(row, dict):
            continue
        for key in outbound_totals.keys():
            try:
                outbound_totals[key] += int(row.get(key, 0) or 0)
            except (TypeError, ValueError):
                pass

    return JSONResponse(
        {
            "ok": True,
            "uptime_seconds": round(uptime_s, 1),
            "workers": {
                "total": len(workers),
                "running": len(running_workers),
            },
            "tasks": {
                "queued": queued_tasks,
                "running": running_tasks,
            },
            "log_ring": {
                "total": total_logs,
                "errors": error_logs,
                "warnings": warn_logs,
            },
            "websocket_connections": {
                "ws": len(connections),
                "chat": len(chat_connections),
                "logs": len(log_connections),
            },
            "channels_outbound": {
                "channels_reporting": len(outbound_by_channel),
                "totals": outbound_totals,
                "by_channel": outbound_by_channel,
            },
        }
    )


@router.get("/api/workspace/file")
def api_workspace_file_get(
    name: str = Query(...),
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    _check_bearer(authorization)
    if name not in _WORKSPACE_ALLOWED:
        raise HTTPException(status_code=400, detail=f"Arquivo nao permitido: {name}")
    workspace = _workspace_dir()
    path = workspace / name
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    return JSONResponse({"ok": True, "name": name, "content": content})


@router.put("/api/workspace/file")
def api_workspace_file_save(
    payload: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    _check_bearer(authorization)
    name = str(payload.get("name", "")).strip()
    if name not in _WORKSPACE_ALLOWED:
        raise HTTPException(status_code=400, detail=f"Arquivo nao permitido: {name}")
    content = str(payload.get("content", ""))
    workspace = _workspace_dir()
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / name).write_text(content, encoding="utf-8")
    _log("workspace.file.saved", data={"name": name, "bytes": len(content)})
    return JSONResponse({"ok": True, "name": name, "bytes": len(content)})


@router.get("/api/heartbeat/status")
def api_heartbeat_status(authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    cfg = load_config()
    interval_s = int(cfg.get("gateway", {}).get("heartbeat_interval_s", 1800))
    workspace = _workspace_dir()
    state_file = workspace / "memory" / "heartbeat-state.json"
    state: dict[str, Any] = {}
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    last_run = state.get("last_run")
    next_run_iso: str | None = None
    seconds_until_next: int | None = None
    if last_run:
        try:
            lr = datetime.fromisoformat(last_run.replace("Z", "+00:00"))
            if lr.tzinfo is None:
                lr = lr.replace(tzinfo=timezone.utc)
            next_dt = lr + timedelta(seconds=interval_s)
            next_run_iso = next_dt.isoformat()
            seconds_until_next = max(0, int((next_dt - datetime.now(timezone.utc)).total_seconds()))
        except Exception:
            pass
    return JSONResponse(
        {
            "ok": True,
            "last_run": last_run,
            "last_result": state.get("last_result"),
            "runs_today": state.get("runs_today", 0),
            "interval_s": interval_s,
            "next_run": next_run_iso,
            "seconds_until_next": seconds_until_next,
        }
    )
