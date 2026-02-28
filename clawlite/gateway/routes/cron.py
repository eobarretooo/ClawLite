from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import JSONResponse

from clawlite.gateway.utils import _check_bearer, _log
from clawlite.runtime.conversation_cron import add_cron_job, list_cron_jobs, remove_cron_job

router = APIRouter()


@router.get("/api/cron")
def api_cron_list(
    channel: str | None = Query(default=None),
    chat_id: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    _check_bearer(authorization)
    jobs = list_cron_jobs(channel=channel, chat_id=chat_id)
    return JSONResponse({"ok": True, "jobs": [j.__dict__ for j in jobs]})


@router.post("/api/cron")
def api_cron_add(payload: dict[str, Any], authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    try:
        job_id = add_cron_job(
            channel=str(payload.get("channel", "telegram")),
            chat_id=str(payload.get("chat_id", "")),
            thread_id=str(payload.get("thread_id", "")),
            label=str(payload.get("label", "default")),
            name=str(payload.get("name", "")),
            text=str(payload.get("text", "")),
            interval_seconds=int(payload.get("interval_seconds", 3600)),
            enabled=bool(payload.get("enabled", True)),
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _log("cron.added", data={"id": job_id, "name": payload.get("name")})
    return JSONResponse({"ok": True, "id": job_id})


@router.delete("/api/cron/{job_id}")
def api_cron_remove(job_id: int, authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    removed = remove_cron_job(job_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Cron job {job_id} não encontrado")
    _log("cron.removed", data={"id": job_id})
    return JSONResponse({"ok": True, "id": job_id})
