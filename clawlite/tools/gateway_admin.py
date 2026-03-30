from __future__ import annotations

import hashlib
import json
import re
import threading
import types
from pathlib import Path
from typing import Any, get_args, get_origin

from pydantic import BaseModel

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
_INTENT_NAME_RE = re.compile(r"^[a-z_][a-z0-9_]*$")
_LOOKUP_PATH_RE = re.compile(r"^[a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)*$")
_PREVIEW_TOKEN_RE = re.compile(r"^[0-9a-f]{64}$")
_TOOL_NAME_RE = re.compile(r"^[a-z_][a-z0-9_]*(?::[a-z_][a-z0-9_]*)*$")
_GATEWAY_ADMIN_RESTART_LOCK = threading.Lock()
_SAFE_EDITABLE_PATH_PATTERNS: tuple[str, ...] = (
    "tools.restrict_to_workspace",
    "tools.default_timeout_s",
    "tools.timeouts.*",
    "tools.loop_detection.enabled",
    "tools.loop_detection.history_size",
    "tools.loop_detection.repeat_threshold",
    "tools.loop_detection.critical_threshold",
    "tools.web.timeout",
    "tools.web.search_timeout",
    "tools.web.max_redirects",
    "tools.web.max_chars",
    "tools.web.block_private_addresses",
)
_PROTECTED_PATH_PATTERNS: tuple[str, ...] = (
    "workspace_path",
    "state_path",
    "provider.*",
    "providers.*",
    "auth.*",
    "agents.*",
    "channels.*",
    "bus.*",
    "observability.*",
    "jobs.*",
    "gateway.auth.*",
    "tools.exec.*",
    "tools.mcp.*",
    "tools.safety.*",
    "tools.web.proxy",
    "tools.web.brave_api_key",
    "tools.web.brave_base_url",
    "tools.web.searxng_base_url",
    "tools.web.allowlist",
    "tools.web.denylist",
)
_SAFE_INTENT_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "name": "set_default_tool_timeout",
        "summary": "Set the default timeout applied to tools without a per-tool override.",
        "paths": ["tools.default_timeout_s"],
        "required_args": ["timeout_s"],
        "optional_args": [],
    },
    {
        "name": "set_tool_timeout",
        "summary": "Set the timeout for one named tool.",
        "paths": ["tools.timeouts.<tool_name>"],
        "required_args": ["tool_name", "timeout_s"],
        "optional_args": [],
    },
    {
        "name": "set_workspace_tool_restriction",
        "summary": "Toggle workspace-only restriction for tool execution.",
        "paths": ["tools.restrict_to_workspace"],
        "required_args": ["enabled"],
        "optional_args": [],
    },
    {
        "name": "set_loop_detection",
        "summary": "Tune the bounded loop-detection settings for tools.",
        "paths": [
            "tools.loop_detection.enabled",
            "tools.loop_detection.history_size",
            "tools.loop_detection.repeat_threshold",
            "tools.loop_detection.critical_threshold",
        ],
        "required_args": [],
        "requires_any_of": ["enabled", "history_size", "repeat_threshold", "critical_threshold"],
        "optional_args": ["enabled", "history_size", "repeat_threshold", "critical_threshold"],
    },
    {
        "name": "set_web_timeouts",
        "summary": "Adjust web fetch and search timeout values.",
        "paths": ["tools.web.timeout", "tools.web.search_timeout"],
        "required_args": [],
        "requires_any_of": ["timeout_s", "search_timeout_s"],
        "optional_args": ["timeout_s", "search_timeout_s"],
    },
    {
        "name": "set_web_content_budget",
        "summary": "Set the max-char budget returned by web fetch.",
        "paths": ["tools.web.max_chars"],
        "required_args": ["max_chars"],
        "optional_args": [],
    },
    {
        "name": "set_web_private_address_blocking",
        "summary": "Toggle private-address blocking for web fetch.",
        "paths": ["tools.web.block_private_addresses"],
        "required_args": ["enabled"],
        "optional_args": [],
    },
    {
        "name": "set_web_fetch_limits",
        "summary": "Adjust several safe web fetch limits in one bounded intent.",
        "paths": [
            "tools.web.timeout",
            "tools.web.search_timeout",
            "tools.web.max_redirects",
            "tools.web.max_chars",
            "tools.web.block_private_addresses",
        ],
        "required_args": [],
        "requires_any_of": [
            "timeout_s",
            "search_timeout_s",
            "max_redirects",
            "max_chars",
            "block_private_addresses",
        ],
        "optional_args": [
            "timeout_s",
            "search_timeout_s",
            "max_redirects",
            "max_chars",
            "block_private_addresses",
        ],
    },
)


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


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _normalize_lookup_path(value: Any) -> str:
    path = str(value or "").strip().lower()
    if not path:
        raise RuntimeError("gateway_admin_lookup_path_required")
    if len(path) > 160 or _LOOKUP_PATH_RE.fullmatch(path) is None:
        raise RuntimeError("gateway_admin_lookup_path_invalid")
    return path


def _path_matches_pattern(path: str, pattern: str) -> bool:
    path_parts = [part for part in str(path or "").split(".") if part]
    pattern_parts = [part for part in str(pattern or "").split(".") if part]
    if len(path_parts) != len(pattern_parts):
        return False
    for current, expected in zip(path_parts, pattern_parts, strict=False):
        if expected != "*" and current != expected:
            return False
    return True


def _path_has_pattern_descendant(path: str, pattern: str) -> bool:
    path_parts = [part for part in str(path or "").split(".") if part]
    pattern_parts = [part for part in str(pattern or "").split(".") if part]
    if len(pattern_parts) <= len(path_parts):
        return False
    for current, expected in zip(path_parts, pattern_parts[: len(path_parts)], strict=False):
        if expected != "*" and current != expected:
            return False
    return True


def _path_is_safe_editable(path: str) -> bool:
    return any(_path_matches_pattern(path, pattern) for pattern in _SAFE_EDITABLE_PATH_PATTERNS)


def _path_has_safe_descendants(path: str) -> bool:
    return any(_path_has_pattern_descendant(path, pattern) for pattern in _SAFE_EDITABLE_PATH_PATTERNS)


def _path_is_protected(path: str) -> bool:
    return any(_path_matches_pattern(path, pattern) for pattern in _PROTECTED_PATH_PATTERNS)


def _path_has_protected_descendants(path: str) -> bool:
    return any(_path_has_pattern_descendant(path, pattern) for pattern in _PROTECTED_PATH_PATTERNS)


def _path_mutation_status(path: str) -> tuple[str, str]:
    if _path_is_safe_editable(path):
        return ("editable", "safe_allowlist")
    if _path_is_protected(path):
        return ("protected", "protected_path")
    if _path_has_safe_descendants(path):
        if _path_has_protected_descendants(path):
            return ("container", "mixed_descendants")
        return ("container", "editable_descendants")
    if _path_has_protected_descendants(path):
        return ("protected", "protected_path")
    return ("readonly", "not_allowlisted")


def _unwrap_annotation(annotation: Any) -> Any:
    current = annotation
    while True:
        origin = get_origin(current)
        if origin in (types.UnionType, getattr(__import__("typing"), "Union", object)):
            args = [item for item in get_args(current) if item is not type(None)]
            if len(args) == 1:
                current = args[0]
                continue
        return current


def _model_type(annotation: Any) -> type[BaseModel] | None:
    current = _unwrap_annotation(annotation)
    if isinstance(current, type) and issubclass(current, BaseModel):
        return current
    return None


def _annotation_kind(annotation: Any) -> str:
    current = _unwrap_annotation(annotation)
    model_type = _model_type(current)
    if model_type is not None:
        return "object"
    origin = get_origin(current)
    if origin is dict:
        return "object"
    if origin in (list, tuple, set):
        return "array"
    if current is bool:
        return "boolean"
    if current is int:
        return "integer"
    if current is float:
        return "number"
    if current is str:
        return "string"
    return "unknown"


def _lookup_payload_value(payload: dict[str, Any], path: str) -> tuple[bool, Any]:
    current: Any = payload
    for segment in [part for part in path.split(".") if part]:
        if not isinstance(current, dict) or segment not in current:
            return (False, None)
        current = current[segment]
    return (True, current)


def _field_label(segment: str, field: Any | None) -> str:
    if field is not None:
        title = str(getattr(field, "title", "") or "").strip()
        if title:
            return title
    return str(segment or "").replace("_", " ").strip().title()


def _field_description(field: Any | None) -> str:
    return str(getattr(field, "description", "") or "").strip()


def _schema_lookup_node(path: str) -> tuple[Any, Any | None, bool]:
    current_annotation: Any = AppConfig
    current_field = None
    dynamic_key = False
    for segment in [part for part in path.split(".") if part]:
        model_cls = _model_type(current_annotation)
        if model_cls is not None:
            field = model_cls.model_fields.get(segment)
            if field is None:
                raise RuntimeError(f"gateway_admin_lookup_path_not_found:{path}")
            current_field = field
            current_annotation = field.annotation
            dynamic_key = False
            continue
        current = _unwrap_annotation(current_annotation)
        origin = get_origin(current)
        if origin is dict:
            args = get_args(current)
            current_field = None
            current_annotation = args[1] if len(args) >= 2 else Any
            dynamic_key = True
            continue
        raise RuntimeError(f"gateway_admin_lookup_path_not_found:{path}")
    return current_annotation, current_field, dynamic_key


def _schema_lookup_children(*, path: str, annotation: Any, current_payload: dict[str, Any], default_payload: dict[str, Any]) -> list[dict[str, Any]]:
    current = _unwrap_annotation(annotation)
    model_cls = _model_type(current)
    if model_cls is not None:
        children: list[dict[str, Any]] = []
        for key, field in model_cls.model_fields.items():
            child_path = f"{path}.{key}"
            status, reason = _path_mutation_status(child_path)
            children.append(
                {
                    "key": key,
                    "path": child_path,
                    "label": _field_label(key, field),
                    "type": _annotation_kind(field.annotation),
                    "editable_via_gateway_admin": status == "editable",
                    "status": status,
                    "reason": reason,
                    "has_children": _annotation_kind(field.annotation) == "object",
                }
            )
        return children
    if get_origin(current) is dict:
        present_keys: set[str] = set()
        current_present, current_value = _lookup_payload_value(current_payload, path)
        default_present, default_value = _lookup_payload_value(default_payload, path)
        for source in (current_value if current_present else {}, default_value if default_present else {}):
            if isinstance(source, dict):
                present_keys.update(str(key or "").strip() for key in source.keys() if str(key or "").strip())
        value_annotation = get_args(current)[1] if len(get_args(current)) >= 2 else Any
        children = []
        for key in sorted(present_keys)[:20]:
            child_path = f"{path}.{key}"
            status, reason = _path_mutation_status(child_path)
            children.append(
                {
                    "key": key,
                    "path": child_path,
                    "label": key,
                    "type": _annotation_kind(value_annotation),
                    "editable_via_gateway_admin": status == "editable",
                    "status": status,
                    "reason": reason,
                    "has_children": _annotation_kind(value_annotation) == "object",
                }
            )
        return children
    return []


def _validate_patch_paths(patch: dict[str, Any]) -> list[str]:
    changed_paths = sorted({_normalize_lookup_path(item) for item in _flatten_patch_paths(patch)})
    for path in changed_paths:
        _schema_lookup_node(path)
        status, _reason = _path_mutation_status(path)
        if status == "editable":
            continue
        if status == "protected":
            raise RuntimeError(f"gateway_admin_patch_path_protected:{path}")
        raise RuntimeError(f"gateway_admin_patch_path_not_editable:{path}:{status}")
    return changed_paths


def _normalize_intent_name(value: Any) -> str:
    intent = str(value or "").strip().lower()
    if not intent:
        raise RuntimeError("gateway_admin_intent_required")
    if len(intent) > 80 or _INTENT_NAME_RE.fullmatch(intent) is None:
        raise RuntimeError("gateway_admin_intent_invalid")
    return intent


def _normalize_tool_name(value: Any) -> str:
    tool_name = str(value or "").strip().lower().replace("-", "_")
    if not tool_name:
        raise RuntimeError("gateway_admin_tool_name_required")
    if len(tool_name) > 80 or _TOOL_NAME_RE.fullmatch(tool_name) is None:
        raise RuntimeError("gateway_admin_tool_name_invalid")
    return tool_name


def _normalize_preview_token(value: Any) -> str:
    token = str(value or "").strip().lower()
    if not token:
        return ""
    if _PREVIEW_TOKEN_RE.fullmatch(token) is None:
        raise RuntimeError("gateway_admin_preview_token_invalid")
    return token


def _coerce_bool_argument(value: Any, *, key: str) -> bool:
    if isinstance(value, bool):
        return value
    token = str(value or "").strip().lower()
    if token in {"1", "true", "yes", "on"}:
        return True
    if token in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"gateway_admin_argument_invalid_bool:{key}")


def _coerce_int_argument(value: Any, *, key: str, minimum: int = 1) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"gateway_admin_argument_invalid_int:{key}") from exc
    if parsed < minimum:
        raise RuntimeError(f"gateway_admin_argument_invalid_int:{key}")
    return parsed


def _coerce_float_argument(value: Any, *, key: str, minimum: float = 0.1) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"gateway_admin_argument_invalid_number:{key}") from exc
    if parsed < minimum:
        raise RuntimeError(f"gateway_admin_argument_invalid_number:{key}")
    return parsed


def _build_intent_patch(arguments: dict[str, Any]) -> tuple[str, dict[str, Any], str]:
    intent = _normalize_intent_name(arguments.get("intent"))
    if intent == "set_default_tool_timeout":
        timeout_s = _coerce_float_argument(arguments.get("timeout_s"), key="timeout_s")
        return (
            intent,
            {"tools": {"default_timeout_s": timeout_s}},
            f"Updated the default tool timeout to {timeout_s:g}s.",
        )
    if intent == "set_tool_timeout":
        tool_name = _normalize_tool_name(arguments.get("tool_name"))
        timeout_s = _coerce_float_argument(arguments.get("timeout_s"), key="timeout_s")
        return (
            intent,
            {"tools": {"timeouts": {tool_name: timeout_s}}},
            f"Updated the `{tool_name}` tool timeout to {timeout_s:g}s.",
        )
    if intent == "set_workspace_tool_restriction":
        enabled = _coerce_bool_argument(arguments.get("enabled"), key="enabled")
        return (
            intent,
            {"tools": {"restrict_to_workspace": enabled}},
            "Restricted tools to the workspace only."
            if enabled
            else "Removed the workspace-only tool restriction.",
        )
    if intent == "set_loop_detection":
        patch: dict[str, Any] = {}
        if "enabled" in arguments:
            patch["enabled"] = _coerce_bool_argument(arguments.get("enabled"), key="enabled")
        if "history_size" in arguments:
            patch["history_size"] = _coerce_int_argument(arguments.get("history_size"), key="history_size")
        if "repeat_threshold" in arguments:
            patch["repeat_threshold"] = _coerce_int_argument(
                arguments.get("repeat_threshold"),
                key="repeat_threshold",
            )
        if "critical_threshold" in arguments:
            patch["critical_threshold"] = _coerce_int_argument(
                arguments.get("critical_threshold"),
                key="critical_threshold",
            )
        if not patch:
            raise RuntimeError("gateway_admin_loop_detection_update_required")
        note = "Updated tool loop-detection settings."
        if set(patch) == {"enabled"}:
            note = "Enabled tool loop detection." if patch["enabled"] else "Disabled tool loop detection."
        return (intent, {"tools": {"loop_detection": patch}}, note)
    if intent == "set_web_timeouts":
        patch: dict[str, Any] = {}
        if "timeout_s" in arguments:
            patch["timeout"] = _coerce_float_argument(arguments.get("timeout_s"), key="timeout_s", minimum=1.0)
        if "search_timeout_s" in arguments or "search_timeout" in arguments:
            patch["search_timeout"] = _coerce_float_argument(
                arguments.get("search_timeout_s", arguments.get("search_timeout")),
                key="search_timeout_s",
                minimum=1.0,
            )
        if not patch:
            raise RuntimeError("gateway_admin_web_timeout_update_required")
        if set(patch) == {"timeout"}:
            return (
                intent,
                {"tools": {"web": patch}},
                f"Updated the web fetch timeout to {patch['timeout']:g}s.",
            )
        if set(patch) == {"search_timeout"}:
            return (
                intent,
                {"tools": {"web": patch}},
                f"Updated the web search timeout to {patch['search_timeout']:g}s.",
            )
        return (intent, {"tools": {"web": patch}}, "Updated web fetch timeouts.")
    if intent == "set_web_content_budget":
        max_chars = _coerce_int_argument(arguments.get("max_chars"), key="max_chars", minimum=128)
        return (
            intent,
            {"tools": {"web": {"max_chars": max_chars}}},
            f"Updated the web fetch max-char budget to {max_chars}.",
        )
    if intent == "set_web_private_address_blocking":
        enabled = _coerce_bool_argument(arguments.get("enabled"), key="enabled")
        return (
            intent,
            {"tools": {"web": {"block_private_addresses": enabled}}},
            "Enabled web private-address blocking." if enabled else "Disabled web private-address blocking.",
        )
    if intent == "set_web_fetch_limits":
        patch: dict[str, Any] = {}
        if "timeout_s" in arguments:
            patch["timeout"] = _coerce_float_argument(arguments.get("timeout_s"), key="timeout_s", minimum=1.0)
        if "search_timeout_s" in arguments or "search_timeout" in arguments:
            patch["search_timeout"] = _coerce_float_argument(
                arguments.get("search_timeout_s", arguments.get("search_timeout")),
                key="search_timeout_s",
                minimum=1.0,
            )
        if "max_redirects" in arguments:
            patch["max_redirects"] = _coerce_int_argument(arguments.get("max_redirects"), key="max_redirects", minimum=0)
        if "max_chars" in arguments:
            patch["max_chars"] = _coerce_int_argument(arguments.get("max_chars"), key="max_chars", minimum=128)
        if "block_private_addresses" in arguments:
            patch["block_private_addresses"] = _coerce_bool_argument(
                arguments.get("block_private_addresses"),
                key="block_private_addresses",
            )
        if not patch:
            raise RuntimeError("gateway_admin_web_fetch_update_required")
        if set(patch) == {"block_private_addresses"}:
            return (
                intent,
                {"tools": {"web": patch}},
                "Enabled web private-address blocking."
                if patch["block_private_addresses"]
                else "Disabled web private-address blocking.",
            )
        return (intent, {"tools": {"web": patch}}, "Updated web fetch limits.")
    raise RuntimeError(f"gateway_admin_intent_unsupported:{intent}")


def _intent_catalog_rows(*, requested_intent: str = "") -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    normalized_requested = str(requested_intent or "").strip().lower()
    for spec in _SAFE_INTENT_CATALOG:
        name = str(spec.get("name", "") or "").strip().lower()
        if normalized_requested and name != normalized_requested:
            continue
        rows.append(
            {
                "name": name,
                "summary": str(spec.get("summary", "") or "").strip(),
                "paths": [str(item or "").strip() for item in list(spec.get("paths", []) or []) if str(item or "").strip()],
                "required_args": [
                    str(item or "").strip()
                    for item in list(spec.get("required_args", []) or [])
                    if str(item or "").strip()
                ],
                "requires_any_of": [
                    str(item or "").strip()
                    for item in list(spec.get("requires_any_of", []) or [])
                    if str(item or "").strip()
                ],
                "optional_args": [
                    str(item or "").strip()
                    for item in list(spec.get("optional_args", []) or [])
                    if str(item or "").strip()
                ],
                "preview_action": "config_intent_preview",
                "apply_action": "config_intent_and_restart",
            }
        )
    return rows


class GatewayAdminTool(Tool):
    name = "gateway_admin"
    description = (
        "Inspect the active config, apply a partial config patch, and restart the ClawLite gateway. "
        "Use only when the user explicitly asks to change config or restart the runtime. "
        "Prefer config_intent_catalog to discover supported safe presets, then use config_intent_preview or config_intent_and_restart, "
        "and use config_schema_lookup or config_patch_preview before raw patching. "
        "For config_patch_and_restart, always pass a short human-readable note describing what was enabled or changed; "
        "ClawLite will send that note back after the gateway restarts. "
        "When applying after a preview, carry the preview_token from config_intent_preview or config_patch_preview into the real apply call."
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
                    "enum": [
                        "config_get",
                        "config_schema_lookup",
                        "config_intent_catalog",
                        "config_patch_preview",
                        "config_intent_preview",
                        "config_intent_and_restart",
                        "config_patch_and_restart",
                        "restart_gateway",
                    ],
                },
                "path": {
                    "type": "string",
                    "description": "Snake_case config path to inspect, for example tools.default_timeout_s.",
                },
                "intent": {
                    "type": "string",
                    "description": (
                        "Safe preset for config_intent_catalog, config_intent_preview, or config_intent_and_restart, "
                        "for example set_default_tool_timeout, set_tool_timeout, set_workspace_tool_restriction, set_loop_detection, set_web_timeouts, "
                        "set_web_content_budget, set_web_private_address_blocking, or set_web_fetch_limits."
                    ),
                },
                "patch": {
                    "type": "object",
                    "description": (
                        "Partial snake_case config patch merged into the current on-disk target config. "
                        "Only gateway_admin allowlisted tool-tuning paths may be changed. "
                        "Use with config_patch_preview before config_patch_and_restart when the patch is not one of the bounded safe intents."
                    ),
                },
                "note": {
                    "type": "string",
                    "description": "Human-readable post-restart confirmation note.",
                },
                "preview_token": {
                    "type": "string",
                    "description": (
                        "Optional verification token returned by config_intent_preview or config_patch_preview. "
                        "If supplied on config_intent_and_restart or config_patch_and_restart, the live apply must "
                        "match the previewed patch, note, and config base or the tool fails closed."
                    ),
                },
                "restart_delay_s": {
                    "type": "number",
                    "minimum": 0,
                },
                "enabled": {
                    "type": "boolean",
                    "description": "Boolean flag used by safe intents such as set_loop_detection.",
                },
                "tool_name": {
                    "type": "string",
                    "description": "Tool name used by set_tool_timeout, for example web_fetch.",
                },
                "timeout_s": {
                    "type": "number",
                    "minimum": 0.1,
                    "description": "Timeout value used by safe timeout intents.",
                },
                "history_size": {
                    "type": "integer",
                    "minimum": 1,
                },
                "repeat_threshold": {
                    "type": "integer",
                    "minimum": 1,
                },
                "critical_threshold": {
                    "type": "integer",
                    "minimum": 1,
                },
                "search_timeout_s": {
                    "type": "number",
                    "minimum": 1.0,
                },
                "max_redirects": {
                    "type": "integer",
                    "minimum": 0,
                },
                "max_chars": {
                    "type": "integer",
                    "minimum": 128,
                },
                "block_private_addresses": {
                    "type": "boolean",
                    "description": "Boolean flag used by set_web_fetch_limits.",
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

    def _config_schema_lookup(self, arguments: dict[str, Any]) -> dict[str, Any]:
        path = _normalize_lookup_path(arguments.get("path"))
        annotation, field, dynamic_key = _schema_lookup_node(path)
        effective_payload = load_raw_config_payload(self._config_path, profile=self._config_profile)
        target_payload = load_target_config_payload(self._config_path, profile=self._config_profile)
        default_payload = AppConfig().to_dict()
        current_present, current_value = _lookup_payload_value(effective_payload, path)
        target_present, target_value = _lookup_payload_value(target_payload, path)
        default_present, default_value = _lookup_payload_value(default_payload, path)
        status, reason = _path_mutation_status(path)
        node_kind = _annotation_kind(annotation)
        return {
            "ok": True,
            "action": "config_schema_lookup",
            "config_path": str(self._config_path or ""),
            "config_profile": str(self._config_profile or ""),
            "path": path,
            "label": _field_label(path.rsplit(".", 1)[-1], field),
            "description": _field_description(field),
            "type": node_kind,
            "status": status,
            "reason": reason,
            "editable_via_gateway_admin": status == "editable",
            "dynamic_key": dynamic_key,
            "has_children": node_kind == "object",
            "effective_value_present": current_present,
            "effective_value": _redact_payload(current_value) if current_present else None,
            "target_value_present": target_present,
            "target_value": _redact_payload(target_value) if target_present else None,
            "default_value_present": default_present,
            "default_value": _redact_payload(default_value) if default_present else None,
            "children": _schema_lookup_children(
                path=path,
                annotation=annotation,
                current_payload=effective_payload,
                default_payload=default_payload,
            ),
        }

    def _config_intent_catalog(self, arguments: dict[str, Any]) -> dict[str, Any]:
        requested = ""
        if str(arguments.get("intent", "") or "").strip():
            requested = _normalize_intent_name(arguments.get("intent"))
        rows = _intent_catalog_rows(requested_intent=requested)
        if requested and not rows:
            raise RuntimeError(f"gateway_admin_intent_unsupported:{requested}")
        return {
            "ok": True,
            "action": "config_intent_catalog",
            "config_path": str(self._config_path or ""),
            "config_profile": str(self._config_profile or ""),
            "intent": requested,
            "count": len(rows),
            "intents": rows,
        }

    def _ensure_restart_not_pending(self) -> None:
        if gateway_restart_pending():
            raise RuntimeError("gateway_restart_already_pending")

    def _preview_token(
        self,
        *,
        preview_scope: str,
        patch: dict[str, Any],
        note: str,
        target_payload: dict[str, Any],
    ) -> tuple[str, str]:
        basis_hash = hashlib.sha256(_canonical_json(target_payload).encode("utf-8")).hexdigest()
        token_payload = {
            "preview_scope": str(preview_scope or "").strip().lower(),
            "patch": patch,
            "note": note,
            "config_path": str(self._config_path or ""),
            "config_profile": str(self._config_profile or ""),
            "target_basis_hash": basis_hash,
        }
        token = hashlib.sha256(_canonical_json(token_payload).encode("utf-8")).hexdigest()
        return (token, basis_hash)

    def _verify_preview_token(
        self,
        *,
        arguments: dict[str, Any],
        preview_scope: str,
        patch: dict[str, Any],
        note: str,
        target_payload: dict[str, Any],
    ) -> None:
        provided = _normalize_preview_token(arguments.get("preview_token"))
        if not provided:
            return
        expected, _basis_hash = self._preview_token(
            preview_scope=preview_scope,
            patch=patch,
            note=note,
            target_payload=target_payload,
        )
        if provided != expected:
            raise RuntimeError("gateway_admin_preview_token_mismatch")

    def _preview_patch(self, *, patch: dict[str, Any], note: str, action: str, preview_scope: str) -> dict[str, Any]:
        changed_paths = _validate_patch_paths(patch)
        effective_payload = load_raw_config_payload(self._config_path, profile=self._config_profile)
        target_payload = load_target_config_payload(self._config_path, profile=self._config_profile)
        base_payload = load_raw_config_payload(self._config_path, profile=None) if self._config_profile else {}
        updated_target = _deep_merge(target_payload, patch)
        effective_candidate = _deep_merge(base_payload, updated_target) if self._config_profile else updated_target
        _validate_config_keys(effective_candidate)
        AppConfig.model_validate(effective_candidate)
        default_payload = AppConfig().to_dict()
        changes: list[dict[str, Any]] = []
        for path in changed_paths:
            status, reason = _path_mutation_status(path)
            effective_present, effective_value = _lookup_payload_value(effective_payload, path)
            target_present, target_value = _lookup_payload_value(target_payload, path)
            effective_next_present, effective_next_value = _lookup_payload_value(effective_candidate, path)
            target_next_present, target_next_value = _lookup_payload_value(updated_target, path)
            default_present, default_value = _lookup_payload_value(default_payload, path)
            changes.append(
                {
                    "path": path,
                    "editable_via_gateway_admin": status == "editable",
                    "status": status,
                    "reason": reason,
                    "effective_value_present": effective_present,
                    "effective_value": _redact_payload(effective_value) if effective_present else None,
                    "target_value_present": target_present,
                    "target_value": _redact_payload(target_value) if target_present else None,
                    "effective_next_value_present": effective_next_present,
                    "effective_next_value": _redact_payload(effective_next_value) if effective_next_present else None,
                    "target_next_value_present": target_next_present,
                    "target_next_value": _redact_payload(target_next_value) if target_next_present else None,
                    "default_value_present": default_present,
                    "default_value": _redact_payload(default_value) if default_present else None,
                    "would_change": (
                        (not target_present and target_next_present)
                        or target_value != target_next_value
                        or (not effective_present and effective_next_present)
                        or effective_value != effective_next_value
                    ),
                }
            )
        restart_required = updated_target != target_payload
        preview_token, basis_hash = self._preview_token(
            preview_scope=preview_scope,
            patch=patch,
            note=note,
            target_payload=target_payload,
        )
        return {
            "ok": True,
            "action": action,
            "preview_only": True,
            "changed_paths": changed_paths,
            "resolved_patch": patch,
            "preview_scope": preview_scope,
            "preview_basis_hash": basis_hash,
            "preview_token": preview_token,
            "would_change": restart_required,
            "config_path": str(self._config_path or ""),
            "config_profile": str(self._config_profile or ""),
            "note": note,
            "restart_note_preview": note,
            "restart_required": restart_required,
            "changes": changes,
        }

    def _apply_patch_and_restart(
        self,
        arguments: dict[str, Any],
        ctx: ToolContext,
        *,
        preview_scope: str = "config_patch",
    ) -> dict[str, Any]:
        raw_patch = arguments.get("patch")
        if not isinstance(raw_patch, dict) or not raw_patch:
            raise RuntimeError("gateway_admin_requires_non_empty_patch")
        changed_paths = _validate_patch_paths(raw_patch)
        note = str(arguments.get("note", "") or "").strip() or _default_note(changed_paths=changed_paths)

        target_payload = load_target_config_payload(self._config_path, profile=self._config_profile)
        base_payload = load_raw_config_payload(self._config_path, profile=None) if self._config_profile else {}
        updated_target = _deep_merge(target_payload, raw_patch)
        effective_candidate = _deep_merge(base_payload, updated_target) if self._config_profile else updated_target
        _validate_config_keys(effective_candidate)
        AppConfig.model_validate(effective_candidate)
        self._verify_preview_token(
            arguments=arguments,
            preview_scope=preview_scope,
            patch=raw_patch,
            note=note,
            target_payload=target_payload,
        )
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

    def _preview_raw_patch(self, arguments: dict[str, Any]) -> dict[str, Any]:
        raw_patch = arguments.get("patch")
        if not isinstance(raw_patch, dict) or not raw_patch:
            raise RuntimeError("gateway_admin_requires_non_empty_patch")
        changed_paths = _validate_patch_paths(raw_patch)
        note = str(arguments.get("note", "") or "").strip() or _default_note(changed_paths=changed_paths)
        return self._preview_patch(
            patch=raw_patch,
            note=note,
            action="config_patch_preview",
            preview_scope="config_patch",
        )

    def _apply_intent_and_restart(self, arguments: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
        intent, patch, default_note = _build_intent_patch(arguments)
        patch_arguments = dict(arguments)
        patch_arguments["patch"] = patch
        if not str(patch_arguments.get("note", "") or "").strip():
            patch_arguments["note"] = default_note
        payload = self._apply_patch_and_restart(
            patch_arguments,
            ctx,
            preview_scope=f"config_intent:{intent}",
        )
        payload["action"] = "config_intent_and_restart"
        payload["intent"] = intent
        payload["resolved_patch"] = patch
        return payload

    def _preview_intent(self, arguments: dict[str, Any]) -> dict[str, Any]:
        intent, patch, default_note = _build_intent_patch(arguments)
        note = str(arguments.get("note", "") or "").strip() or default_note
        payload = self._preview_patch(
            patch=patch,
            note=note,
            action="config_intent_preview",
            preview_scope=f"config_intent:{intent}",
        )
        payload["intent"] = intent
        return payload

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
        elif action == "config_schema_lookup":
            payload = self._config_schema_lookup(arguments)
        elif action == "config_intent_catalog":
            payload = self._config_intent_catalog(arguments)
        elif action == "config_patch_preview":
            payload = self._preview_raw_patch(arguments)
        elif action == "config_intent_preview":
            payload = self._preview_intent(arguments)
        elif action == "config_intent_and_restart":
            with _GATEWAY_ADMIN_RESTART_LOCK:
                payload = self._apply_intent_and_restart(arguments, ctx)
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
