from __future__ import annotations

import threading
import json
from pathlib import Path
from typing import Any

from clawlite.config.loader import load_raw_config_payload, load_target_config_payload, save_raw_config_payload
from clawlite.config.loader import _validate_config_keys
from clawlite.config.schema import AppConfig
from clawlite.gateway.restart_control import gateway_restart_pending, schedule_gateway_restart
from clawlite.gateway.restart_sentinel import (
    build_restart_sentinel_payload,
    clear_restart_sentinel,
    derive_restart_metadata,
    derive_restart_target,
    write_restart_sentinel,
)
from clawlite.tools.base import Tool, ToolContext


_SENSITIVE_KEY_MARKERS: tuple[str, ...] = (
    "api_key",
    "access_token",
    "token",
    "authorization",
    "auth",
    "credential",
    "credentials",
    "secret",
    "password",
)

_DISALLOWED_SESSION_PREFIXES: tuple[str, ...] = (
    "autonomy:",
    "heartbeat:",
    "bootstrap:",
)
_GATEWAY_ADMIN_RESTART_LOCK = threading.Lock()


def _deep_merge(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(dict(out.get(key) or {}), value)
        else:
            out[key] = value
    return out


def _flatten_patch_paths(value: Any, *, prefix: str = "") -> list[str]:
    if not isinstance(value, dict) or not value:
        return [prefix] if prefix else []
    out: list[str] = []
    for key, nested in value.items():
        clean_key = str(key or "").strip()
        if not clean_key:
            continue
        child_prefix = clean_key if not prefix else f"{prefix}.{clean_key}"
        if isinstance(nested, dict) and nested:
            out.extend(_flatten_patch_paths(nested, prefix=child_prefix))
        else:
            out.append(child_prefix)
    return out


def _is_sensitive_key(key: Any) -> bool:
    normalized = str(key or "").strip().lower()
    if not normalized:
        return False
    return any(marker in normalized for marker in _SENSITIVE_KEY_MARKERS)


def _redact_payload(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, nested in value.items():
            if _is_sensitive_key(key):
                redacted[str(key)] = "***"
            else:
                redacted[str(key)] = _redact_payload(nested)
        return redacted
    if isinstance(value, list):
        return [_redact_payload(item) for item in value]
    return value


def _default_note(*, changed_paths: list[str]) -> str:
    if not changed_paths:
        return "Applied the requested config change."
    if len(changed_paths) == 1:
        return f"Applied the requested config change for `{changed_paths[0]}`."
    return f"Applied the requested config change for {len(changed_paths)} config fields."


class GatewayAdminTool(Tool):
    name = "gateway_admin"
    description = (
        "Inspect the active config, apply a partial config patch, and restart the ClawLite gateway. "
        "Use only when the user explicitly asks to change config or restart the runtime. "
        "For config_patch_and_restart, always pass a short human-readable note describing what was enabled or changed; "
        "ClawLite will send that note back after the gateway restarts."
    )

    def __init__(
        self,
        *,
        config_path: str | Path | None,
        config_profile: str | None,
        state_path: str | Path,
    ) -> None:
        self._config_path = None if config_path is None else str(config_path)
        self._config_profile = str(config_profile or "").strip() or None
        self._state_path = Path(state_path).expanduser()

    def args_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["config_get", "config_patch_and_restart", "restart_gateway"],
                },
                "patch": {
                    "type": "object",
                    "description": "Partial config patch merged into the current on-disk target config.",
                },
                "note": {
                    "type": "string",
                    "description": "Human-readable post-restart confirmation note.",
                },
                "restart_delay_s": {
                    "type": "number",
                    "minimum": 0,
                },
            },
            "required": ["action"],
            "additionalProperties": False,
        }

    def _reject_unsupported_session(self, ctx: ToolContext) -> None:
        session_id = str(ctx.session_id or "").strip().lower()
        if session_id.startswith(_DISALLOWED_SESSION_PREFIXES) or ":sub:" in session_id:
            raise RuntimeError("gateway_admin_not_allowed_in_background_or_subagent_sessions")

    def _config_snapshot(self) -> dict[str, Any]:
        effective = load_raw_config_payload(self._config_path, profile=self._config_profile)
        target = load_target_config_payload(self._config_path, profile=self._config_profile)
        return {
            "ok": True,
            "config_path": str(self._config_path or ""),
            "config_profile": str(self._config_profile or ""),
            "effective_config": _redact_payload(effective),
            "target_config": _redact_payload(target),
        }

    def _ensure_restart_not_pending(self) -> None:
        if gateway_restart_pending():
            raise RuntimeError("gateway_restart_already_pending")

    def _apply_patch_and_restart(self, arguments: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
        raw_patch = arguments.get("patch")
        if not isinstance(raw_patch, dict) or not raw_patch:
            raise RuntimeError("gateway_admin_requires_non_empty_patch")

        target_payload = load_target_config_payload(self._config_path, profile=self._config_profile)
        base_payload = load_raw_config_payload(self._config_path, profile=None) if self._config_profile else {}
        updated_target = _deep_merge(target_payload, raw_patch)
        effective_candidate = _deep_merge(base_payload, updated_target) if self._config_profile else updated_target
        _validate_config_keys(effective_candidate)
        AppConfig.model_validate(effective_candidate)

        changed_paths = sorted(set(_flatten_patch_paths(raw_patch)))
        if updated_target == target_payload:
            return {
                "ok": True,
                "action": "config_patch_and_restart",
                "changed": False,
                "restart_scheduled": False,
                "changed_paths": changed_paths,
                "config_path": str(self._config_path or ""),
                "config_profile": str(self._config_profile or ""),
            }

        self._ensure_restart_not_pending()
        saved_path = save_raw_config_payload(updated_target, self._config_path, profile=self._config_profile)
        note = str(arguments.get("note", "") or "").strip() or _default_note(changed_paths=changed_paths)
        try:
            sentinel_payload = build_restart_sentinel_payload(
                kind="config_patch",
                session_id=str(ctx.session_id or "").strip(),
                channel=str(ctx.channel or "").strip().lower(),
                target=derive_restart_target(
                    session_id=str(ctx.session_id or "").strip(),
                    channel=str(ctx.channel or "").strip().lower(),
                    user_id=str(ctx.user_id or "").strip(),
                ),
                note=note,
                changed_paths=changed_paths,
                metadata=derive_restart_metadata(
                    session_id=str(ctx.session_id or "").strip(),
                    channel=str(ctx.channel or "").strip().lower(),
                ),
            )
            sentinel_path = write_restart_sentinel(state_path=self._state_path, payload=sentinel_payload)
            restart = schedule_gateway_restart(
                delay_s=max(0.0, float(arguments.get("restart_delay_s", 1.5) or 1.5)),
                reason="config_patch_and_restart",
            )
        except Exception:
            save_raw_config_payload(target_payload, self._config_path, profile=self._config_profile)
            clear_restart_sentinel(self._state_path)
            raise
        return {
            "ok": True,
            "action": "config_patch_and_restart",
            "changed": True,
            "changed_paths": changed_paths,
            "saved_path": str(saved_path),
            "config_path": str(self._config_path or ""),
            "config_profile": str(self._config_profile or ""),
            "restart": restart,
            "sentinel_path": str(sentinel_path),
            "note": note,
        }

    def _restart_gateway(self, arguments: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
        self._ensure_restart_not_pending()
        note = str(arguments.get("note", "") or "").strip() or "Restarted the gateway as requested."
        try:
            sentinel_payload = build_restart_sentinel_payload(
                kind="restart",
                session_id=str(ctx.session_id or "").strip(),
                channel=str(ctx.channel or "").strip().lower(),
                target=derive_restart_target(
                    session_id=str(ctx.session_id or "").strip(),
                    channel=str(ctx.channel or "").strip().lower(),
                    user_id=str(ctx.user_id or "").strip(),
                ),
                note=note,
                changed_paths=[],
                metadata=derive_restart_metadata(
                    session_id=str(ctx.session_id or "").strip(),
                    channel=str(ctx.channel or "").strip().lower(),
                ),
            )
            sentinel_path = write_restart_sentinel(state_path=self._state_path, payload=sentinel_payload)
            restart = schedule_gateway_restart(
                delay_s=max(0.0, float(arguments.get("restart_delay_s", 1.5) or 1.5)),
                reason="restart_gateway",
            )
        except Exception:
            clear_restart_sentinel(self._state_path)
            raise
        return {
            "ok": True,
            "action": "restart_gateway",
            "restart": restart,
            "sentinel_path": str(sentinel_path),
            "note": note,
        }

    async def run(self, arguments: dict[str, Any], ctx: ToolContext) -> str:
        self._reject_unsupported_session(ctx)
        action = str(arguments.get("action", "") or "").strip().lower()
        if action == "config_get":
            payload = self._config_snapshot()
        elif action == "config_patch_and_restart":
            with _GATEWAY_ADMIN_RESTART_LOCK:
                payload = self._apply_patch_and_restart(arguments, ctx)
        elif action == "restart_gateway":
            with _GATEWAY_ADMIN_RESTART_LOCK:
                payload = self._restart_gateway(arguments, ctx)
        else:
            raise RuntimeError(f"unsupported_gateway_admin_action:{action or 'unknown'}")
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)


__all__ = ["GatewayAdminTool"]
