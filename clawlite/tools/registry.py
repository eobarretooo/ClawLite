from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import json
import re
import shlex
import time
from typing import Any
from urllib.parse import urlsplit

from clawlite.config.schema import ToolSafetyPolicyConfig
from clawlite.runtime.telemetry import get_tracer, set_span_attributes
from clawlite.tools.base import Tool, ToolContext, ToolError, ToolTimeoutError


# ---------------------------------------------------------------------------
# LRU result cache
# ---------------------------------------------------------------------------

class _CacheEntry:
    __slots__ = ("value", "expires_at")

    def __init__(self, value: str, ttl_s: float) -> None:
        self.value = value
        self.expires_at = time.monotonic() + ttl_s


class ToolResultCache:
    """In-process LRU cache for cacheable tools. Max 256 entries, 5 min TTL."""

    MAX_ENTRIES = 256
    TTL_S = 300.0

    def __init__(self) -> None:
        self._store: dict[str, _CacheEntry] = {}
        self._order: list[str] = []

    @staticmethod
    def _key(tool_name: str, arguments: dict[str, Any]) -> str:
        try:
            raw = tool_name + json.dumps(arguments, sort_keys=True, default=str)
        except Exception:
            raw = tool_name + str(arguments)
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, tool_name: str, arguments: dict[str, Any]) -> str | None:
        key = self._key(tool_name, arguments)
        entry = self._store.get(key)
        if entry is None:
            return None
        if time.monotonic() > entry.expires_at:
            self._store.pop(key, None)
            try:
                self._order.remove(key)
            except ValueError:
                pass
            return None
        return entry.value

    def set(self, tool_name: str, arguments: dict[str, Any], value: str) -> None:
        key = self._key(tool_name, arguments)
        if key in self._store:
            try:
                self._order.remove(key)
            except ValueError:
                pass
        elif len(self._store) >= self.MAX_ENTRIES:
            evict = self._order.pop(0)
            self._store.pop(evict, None)
        self._store[key] = _CacheEntry(value, self.TTL_S)
        self._order.append(key)


class ToolRegistry:
    _EXEC_SHELL_META_RE = re.compile(r"(^|[^\\])(?:\|\||&&|[|<>;`])")
    _EXEC_POSIX_SHELL_BINARIES = frozenset({"bash", "dash", "ksh", "sh", "zsh"})
    _EXEC_WINDOWS_SHELL_BINARIES = frozenset({"cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh", "pwsh.exe"})
    _EXEC_POSIX_SHELL_FLAGS = frozenset({"-c", "-lc"})
    _EXEC_WINDOWS_SHELL_FLAGS = frozenset({"/c", "-c", "-command"})

    _APPROVAL_REQUEST_LIMIT = 256
    _APPROVAL_AUDIT_LIMIT = 200

    def __init__(
        self,
        *,
        safety: ToolSafetyPolicyConfig | None = None,
        default_timeout_s: float = 20.0,
        tool_timeouts: dict[str, float] | None = None,
    ) -> None:
        self._tools: dict[str, Tool] = {}
        self._safety = safety or ToolSafetyPolicyConfig()
        self._default_timeout_s = max(0.1, float(default_timeout_s))
        self._tool_timeouts = {
            str(key or "").strip().lower(): max(0.1, float(value))
            for key, value in dict(tool_timeouts or {}).items()
            if str(key or "").strip()
        }
        self._cache = ToolResultCache()
        self._approval_ttl_s = max(1.0, float(getattr(self._safety, "approval_grant_ttl_s", 900.0) or 900.0))
        self._approval_grants: dict[str, float] = {}
        self._approval_requests: dict[str, dict[str, Any]] = {}
        self._approval_request_order: list[str] = []
        self._approval_audits: list[dict[str, Any]] = []

    @staticmethod
    def _tool_exception_retryable(exc: Exception) -> bool:
        if isinstance(exc, ToolTimeoutError):
            return False
        if isinstance(exc, ToolError):
            return bool(exc.recoverable)
        return isinstance(exc, (RuntimeError, OSError, ConnectionError))

    @staticmethod
    def _apply_layer(
        *,
        target_risky_tools: list[str],
        target_risky_specifiers: list[str],
        target_approval_specifiers: list[str],
        target_approval_channels: list[str],
        target_blocked_channels: list[str],
        target_allowed_channels: list[str],
        layer: Any,
    ) -> tuple[list[str], list[str], list[str], list[str], list[str], list[str]]:
        risky_tools = target_risky_tools
        risky_specifiers = target_risky_specifiers
        approval_specifiers = target_approval_specifiers
        approval_channels = target_approval_channels
        blocked_channels = target_blocked_channels
        allowed_channels = target_allowed_channels
        if layer is None:
            return risky_tools, risky_specifiers, approval_specifiers, approval_channels, blocked_channels, allowed_channels
        if layer.risky_tools is not None:
            risky_tools = list(layer.risky_tools)
        if layer.risky_specifiers is not None:
            risky_specifiers = list(layer.risky_specifiers)
        if layer.approval_specifiers is not None:
            approval_specifiers = list(layer.approval_specifiers)
        if layer.approval_channels is not None:
            approval_channels = list(layer.approval_channels)
        if layer.blocked_channels is not None:
            blocked_channels = list(layer.blocked_channels)
        if layer.allowed_channels is not None:
            allowed_channels = list(layer.allowed_channels)
        return risky_tools, risky_specifiers, approval_specifiers, approval_channels, blocked_channels, allowed_channels

    @staticmethod
    def _derive_agent_from_session(session_id: str) -> str:
        raw = str(session_id or "").strip().lower()
        if not raw.startswith("agent:"):
            return ""
        parts = raw.split(":")
        if len(parts) < 3:
            return ""
        return parts[1].strip()

    def _resolve_effective_safety(
        self,
        *,
        session_id: str,
        channel: str,
    ) -> tuple[str, list[str], list[str], list[str], list[str], list[str], list[str]]:
        resolved_channel = str(channel or "").strip().lower() or self._derive_channel_from_session(session_id)
        resolved_agent = self._derive_agent_from_session(session_id)

        risky_tools = list(self._safety.risky_tools)
        risky_specifiers = list(self._safety.risky_specifiers)
        approval_specifiers = list(self._safety.approval_specifiers)
        approval_channels = list(self._safety.approval_channels)
        blocked_channels = list(self._safety.blocked_channels)
        allowed_channels = list(self._safety.allowed_channels)

        selected_profile = str(self._safety.profile or "").strip().lower()
        if selected_profile:
            profile_layer = self._safety.profiles.get(selected_profile)
            risky_tools, risky_specifiers, approval_specifiers, approval_channels, blocked_channels, allowed_channels = self._apply_layer(
                target_risky_tools=risky_tools,
                target_risky_specifiers=risky_specifiers,
                target_approval_specifiers=approval_specifiers,
                target_approval_channels=approval_channels,
                target_blocked_channels=blocked_channels,
                target_allowed_channels=allowed_channels,
                layer=profile_layer,
            )

        if resolved_agent:
            agent_layer = self._safety.by_agent.get(resolved_agent)
            risky_tools, risky_specifiers, approval_specifiers, approval_channels, blocked_channels, allowed_channels = self._apply_layer(
                target_risky_tools=risky_tools,
                target_risky_specifiers=risky_specifiers,
                target_approval_specifiers=approval_specifiers,
                target_approval_channels=approval_channels,
                target_blocked_channels=blocked_channels,
                target_allowed_channels=allowed_channels,
                layer=agent_layer,
            )

        if resolved_channel:
            channel_layer = self._safety.by_channel.get(resolved_channel)
            risky_tools, risky_specifiers, approval_specifiers, approval_channels, blocked_channels, allowed_channels = self._apply_layer(
                target_risky_tools=risky_tools,
                target_risky_specifiers=risky_specifiers,
                target_approval_specifiers=approval_specifiers,
                target_approval_channels=approval_channels,
                target_blocked_channels=blocked_channels,
                target_allowed_channels=allowed_channels,
                layer=channel_layer,
            )

        return (
            resolved_channel,
            risky_tools,
            risky_specifiers,
            approval_specifiers,
            approval_channels,
            blocked_channels,
            allowed_channels,
        )

    @staticmethod
    def _normalize_specifier_fragment(value: Any) -> str:
        text = str(value or "").strip().lower()
        if not text:
            return ""
        normalized = re.sub(r"[^a-z0-9]+", "-", text)
        return normalized.strip("-")

    @classmethod
    def _command_specifier(cls, raw_command: Any) -> str:
        command = str(raw_command or "").strip()
        if not command:
            return ""
        try:
            argv = shlex.split(command)
        except ValueError:
            return ""
        if not argv:
            return ""
        raw_binary = str(argv[0] or "").strip().strip("\"'")
        if not raw_binary:
            return ""
        parts = [part for part in re.split(r"[\\/]", raw_binary) if part]
        return cls._normalize_specifier_fragment(parts[-1] if parts else raw_binary)

    @classmethod
    def _exec_needs_shell_wrapper(cls, raw_command: Any) -> bool:
        command = str(raw_command or "")
        if not command.strip():
            return False
        if cls._EXEC_SHELL_META_RE.search(command):
            return True
        return "$(" in command

    @classmethod
    def _exec_uses_explicit_shell_wrapper(cls, raw_command: Any) -> bool:
        command = str(raw_command or "").strip()
        if not command:
            return False
        try:
            argv = shlex.split(command)
        except ValueError:
            return False
        if not argv:
            return False
        binary = cls._command_specifier(argv[0])
        if binary in cls._EXEC_POSIX_SHELL_BINARIES:
            return any(str(token).lower() in cls._EXEC_POSIX_SHELL_FLAGS for token in argv[1:-1])
        if binary in {"cmd", "cmd.exe"}:
            return any(str(token).lower() == "/c" for token in argv[1:-1])
        if binary in cls._EXEC_WINDOWS_SHELL_BINARIES:
            return any(str(token).lower() in cls._EXEC_WINDOWS_SHELL_FLAGS for token in argv[1:-1])
        return False

    @classmethod
    def _exec_env_key_fragments(cls, raw_env: Any) -> list[str]:
        if not isinstance(raw_env, dict):
            return []
        out: list[str] = []
        seen: set[str] = set()
        for key in sorted(raw_env.keys(), key=lambda item: str(item or "").strip().lower()):
            normalized = cls._normalize_specifier_fragment(key)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            out.append(normalized)
        return out

    @classmethod
    def _url_host_fragment(cls, raw_url: Any) -> str:
        value = str(raw_url or "").strip()
        if not value:
            return ""
        try:
            parsed = urlsplit(value)
        except Exception:
            return ""
        hostname = str(parsed.hostname or "").strip().lower()
        if not hostname:
            return ""
        return cls._normalize_specifier_fragment(hostname)

    @classmethod
    def _derive_tool_specifiers(cls, *, tool_name: str, arguments: dict[str, Any]) -> list[str]:
        normalized_tool = str(tool_name or "").strip().lower()
        if not normalized_tool:
            return []
        out: list[str] = [normalized_tool]
        seen = set(out)

        def _add_direct(candidate: str) -> None:
            normalized = str(candidate or "").strip().lower()
            if not normalized or normalized in seen:
                return
            seen.add(normalized)
            out.append(normalized)

        def _add(fragment: Any) -> None:
            normalized = cls._normalize_specifier_fragment(fragment)
            if not normalized:
                return
            _add_direct(f"{normalized_tool}:{normalized}")

        for key in ("action", "operation", "method", "mode"):
            _add(arguments.get(key))

        if normalized_tool == "run_skill":
            _add(arguments.get("name"))
        elif normalized_tool == "exec":
            command_fragment = cls._command_specifier(arguments.get("command"))
            if command_fragment:
                _add(command_fragment)
                _add_direct(f"{normalized_tool}:cmd")
                _add_direct(f"{normalized_tool}:cmd:{command_fragment}")
            if cls._exec_needs_shell_wrapper(arguments.get("command")) or cls._exec_uses_explicit_shell_wrapper(
                arguments.get("command")
            ):
                _add_direct(f"{normalized_tool}:shell")
                _add_direct(f"{normalized_tool}:shell-meta")
            env_fragments = cls._exec_env_key_fragments(arguments.get("env"))
            if env_fragments:
                _add_direct(f"{normalized_tool}:env")
                for fragment in env_fragments:
                    _add_direct(f"{normalized_tool}:env-key:{fragment}")
            if str(arguments.get("cwd", arguments.get("workdir")) or "").strip():
                _add_direct(f"{normalized_tool}:cwd")
        elif normalized_tool == "web_fetch":
            host_fragment = cls._url_host_fragment(arguments.get("url"))
            if host_fragment:
                _add_direct(f"{normalized_tool}:host")
                _add_direct(f"{normalized_tool}:host:{host_fragment}")
        elif normalized_tool == "browser":
            host_fragment = cls._url_host_fragment(arguments.get("url"))
            action_fragment = cls._normalize_specifier_fragment(arguments.get("action"))
            if host_fragment:
                _add_direct(f"{normalized_tool}:host")
                _add_direct(f"{normalized_tool}:host:{host_fragment}")
                if action_fragment:
                    _add_direct(f"{normalized_tool}:{action_fragment}:host")
                    _add_direct(f"{normalized_tool}:{action_fragment}:host:{host_fragment}")

        return out

    @staticmethod
    def _matches_specifier_rule(*, specifier: str, rule: str) -> bool:
        normalized_specifier = str(specifier or "").strip().lower()
        normalized_rule = str(rule or "").strip().lower()
        if not normalized_specifier or not normalized_rule:
            return False
        if normalized_specifier == normalized_rule:
            return True
        if normalized_rule.endswith(":*"):
            prefix = normalized_rule[:-2]
            return normalized_specifier == prefix or normalized_specifier.startswith(f"{prefix}:")
        return False

    @classmethod
    def _matched_specifier_rules(cls, *, tool_name: str, arguments: dict[str, Any], rules: list[str]) -> list[str]:
        if not rules:
            return []
        matched: list[str] = []
        for rule in rules:
            if any(cls._matches_specifier_rule(specifier=item, rule=rule) for item in cls._derive_tool_specifiers(tool_name=tool_name, arguments=arguments)):
                matched.append(rule)
        return matched

    @classmethod
    def _is_risky_by_safety(
        cls,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        risky_tools: list[str],
        risky_specifiers: list[str],
    ) -> bool:
        normalized_tool = str(tool_name or "").strip().lower()
        if normalized_tool in risky_tools:
            return True
        return bool(cls._matched_specifier_rules(tool_name=tool_name, arguments=arguments, rules=risky_specifiers))

    @staticmethod
    def _is_channel_blocked(*, channel: str, blocked_channels: list[str], allowed_channels: list[str]) -> bool:
        normalized_channel = str(channel or "").strip().lower()
        if not normalized_channel:
            return False
        if normalized_channel in allowed_channels:
            return False
        return normalized_channel in blocked_channels

    @staticmethod
    def _approval_grant_key(*, session_id: str, channel: str, rule: str) -> str:
        return "::".join(
            [
                str(session_id or "").strip(),
                str(channel or "").strip().lower(),
                str(rule or "").strip().lower(),
            ]
        )

    @staticmethod
    def _approval_exact_grant_key(*, request_id: str, session_id: str, channel: str, rule: str) -> str:
        return "::".join(
            [
                "exact",
                str(request_id or "").strip(),
                str(session_id or "").strip(),
                str(channel or "").strip().lower(),
                str(rule or "").strip().lower(),
            ]
        )

    @staticmethod
    def _parse_approval_grant_key(key: str) -> dict[str, str]:
        raw = str(key or "").strip()
        parts = raw.split("::")
        if len(parts) >= 5 and str(parts[0] or "").strip().lower() == "exact":
            return {
                "scope": "exact",
                "request_id": str(parts[1] or "").strip(),
                "session_id": str(parts[2] or "").strip(),
                "channel": str(parts[3] or "").strip().lower(),
                "rule": str(parts[4] or "").strip().lower(),
            }
        session_part, channel_part, rule_part = (parts + ["", "", ""])[:3]
        return {
            "scope": "legacy",
            "request_id": "",
            "session_id": str(session_part or "").strip(),
            "channel": str(channel_part or "").strip().lower(),
            "rule": str(rule_part or "").strip().lower(),
        }

    @staticmethod
    def _approval_rule_tool(rule: Any) -> str:
        text = str(rule or "").strip().lower()
        if not text:
            return ""
        return str(text.split(":", 1)[0] or "").strip().lower()

    @staticmethod
    def _utc_now_iso() -> str:
        return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")

    def _append_approval_audit(self, row: dict[str, Any]) -> None:
        if not isinstance(row, dict) or not row:
            return
        payload = dict(row)
        payload.setdefault("recorded_at", self._utc_now_iso())
        payload.setdefault("recorded_at_monotonic", time.monotonic())
        try:
            cloned = json.loads(json.dumps(payload, ensure_ascii=False, default=str))
            normalized = cloned if isinstance(cloned, dict) else payload
        except Exception:
            normalized = payload
        self._approval_audits.append(normalized)
        if len(self._approval_audits) > self._APPROVAL_AUDIT_LIMIT:
            self._approval_audits = self._approval_audits[-self._APPROVAL_AUDIT_LIMIT :]

    @staticmethod
    def _approval_audit_context(value: Any) -> dict[str, Any]:
        context = value if isinstance(value, dict) else {}
        payload = {
            "tool": str(context.get("tool", "") or "").strip().lower(),
            "command_binary": str(context.get("command_binary", "") or "").strip(),
            "shell_wrapper": bool(context.get("shell_wrapper", False)),
            "env_keys": list(context.get("env_keys", []) or []),
            "cwd": str(context.get("cwd", "") or "").strip(),
            "action": str(context.get("action", "") or "").strip().lower(),
            "method": str(context.get("method", "") or "").strip().upper(),
            "host": str(context.get("host", "") or "").strip().lower(),
            "name": str(context.get("name", "") or "").strip(),
        }
        return {key: item for key, item in payload.items() if item not in ("", [], {}, None, False)}

    @staticmethod
    def _review_reason_summary(*, decision: str, status: str, note: str, error: str) -> tuple[str, str]:
        normalized_note = str(note or "").strip()
        if normalized_note:
            return "note", normalized_note
        normalized_error = str(error or "").strip()
        if normalized_error:
            return "error", normalized_error
        normalized_decision = str(decision or "").strip().lower()
        if normalized_decision:
            return "decision", normalized_decision
        normalized_status = str(status or "").strip().lower()
        if normalized_status:
            return "status", normalized_status
        return "", ""

    @staticmethod
    def _grant_revoke_reason_summary(
        *,
        removed: list[dict[str, Any]],
        scope: str,
        request_id: str,
        rule: str,
        session_id: str,
        channel: str,
    ) -> tuple[str, str]:
        removed_count = len(list(removed or []))
        normalized_scope = str(scope or "").strip().lower()
        normalized_request_id = str(request_id or "").strip()
        normalized_rule = str(rule or "").strip().lower()
        normalized_session = str(session_id or "").strip()
        normalized_channel = str(channel or "").strip().lower()
        filters = [
            normalized_scope,
            normalized_request_id,
            normalized_rule,
            normalized_session,
            normalized_channel,
        ]
        if removed_count > 0:
            detail = f"removed {removed_count} grant(s)"
            if normalized_scope:
                detail = f"{detail} [{normalized_scope}]"
            return "result", detail
        if any(filters):
            scope_label = normalized_scope or "selected"
            return "result", f"no matching grants [{scope_label}]"
        return "", ""

    def _request_review_audit_row(
        self,
        *,
        payload: dict[str, Any] | None,
        request_id: str,
        decision: str,
        actor: str,
        note: str,
        trusted_actor: bool,
        changed: bool,
        status: str,
        error: str = "",
    ) -> dict[str, Any]:
        request_payload = payload if isinstance(payload, dict) else {}
        rules = [
            str(item or "").strip().lower()
            for item in request_payload.get("matched_approval_specifiers", []) or []
            if str(item or "").strip()
        ]
        reason_source, reason_summary = self._review_reason_summary(
            decision=decision,
            status=status,
            note=note,
            error=error,
        )
        row: dict[str, Any] = {
            "action": "review",
            "changed": bool(changed),
            "status": str(status or "").strip().lower(),
            "decision": str(decision or "").strip().lower(),
            "request_id": str(request_id or "").strip(),
            "tool": str(request_payload.get("tool", "") or "").strip().lower(),
            "session_id": str(request_payload.get("session_id", "") or "").strip(),
            "channel": str(request_payload.get("channel", "") or "").strip().lower(),
            "requester_actor": str(request_payload.get("requester_actor", "") or "").strip(),
            "rules": rules,
            "approval_context": self._approval_audit_context(request_payload.get("approval_context")),
            "actor": str(actor or "").strip(),
            "note": str(note or "").strip(),
            "trusted_actor": bool(trusted_actor),
            "reason_source": reason_source,
            "reason_summary": reason_summary,
        }
        if rules:
            row["rule"] = rules[0]
        if error:
            row["error"] = str(error or "").strip()
        return row

    def _grant_revoke_audit_row(
        self,
        *,
        session_id: str,
        channel: str,
        rule: str,
        request_id: str,
        scope: str,
        removed: list[dict[str, Any]],
    ) -> dict[str, Any]:
        normalized_rule = str(rule or "").strip().lower()
        normalized_request_id = str(request_id or "").strip()
        normalized_scope = str(scope or "").strip().lower()
        normalized_session = str(session_id or "").strip()
        normalized_channel = str(channel or "").strip().lower()
        selected_tool = self._approval_rule_tool(normalized_rule)
        if not selected_tool and removed:
            selected_tool = self._approval_rule_tool((removed[0] or {}).get("rule", ""))
        reason_source, reason_summary = self._grant_revoke_reason_summary(
            removed=removed,
            scope=normalized_scope,
            request_id=normalized_request_id,
            rule=normalized_rule,
            session_id=normalized_session,
            channel=normalized_channel,
        )
        return {
            "action": "revoke_grant",
            "changed": bool(removed),
            "status": "removed" if removed else "unchanged",
            "removed_count": len(removed),
            "session_id": normalized_session,
            "channel": normalized_channel,
            "rule": normalized_rule,
            "tool": selected_tool,
            "request_id": normalized_request_id,
            "scope": normalized_scope,
            "removed": list(removed),
            "reason_source": reason_source,
            "reason_summary": reason_summary,
        }

    def _prune_approval_state(self) -> None:
        now = time.monotonic()
        expired_grants = [key for key, expires_at in self._approval_grants.items() if expires_at <= now]
        for key in expired_grants:
            self._approval_grants.pop(key, None)

        expired_requests: list[str] = []
        for request_id, payload in self._approval_requests.items():
            expires_at = float(payload.get("expires_at_monotonic", 0.0) or 0.0)
            if expires_at and expires_at <= now:
                expired_requests.append(request_id)
        for request_id in expired_requests:
            self._approval_requests.pop(request_id, None)
        if expired_requests:
            expired_set = set(expired_requests)
            self._approval_request_order = [item for item in self._approval_request_order if item not in expired_set]

    @staticmethod
    def _arguments_preview(arguments: dict[str, Any], *, max_chars: int = 240) -> str:
        try:
            preview = json.dumps(arguments, sort_keys=True, ensure_ascii=False, default=str)
        except Exception:
            preview = str(arguments)
        preview = str(preview or "").strip()
        if len(preview) <= max_chars:
            return preview
        return preview[: max_chars - 3] + "..."

    @classmethod
    def _approval_context(cls, *, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        normalized_tool = str(tool_name or "").strip().lower()
        if not normalized_tool:
            return {}

        context: dict[str, Any] = {}
        if normalized_tool == "exec":
            command_text = str(arguments.get("command", "") or "").strip()
            binary = cls._command_specifier(arguments.get("command"))
            env_keys = cls._exec_env_key_fragments(arguments.get("env"))
            cwd = str(arguments.get("cwd", arguments.get("workdir")) or "").strip()
            context = {
                "tool": normalized_tool,
                "command_text": command_text,
                "command_binary": binary,
                "shell_wrapper": cls._exec_needs_shell_wrapper(arguments.get("command"))
                or cls._exec_uses_explicit_shell_wrapper(arguments.get("command")),
                "env_keys": env_keys,
                "cwd": cwd,
            }
        elif normalized_tool == "web_fetch":
            context = {
                "tool": normalized_tool,
                "url": str(arguments.get("url", "") or "").strip(),
                "host": cls._url_host_fragment(arguments.get("url")),
                "method": str(arguments.get("method", "") or "").strip().upper(),
            }
        elif normalized_tool == "browser":
            context = {
                "tool": normalized_tool,
                "action": str(arguments.get("action", "") or "").strip().lower(),
                "url": str(arguments.get("url", "") or "").strip(),
                "host": cls._url_host_fragment(arguments.get("url")),
            }
        elif normalized_tool == "run_skill":
            context = {
                "tool": normalized_tool,
                "name": str(arguments.get("name", "") or "").strip(),
                "script": str(arguments.get("script", "") or "").strip(),
            }

        return {key: value for key, value in context.items() if value not in ("", [], {}, None, False)}

    def _approval_request_id(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        session_id: str,
        channel: str,
        matched_rules: list[str],
    ) -> str:
        raw = json.dumps(
            {
                "tool": str(tool_name or "").strip().lower(),
                "arguments": arguments,
                "session_id": str(session_id or "").strip(),
                "channel": str(channel or "").strip().lower(),
                "rules": sorted(str(item or "").strip().lower() for item in matched_rules if str(item or "").strip()),
            },
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )
        return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:16]

    def _register_approval_request(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        session_id: str,
        channel: str,
        user_id: str,
        requester_id: str,
        safety: dict[str, Any],
    ) -> dict[str, Any]:
        self._prune_approval_state()
        matched_rules = [
            str(item or "").strip().lower()
            for item in safety.get("matched_approval_specifiers", []) or []
            if str(item or "").strip()
        ]
        if not matched_rules:
            return {}
        resolved_channel = str(safety.get("resolved_channel") or channel or "").strip().lower()
        request_id = self._approval_request_id(
            tool_name=tool_name,
            arguments=arguments,
            session_id=session_id,
            channel=resolved_channel,
            matched_rules=matched_rules,
        )
        existing = self._approval_requests.get(request_id)
        if existing is not None and str(existing.get("status", "pending") or "pending").strip().lower() == "pending":
            return dict(existing)
        payload = {
            "request_id": request_id,
            "tool": str(tool_name or "").strip().lower(),
            "session_id": str(session_id or "").strip(),
            "channel": resolved_channel,
            "user_id": str(user_id or "").strip(),
            "requester_id": str(requester_id or "").strip(),
            "requester_actor": (
                f"{resolved_channel}:{str(requester_id or '').strip()}"
                if resolved_channel and str(requester_id or "").strip()
                else ""
            ),
            "derived_specifiers": list(safety.get("derived_specifiers", []) or []),
            "matched_approval_specifiers": matched_rules,
            "approval_reason": str(safety.get("approval_reason", "") or "").strip(),
            "arguments_preview": self._arguments_preview(arguments),
            "approval_context": self._approval_context(tool_name=tool_name, arguments=arguments),
            "status": "pending",
            "created_at_monotonic": time.monotonic(),
            "expires_at_monotonic": time.monotonic() + self._approval_ttl_s,
            "notified_count": 0,
            "actor": "",
            "note": "",
        }
        self._approval_requests[request_id] = payload
        self._approval_request_order.append(request_id)
        if len(self._approval_request_order) > self._APPROVAL_REQUEST_LIMIT:
            evict = self._approval_request_order.pop(0)
            self._approval_requests.pop(evict, None)
        return dict(payload)

    def _has_approval_grant(
        self,
        *,
        session_id: str,
        channel: str,
        matched_rules: list[str],
        request_id: str = "",
    ) -> bool:
        self._prune_approval_state()
        normalized_channel = str(channel or "").strip().lower()
        if not normalized_channel or not matched_rules:
            return False
        now = time.monotonic()
        normalized_request_id = str(request_id or "").strip()
        if normalized_request_id:
            exact_matches = True
            for rule in matched_rules:
                exact_key = self._approval_exact_grant_key(
                    request_id=normalized_request_id,
                    session_id=session_id,
                    channel=normalized_channel,
                    rule=rule,
                )
                if float(self._approval_grants.get(exact_key, 0.0) or 0.0) <= now:
                    exact_matches = False
                    break
            if exact_matches:
                return True
        for rule in matched_rules:
            key = self._approval_grant_key(session_id=session_id, channel=normalized_channel, rule=rule)
            if float(self._approval_grants.get(key, 0.0) or 0.0) <= now:
                return False
        return True

    def consume_pending_approval_requests(
        self,
        *,
        session_id: str,
        channel: str = "",
    ) -> list[dict[str, Any]]:
        self._prune_approval_state()
        resolved_channel = str(channel or "").strip().lower() or self._derive_channel_from_session(session_id)
        out: list[dict[str, Any]] = []
        for request_id in self._approval_request_order:
            payload = self._approval_requests.get(request_id)
            if not isinstance(payload, dict):
                continue
            if str(payload.get("status", "") or "").strip().lower() != "pending":
                continue
            if str(payload.get("session_id", "") or "").strip() != str(session_id or "").strip():
                continue
            payload_channel = str(payload.get("channel", "") or "").strip().lower()
            if resolved_channel and payload_channel and payload_channel != resolved_channel:
                continue
            if int(payload.get("notified_count", 0) or 0) > 0:
                continue
            payload["notified_count"] = int(payload.get("notified_count", 0) or 0) + 1
            out.append(dict(payload))
        return out

    def review_approval_request(
        self,
        request_id: str,
        *,
        decision: str,
        actor: str = "",
        note: str = "",
        trusted_actor: bool = False,
    ) -> dict[str, Any]:
        self._prune_approval_state()
        normalized_request_id = str(request_id or "").strip()
        normalized_decision = str(decision or "").strip().lower()
        if normalized_decision not in {"approved", "rejected"}:
            return {"ok": False, "error": "invalid_review_decision"}
        payload = self._approval_requests.get(normalized_request_id)
        if payload is None:
            self._append_approval_audit(
                {
                    "action": "review",
                    "changed": False,
                    "status": "missing",
                    "decision": normalized_decision,
                    "request_id": normalized_request_id,
                    "actor": str(actor or "").strip(),
                    "note": str(note or "").strip(),
                    "trusted_actor": bool(trusted_actor),
                    "error": "approval_request_not_found",
                }
            )
            return {"ok": False, "error": "approval_request_not_found"}
        expected_actor = str(payload.get("requester_actor", "") or "").strip()
        normalized_actor = str(actor or "").strip()
        if expected_actor and not trusted_actor:
            self._append_approval_audit(
                self._request_review_audit_row(
                    payload=payload,
                    request_id=normalized_request_id,
                    decision=normalized_decision,
                    actor=normalized_actor,
                    note=note,
                    trusted_actor=trusted_actor,
                    changed=False,
                    status=str(payload.get("status", "pending") or "pending"),
                    error="approval_channel_bound",
                )
            )
            return {
                "ok": False,
                "error": "approval_channel_bound",
                "request_id": normalized_request_id,
                "tool": str(payload.get("tool", "") or "").strip(),
                "channel": str(payload.get("channel", "") or "").strip(),
                "session_id": str(payload.get("session_id", "") or "").strip(),
                "expected_actor": expected_actor,
            }
        if expected_actor and not normalized_actor:
            self._append_approval_audit(
                self._request_review_audit_row(
                    payload=payload,
                    request_id=normalized_request_id,
                    decision=normalized_decision,
                    actor=normalized_actor,
                    note=note,
                    trusted_actor=trusted_actor,
                    changed=False,
                    status=str(payload.get("status", "pending") or "pending"),
                    error="approval_actor_required",
                )
            )
            return {
                "ok": False,
                "error": "approval_actor_required",
                "request_id": normalized_request_id,
                "tool": str(payload.get("tool", "") or "").strip(),
                "channel": str(payload.get("channel", "") or "").strip(),
                "session_id": str(payload.get("session_id", "") or "").strip(),
                "expected_actor": expected_actor,
            }
        if expected_actor and normalized_actor != expected_actor:
            self._append_approval_audit(
                self._request_review_audit_row(
                    payload=payload,
                    request_id=normalized_request_id,
                    decision=normalized_decision,
                    actor=normalized_actor,
                    note=note,
                    trusted_actor=trusted_actor,
                    changed=False,
                    status=str(payload.get("status", "pending") or "pending"),
                    error="approval_actor_mismatch",
                )
            )
            return {
                "ok": False,
                "error": "approval_actor_mismatch",
                "request_id": normalized_request_id,
                "tool": str(payload.get("tool", "") or "").strip(),
                "channel": str(payload.get("channel", "") or "").strip(),
                "session_id": str(payload.get("session_id", "") or "").strip(),
                "expected_actor": expected_actor,
            }
        status = str(payload.get("status", "pending") or "pending").strip().lower()
        if status != "pending":
            self._append_approval_audit(
                self._request_review_audit_row(
                    payload=payload,
                    request_id=normalized_request_id,
                    decision=normalized_decision,
                    actor=normalized_actor,
                    note=note,
                    trusted_actor=trusted_actor,
                    changed=False,
                    status=status,
                )
            )
            return {
                "ok": True,
                "changed": False,
                "status": status,
                "request_id": normalized_request_id,
                "tool": str(payload.get("tool", "") or "").strip(),
                "channel": str(payload.get("channel", "") or "").strip(),
                "session_id": str(payload.get("session_id", "") or "").strip(),
            }

        payload["status"] = normalized_decision
        payload["actor"] = str(actor or "").strip()
        payload["note"] = str(note or "").strip()
        payload["reviewed_at_monotonic"] = time.monotonic()
        if normalized_decision == "approved":
            expires_at = time.monotonic() + self._approval_ttl_s
            for rule in payload.get("matched_approval_specifiers", []) or []:
                key = self._approval_exact_grant_key(
                    request_id=normalized_request_id,
                    session_id=str(payload.get("session_id", "") or "").strip(),
                    channel=str(payload.get("channel", "") or "").strip().lower(),
                    rule=str(rule or "").strip().lower(),
                )
                self._approval_grants[key] = expires_at
            payload["grant_expires_at_monotonic"] = expires_at
            payload["grant_scope"] = "exact"
        self._append_approval_audit(
            self._request_review_audit_row(
                payload=payload,
                request_id=normalized_request_id,
                decision=normalized_decision,
                actor=normalized_actor,
                note=note,
                trusted_actor=trusted_actor,
                changed=True,
                status=normalized_decision,
            )
        )

        return {
            "ok": True,
            "changed": True,
            "status": normalized_decision,
            "request_id": normalized_request_id,
            "tool": str(payload.get("tool", "") or "").strip(),
            "channel": str(payload.get("channel", "") or "").strip(),
            "session_id": str(payload.get("session_id", "") or "").strip(),
            "matched_approval_specifiers": list(payload.get("matched_approval_specifiers", []) or []),
            "approval_context": dict(payload.get("approval_context", {}) or {}),
            "grant_ttl_s": self._approval_ttl_s if normalized_decision == "approved" else 0.0,
        }

    def approval_requests_snapshot(
        self,
        *,
        status: str = "pending",
        session_id: str = "",
        channel: str = "",
        tool: str = "",
        rule: str = "",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        self._prune_approval_state()
        normalized_status = str(status or "pending").strip().lower() or "pending"
        normalized_session = str(session_id or "").strip()
        normalized_channel = str(channel or "").strip().lower()
        normalized_tool = str(tool or "").strip().lower()
        normalized_rule = str(rule or "").strip().lower()
        max_rows = max(1, int(limit or 1))
        now = time.monotonic()
        rows: list[dict[str, Any]] = []

        for request_id in reversed(self._approval_request_order):
            payload = self._approval_requests.get(request_id)
            if not isinstance(payload, dict):
                continue
            payload_status = str(payload.get("status", "pending") or "pending").strip().lower()
            if normalized_status not in {"", "all"} and payload_status != normalized_status:
                continue
            if normalized_session and str(payload.get("session_id", "") or "").strip() != normalized_session:
                continue
            if normalized_channel and str(payload.get("channel", "") or "").strip().lower() != normalized_channel:
                continue
            if normalized_tool and str(payload.get("tool", "") or "").strip().lower() != normalized_tool:
                continue
            if normalized_rule and normalized_rule not in {
                str(item or "").strip().lower() for item in payload.get("matched_approval_specifiers", []) or []
            }:
                continue

            created_at = float(payload.get("created_at_monotonic", 0.0) or 0.0)
            reviewed_at = float(payload.get("reviewed_at_monotonic", 0.0) or 0.0)
            expires_at = float(payload.get("expires_at_monotonic", 0.0) or 0.0)
            grant_expires_at = float(payload.get("grant_expires_at_monotonic", 0.0) or 0.0)
            row = dict(payload)
            row["request_age_s"] = max(0.0, now - created_at) if created_at > 0 else 0.0
            row["expires_in_s"] = max(0.0, expires_at - now) if expires_at > 0 else 0.0
            if reviewed_at > 0:
                row["review_age_s"] = max(0.0, now - reviewed_at)
            if grant_expires_at > 0:
                row["grant_expires_in_s"] = max(0.0, grant_expires_at - now)
            rows.append(row)
            if len(rows) >= max_rows:
                break
        return rows

    def approval_grants_snapshot(
        self,
        *,
        session_id: str = "",
        channel: str = "",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        self._prune_approval_state()
        normalized_session = str(session_id or "").strip()
        normalized_channel = str(channel or "").strip().lower()
        max_rows = max(1, int(limit or 1))
        now = time.monotonic()
        rows: list[dict[str, Any]] = []

        for key, expires_at in sorted(self._approval_grants.items(), key=lambda item: float(item[1])):
            parsed = self._parse_approval_grant_key(key)
            session_part = parsed["session_id"]
            channel_part = parsed["channel"]
            rule_part = parsed["rule"]
            if normalized_session and session_part != normalized_session:
                continue
            if normalized_channel and channel_part != normalized_channel:
                continue
            rows.append(
                {
                    "session_id": session_part,
                    "channel": channel_part,
                    "rule": rule_part,
                    "scope": parsed["scope"],
                    "request_id": parsed["request_id"],
                    "expires_in_s": max(0.0, float(expires_at or 0.0) - now),
                }
            )
            if len(rows) >= max_rows:
                break
        return rows

    def revoke_approval_grants(
        self,
        *,
        session_id: str = "",
        channel: str = "",
        rule: str = "",
        request_id: str = "",
        scope: str = "",
    ) -> dict[str, Any]:
        self._prune_approval_state()
        normalized_session = str(session_id or "").strip()
        normalized_channel = str(channel or "").strip().lower()
        normalized_rule = str(rule or "").strip().lower()
        normalized_request_id = str(request_id or "").strip()
        normalized_scope = str(scope or "").strip().lower()
        removed: list[dict[str, Any]] = []

        for key in list(self._approval_grants.keys()):
            parsed = self._parse_approval_grant_key(key)
            session_part = parsed["session_id"]
            channel_part = parsed["channel"]
            rule_part = parsed["rule"]
            request_part = parsed["request_id"]
            scope_part = str(parsed["scope"] or "").strip().lower()
            if normalized_session and session_part != normalized_session:
                continue
            if normalized_channel and channel_part != normalized_channel:
                continue
            if normalized_rule and rule_part != normalized_rule:
                continue
            if normalized_request_id and request_part != normalized_request_id:
                continue
            if normalized_scope and scope_part != normalized_scope:
                continue
            self._approval_grants.pop(key, None)
            removed.append(
                {
                    "session_id": session_part,
                    "channel": channel_part,
                    "rule": rule_part,
                    "scope": parsed["scope"],
                    "request_id": parsed["request_id"],
                }
            )

        self._append_approval_audit(
            self._grant_revoke_audit_row(
                session_id=normalized_session,
                channel=normalized_channel,
                rule=normalized_rule,
                request_id=normalized_request_id,
                scope=normalized_scope,
                removed=removed,
            )
        )

        return {
            "ok": True,
            "removed": removed,
            "removed_count": len(removed),
            "session_id": normalized_session,
            "channel": normalized_channel,
            "rule": normalized_rule,
            "request_id": normalized_request_id,
            "scope": normalized_scope,
        }

    def approval_audit_snapshot(
        self,
        *,
        action: str = "",
        session_id: str = "",
        channel: str = "",
        request_id: str = "",
        tool: str = "",
        rule: str = "",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        self._prune_approval_state()
        normalized_action = str(action or "").strip().lower()
        normalized_session = str(session_id or "").strip()
        normalized_channel = str(channel or "").strip().lower()
        normalized_request_id = str(request_id or "").strip()
        normalized_tool = str(tool or "").strip().lower()
        normalized_rule = str(rule or "").strip().lower()
        max_rows = max(1, int(limit or 1))
        now = time.monotonic()
        rows: list[dict[str, Any]] = []

        for payload in reversed(self._approval_audits):
            row = dict(payload or {})
            if normalized_action and str(row.get("action", "") or "").strip().lower() != normalized_action:
                continue
            if normalized_session:
                row_sessions = {
                    str(row.get("session_id", "") or "").strip(),
                    *(str((item or {}).get("session_id", "") or "").strip() for item in row.get("removed", []) or []),
                }
                row_sessions.discard("")
                if normalized_session not in row_sessions:
                    continue
            if normalized_channel:
                row_channels = {
                    str(row.get("channel", "") or "").strip().lower(),
                    *(str((item or {}).get("channel", "") or "").strip().lower() for item in row.get("removed", []) or []),
                }
                row_channels.discard("")
                if normalized_channel not in row_channels:
                    continue
            if normalized_request_id:
                row_request_ids = {
                    str(row.get("request_id", "") or "").strip(),
                    *(str((item or {}).get("request_id", "") or "").strip() for item in row.get("removed", []) or []),
                }
                row_request_ids.discard("")
                if normalized_request_id not in row_request_ids:
                    continue
            if normalized_tool:
                row_tools = {
                    str(row.get("tool", "") or "").strip().lower(),
                    self._approval_rule_tool(row.get("rule", "")),
                }
                row_tools.update(self._approval_rule_tool(item) for item in row.get("rules", []) or [])
                row_tools.update(self._approval_rule_tool((item or {}).get("rule", "")) for item in row.get("removed", []) or [])
                row_tools.discard("")
                if normalized_tool not in row_tools:
                    continue
            if normalized_rule:
                row_rules = {
                    str(row.get("rule", "") or "").strip().lower(),
                    *(str(item or "").strip().lower() for item in row.get("rules", []) or []),
                    *(str((item or {}).get("rule", "") or "").strip().lower() for item in row.get("removed", []) or []),
                }
                row_rules.discard("")
                if normalized_rule not in row_rules:
                    continue
            recorded_at_monotonic = float(row.get("recorded_at_monotonic", 0.0) or 0.0)
            if recorded_at_monotonic > 0.0:
                row["audit_age_s"] = max(0.0, now - recorded_at_monotonic)
            rows.append(row)
            if len(rows) >= max_rows:
                break
        return rows

    def safety_decision(
        self,
        name: str,
        arguments: dict[str, Any] | None,
        *,
        session_id: str,
        channel: str = "",
    ) -> dict[str, Any]:
        safe_arguments = dict(arguments or {})
        resolved_channel, risky_tools, risky_specifiers, approval_specifiers, approval_channels, blocked_channels, allowed_channels = self._resolve_effective_safety(
            session_id=session_id,
            channel=channel,
        )
        derived_specifiers = self._derive_tool_specifiers(tool_name=name, arguments=safe_arguments)
        matched_specifiers = self._matched_specifier_rules(tool_name=name, arguments=safe_arguments, rules=risky_specifiers)
        matched_approval_specifiers = self._matched_specifier_rules(
            tool_name=name,
            arguments=safe_arguments,
            rules=approval_specifiers,
        )
        approval_request_id = ""
        if matched_approval_specifiers:
            approval_request_id = self._approval_request_id(
                tool_name=name,
                arguments=safe_arguments,
                session_id=session_id,
                channel=resolved_channel,
                matched_rules=matched_approval_specifiers,
            )
        approval_granted = False
        if matched_approval_specifiers:
            approval_granted = self._has_approval_grant(
                session_id=session_id,
                channel=resolved_channel,
                matched_rules=matched_approval_specifiers,
                request_id=approval_request_id,
            )
        matched_tool = str(name or "").strip().lower() in risky_tools
        is_risky = matched_tool or bool(matched_specifiers)
        has_channel_restrictions = bool(allowed_channels or blocked_channels)
        blocked = False
        block_reason = ""
        if self._safety.enabled and is_risky and has_channel_restrictions:
            if not resolved_channel:
                blocked = True
                block_reason = "unknown_channel"
            elif self._is_channel_blocked(
                channel=resolved_channel,
                blocked_channels=blocked_channels,
                allowed_channels=allowed_channels,
            ):
                blocked = True
                block_reason = f"channel:{resolved_channel}"

        approval_required = False
        approval_reason = ""
        has_approval_channel_rules = bool(approval_channels)
        if (
            not blocked
            and self._safety.enabled
            and matched_approval_specifiers
            and has_approval_channel_rules
            and not approval_granted
        ):
            if not resolved_channel:
                approval_required = True
                approval_reason = "unknown_channel"
            elif resolved_channel not in allowed_channels and resolved_channel in approval_channels:
                approval_required = True
                approval_reason = f"channel:{resolved_channel}"

        decision = "allow"
        if blocked:
            decision = "block"
        elif approval_required:
            decision = "approval"

        return {
            "tool": str(name or "").strip(),
            "session_id": session_id,
            "requested_channel": str(channel or "").strip().lower(),
            "resolved_channel": resolved_channel,
            "derived_specifiers": derived_specifiers,
            "risky": is_risky,
            "approval_required": approval_required,
            "approval_granted": approval_granted,
            "approval_request_id": approval_request_id,
            "blocked": blocked,
            "decision": decision,
            "block_reason": block_reason,
            "approval_reason": approval_reason,
            "approval_context": self._approval_context(tool_name=name, arguments=safe_arguments),
            "matched_tool": matched_tool,
            "matched_specifiers": matched_specifiers,
            "matched_approval_specifiers": matched_approval_specifiers,
            "risky_tools": risky_tools,
            "risky_specifiers": risky_specifiers,
            "approval_specifiers": approval_specifiers,
            "approval_channels": approval_channels,
            "blocked_channels": blocked_channels,
            "allowed_channels": allowed_channels,
            "safety_enabled": bool(self._safety.enabled),
        }

    @staticmethod
    def _derive_channel_from_session(session_id: str) -> str:
        raw = str(session_id or "").strip().lower()
        if not raw:
            return ""
        if ":" not in raw:
            return ""
        return raw.split(":", 1)[0].strip()

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def replace(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def schema(self) -> list[dict[str, Any]]:
        return [self._tools[name].export_schema() for name in sorted(self._tools.keys())]

    @staticmethod
    def _matches_schema_type(value: Any, expected_type: str) -> bool:
        normalized = str(expected_type or "").strip().lower()
        if normalized == "string":
            return isinstance(value, str)
        if normalized == "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        if normalized == "number":
            return (isinstance(value, int) and not isinstance(value, bool)) or isinstance(value, float)
        if normalized == "boolean":
            return isinstance(value, bool)
        if normalized == "object":
            return isinstance(value, dict)
        if normalized == "array":
            return isinstance(value, list)
        if normalized == "null":
            return value is None
        return True

    @classmethod
    def _format_validation_error(cls, *, path: str, reason: str) -> str:
        clean_reason = str(reason or "").strip()
        if not clean_reason:
            return ""
        clean_path = str(path or "").strip()
        return f"{clean_path}:{clean_reason}" if clean_path else clean_reason

    @classmethod
    def _child_schema_path(cls, path: str, fragment: str) -> str:
        clean_fragment = str(fragment or "").strip()
        if not clean_fragment:
            return str(path or "").strip()
        clean_path = str(path or "").strip()
        if not clean_path:
            return clean_fragment
        if clean_fragment.startswith("["):
            return f"{clean_path}{clean_fragment}"
        return f"{clean_path}.{clean_fragment}"

    @classmethod
    def _normalize_validation_errors(cls, errors: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in errors:
            clean = str(item or "").strip()
            if not clean or clean in seen:
                continue
            seen.add(clean)
            normalized.append(clean)
        return normalized

    @classmethod
    def _format_argument_validation_failure(cls, *, tool_name: str, errors: list[str]) -> str:
        normalized = cls._normalize_validation_errors(errors)
        if not normalized:
            return f"tool_invalid_arguments:{tool_name}:unknown"
        if len(normalized) == 1:
            return f"tool_invalid_arguments:{tool_name}:{normalized[0]}"
        payload = json.dumps(normalized, ensure_ascii=False)
        return f"tool_invalid_arguments:{tool_name}:multiple:{payload}"

    @classmethod
    def _validate_schema_value(cls, value: Any, schema: dict[str, Any], *, path: str = "") -> list[str]:
        if not isinstance(schema, dict):
            return []

        raw_type = schema.get("type")
        accepted_types = raw_type if isinstance(raw_type, list) else [raw_type] if raw_type is not None else []
        normalized_types = [str(item or "").strip().lower() for item in accepted_types if str(item or "").strip()]
        if normalized_types and not any(cls._matches_schema_type(value, item) for item in normalized_types):
            return [cls._format_validation_error(path=path, reason=f"expected_{'_or_'.join(normalized_types)}")]

        enum_values = schema.get("enum")
        if isinstance(enum_values, list) and enum_values and value not in enum_values:
            return [cls._format_validation_error(path=path, reason="value_not_allowed")]

        if value is None:
            return []

        errors: list[str] = []

        min_length = schema.get("minLength")
        if min_length is not None and isinstance(value, str):
            try:
                if len(value) < int(min_length):
                    errors.append(cls._format_validation_error(path=path, reason=f"min_length_{min_length}"))
            except Exception:
                errors.append(cls._format_validation_error(path=path, reason="invalid_min_length"))

        max_length = schema.get("maxLength")
        if max_length is not None and isinstance(value, str):
            try:
                if len(value) > int(max_length):
                    errors.append(cls._format_validation_error(path=path, reason=f"max_length_{max_length}"))
            except Exception:
                errors.append(cls._format_validation_error(path=path, reason="invalid_max_length"))

        minimum = schema.get("minimum")
        if minimum is not None and isinstance(value, (int, float)) and not isinstance(value, bool):
            try:
                if value < minimum:
                    errors.append(cls._format_validation_error(path=path, reason=f"minimum_{minimum}"))
            except Exception:
                errors.append(cls._format_validation_error(path=path, reason="invalid_minimum"))

        maximum = schema.get("maximum")
        if maximum is not None and isinstance(value, (int, float)) and not isinstance(value, bool):
            try:
                if value > maximum:
                    errors.append(cls._format_validation_error(path=path, reason=f"maximum_{maximum}"))
            except Exception:
                errors.append(cls._format_validation_error(path=path, reason="invalid_maximum"))

        if isinstance(value, list):
            min_items = schema.get("minItems")
            if min_items is not None:
                try:
                    if len(value) < int(min_items):
                        errors.append(cls._format_validation_error(path=path, reason=f"min_items_{min_items}"))
                except Exception:
                    errors.append(cls._format_validation_error(path=path, reason="invalid_min_items"))

            max_items = schema.get("maxItems")
            if max_items is not None:
                try:
                    if len(value) > int(max_items):
                        errors.append(cls._format_validation_error(path=path, reason=f"max_items_{max_items}"))
                except Exception:
                    errors.append(cls._format_validation_error(path=path, reason="invalid_max_items"))

            items_schema = schema.get("items")
            if isinstance(items_schema, dict):
                for index, item in enumerate(value):
                    errors.extend(cls._validate_schema_value(
                        item,
                        items_schema,
                        path=cls._child_schema_path(path, f"[{index}]"),
                    ))

        if isinstance(value, dict):
            properties = schema.get("properties", {})
            property_schemas = properties if isinstance(properties, dict) else {}
            required = schema.get("required", [])
            if isinstance(required, list):
                missing = [
                    str(item).strip()
                    for item in required
                    if str(item).strip() and str(item).strip() not in value
                ]
                if missing:
                    for item in sorted(missing):
                        errors.append(cls._format_validation_error(path=path, reason=f"missing_required:{item}"))

            additional_properties = schema.get("additionalProperties", True)
            if additional_properties is False:
                unexpected = sorted(str(key).strip() for key in value.keys() if key not in property_schemas)
                if unexpected:
                    for item in unexpected:
                        errors.append(cls._format_validation_error(path=path, reason=f"unexpected_arguments:{item}"))

            for key, item in value.items():
                child_schema = property_schemas.get(key)
                if not isinstance(child_schema, dict):
                    continue
                errors.extend(cls._validate_schema_value(
                    item,
                    child_schema,
                    path=cls._child_schema_path(path, str(key).strip()),
                ))

        return cls._normalize_validation_errors(errors)

    @classmethod
    def _validate_arguments(cls, tool: Tool, arguments: Any) -> dict[str, Any]:
        if not isinstance(arguments, dict):
            raise RuntimeError(f"tool_invalid_arguments:{tool.name}:expected_object")

        schema = tool.args_schema()
        if not isinstance(schema, dict):
            return dict(arguments)

        schema_type = str(schema.get("type", "") or "").strip().lower()
        if schema_type and schema_type != "object":
            return dict(arguments)

        validation_errors = cls._validate_schema_value(arguments, schema)
        if validation_errors:
            raise RuntimeError(cls._format_argument_validation_failure(tool_name=tool.name, errors=validation_errors))

        return dict(arguments)

    def _resolve_timeout(self, tool: Tool, arguments: dict[str, Any]) -> float:
        # 1. tool-level argument override
        raw = arguments.get("timeout") or arguments.get("timeout_s")
        if raw is not None:
            try:
                v = float(raw)
                if v > 0:
                    return v
            except (TypeError, ValueError):
                pass
        # 2. config override for the named tool
        configured = self._tool_timeouts.get(str(tool.name or "").strip().lower())
        if configured is not None and configured > 0:
            return configured
        # 3. tool class default
        if tool.default_timeout_s is not None and tool.default_timeout_s > 0:
            return tool.default_timeout_s
        # 4. global default
        return self._default_timeout_s

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        session_id: str,
        channel: str = "",
        user_id: str = "",
        requester_id: str = "",
    ) -> str:
        tool = self.get(name)
        if tool is None:
            raise ToolError(name, "not_found", recoverable=False)
        validated_arguments = self._validate_arguments(tool, arguments)

        resolved_channel, risky_tools, risky_specifiers, approval_specifiers, approval_channels, blocked_channels, allowed_channels = self._resolve_effective_safety(
            session_id=session_id,
            channel=channel,
        )
        safety = self.safety_decision(
            name,
            validated_arguments,
            session_id=session_id,
            channel=channel,
        )
        if bool(safety.get("blocked", False)):
            reason_channel = str(safety.get("resolved_channel") or "").strip() or "unknown"
            raise RuntimeError(f"tool_blocked_by_safety_policy:{name}:{reason_channel}")
        if bool(safety.get("approval_required", False)):
            self._register_approval_request(
                tool_name=name,
                arguments=validated_arguments,
                session_id=session_id,
                channel=resolved_channel or channel,
                user_id=user_id,
                requester_id=requester_id,
                safety=safety,
            )
            reason_channel = str(safety.get("resolved_channel") or "").strip() or "unknown"
            raise RuntimeError(f"tool_requires_approval:{name}:{reason_channel}")

        ctx = ToolContext(session_id=session_id, channel=resolved_channel, user_id=user_id)

        # Cache lookup (only for cacheable tools)
        if getattr(tool, "cacheable", False):
            cached = self._cache.get(name, validated_arguments)
            if cached is not None:
                return cached

        # Execute with centralized timeout middleware
        timeout_s = self._resolve_timeout(tool, validated_arguments)
        tracer = get_tracer("clawlite.tools")
        try:
            with tracer.start_as_current_span("tool.execute") as span:
                set_span_attributes(
                    span,
                    {
                        "tool.name": name,
                        "tool.session_id": session_id,
                        "tool.channel": resolved_channel,
                        "tool.user_id": user_id,
                        "tool.timeout_s": timeout_s,
                    },
                )
                retry_attempts = 2
                result = None
                for attempt in range(1, retry_attempts + 1):
                    try:
                        result = await asyncio.wait_for(tool.run(validated_arguments, ctx), timeout=timeout_s)
                        break
                    except Exception as exc:
                        span.record_exception(exc)
                        if attempt >= retry_attempts or not self._tool_exception_retryable(exc):
                            raise
                        await asyncio.sleep(min(0.2 * attempt, 0.5))
                if result is None:
                    raise RuntimeError(f"tool_execution_failed:{name}")
                set_span_attributes(
                    span,
                    {
                        "tool.result.length": len(str(result or "")),
                    },
                )
        except asyncio.TimeoutError:
            raise ToolTimeoutError(name, timeout_s)
        except (ToolError, ToolTimeoutError):
            raise
        except RuntimeError as exc:
            raise ToolError(name, "execution_failed", recoverable=False, cause=exc) from exc
        except Exception as exc:
            raise ToolError(name, "execution_failed", recoverable=False, cause=exc) from exc

        # Store in cache if applicable
        if getattr(tool, "cacheable", False):
            try:
                self._cache.set(name, validated_arguments, result)
            except Exception:
                pass  # cache errors never propagate

        return result
