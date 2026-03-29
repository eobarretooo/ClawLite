from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_SENTINEL_FILENAME = "restart-sentinel.json"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def restart_sentinel_path(state_path: str | Path) -> Path:
    return Path(state_path).expanduser() / _SENTINEL_FILENAME


def write_restart_sentinel(*, state_path: str | Path, payload: dict[str, Any]) -> Path:
    target = restart_sentinel_path(state_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "version": 1,
        "payload": dict(payload or {}),
    }
    target.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def read_restart_sentinel(state_path: str | Path) -> dict[str, Any] | None:
    target = restart_sentinel_path(state_path)
    if not target.exists():
        return None
    try:
        parsed = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        target.unlink(missing_ok=True)
        return None
    if not isinstance(parsed, dict):
        return None
    payload = parsed.get("payload")
    if not isinstance(payload, dict):
        return None
    return dict(payload)


def clear_restart_sentinel(state_path: str | Path) -> None:
    restart_sentinel_path(state_path).unlink(missing_ok=True)


def consume_restart_sentinel(state_path: str | Path) -> dict[str, Any] | None:
    payload = read_restart_sentinel(state_path)
    if payload is None:
        clear_restart_sentinel(state_path)
        return None
    clear_restart_sentinel(state_path)
    return payload


def _coerce_positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def derive_restart_metadata(*, session_id: str, channel: str) -> dict[str, Any]:
    normalized_channel = str(channel or "").strip().lower()
    normalized_session = str(session_id or "").strip()
    if normalized_channel != "telegram":
        return {}
    lowered = normalized_session.lower()
    if not lowered.startswith("telegram:"):
        return {}
    payload = normalized_session.split(":", 1)[1]
    if ":topic:" in payload:
        _, _, maybe_thread = payload.partition(":topic:")
        thread_id = _coerce_positive_int(maybe_thread.strip())
        return {"message_thread_id": thread_id} if thread_id is not None else {}
    if ":thread:" in payload:
        _, _, maybe_thread = payload.partition(":thread:")
        thread_id = _coerce_positive_int(maybe_thread.strip())
        return {"message_thread_id": thread_id} if thread_id is not None else {}
    return {}


def derive_restart_target(*, session_id: str, channel: str, user_id: str) -> str:
    normalized_channel = str(channel or "").strip().lower()
    normalized_session = str(session_id or "").strip()
    normalized_user = str(user_id or "").strip()
    if normalized_channel == "telegram" and normalized_session.lower().startswith("telegram:"):
        return normalized_session
    return normalized_user


def build_restart_sentinel_payload(
    *,
    kind: str,
    session_id: str,
    channel: str,
    target: str,
    note: str,
    changed_paths: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    safe_metadata: dict[str, Any] = {}
    raw_metadata = dict(metadata or {})
    message_thread_id = raw_metadata.get("message_thread_id")
    if isinstance(message_thread_id, int) and message_thread_id > 0:
        safe_metadata["message_thread_id"] = message_thread_id
    elif isinstance(message_thread_id, str):
        try:
            parsed_thread_id = int(message_thread_id)
        except ValueError:
            parsed_thread_id = 0
        if parsed_thread_id > 0:
            safe_metadata["message_thread_id"] = parsed_thread_id
    return {
        "kind": str(kind or "").strip() or "restart",
        "created_at": _utc_now_iso(),
        "session_id": str(session_id or "").strip(),
        "channel": str(channel or "").strip().lower(),
        "target": str(target or "").strip(),
        "note": str(note or "").strip(),
        "changed_paths": [
            str(item or "").strip()
            for item in list(changed_paths or [])
            if str(item or "").strip()
        ],
        "metadata": safe_metadata,
    }


def format_restart_sentinel_notice(payload: dict[str, Any] | None) -> str:
    row = dict(payload or {})
    kind = str(row.get("kind", "") or "").strip().lower()
    note = str(row.get("note", "") or "").strip()
    changed_paths = [
        str(item or "").strip()
        for item in list(row.get("changed_paths", []) or [])
        if str(item or "").strip()
    ]
    if kind == "config_patch":
        header = "ClawLite restarted and applied the requested config change."
    else:
        header = "ClawLite restarted successfully."
    lines = [header]
    if note:
        lines.append(note)
    if changed_paths:
        preview = ", ".join(changed_paths[:4])
        if len(changed_paths) > 4:
            preview = f"{preview}, +{len(changed_paths) - 4} more"
        lines.append(f"Changed: {preview}")
    return "\n".join(lines).strip()


__all__ = [
    "build_restart_sentinel_payload",
    "clear_restart_sentinel",
    "consume_restart_sentinel",
    "derive_restart_metadata",
    "derive_restart_target",
    "format_restart_sentinel_notice",
    "read_restart_sentinel",
    "restart_sentinel_path",
    "write_restart_sentinel",
]
