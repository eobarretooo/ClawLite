from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import JSONResponse

from clawlite.gateway.chat import _collect_session_index, _session_messages
from clawlite.gateway.state import TELEMETRY_FILE
from clawlite.gateway.utils import (
    _check_bearer,
    _parse_ts,
    _period_start,
    _read_jsonl,
    _telemetry_costs,
    _telemetry_tokens,
)

router = APIRouter()


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
    rows = _read_jsonl(TELEMETRY_FILE)
    clean_session = session_id.strip()
    start_dt = _parse_ts(start) if start else _period_start(period)
    end_dt = _parse_ts(end) if end else None
    if start_dt and end_dt and end_dt < start_dt:
        raise HTTPException(status_code=400, detail="Intervalo inválido: end < start")

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

    return JSONResponse({
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
    })
