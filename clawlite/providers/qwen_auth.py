from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import httpx


QWEN_OAUTH_TOKEN_URL = "https://chat.qwen.ai/api/v1/oauth2/token"
QWEN_OAUTH_CLIENT_ID = "".join(
    (
        "f0304373",
        "b74a44d2",
        "b584a3fb",
        "70ca9e56",
    )
)


def _read_oauth_payload(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _pick_value(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(payload.get(key, "") or "").strip()
        if value:
            return value
    return ""


def _token_target(payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    tokens = payload.get("tokens")
    if isinstance(tokens, dict):
        return tokens, True
    return payload, False


def load_qwen_auth_state(path: str | Path | None = None) -> dict[str, str]:
    raw_path = str(path or os.getenv("CLAWLITE_QWEN_AUTH_PATH", "") or "").strip()
    candidates: list[Path] = []
    if raw_path:
        candidates.append(Path(raw_path).expanduser())
    candidates.extend(
        [
            Path.home() / ".qwen" / "oauth_creds.json",
            Path.home() / ".qwen" / "auth.json",
        ]
    )

    for candidate in candidates:
        payload = _read_oauth_payload(candidate)
        if not payload:
            continue
        source_payload, has_tokens_block = _token_target(payload)
        token = _pick_value(source_payload, "access_token", "accessToken", "token")
        refresh_token = _pick_value(source_payload, "refresh_token", "refreshToken")
        account_id = _pick_value(source_payload, "account_id", "accountId", "organization")
        token_url = (
            _pick_value(payload, "token_url", "tokenUrl", "oauth_token_url", "oauthTokenUrl")
            or QWEN_OAUTH_TOKEN_URL
        )
        client_id = (
            _pick_value(source_payload, "client_id", "clientId")
            or _pick_value(payload, "client_id", "clientId")
            or os.getenv("QWEN_OAUTH_CLIENT_ID", "").strip()
            or QWEN_OAUTH_CLIENT_ID
        )
        if token or refresh_token:
            return {
                "access_token": token,
                "refresh_token": refresh_token,
                "account_id": account_id,
                "client_id": client_id,
                "token_url": token_url,
                "source": f"file:{candidate}" if token else "",
                "path": str(candidate),
                "has_tokens_block": "true" if has_tokens_block else "false",
            }
    fallback = Path.home() / ".qwen" / "oauth_creds.json"
    return {
        "access_token": "",
        "refresh_token": "",
        "account_id": "",
        "client_id": os.getenv("QWEN_OAUTH_CLIENT_ID", "").strip() or QWEN_OAUTH_CLIENT_ID,
        "token_url": QWEN_OAUTH_TOKEN_URL,
        "source": "",
        "path": str(candidates[-1]) if candidates else str(fallback),
        "has_tokens_block": "false",
    }


def load_qwen_auth_file(path: str | Path | None = None) -> dict[str, str]:
    state = load_qwen_auth_state(path)
    return {
        "access_token": str(state.get("access_token", "") or "").strip(),
        "account_id": str(state.get("account_id", "") or "").strip(),
        "source": str(state.get("source", "") or "").strip(),
    }


def _persist_qwen_auth_state(
    *,
    path: Path,
    payload: dict[str, Any],
    access_token: str,
    refresh_token: str,
    expires_in: int | None,
) -> dict[str, str]:
    updated = dict(payload) if isinstance(payload, dict) else {}
    target, has_tokens_block = _token_target(updated)
    target["access_token"] = access_token
    if refresh_token:
        target["refresh_token"] = refresh_token
    expiry_millis = None
    if expires_in is not None and expires_in > 0:
        expiry_millis = int(time.time() * 1000) + (int(expires_in) * 1000)
        target["expiry_date"] = expiry_millis
        target["expires_at"] = expiry_millis
    if has_tokens_block:
        updated["tokens"] = target
    else:
        updated.update(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "account_id": _pick_value(target, "account_id", "accountId", "organization"),
        "source": f"file:{path}",
        "path": str(path),
    }


async def refresh_qwen_auth_file(path: str | Path | None = None, *, timeout: float = 15.0) -> dict[str, str]:
    state = load_qwen_auth_state(path)
    refresh_token = str(state.get("refresh_token", "") or "").strip()
    auth_path = Path(str(state.get("path", "") or "")).expanduser()
    if not refresh_token or not auth_path:
        raise RuntimeError("provider_oauth_refresh_unavailable:qwen_oauth")

    token_url = str(state.get("token_url", "") or QWEN_OAUTH_TOKEN_URL).strip() or QWEN_OAUTH_TOKEN_URL
    client_id = str(state.get("client_id", "") or "").strip() or QWEN_OAUTH_CLIENT_ID

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            token_url,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
            },
            headers={
                "content-type": "application/x-www-form-urlencoded",
                "accept": "application/json",
            },
        )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("provider_oauth_refresh_invalid_payload:qwen_oauth")
    if _pick_value(payload, "error", "error_description"):
        raise RuntimeError(
            f"provider_oauth_refresh_failed:qwen_oauth:{_pick_value(payload, 'error_description', 'error')}"
        )

    access_token = _pick_value(payload, "access_token", "accessToken", "token")
    if not access_token:
        raise RuntimeError("provider_oauth_refresh_missing_token:qwen_oauth")
    next_refresh_token = _pick_value(payload, "refresh_token", "refreshToken") or refresh_token
    expires_in_raw = payload.get("expires_in", payload.get("expiresIn"))
    try:
        expires_in = int(expires_in_raw) if expires_in_raw is not None else None
    except Exception:
        expires_in = None

    original_payload = _read_oauth_payload(auth_path)
    return _persist_qwen_auth_state(
        path=auth_path,
        payload=original_payload,
        access_token=access_token,
        refresh_token=next_refresh_token,
        expires_in=expires_in,
    )
