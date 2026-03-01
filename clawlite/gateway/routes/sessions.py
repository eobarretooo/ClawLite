from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import JSONResponse

from clawlite.config import settings as app_settings
from clawlite.gateway.chat import _collect_session_index, _session_messages
from clawlite.gateway.utils import (
    _check_bearer,
    _iso_now,
    _log,
    _parse_ts,
    _period_start,
    _read_jsonl,
    _telemetry_costs,
    _telemetry_tokens,
)

router = APIRouter()


def _telemetry_file() -> Path:
    return Path(app_settings.CONFIG_DIR) / "dashboard" / "telemetry.jsonl"


def _sessions_file() -> Path:
    return Path(app_settings.CONFIG_DIR) / "dashboard" / "sessions.jsonl"


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for row in rows:
        if isinstance(row, dict):
            lines.append(json.dumps(row, ensure_ascii=False))
    text = ("\n".join(lines) + "\n") if lines else ""
    path.write_text(text, encoding="utf-8")


@router.get("/api/dashboard/sessions")
def api_dashboard_sessions(
    authorization: str | None = Header(default=None),
    q: str = Query(default=""),
) -> JSONResponse:
    _check_bearer(authorization)
    return JSONResponse({"ok": True, "sessions": _collect_session_index(q)})


@router.get("/api/dashboard/sessions/{session_id}")
def api_dashboard_session_messages(session_id: str, authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    return JSONResponse({"ok": True, "session_id": session_id, "messages": _session_messages(session_id)})


@router.get("/api/sessions")
def api_sessions_list(
    authorization: str | None = Header(default=None),
    q: str = Query(default=""),
) -> JSONResponse:
    _check_bearer(authorization)
    return JSONResponse({"ok": True, "sessions": _collect_session_index(q)})


@router.get("/api/sessions/{session_id}/preview")
def api_sessions_preview(
    session_id: str,
    authorization: str | None = Header(default=None),
    limit: int = Query(default=50, ge=1, le=500),
) -> JSONResponse:
    _check_bearer(authorization)
    rows = _session_messages(session_id)
    return JSONResponse(
        {
            "ok": True,
            "session_id": session_id,
            "messages": rows[-limit:],
            "count": len(rows),
        }
    )


@router.patch("/api/sessions/{session_id}")
def api_sessions_patch(
    session_id: str,
    payload: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    _check_bearer(authorization)
    rename_to = str(payload.get("rename_to") or payload.get("session_id") or "").strip()
    if not rename_to:
        raise HTTPException(status_code=400, detail="Campo 'rename_to' é obrigatório")
    if rename_to == session_id:
        return JSONResponse({"ok": True, "updated": 0, "telemetry_updated": 0, "session_id": session_id})

    session_rows = _read_jsonl(_sessions_file())
    updated = 0
    for row in session_rows:
        if str(row.get("session_id", "")) == session_id:
            row["session_id"] = rename_to
            row["ts_updated"] = _iso_now()
            updated += 1
    _write_jsonl(_sessions_file(), session_rows)

    telemetry_rows = _read_jsonl(_telemetry_file())
    telemetry_updated = 0
    for row in telemetry_rows:
        if str(row.get("session_id", "")) == session_id:
            row["session_id"] = rename_to
            telemetry_updated += 1
    _write_jsonl(_telemetry_file(), telemetry_rows)

    _log("sessions.patch", data={"from": session_id, "to": rename_to, "updated": updated})
    return JSONResponse(
        {
            "ok": True,
            "session_id": rename_to,
            "updated": updated,
            "telemetry_updated": telemetry_updated,
        }
    )


@router.post("/api/sessions/{session_id}/reset")
def api_sessions_reset(session_id: str, authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    session_rows = _read_jsonl(_sessions_file())
    kept = [row for row in session_rows if str(row.get("session_id", "")) != session_id]
    removed = len(session_rows) - len(kept)
    _write_jsonl(_sessions_file(), kept)
    _log("sessions.reset", data={"session_id": session_id, "removed": removed})
    return JSONResponse({"ok": True, "session_id": session_id, "removed": removed})


@router.delete("/api/sessions/{session_id}")
def api_sessions_delete(session_id: str, authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    session_rows = _read_jsonl(_sessions_file())
    kept_sessions = [row for row in session_rows if str(row.get("session_id", "")) != session_id]
    removed_sessions = len(session_rows) - len(kept_sessions)
    _write_jsonl(_sessions_file(), kept_sessions)

    telemetry_rows = _read_jsonl(_telemetry_file())
    kept_telemetry = [row for row in telemetry_rows if str(row.get("session_id", "")) != session_id]
    removed_telemetry = len(telemetry_rows) - len(kept_telemetry)
    _write_jsonl(_telemetry_file(), kept_telemetry)

    _log(
        "sessions.delete",
        data={"session_id": session_id, "messages": removed_sessions, "telemetry": removed_telemetry},
    )
    return JSONResponse(
        {
            "ok": True,
            "session_id": session_id,
            "messages_removed": removed_sessions,
            "telemetry_removed": removed_telemetry,
        }
    )


@router.post("/api/sessions/compact")
def api_sessions_compact(
    payload: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    _check_bearer(authorization)
    raw_limit = payload.get("max_messages", 40)
    try:
        max_messages = int(raw_limit)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Campo 'max_messages' deve ser inteiro") from None
    if max_messages < 1 or max_messages > 2000:
        raise HTTPException(status_code=400, detail="max_messages deve estar entre 1 e 2000")

    rows = _read_jsonl(_sessions_file())
    by_session: dict[str, list[int]] = {}
    for idx, row in enumerate(rows):
        sid = str(row.get("session_id", "")).strip()
        if not sid:
            continue
        by_session.setdefault(sid, []).append(idx)

    keep_indexes: set[int] = set()
    for indexes in by_session.values():
        keep_indexes.update(indexes[-max_messages:])

    compacted_rows = [row for idx, row in enumerate(rows) if idx in keep_indexes]
    removed = len(rows) - len(compacted_rows)
    _write_jsonl(_sessions_file(), compacted_rows)
    _log("sessions.compact", data={"removed": removed, "max_messages": max_messages})
    return JSONResponse(
        {
            "ok": True,
            "removed": removed,
            "remaining": len(compacted_rows),
            "max_messages": max_messages,
        }
    )


@router.get("/api/dashboard/telemetry")
def api_dashboard_telemetry(
    authorization: str | None = Header(default=None),
    session_id: str = Query(default=""),
    period: str = Query(default="7d"),
    granularity: str = Query(default="auto"),
    start: str = Query(default=""),
    end: str = Query(default=""),
    limit: int = Query(default=200),
) -> JSONResponse:
    _check_bearer(authorization)
    rows = _read_jsonl(_telemetry_file())
    clean_session = session_id.strip()
    start_dt = _parse_ts(start) if start else _period_start(period)
    end_dt = _parse_ts(end) if end else None
    if start_dt and end_dt and end_dt < start_dt:
        raise HTTPException(status_code=400, detail="Intervalo invalido: end < start")

    filtered: list[dict[str, Any]] = []
    for row in rows:
        if clean_session and str(row.get("session_id", "")) != clean_session:
            continue
        row_ts = _parse_ts(row.get("ts"))
        if start_dt and (row_ts is None or row_ts < start_dt):
            continue
        if end_dt and (row_ts is None or row_ts > end_dt):
            continue
        filtered.append(row)

    summary = {
        "events": 0,
        "sessions": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "tokens": 0,
        "prompt_cost_usd": 0.0,
        "completion_cost_usd": 0.0,
        "cost_usd": 0.0,
    }
    session_map: dict[str, dict[str, Any]] = {}

    use_hour = False
    if granularity.lower() == "hour":
        use_hour = True
    elif granularity.lower() == "auto":
        use_hour = period.lower() in {"24h", "today"}

    timeline_map: dict[str, dict[str, Any]] = {}
    for row in filtered:
        prompt_tokens, completion_tokens, tokens = _telemetry_tokens(row)
        prompt_cost, completion_cost, total_cost = _telemetry_costs(row)
        sid = str(row.get("session_id", "")).strip() or "unknown"

        summary["events"] += 1
        summary["prompt_tokens"] += prompt_tokens
        summary["completion_tokens"] += completion_tokens
        summary["tokens"] += tokens
        summary["prompt_cost_usd"] = round(summary["prompt_cost_usd"] + prompt_cost, 6)
        summary["completion_cost_usd"] = round(summary["completion_cost_usd"] + completion_cost, 6)
        summary["cost_usd"] = round(summary["cost_usd"] + total_cost, 6)

        item = session_map.setdefault(
            sid,
            {
                "session_id": sid,
                "events": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "tokens": 0,
                "cost_usd": 0.0,
                "last_ts": "",
            },
        )
        item["events"] += 1
        item["prompt_tokens"] += prompt_tokens
        item["completion_tokens"] += completion_tokens
        item["tokens"] += tokens
        item["cost_usd"] = round(item["cost_usd"] + total_cost, 6)
        ts = str(row.get("ts", ""))
        if ts >= item["last_ts"]:
            item["last_ts"] = ts

        dt = _parse_ts(row.get("ts"))
        if dt is None:
            continue
        if use_hour:
            bucket_dt = dt.replace(minute=0, second=0, microsecond=0)
            bucket = bucket_dt.isoformat().replace("+00:00", "Z")
        else:
            bucket = dt.strftime("%Y-%m-%d")
        bucket_item = timeline_map.setdefault(
            bucket,
            {
                "bucket": bucket,
                "events": 0,
                "tokens": 0,
                "cost_usd": 0.0,
            },
        )
        bucket_item["events"] += 1
        bucket_item["tokens"] += tokens
        bucket_item["cost_usd"] = round(bucket_item["cost_usd"] + total_cost, 6)

    summary["sessions"] = len(session_map)
    sessions = sorted(
        session_map.values(),
        key=lambda row: (float(row.get("cost_usd", 0.0)), int(row.get("tokens", 0))),
        reverse=True,
    )
    timeline = [timeline_map[k] for k in sorted(timeline_map)]
    n = max(1, min(limit, 500))

    return JSONResponse(
        {
            "ok": True,
            "filters": {
                "session_id": clean_session,
                "period": period,
                "granularity": "hour" if use_hour else "day",
                "start": start_dt.isoformat() if start_dt else "",
                "end": end_dt.isoformat() if end_dt else "",
            },
            "summary": summary,
            "sessions": sessions,
            "timeline": timeline,
            "events": filtered[-n:],
        }
    )
