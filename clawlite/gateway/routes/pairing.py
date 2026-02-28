from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import JSONResponse

from clawlite.gateway.utils import _check_bearer, _log
from clawlite.runtime.pairing import approve_pairing, list_approved, list_pending, reject_pairing

router = APIRouter()


@router.get("/api/pairing/pending")
def api_pairing_pending(
    authorization: str | None = Header(default=None),
    channel: str = Query(default=""),
) -> JSONResponse:
    _check_bearer(authorization)
    return JSONResponse({"ok": True, "pending": list_pending(channel=channel)})


@router.get("/api/pairing/approved")
def api_pairing_approved(
    authorization: str | None = Header(default=None),
    channel: str = Query(default=""),
) -> JSONResponse:
    _check_bearer(authorization)
    return JSONResponse({"ok": True, "approved": list_approved(channel=channel)})


@router.post("/api/pairing/approve")
def api_pairing_approve(payload: dict[str, Any], authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    channel = str(payload.get("channel", "")).strip()
    code = str(payload.get("code", "")).strip()
    if not channel or not code:
        raise HTTPException(status_code=400, detail="Informe channel e code")
    try:
        row = approve_pairing(channel, code)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _log("pairing.approved", data={"channel": row["channel"], "peer_id": row["peer_id"]})
    return JSONResponse({"ok": True, "approved": row})


@router.post("/api/pairing/reject")
def api_pairing_reject(payload: dict[str, Any], authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    channel = str(payload.get("channel", "")).strip()
    code = str(payload.get("code", "")).strip()
    if not channel or not code:
        raise HTTPException(status_code=400, detail="Informe channel e code")
    try:
        row = reject_pairing(channel, code)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _log("pairing.rejected", data={"channel": row["channel"], "peer_id": row["peer_id"]})
    return JSONResponse({"ok": True, "rejected": row})
