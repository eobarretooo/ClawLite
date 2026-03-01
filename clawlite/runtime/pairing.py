from __future__ import annotations

import json
import secrets
import string
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from clawlite.config import settings as app_settings

_LOCK = Lock()
_DEFAULT_TTL_SECONDS = 24 * 60 * 60
_ALPHABET = string.ascii_uppercase + string.digits


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _pairing_path() -> Path:
    return Path(app_settings.CONFIG_DIR) / "pairing.json"


def _safe_dt(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalize_channel(channel: str) -> str:
    return str(channel or "").strip().lower()


def _normalize_peer(peer: str) -> str:
    return str(peer or "").strip()


def _normalize_cmp(value: str) -> str:
    text = str(value or "").strip()
    return text.lower() if text else ""


def _pairing_enabled() -> bool:
    cfg = app_settings.load_config()
    security = cfg.get("security", {}) if isinstance(cfg.get("security"), dict) else {}
    pairing = security.get("pairing", {}) if isinstance(security.get("pairing"), dict) else {}
    return bool(pairing.get("enabled", False))


def _pairing_ttl_seconds() -> int:
    cfg = app_settings.load_config()
    security = cfg.get("security", {}) if isinstance(cfg.get("security"), dict) else {}
    pairing = security.get("pairing", {}) if isinstance(security.get("pairing"), dict) else {}
    raw = pairing.get("code_ttl_seconds", _DEFAULT_TTL_SECONDS)
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_TTL_SECONDS
    return parsed if parsed > 0 else _DEFAULT_TTL_SECONDS


def _new_state() -> dict[str, Any]:
    return {
        "pending": [],
        "approved": {},
    }


def _load_state() -> dict[str, Any]:
    path = _pairing_path()
    if not path.exists():
        return _new_state()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _new_state()
    if not isinstance(raw, dict):
        return _new_state()
    pending = raw.get("pending", [])
    approved = raw.get("approved", {})
    return {
        "pending": pending if isinstance(pending, list) else [],
        "approved": approved if isinstance(approved, dict) else {},
    }


def _save_state(state: dict[str, Any]) -> None:
    path = _pairing_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _cleanup_pending_entries(state: dict[str, Any], *, now: datetime | None = None) -> bool:
    now_dt = now or _utc_now()
    ttl = timedelta(seconds=_pairing_ttl_seconds())
    pending = state.get("pending", [])
    if not isinstance(pending, list):
        state["pending"] = []
        return True

    kept: list[dict[str, Any]] = []
    for item in pending:
        if not isinstance(item, dict):
            continue
        created = _safe_dt(str(item.get("created_at", "")))
        if created is None:
            continue
        if now_dt - created > ttl:
            continue
        channel = _normalize_channel(str(item.get("channel", "")))
        peer_id = _normalize_peer(str(item.get("peer_id", "")))
        code = str(item.get("code", "")).strip().upper()
        if not channel or not peer_id or not code:
            continue
        kept.append(
            {
                "channel": channel,
                "peer_id": peer_id,
                "display": str(item.get("display", "")).strip(),
                "code": code,
                "created_at": created.isoformat(),
            }
        )
    changed = len(kept) != len(pending)
    state["pending"] = kept
    return changed


def _generate_code(size: int = 6) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(size))


def is_sender_allowed(channel: str, peer_candidates: list[str], configured_allow: list[str]) -> bool:
    channel_name = _normalize_channel(channel)
    candidates = [_normalize_peer(c) for c in peer_candidates if _normalize_peer(c)]
    if not candidates:
        return False

    configured = {_normalize_cmp(v) for v in configured_allow if _normalize_cmp(v)}
    if not _pairing_enabled():
        if not configured:
            return True
        return any(_normalize_cmp(candidate) in configured for candidate in candidates)

    with _LOCK:
        state = _load_state()
        changed = _cleanup_pending_entries(state)
        approved_map = state.get("approved", {})
        approved_list = approved_map.get(channel_name, []) if isinstance(approved_map, dict) else []
        approved = {_normalize_cmp(v) for v in approved_list if _normalize_cmp(v)}
        allowed = configured | approved
        if changed:
            _save_state(state)
    return any(_normalize_cmp(candidate) in allowed for candidate in candidates)


def issue_pairing_code(channel: str, peer_id: str, display: str = "") -> dict[str, Any]:
    channel_name = _normalize_channel(channel)
    peer = _normalize_peer(peer_id)
    if not channel_name or not peer:
        raise ValueError("channel e peer_id são obrigatórios")

    with _LOCK:
        state = _load_state()
        _cleanup_pending_entries(state)
        pending = state.get("pending", [])

        existing: dict[str, Any] | None = None
        for item in pending:
            if not isinstance(item, dict):
                continue
            if _normalize_channel(str(item.get("channel", ""))) != channel_name:
                continue
            if _normalize_peer(str(item.get("peer_id", ""))) != peer:
                continue
            existing = item
            break

        if existing is None:
            existing = {
                "channel": channel_name,
                "peer_id": peer,
                "display": str(display or "").strip(),
                "code": _generate_code(6),
                "created_at": _utc_now().isoformat(),
            }
            pending.append(existing)
        else:
            if display and not str(existing.get("display", "")).strip():
                existing["display"] = str(display).strip()

        _save_state(state)
        return dict(existing)


def list_pending(channel: str = "") -> list[dict[str, Any]]:
    channel_name = _normalize_channel(channel)
    with _LOCK:
        state = _load_state()
        changed = _cleanup_pending_entries(state)
        rows = []
        for item in state.get("pending", []):
            if not isinstance(item, dict):
                continue
            if channel_name and _normalize_channel(str(item.get("channel", ""))) != channel_name:
                continue
            rows.append(
                {
                    "channel": _normalize_channel(str(item.get("channel", ""))),
                    "peer_id": _normalize_peer(str(item.get("peer_id", ""))),
                    "display": str(item.get("display", "")).strip(),
                    "code": str(item.get("code", "")).strip().upper(),
                    "created_at": str(item.get("created_at", "")).strip(),
                }
            )
        if changed:
            _save_state(state)
    rows.sort(key=lambda row: row.get("created_at", ""), reverse=True)
    return rows


def list_approved(channel: str = "") -> list[dict[str, Any]]:
    channel_name = _normalize_channel(channel)
    with _LOCK:
        state = _load_state()
        approved = state.get("approved", {})
        if not isinstance(approved, dict):
            return []
        rows: list[dict[str, Any]] = []
        for ch, peers in approved.items():
            ch_name = _normalize_channel(str(ch))
            if channel_name and ch_name != channel_name:
                continue
            if not isinstance(peers, list):
                continue
            for peer in peers:
                peer_id = _normalize_peer(str(peer))
                if not peer_id:
                    continue
                rows.append({"channel": ch_name, "peer_id": peer_id})
    rows.sort(key=lambda row: (row["channel"], row["peer_id"]))
    return rows


def _persist_allowlist(channel: str, peer_id: str) -> None:
    cfg = app_settings.load_config()
    channels = cfg.get("channels", {})
    if not isinstance(channels, dict):
        channels = {}
        cfg["channels"] = channels

    channel_cfg = channels.get(channel, {})
    if not isinstance(channel_cfg, dict):
        channel_cfg = {}
    allow = channel_cfg.get("allowFrom", [])
    if isinstance(allow, list):
        values = [str(item).strip() for item in allow if str(item).strip()]
    elif isinstance(allow, str):
        values = [item.strip() for item in allow.split(",") if item.strip()]
    else:
        values = []
    if peer_id not in values:
        values.append(peer_id)
    channel_cfg["allowFrom"] = values
    channels[channel] = channel_cfg
    cfg["channels"] = channels
    app_settings.save_config(cfg)


def approve_pairing(channel: str, code: str) -> dict[str, Any]:
    channel_name = _normalize_channel(channel)
    code_value = str(code or "").strip().upper()
    if not channel_name or not code_value:
        raise ValueError("channel e code são obrigatórios")

    with _LOCK:
        state = _load_state()
        _cleanup_pending_entries(state)
        pending = state.get("pending", [])
        idx = -1
        entry: dict[str, Any] | None = None
        for i, item in enumerate(pending):
            if not isinstance(item, dict):
                continue
            if _normalize_channel(str(item.get("channel", ""))) != channel_name:
                continue
            if str(item.get("code", "")).strip().upper() != code_value:
                continue
            idx = i
            entry = item
            break
        if entry is None or idx < 0:
            raise ValueError("código de pairing não encontrado")

        pending.pop(idx)
        approved = state.get("approved", {})
        if not isinstance(approved, dict):
            approved = {}
            state["approved"] = approved
        peers = approved.get(channel_name, [])
        if not isinstance(peers, list):
            peers = []
        peer_id = _normalize_peer(str(entry.get("peer_id", "")))
        if peer_id and all(_normalize_cmp(peer_id) != _normalize_cmp(v) for v in peers):
            peers.append(peer_id)
        approved[channel_name] = peers
        _save_state(state)

    if peer_id:
        _persist_allowlist(channel_name, peer_id)
    return {
        "channel": channel_name,
        "peer_id": peer_id,
        "display": str(entry.get("display", "")).strip(),
        "code": code_value,
    }


def reject_pairing(channel: str, code: str) -> dict[str, Any]:
    channel_name = _normalize_channel(channel)
    code_value = str(code or "").strip().upper()
    if not channel_name or not code_value:
        raise ValueError("channel e code são obrigatórios")

    with _LOCK:
        state = _load_state()
        _cleanup_pending_entries(state)
        pending = state.get("pending", [])
        idx = -1
        entry: dict[str, Any] | None = None
        for i, item in enumerate(pending):
            if not isinstance(item, dict):
                continue
            if _normalize_channel(str(item.get("channel", ""))) != channel_name:
                continue
            if str(item.get("code", "")).strip().upper() != code_value:
                continue
            idx = i
            entry = item
            break
        if entry is None or idx < 0:
            raise ValueError("código de pairing não encontrado")
        pending.pop(idx)
        _save_state(state)

    return {
        "channel": channel_name,
        "peer_id": _normalize_peer(str(entry.get("peer_id", ""))),
        "display": str(entry.get("display", "")).strip(),
        "code": code_value,
    }


def pairing_file_path() -> Path:
    return _pairing_path()
