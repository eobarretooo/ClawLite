from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import websockets

from clawlite.channels.base import BaseChannel, cancel_task

DISCORD_DEFAULT_API_BASE = "https://discord.com/api/v10"
DISCORD_DEFAULT_GATEWAY_URL = "wss://gateway.discord.gg/?v=10&encoding=json"
# 37377 base (GUILDS|GUILD_MESSAGES|DIRECT_MESSAGES|MESSAGE_CONTENT)
# + 1024  GUILD_MESSAGE_REACTIONS
# + 8192  DIRECT_MESSAGE_REACTIONS
DISCORD_DEFAULT_GATEWAY_INTENTS = 46593
DISCORD_TYPING_INTERVAL_S = 8.0
DISCORD_VOICE_MESSAGE_FLAG = 1 << 13  # 8192 — IS_VOICE_MESSAGE
DISCORD_VOICE_WAVEFORM_SAMPLES = 256
DISCORD_COMPONENT_KIND_BY_TYPE: dict[int, str] = {
    2: "button",
    3: "select",
    5: "user_select",
    6: "role_select",
    7: "mentionable_select",
    8: "channel_select",
}


@dataclass(slots=True, frozen=True)
class _DiscordSendTarget:
    kind: str
    value: str


@dataclass(slots=True, frozen=True)
class _DiscordGuildChannelPolicy:
    allow: bool = True
    require_mention: bool | None = None
    ignore_other_mentions: bool | None = None
    users: tuple[str, ...] = ()
    roles: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class _DiscordGuildPolicy:
    slug: str = ""
    require_mention: bool | None = None
    ignore_other_mentions: bool | None = None
    users: tuple[str, ...] = ()
    roles: tuple[str, ...] = ()
    channels: dict[str, _DiscordGuildChannelPolicy] | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_utc_timestamp(raw: str) -> datetime | None:
    value = str(raw or "").strip()
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class DiscordChannel(BaseChannel):
    def __init__(self, *, config: dict[str, Any], on_message=None) -> None:
        super().__init__(name="discord", config=config, on_message=on_message)
        token = str(config.get("token", "") or "").strip()
        if not token:
            raise ValueError("discord token is required")
        self.token = token
        self.api_base = str(
            config.get("api_base", config.get("apiBase", DISCORD_DEFAULT_API_BASE))
            or DISCORD_DEFAULT_API_BASE
        ).strip().rstrip("/")
        self.gateway_url = str(
            config.get(
                "gateway_url",
                config.get("gatewayUrl", DISCORD_DEFAULT_GATEWAY_URL),
            )
            or DISCORD_DEFAULT_GATEWAY_URL
        ).strip()
        self.gateway_intents = max(
            0,
            int(
                config.get(
                    "gateway_intents",
                    config.get("gatewayIntents", DISCORD_DEFAULT_GATEWAY_INTENTS),
                )
                or DISCORD_DEFAULT_GATEWAY_INTENTS
            ),
        )
        self.timeout_s = max(
            0.1,
            float(config.get("timeout_s", config.get("timeoutS", 10.0)) or 10.0),
        )
        self.typing_enabled = bool(
            config.get("typing_enabled", config.get("typingEnabled", True))
        )
        self.typing_interval_s = max(
            0.5,
            float(
                config.get(
                    "typing_interval_s",
                    config.get("typingIntervalS", DISCORD_TYPING_INTERVAL_S),
                )
                or DISCORD_TYPING_INTERVAL_S
            ),
        )
        self.gateway_backoff_base_s = max(
            0.1,
            float(
                config.get(
                    "gateway_backoff_base_s",
                    config.get("gatewayBackoffBaseS", 2.0),
                )
                or 2.0
            ),
        )
        self.gateway_backoff_max_s = max(
            self.gateway_backoff_base_s,
            float(
                config.get(
                    "gateway_backoff_max_s",
                    config.get("gatewayBackoffMaxS", 30.0),
                )
                or 30.0
            ),
        )
        self.send_retry_attempts = max(
            1,
            int(
                config.get("send_retry_attempts", config.get("sendRetryAttempts", 3))
                or 3
            ),
        )
        self.send_retry_after_default_s = max(
            0.0,
            float(
                config.get(
                    "send_retry_after_default_s",
                    config.get("sendRetryAfterDefaultS", 1.0),
                )
                or 1.0
            ),
        )
        self.allow_from = self._normalize_allow_from(
            config.get("allow_from", config.get("allowFrom", []))
        )
        self.dm_policy = self._normalize_dm_policy(
            config.get("dm_policy", config.get("dmPolicy", "open"))
        )
        self.group_policy = self._normalize_group_policy(
            config.get("group_policy", config.get("groupPolicy", "open"))
        )
        self.allow_bots = self._normalize_allow_bots(
            config.get("allow_bots", config.get("allowBots", False))
        )
        self.require_mention = bool(
            config.get("require_mention", config.get("requireMention", False))
        )
        self.ignore_other_mentions = bool(
            config.get(
                "ignore_other_mentions",
                config.get("ignoreOtherMentions", False),
            )
        )
        self.reply_to_mode = self._normalize_reply_to_mode(
            config.get("reply_to_mode", config.get("replyToMode", "all"))
        )
        self.slash_isolated_sessions = bool(
            config.get(
                "slash_isolated_sessions",
                config.get("slashIsolatedSessions", True),
            )
        )
        self.presence_status = str(config.get("status", "") or "").strip().lower()
        self.presence_activity = str(config.get("activity", "") or "").strip()
        self.presence_activity_type = min(
            5,
            max(0, int(config.get("activity_type", config.get("activityType", 4)) or 4)),
        )
        self.presence_activity_url = str(config.get("activity_url", config.get("activityUrl", "")) or "").strip()
        auto_presence_raw = config.get("auto_presence", config.get("autoPresence", {}))
        if not isinstance(auto_presence_raw, dict):
            auto_presence_raw = {}
        self.auto_presence_enabled = bool(
            auto_presence_raw.get("enabled", auto_presence_raw.get("enabled", False))
        )
        self.auto_presence_interval_s = max(
            5.0,
            float(
                auto_presence_raw.get(
                    "interval_s",
                    auto_presence_raw.get("intervalS", 30.0),
                )
                or 30.0
            ),
        )
        self.auto_presence_min_update_interval_s = max(
            1.0,
            float(
                auto_presence_raw.get(
                    "min_update_interval_s",
                    auto_presence_raw.get("minUpdateIntervalS", 15.0),
                )
                or 15.0
            ),
        )
        self.auto_presence_healthy_text = str(
            auto_presence_raw.get("healthy_text", auto_presence_raw.get("healthyText", "")) or ""
        ).strip()
        self.auto_presence_degraded_text = str(
            auto_presence_raw.get("degraded_text", auto_presence_raw.get("degradedText", "")) or ""
        ).strip()
        self.auto_presence_exhausted_text = str(
            auto_presence_raw.get("exhausted_text", auto_presence_raw.get("exhaustedText", "")) or ""
        ).strip()
        self.guilds = self._normalize_guild_policies(
            config.get("guilds", config.get("guilds", {}))
        )
        self.thread_bindings_enabled = bool(
            config.get(
                "thread_bindings_enabled",
                config.get("threadBindingsEnabled", True),
            )
        )
        thread_binding_state_path_raw = str(
            config.get(
                "thread_binding_state_path",
                config.get("threadBindingStatePath", ""),
            )
            or ""
        ).strip()
        self.thread_binding_state_path = (
            Path(thread_binding_state_path_raw).expanduser()
            if thread_binding_state_path_raw
            else None
        )
        self.thread_binding_idle_timeout_s = max(
            0.0,
            float(
                config.get(
                    "thread_binding_idle_timeout_s",
                    config.get("threadBindingIdleTimeoutS", 0.0),
                )
                or 0.0
            ),
        )
        self.thread_binding_max_age_s = max(
            0.0,
            float(
                config.get(
                    "thread_binding_max_age_s",
                    config.get("threadBindingMaxAgeS", 0.0),
                )
                or 0.0
            ),
        )
        self._headers = {
            "Authorization": f"Bot {self.token}",
            "Content-Type": "application/json",
        }
        self._client: httpx.AsyncClient | None = None
        self._ws: Any | None = None
        self._gateway_task: asyncio.Task[Any] | None = None
        self._heartbeat_task: asyncio.Task[Any] | None = None
        self._auto_presence_task: asyncio.Task[Any] | None = None
        self._typing_tasks: dict[str, asyncio.Task[Any]] = {}
        self._dm_channel_ids: dict[str, str] = {}
        self._sequence: int | None = None
        self._session_id: str = ""
        self._resume_url: str = ""
        self._bot_user_id: str = ""
        self._application_id: str = ""
        self._policy_allowed_count: int = 0
        self._policy_blocked_count: int = 0
        self._thread_bindings: dict[str, dict[str, str]] = {}
        self._thread_bindings_lock = asyncio.Lock()
        self._thread_bindings_loaded = False
        self._presence_last_payload_signature = ""
        self._presence_last_sent_at = 0.0
        self._presence_last_error = ""
        self._presence_last_state = ""

    @staticmethod
    def _normalize_allow_from(raw: Any) -> list[str]:
        if not isinstance(raw, list):
            return []
        values: list[str] = []
        for item in raw:
            value = str(item or "").strip()
            if value:
                values.append(value)
        return values

    @staticmethod
    def _normalize_dm_policy(raw: Any) -> str:
        policy = str(raw or "open").strip().lower()
        if policy not in {"open", "allowlist", "disabled"}:
            return "open"
        return policy

    @staticmethod
    def _normalize_group_policy(raw: Any) -> str:
        policy = str(raw or "open").strip().lower()
        if policy not in {"open", "mention", "allowlist", "disabled"}:
            return "open"
        return policy

    @staticmethod
    def _normalize_allow_bots(raw: Any) -> str:
        if isinstance(raw, bool):
            return "all" if raw else "disabled"
        value = str(raw or "disabled").strip().lower()
        if value in {"all", "true", "yes", "on", "open"}:
            return "all"
        if value in {"mentions", "mention"}:
            return "mentions"
        return "disabled"

    @staticmethod
    def _normalize_reply_to_mode(raw: Any) -> str:
        mode = str(raw or "all").strip().lower()
        if mode not in {"off", "first", "all"}:
            return "all"
        return mode

    @staticmethod
    def _normalize_string_list(raw: Any) -> tuple[str, ...]:
        if not isinstance(raw, list):
            return ()
        values: list[str] = []
        for item in raw:
            value = str(item or "").strip()
            if value:
                values.append(value)
        return tuple(values)

    @staticmethod
    def _normalize_component_values(raw: Any) -> list[str]:
        if not isinstance(raw, list):
            return []
        values: list[str] = []
        for item in raw:
            value = str(item or "").strip()
            if value:
                values.append(value)
        return values

    @staticmethod
    def _component_kind(component_type: int) -> str:
        return DISCORD_COMPONENT_KIND_BY_TYPE.get(int(component_type or 0), "component")

    @classmethod
    def _component_update_kind(cls, component_type: int) -> str:
        if int(component_type or 0) == 2:
            return "button_click"
        kind = cls._component_kind(component_type)
        if kind == "select":
            return "string_select"
        if kind.endswith("_select"):
            return kind
        return "component_interaction"

    @staticmethod
    def _resolved_user_label(value: str, resolved: dict[str, Any]) -> str:
        users = resolved.get("users")
        members = resolved.get("members")
        user = users.get(value) if isinstance(users, dict) else None
        member = members.get(value) if isinstance(members, dict) else None
        if isinstance(member, dict):
            nickname = str(member.get("nick", "") or "").strip()
            if nickname:
                return nickname
        if isinstance(user, dict):
            for key in ("global_name", "display_name", "username"):
                label = str(user.get(key, "") or "").strip()
                if label:
                    return label
        return ""

    @classmethod
    def _component_selected_labels(
        cls,
        *,
        component_type: int,
        values: list[str],
        data: dict[str, Any],
    ) -> list[str]:
        if not values:
            return []
        normalized_component_type = int(component_type or 0)
        if normalized_component_type == 3:
            return list(values)
        resolved = data.get("resolved")
        if not isinstance(resolved, dict):
            return list(values)
        labels: list[str] = []
        for value in values:
            label = ""
            if normalized_component_type in {5, 7}:
                label = cls._resolved_user_label(value, resolved)
            if not label and normalized_component_type in {6, 7}:
                roles = resolved.get("roles")
                role = roles.get(value) if isinstance(roles, dict) else None
                if isinstance(role, dict):
                    role_name = str(role.get("name", "") or "").strip()
                    if role_name:
                        label = f"@{role_name}"
            if not label and normalized_component_type == 8:
                channels = resolved.get("channels")
                channel = channels.get(value) if isinstance(channels, dict) else None
                if isinstance(channel, dict):
                    channel_name = str(channel.get("name", "") or "").strip()
                    if channel_name:
                        label = f"#{channel_name}"
            labels.append(label or value)
        return labels

    @classmethod
    def _component_event_text(
        cls,
        *,
        component_type: int,
        custom_id: str,
        values: list[str],
        labels: list[str],
    ) -> str:
        kind = cls._component_kind(component_type)
        label = f"{kind}:{custom_id}" if custom_id else kind
        rendered_values = labels or values
        if rendered_values:
            return f"[{label} {', '.join(rendered_values)}]"
        return f"[{label}]"

    @classmethod
    def _normalize_modal_fields(cls, raw: Any) -> list[dict[str, Any]]:
        if not isinstance(raw, list):
            return []
        fields: list[dict[str, Any]] = []
        for row in raw:
            if not isinstance(row, dict):
                continue
            components = row.get("components")
            if not isinstance(components, list):
                continue
            for component in components:
                if not isinstance(component, dict):
                    continue
                value = str(component.get("value", "") or "").strip()
                label = str(component.get("label", "") or "").strip()
                custom_id = str(component.get("custom_id", "") or "").strip()
                if not value and not label and not custom_id:
                    continue
                fields.append(
                    {
                        "component_type": int(component.get("type", 0) or 0),
                        "custom_id": custom_id,
                        "label": label,
                        "value": value,
                    }
                )
        return fields

    @staticmethod
    def _modal_field_ids(fields: list[dict[str, Any]]) -> list[str]:
        return [
            str(item.get("custom_id", "") or "").strip()
            for item in fields
            if str(item.get("custom_id", "") or "").strip()
        ]

    @staticmethod
    def _modal_field_labels(fields: list[dict[str, Any]]) -> list[str]:
        labels: list[str] = []
        for item in fields:
            label = str(item.get("label", "") or "").strip()
            if label:
                labels.append(label)
                continue
            field_id = str(item.get("custom_id", "") or "").strip()
            if field_id:
                labels.append(field_id)
        return labels

    @staticmethod
    def _modal_event_text(*, custom_id: str, fields: list[dict[str, Any]]) -> str:
        header = f"[modal_submit:{custom_id}]" if custom_id else "[modal_submit]"
        if not fields:
            return header
        lines: list[str] = [header]
        for item in fields:
            value = str(item.get("value", "") or "").strip()
            if not value:
                continue
            label = str(item.get("label", "") or "").strip()
            field_id = str(item.get("custom_id", "") or "").strip()
            key = label or field_id or "field"
            lines.append(f"{key}: {value}")
        return "\n".join(lines)

    @classmethod
    def _normalize_guild_policies(
        cls, raw: Any
    ) -> dict[str, _DiscordGuildPolicy]:
        if not isinstance(raw, dict):
            return {}
        policies: dict[str, _DiscordGuildPolicy] = {}
        for guild_id, value in raw.items():
            if not isinstance(value, dict):
                continue
            clean_guild_id = str(guild_id or "").strip()
            if not clean_guild_id:
                continue
            channel_rules_raw = value.get("channels", {})
            channel_rules: dict[str, _DiscordGuildChannelPolicy] = {}
            if isinstance(channel_rules_raw, dict):
                for channel_id, channel_value in channel_rules_raw.items():
                    clean_channel_id = str(channel_id or "").strip()
                    if not clean_channel_id:
                        continue
                    if isinstance(channel_value, bool):
                        channel_rules[clean_channel_id] = _DiscordGuildChannelPolicy(
                            allow=bool(channel_value)
                        )
                        continue
                    if not isinstance(channel_value, dict):
                        continue
                    channel_rules[clean_channel_id] = _DiscordGuildChannelPolicy(
                        allow=bool(channel_value.get("allow", True)),
                        require_mention=channel_value.get(
                            "require_mention",
                            channel_value.get("requireMention"),
                        ),
                        ignore_other_mentions=channel_value.get(
                            "ignore_other_mentions",
                            channel_value.get("ignoreOtherMentions"),
                        ),
                        users=cls._normalize_string_list(channel_value.get("users", [])),
                        roles=cls._normalize_string_list(channel_value.get("roles", [])),
                    )
            policies[clean_guild_id] = _DiscordGuildPolicy(
                slug=str(value.get("slug", "") or "").strip(),
                require_mention=value.get(
                    "require_mention",
                    value.get("requireMention"),
                ),
                ignore_other_mentions=value.get(
                    "ignore_other_mentions",
                    value.get("ignoreOtherMentions"),
                ),
                users=cls._normalize_string_list(value.get("users", [])),
                roles=cls._normalize_string_list(value.get("roles", [])),
                channels=channel_rules,
            )
        return policies

    @staticmethod
    def _sender_candidates(*, user_id: Any, username: str = "") -> set[str]:
        candidates = {str(user_id or "").strip()}
        normalized_username = str(username or "").strip().lstrip("@")
        if normalized_username:
            candidates.add(normalized_username)
            candidates.add(f"@{normalized_username}")
        return {item for item in candidates if item}

    def _is_allowed_sender(self, *, user_id: str, username: str = "") -> bool:
        if not self.allow_from:
            return True
        candidates = self._sender_candidates(user_id=user_id, username=username)
        allowed = {item.strip() for item in self.allow_from if str(item or "").strip()}
        return any(candidate in allowed for candidate in candidates)

    @staticmethod
    def _matches_sender_entries(
        *,
        user_id: str,
        username: str,
        allowed_entries: tuple[str, ...] | list[str],
    ) -> bool:
        allowed = {item.strip() for item in allowed_entries if str(item or "").strip()}
        if not allowed:
            return False
        candidates = DiscordChannel._sender_candidates(
            user_id=user_id,
            username=username,
        )
        return any(candidate in allowed for candidate in candidates)

    @staticmethod
    def _matches_role_entries(
        *,
        role_ids: tuple[str, ...] | list[str],
        allowed_entries: tuple[str, ...] | list[str],
    ) -> bool:
        allowed = {item.strip() for item in allowed_entries if str(item or "").strip()}
        if not allowed:
            return False
        return any(str(role_id or "").strip() in allowed for role_id in role_ids)

    @staticmethod
    def _looks_like_snowflake(value: str) -> bool:
        raw = str(value or "").strip()
        return raw.isdigit() and len(raw) >= 5

    @classmethod
    def _parse_send_target(cls, raw: str) -> _DiscordSendTarget:
        target = str(raw or "").strip()
        if not target:
            return _DiscordSendTarget(kind="", value="")

        if target.startswith("<#") and target.endswith(">"):
            return _DiscordSendTarget(kind="channel", value=target[2:-1].strip())
        if target.startswith("<@") and target.endswith(">"):
            return _DiscordSendTarget(
                kind="user",
                value=target[2:-1].strip().lstrip("!"),
            )

        lowered = target.lower()
        if lowered.startswith("discord:"):
            target = target.split(":", 1)[1].strip()
            lowered = target.lower()

        for prefix, kind in (
            ("channel:", "channel"),
            ("group:", "channel"),
            ("user:", "user"),
            ("dm:", "user"),
            ("direct:", "user"),
        ):
            if lowered.startswith(prefix):
                value = target[len(prefix) :].strip()
                if kind == "channel" and ":thread:" in value:
                    _, _, thread_id = value.partition(":thread:")
                    thread = thread_id.strip()
                    if thread:
                        value = thread
                return _DiscordSendTarget(kind=kind, value=value)

        if ":thread:" in target:
            _, _, thread_id = target.partition(":thread:")
            thread = thread_id.strip()
            if thread:
                return _DiscordSendTarget(kind="channel", value=thread)

        return _DiscordSendTarget(kind="ambiguous", value=target)

    @staticmethod
    def _parse_retry_after(raw: str) -> float | None:
        value = str(raw or "").strip()
        if not value:
            return None
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        if parsed < 0.0:
            return 0.0
        return parsed

    def _extract_retry_after(self, response: httpx.Response) -> float:
        header_retry_after = self._parse_retry_after(
            response.headers.get("Retry-After", "")
        )
        if header_retry_after is not None:
            return header_retry_after
        reset_after = self._parse_retry_after(
            response.headers.get("X-RateLimit-Reset-After", "")
        )
        if reset_after is not None:
            return reset_after
        if response.content:
            try:
                data = response.json()
            except Exception:
                data = {}
            if isinstance(data, dict):
                body_retry_after = self._parse_retry_after(
                    str(data.get("retry_after", ""))
                )
                if body_retry_after is not None:
                    return body_retry_after
        return self.send_retry_after_default_s

    def _guild_policy(self, guild_id: str) -> _DiscordGuildPolicy | None:
        return self.guilds.get(str(guild_id or "").strip())

    def _load_thread_bindings(self) -> dict[str, dict[str, str]]:
        path = self.thread_binding_state_path
        if path is None or not path.exists():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            self._last_error = str(exc)
            return {}
        items = raw.get("items", []) if isinstance(raw, dict) else []
        bindings: dict[str, dict[str, str]] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            channel_id = str(item.get("channel_id", "") or "").strip()
            session_id = str(item.get("session_id", "") or "").strip()
            if not channel_id or not session_id:
                continue
            bindings[channel_id] = {
                "session_id": session_id,
                "guild_id": str(item.get("guild_id", "") or "").strip(),
                "source_session_id": str(item.get("source_session_id", "") or "").strip(),
                "bound_by": str(item.get("bound_by", "") or "").strip(),
                "bound_at": str(item.get("bound_at", "") or "").strip(),
                "updated_at": str(item.get("updated_at", "") or "").strip(),
            }
        return bindings

    def _write_thread_bindings(self, bindings: dict[str, dict[str, str]]) -> None:
        path = self.thread_binding_state_path
        if path is None:
            return
        if not bindings:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        items: list[dict[str, str]] = []
        for channel_id, row in sorted(bindings.items()):
            payload = dict(row)
            payload["channel_id"] = channel_id
            items.append(payload)
        tmp_path = path.with_name(f"{path.name}.tmp")
        tmp_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "updated_at": _utc_now(),
                    "items": items,
                },
                ensure_ascii=True,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        tmp_path.replace(path)

    async def _ensure_thread_bindings_loaded(self) -> None:
        if self._thread_bindings_loaded:
            return
        async with self._thread_bindings_lock:
            if self._thread_bindings_loaded:
                return
            self._thread_bindings = await asyncio.to_thread(self._load_thread_bindings)
            self._thread_bindings_loaded = True

    def resolve_bound_session(self, channel_id: str) -> dict[str, str] | None:
        binding = self._thread_bindings.get(str(channel_id or "").strip())
        if not isinstance(binding, dict):
            return None
        if self._binding_expiration_reason(binding) is not None:
            return None
        return dict(binding)

    def _binding_expiration_reason(self, binding: dict[str, str]) -> str | None:
        now = datetime.now(timezone.utc)
        if self.thread_binding_max_age_s > 0.0:
            bound_at = _parse_utc_timestamp(str(binding.get("bound_at", "") or ""))
            if bound_at is not None:
                age_s = max(0.0, (now - bound_at).total_seconds())
                if age_s >= self.thread_binding_max_age_s:
                    return "max_age"
        if self.thread_binding_idle_timeout_s > 0.0:
            updated_at = _parse_utc_timestamp(
                str(binding.get("updated_at") or binding.get("bound_at") or "")
            )
            if updated_at is not None:
                idle_s = max(0.0, (now - updated_at).total_seconds())
                if idle_s >= self.thread_binding_idle_timeout_s:
                    return "idle_timeout"
        return None

    async def _prune_expired_thread_binding(
        self,
        channel_id: str,
        binding: dict[str, str],
    ) -> str | None:
        reason = self._binding_expiration_reason(binding)
        if reason is None:
            return None
        async with self._thread_bindings_lock:
            current = self._thread_bindings.get(channel_id)
            if current != binding:
                if not isinstance(current, dict):
                    return reason
                return self._binding_expiration_reason(current)
            self._thread_bindings.pop(channel_id, None)
            if self.thread_binding_state_path is not None:
                await asyncio.to_thread(
                    self._write_thread_bindings,
                    dict(self._thread_bindings),
                )
        return reason

    async def bind_thread(
        self,
        *,
        channel_id: str,
        session_id: str,
        actor: str = "",
        guild_id: str = "",
        source_session_id: str = "",
    ) -> dict[str, Any]:
        clean_channel_id = str(channel_id or "").strip()
        clean_session_id = str(session_id or "").strip()
        if not clean_channel_id:
            return {"ok": False, "error": "discord_thread_binding_channel_required"}
        if not clean_session_id:
            return {"ok": False, "error": "discord_thread_binding_session_required"}
        if not self.thread_bindings_enabled:
            return {"ok": False, "error": "discord_thread_bindings_disabled"}
        await self._ensure_thread_bindings_loaded()
        async with self._thread_bindings_lock:
            now = _utc_now()
            previous = dict(self._thread_bindings.get(clean_channel_id, {}))
            entry = {
                "session_id": clean_session_id,
                "guild_id": str(guild_id or "").strip(),
                "source_session_id": str(source_session_id or "").strip(),
                "bound_by": str(actor or "").strip(),
                "bound_at": str(previous.get("bound_at", "") or now),
                "updated_at": now,
            }
            changed = previous != entry
            self._thread_bindings[clean_channel_id] = entry
            if self.thread_binding_state_path is not None:
                await asyncio.to_thread(
                    self._write_thread_bindings,
                    dict(self._thread_bindings),
                )
        return {
            "ok": True,
            "changed": changed,
            "channel_id": clean_channel_id,
            "session_id": clean_session_id,
            "binding": dict(entry),
        }

    async def unbind_thread(self, *, channel_id: str) -> dict[str, Any]:
        clean_channel_id = str(channel_id or "").strip()
        if not clean_channel_id:
            return {"ok": False, "error": "discord_thread_binding_channel_required"}
        await self._ensure_thread_bindings_loaded()
        async with self._thread_bindings_lock:
            previous = self._thread_bindings.pop(clean_channel_id, None)
            if self.thread_binding_state_path is not None:
                await asyncio.to_thread(
                    self._write_thread_bindings,
                    dict(self._thread_bindings),
                )
        return {
            "ok": True,
            "changed": previous is not None,
            "channel_id": clean_channel_id,
            "binding": dict(previous) if isinstance(previous, dict) else {},
        }

    async def _apply_bound_session(
        self,
        *,
        channel_id: str,
        fallback_session_id: str,
        metadata: dict[str, Any],
    ) -> str:
        if not self.thread_bindings_enabled:
            return fallback_session_id
        clean_channel_id = str(channel_id or "").strip()
        await self._ensure_thread_bindings_loaded()
        binding = self._thread_bindings.get(clean_channel_id)
        if not isinstance(binding, dict):
            return fallback_session_id
        expiration_reason = await self._prune_expired_thread_binding(
            clean_channel_id,
            dict(binding),
        )
        if expiration_reason is not None:
            metadata["discord_binding_expired"] = expiration_reason
            return fallback_session_id
        bound_session_id = str(binding.get("session_id", "") or "").strip()
        if not bound_session_id:
            return fallback_session_id
        now = _utc_now()
        if str(binding.get("updated_at", "") or "") != now:
            async with self._thread_bindings_lock:
                current = self._thread_bindings.get(clean_channel_id)
                if isinstance(current, dict):
                    updated_binding = dict(current)
                    updated_binding["updated_at"] = now
                    self._thread_bindings[clean_channel_id] = updated_binding
                    if self.thread_binding_state_path is not None:
                        await asyncio.to_thread(
                            self._write_thread_bindings,
                            dict(self._thread_bindings),
                        )
                    binding = updated_binding
        metadata["discord_binding_active"] = True
        metadata["discord_binding_channel_id"] = clean_channel_id
        metadata["discord_source_session_key"] = fallback_session_id
        metadata["discord_bound_session_key"] = bound_session_id
        bound_by = str(binding.get("bound_by", "") or "").strip()
        if bound_by:
            metadata["discord_bound_by"] = bound_by
        bound_at = str(binding.get("bound_at", "") or "").strip()
        if bound_at:
            metadata["discord_bound_at"] = bound_at
        return bound_session_id

    @staticmethod
    def _role_ids_from_payload(payload: dict[str, Any]) -> tuple[str, ...]:
        member = payload.get("member")
        if not isinstance(member, dict):
            return ()
        roles = member.get("roles")
        if not isinstance(roles, list):
            return ()
        normalized: list[str] = []
        for item in roles:
            value = str(item or "").strip()
            if value:
                normalized.append(value)
        return tuple(normalized)

    def _message_mentions_bot(self, payload: dict[str, Any]) -> bool:
        bot_user_id = str(self._bot_user_id or "").strip()
        if not bot_user_id:
            return False
        content = str(payload.get("content", "") or "")
        if f"<@{bot_user_id}>" in content or f"<@!{bot_user_id}>" in content:
            return True
        mentions = payload.get("mentions")
        if isinstance(mentions, list):
            for mention in mentions:
                if not isinstance(mention, dict):
                    continue
                if str(mention.get("id", "") or "").strip() == bot_user_id:
                    return True
        referenced_message = payload.get("referenced_message")
        if isinstance(referenced_message, dict):
            author = referenced_message.get("author")
            if isinstance(author, dict):
                if str(author.get("id", "") or "").strip() == bot_user_id:
                    return True
        return False

    def _message_mentions_others(self, payload: dict[str, Any]) -> bool:
        bot_user_id = str(self._bot_user_id or "").strip()
        mentions = payload.get("mentions")
        if isinstance(mentions, list):
            for mention in mentions:
                if not isinstance(mention, dict):
                    continue
                mentioned_id = str(mention.get("id", "") or "").strip()
                if mentioned_id and mentioned_id != bot_user_id:
                    return True
        mention_roles = payload.get("mention_roles")
        if isinstance(mention_roles, list):
            if any(str(item or "").strip() for item in mention_roles):
                return True
        return bool(payload.get("mention_everyone"))

    @staticmethod
    def _derive_session_id(
        *,
        channel_id: str,
        guild_id: str,
        user_id: str,
    ) -> str:
        clean_channel_id = str(channel_id or "").strip()
        clean_guild_id = str(guild_id or "").strip()
        clean_user_id = str(user_id or "").strip()
        if clean_guild_id:
            return f"discord:guild:{clean_guild_id}:channel:{clean_channel_id}"
        dm_scope = clean_user_id or clean_channel_id
        return f"discord:dm:{dm_scope}"

    def _derive_interaction_session_id(
        self,
        *,
        channel_id: str,
        guild_id: str,
        user_id: str,
        interaction_type: int,
    ) -> str:
        base_session_id = self._derive_session_id(
            channel_id=channel_id,
            guild_id=guild_id,
            user_id=user_id,
        )
        if interaction_type != 2 or not self.slash_isolated_sessions:
            return base_session_id
        clean_channel_id = str(channel_id or "").strip()
        clean_guild_id = str(guild_id or "").strip()
        clean_user_id = str(user_id or "").strip()
        if clean_guild_id and clean_channel_id and clean_user_id:
            return (
                f"discord:guild:{clean_guild_id}:channel:{clean_channel_id}:slash:{clean_user_id}"
            )
        if clean_user_id:
            return f"discord:dm:{clean_user_id}:slash"
        return base_session_id

    def _is_payload_authorized(
        self,
        *,
        payload: dict[str, Any],
        user_id: str,
        username: str,
        role_ids: tuple[str, ...] = (),
        author_is_bot: bool = False,
        ignore_mention_policy: bool = False,
    ) -> bool:
        guild_id = str(payload.get("guild_id", "") or "").strip()

        if author_is_bot:
            if self.allow_bots == "disabled":
                return False
            if self.allow_bots == "mentions" and not self._message_mentions_bot(payload):
                return False

        if self.allow_from and not self._is_allowed_sender(
            user_id=user_id,
            username=username,
        ):
            return False

        if not guild_id:
            if self.dm_policy == "disabled":
                return False
            if self.dm_policy == "allowlist" and not self._is_allowed_sender(
                user_id=user_id,
                username=username,
            ):
                return False
            return True

        if self.group_policy == "disabled":
            return False

        guild_policy = self._guild_policy(guild_id)
        if self.group_policy == "allowlist" and guild_policy is None:
            return False

        channel_id = str(payload.get("channel_id", "") or "").strip()
        channel_policy: _DiscordGuildChannelPolicy | None = None
        if guild_policy is not None:
            channel_map = guild_policy.channels or {}
            if channel_map:
                channel_policy = channel_map.get(channel_id)
                if channel_policy is None:
                    return False
                if not channel_policy.allow:
                    return False
            effective_users = (
                channel_policy.users
                if channel_policy is not None and channel_policy.users
                else guild_policy.users
            )
            effective_roles = (
                channel_policy.roles
                if channel_policy is not None and channel_policy.roles
                else guild_policy.roles
            )
            if effective_users or effective_roles:
                if not (
                    self._matches_sender_entries(
                        user_id=user_id,
                        username=username,
                        allowed_entries=effective_users,
                    )
                    or self._matches_role_entries(
                        role_ids=role_ids,
                        allowed_entries=effective_roles,
                    )
                ):
                    return False

        if ignore_mention_policy:
            return True

        require_mention = self.require_mention or self.group_policy == "mention"
        ignore_other_mentions = self.ignore_other_mentions
        if guild_policy is not None:
            if guild_policy.require_mention is not None:
                require_mention = bool(guild_policy.require_mention)
            if guild_policy.ignore_other_mentions is not None:
                ignore_other_mentions = bool(guild_policy.ignore_other_mentions)
        if channel_policy is not None:
            if channel_policy.require_mention is not None:
                require_mention = bool(channel_policy.require_mention)
            if channel_policy.ignore_other_mentions is not None:
                ignore_other_mentions = bool(channel_policy.ignore_other_mentions)

        mentioned_bot = self._message_mentions_bot(payload)
        if require_mention and not mentioned_bot:
            return False
        if ignore_other_mentions and not mentioned_bot and self._message_mentions_others(payload):
            return False
        return True

    async def start(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout_s,
                headers=self._headers,
            )
        self._running = True
        if self.thread_bindings_enabled:
            await self._ensure_thread_bindings_loaded()
        if self.on_message is not None and (
            self._gateway_task is None or self._gateway_task.done()
        ):
            self._gateway_task = asyncio.create_task(self._gateway_runner())
        if self.auto_presence_enabled and (
            self._auto_presence_task is None or self._auto_presence_task.done()
        ):
            self._auto_presence_task = asyncio.create_task(self._auto_presence_loop())

    async def stop(self) -> None:
        self._running = False
        await cancel_task(self._gateway_task)
        self._gateway_task = None
        await cancel_task(self._heartbeat_task)
        self._heartbeat_task = None
        await cancel_task(self._auto_presence_task)
        self._auto_presence_task = None
        for task in list(self._typing_tasks.values()):
            await cancel_task(task)
        self._typing_tasks.clear()
        self._dm_channel_ids.clear()
        ws = self._ws
        self._ws = None
        if ws is not None:
            close_fn = getattr(ws, "close", None)
            if callable(close_fn):
                result = close_fn()
                if asyncio.iscoroutine(result):
                    await result
        client = self._client
        self._client = None
        if client is not None:
            close_fn = getattr(client, "aclose", None)
            if callable(close_fn):
                await close_fn()

    async def _post_json(
        self,
        *,
        url: str,
        payload: dict[str, Any],
        error_prefix: str,
    ) -> httpx.Response:
        client = self._client
        if client is None:
            raise RuntimeError("discord_not_running")
        for attempt in range(1, self.send_retry_attempts + 1):
            try:
                response = await client.post(url, json=payload)
            except httpx.HTTPError as exc:
                self._last_error = str(exc)
                raise RuntimeError(f"{error_prefix}_request_error") from exc

            if response.status_code == 429:
                self._last_error = "http:429"
                if attempt >= self.send_retry_attempts:
                    raise RuntimeError(f"{error_prefix}_rate_limited")
                retry_after = self._extract_retry_after(response)
                await asyncio.sleep(retry_after)
                continue

            if response.status_code < 200 or response.status_code >= 300:
                self._last_error = f"http:{response.status_code}"
                raise RuntimeError(f"{error_prefix}_http_{response.status_code}")

            return response

        raise RuntimeError(f"{error_prefix}_rate_limited")

    async def _ensure_dm_channel_id(self, user_id: str) -> str:
        normalized_user_id = str(user_id or "").strip()
        if not normalized_user_id:
            raise ValueError("discord user target is required")
        cached = self._dm_channel_ids.get(normalized_user_id, "")
        if cached:
            return cached
        response = await self._post_json(
            url=f"{self.api_base}/users/@me/channels",
            payload={"recipient_id": normalized_user_id},
            error_prefix="discord_dm_channel",
        )
        try:
            data = response.json() if response.content else {}
        except Exception:
            data = {}
        channel_id = str(data.get("id", "") or "").strip()
        if not channel_id:
            raise RuntimeError("discord_dm_channel_invalid_response")
        self._dm_channel_ids[normalized_user_id] = channel_id
        return channel_id

    async def send(
        self,
        *,
        target: str,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        if not self._running:
            raise RuntimeError("discord_not_running")

        resolved_target = self._parse_send_target(target)
        if not resolved_target.value:
            raise ValueError("discord target(channel_id) is required")

        payload: dict[str, Any] = {"content": str(text or "")}
        metadata_payload = dict(metadata or {})
        interaction_id = str(metadata_payload.get("interaction_id", "") or "").strip()
        interaction_token = str(metadata_payload.get("interaction_token", "") or "").strip()
        reply_to_message_id = str(
            metadata_payload.get(
                "reply_to_message_id",
                metadata_payload.get("message_reference_id", ""),
            )
            or ""
        ).strip()
        if reply_to_message_id:
            payload["message_reference"] = {
                "message_id": reply_to_message_id,
                "fail_if_not_exists": False,
            }
            payload["allowed_mentions"] = {"replied_user": False}

        # Rich embeds — pass as metadata key "discord_embeds" or "embeds"
        raw_embeds = metadata_payload.get("discord_embeds") or metadata_payload.get("embeds")
        if isinstance(raw_embeds, list) and raw_embeds:
            payload["embeds"] = [
                e for e in raw_embeds if isinstance(e, dict)
            ][:10]  # Discord max 10 embeds per message

        # Message components (buttons, select menus) — pass as metadata key "discord_components"
        raw_components = metadata_payload.get("discord_components") or metadata_payload.get("components")
        if isinstance(raw_components, list) and raw_components:
            payload["components"] = [c for c in raw_components if isinstance(c, dict)][:5]  # Discord max 5 action rows

        # Poll — pass as metadata key "discord_poll": {"question": str, "answers": [str, ...], "duration_hours": int}
        raw_poll = metadata_payload.get("discord_poll")
        if isinstance(raw_poll, dict) and raw_poll.get("question") and raw_poll.get("answers"):
            answers_raw = [str(a) for a in raw_poll["answers"] if a][:10]
            payload["poll"] = {
                "question": {"text": str(raw_poll["question"])[:300]},
                "answers": [{"poll_media": {"text": a[:55]}} for a in answers_raw],
                "duration": max(1, int(raw_poll.get("duration_hours", 24) or 24)),
                "allow_multiselect": bool(raw_poll.get("allow_multiselect", False)),
                "layout_type": 1,
            }

        if interaction_token and self._application_id:
            reply_id = await self.reply_interaction(
                interaction_id=interaction_id,
                interaction_token=interaction_token,
                text=str(text or ""),
                components=payload.get("components"),
                embeds=payload.get("embeds"),
                ephemeral=bool(
                    metadata_payload.get(
                        "discord_ephemeral",
                        metadata_payload.get("ephemeral", False),
                    )
                ),
            )
            if reply_id:
                return f"discord:interaction:{reply_id}"
            raise RuntimeError("discord_interaction_reply_failed")

        channel_id = ""
        try:
            if resolved_target.kind == "user":
                channel_id = await self._ensure_dm_channel_id(resolved_target.value)
            else:
                channel_id = resolved_target.value

            try:
                response = await self._post_json(
                    url=f"{self.api_base}/channels/{channel_id}/messages",
                    payload=payload,
                    error_prefix="discord_send",
                )
            except RuntimeError as exc:
                should_fallback_to_dm = (
                    str(exc) == "discord_send_http_404"
                    and resolved_target.kind == "ambiguous"
                    and self._looks_like_snowflake(resolved_target.value)
                )
                if not should_fallback_to_dm:
                    raise
                original_exc = exc
                try:
                    channel_id = await self._ensure_dm_channel_id(resolved_target.value)
                except Exception:
                    raise original_exc
                response = await self._post_json(
                    url=f"{self.api_base}/channels/{channel_id}/messages",
                    payload=payload,
                    error_prefix="discord_send",
                )

            if response.content:
                try:
                    data = response.json()
                except Exception:
                    data = {}
            else:
                data = {}
            message_id = str(data.get("id", "") or "").strip()
            if not message_id:
                digest = hashlib.sha256(
                    f"{channel_id}:{text}".encode("utf-8")
                ).hexdigest()[:16]
                message_id = f"fallback-{digest}"
            self._last_error = ""
            return f"discord:sent:{message_id}"
        finally:
            if channel_id:
                await self._stop_typing(channel_id)

    async def add_reaction(self, channel_id: str, message_id: str, emoji: str) -> bool:
        """Add a reaction emoji to a message.

        emoji: Unicode emoji (e.g. "👍") or custom emoji name:id (e.g. "name:123456").
        Returns True on success (HTTP 204), False on any error.
        """
        if not self._running:
            return False
        client = self._client
        if client is None:
            return False
        import urllib.parse
        encoded_emoji = urllib.parse.quote(str(emoji or "").strip(), safe="")
        if not encoded_emoji:
            return False
        channel_id = str(channel_id or "").strip()
        message_id = str(message_id or "").strip()
        if not channel_id or not message_id:
            return False
        url = f"{self.api_base}/channels/{channel_id}/messages/{message_id}/reactions/{encoded_emoji}/@me"
        for attempt in range(1, self.send_retry_attempts + 1):
            try:
                response = await client.put(url)
            except Exception as exc:
                self._last_error = str(exc)
                return False
            if response.status_code == 204:
                return True
            if response.status_code == 429:
                self._last_error = "http:429"
                if attempt >= self.send_retry_attempts:
                    return False
                retry_after = self._extract_retry_after(response)
                await asyncio.sleep(retry_after)
                continue
            self._last_error = f"http:{response.status_code}"
            return False
        return False

    async def create_thread(
        self,
        *,
        channel_id: str,
        name: str,
        message_id: str | None = None,
        auto_archive_duration: int = 1440,
    ) -> str:
        """Create a Discord thread.

        If message_id is given, creates a thread anchored to that message.
        Otherwise creates a standalone channel thread.
        Returns the new thread_id or empty string on failure.
        auto_archive_duration: minutes before auto-archive (60, 1440, 4320, 10080).
        """
        channel_id = str(channel_id or "").strip()
        name = str(name or "").strip()[:100]  # Discord limit
        if not channel_id or not name:
            return ""
        if message_id:
            url = f"{self.api_base}/channels/{channel_id}/messages/{message_id}/threads"
        else:
            url = f"{self.api_base}/channels/{channel_id}/threads"
        payload: dict[str, Any] = {
            "name": name,
            "auto_archive_duration": auto_archive_duration,
        }
        try:
            response = await self._post_json(
                url=url,
                payload=payload,
                error_prefix="discord_thread",
            )
            data = response.json() if response.content else {}
            return str(data.get("id", "") or "").strip()
        except Exception as exc:
            self._last_error = str(exc)
            return ""

    async def _gateway_runner(self) -> None:
        backoff_s = self.gateway_backoff_base_s
        while self._running:
            await cancel_task(self._heartbeat_task)
            self._heartbeat_task = None
            connect_url = self._resume_url or self.gateway_url
            try:
                async with websockets.connect(
                    connect_url,
                    open_timeout=self.timeout_s,
                    close_timeout=self.timeout_s,
                    ping_interval=None,
                ) as ws:
                    self._ws = ws
                    self._last_error = ""
                    backoff_s = self.gateway_backoff_base_s
                    await self._gateway_loop()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._last_error = str(exc)
                if not self._running:
                    break
                await asyncio.sleep(backoff_s)
                backoff_s = min(
                    self.gateway_backoff_max_s,
                    max(self.gateway_backoff_base_s, backoff_s * 2.0),
                )
            finally:
                self._ws = None
                await cancel_task(self._heartbeat_task)
                self._heartbeat_task = None

    async def _gateway_loop(self) -> None:
        ws = self._ws
        if ws is None:
            return
        async for raw in ws:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="replace")
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            should_continue = await self._handle_gateway_payload(data)
            if not should_continue:
                break

    async def _handle_gateway_payload(self, data: dict[str, Any]) -> bool:
        seq = data.get("s")
        if isinstance(seq, int):
            self._sequence = seq

        op = int(data.get("op", -1))
        event_type = str(data.get("t", "") or "").strip().upper()
        payload = data.get("d")

        if op == 10 and isinstance(payload, dict):
            interval_ms = float(payload.get("heartbeat_interval", 45000) or 45000)
            await self._start_heartbeat(interval_ms / 1000.0)
            if self._session_id and self._sequence is not None:
                await self._resume()
            else:
                await self._identify()
            return True

        if op == 11:
            return True

        if op == 1:
            await self._send_ws_json({"op": 1, "d": self._sequence})
            return True

        if op == 7:
            return False

        if op == 9:
            resumable = bool(payload)
            if not resumable:
                self._session_id = ""
                self._resume_url = ""
                self._sequence = None
            return False

        if op != 0 or not isinstance(payload, dict):
            return True

        if event_type == "READY":
            self._session_id = str(payload.get("session_id", "") or "").strip()
            self._resume_url = str(payload.get("resume_gateway_url", "") or "").strip()
            user = payload.get("user")
            if isinstance(user, dict):
                self._bot_user_id = str(user.get("id", "") or "").strip()
            app = payload.get("application")
            if isinstance(app, dict):
                self._application_id = str(app.get("id", "") or "").strip()
            if self.auto_presence_enabled:
                await self._update_presence(force=True)
            return True

        if event_type == "RESUMED":
            if self.auto_presence_enabled:
                await self._update_presence(force=True)
            return True

        if event_type == "MESSAGE_CREATE":
            await self._handle_message_create(payload)
            return True

        if event_type == "MESSAGE_REACTION_ADD":
            await self._handle_message_reaction_add(payload)
            return True

        if event_type == "MESSAGE_REACTION_REMOVE":
            return True  # Silently acknowledged

        if event_type == "INTERACTION_CREATE":
            await self._handle_interaction_create(payload)
            return True

        return True

    async def _send_ws_json(self, payload: dict[str, Any]) -> None:
        ws = self._ws
        if ws is None:
            return
        await ws.send(json.dumps(payload))

    async def _identify(self) -> None:
        identify_payload: dict[str, Any] = {
            "token": self.token,
            "intents": self.gateway_intents,
            "properties": {
                "os": "clawlite",
                "browser": "clawlite",
                "device": "clawlite",
            },
        }
        presence = self._presence_payload()
        if presence is not None:
            identify_payload["presence"] = presence
        await self._send_ws_json(
            {
                "op": 2,
                "d": identify_payload,
            }
        )

    async def _resume(self) -> None:
        if not self._session_id:
            await self._identify()
            return
        await self._send_ws_json(
            {
                "op": 6,
                "d": {
                    "token": self.token,
                    "session_id": self._session_id,
                    "seq": self._sequence,
                },
            }
        )

    async def _start_heartbeat(self, interval_s: float) -> None:
        await cancel_task(self._heartbeat_task)

        async def _heartbeat_loop() -> None:
            while self._running and self._ws is not None:
                await self._send_ws_json({"op": 1, "d": self._sequence})
                await asyncio.sleep(max(0.1, interval_s))

        self._heartbeat_task = asyncio.create_task(_heartbeat_loop())

    @staticmethod
    def _normalize_attachment_rows(raw: Any) -> list[dict[str, Any]]:
        if not isinstance(raw, list):
            return []
        attachments: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            attachments.append(
                {
                    "id": str(item.get("id", "") or "").strip(),
                    "filename": str(item.get("filename", "") or "").strip(),
                    "url": str(item.get("url", "") or "").strip(),
                    "content_type": str(
                        item.get("content_type", item.get("contentType", "")) or ""
                    ).strip(),
                    "size": int(item.get("size", 0) or 0),
                }
            )
        return attachments

    async def _download_attachment(self, url: str, filename: str = "") -> bytes | None:
        """Download an attachment from Discord CDN. Returns raw bytes or None on failure."""
        url = str(url or "").strip()
        if not url or not url.startswith("https://"):
            return None
        try:
            async with httpx.AsyncClient(timeout=self.timeout_s * 3) as cdn_client:
                response = await cdn_client.get(url)
                if response.status_code == 200:
                    return bytes(response.content)
        except Exception as exc:
            self._last_error = str(exc)
        return None

    async def _handle_message_create(self, payload: dict[str, Any]) -> None:
        author = payload.get("author")
        if not isinstance(author, dict):
            return
        author_id = str(author.get("id", "") or "").strip()
        if not author_id:
            return
        author_is_bot = bool(author.get("bot"))
        if self._bot_user_id and author_id == self._bot_user_id:
            return

        channel_id = str(payload.get("channel_id", "") or "").strip()
        if not channel_id:
            return

        username = str(author.get("username", "") or "").strip()
        if not self._is_payload_authorized(
            payload=payload,
            user_id=author_id,
            username=username,
            role_ids=self._role_ids_from_payload(payload),
            author_is_bot=author_is_bot,
        ):
            self._policy_blocked_count += 1
            return
        self._policy_allowed_count += 1

        attachments = self._normalize_attachment_rows(payload.get("attachments"))
        content = str(payload.get("content", "") or "").strip()

        # Download attachment bytes concurrently
        attachment_data: list[dict[str, Any]] = []
        if attachments:
            download_tasks = [
                self._download_attachment(row["url"], row["filename"])
                for row in attachments
            ]
            results = await asyncio.gather(*download_tasks, return_exceptions=True)
            for row, data in zip(attachments, results):
                entry = dict(row)
                entry["data"] = data if isinstance(data, bytes) else None
                attachment_data.append(entry)

        # Build text
        attachment_desc = " ".join(
            row["filename"] or row["id"] or "file"
            for row in attachments
            if row.get("filename") or row.get("id")
        )
        if content:
            text = content
        elif attachment_desc:
            text = f"[attachments: {attachment_desc}]"
        else:
            text = "[attachment]"

        metadata = {
            "channel": "discord",
            "channel_id": channel_id,
            "guild_id": str(payload.get("guild_id", "") or "").strip(),
            "message_id": str(payload.get("id", "") or "").strip(),
            "author_username": username,
            "author_global_name": str(author.get("global_name", "") or "").strip(),
            "attachments": attachments,
            "attachment_data": attachment_data,
            "is_dm": not bool(payload.get("guild_id")),
        }

        await self._start_typing(channel_id)
        try:
            session_id = self._derive_session_id(
                channel_id=channel_id,
                guild_id=metadata["guild_id"],
                user_id=author_id,
            )
            session_id = await self._apply_bound_session(
                channel_id=channel_id,
                fallback_session_id=session_id,
                metadata=metadata,
            )
            metadata["session_key"] = session_id
            await self.emit(
                session_id=session_id,
                user_id=author_id,
                text=text,
                metadata=metadata,
            )
        finally:
            await self._stop_typing(channel_id)

    async def _handle_message_reaction_add(self, payload: dict[str, Any]) -> None:
        """Handle incoming reaction — emits as metadata-only event for agent awareness."""
        user_id = str(payload.get("user_id", "") or "").strip()
        if not user_id or user_id == self._bot_user_id:
            return
        channel_id = str(payload.get("channel_id", "") or "").strip()
        if not channel_id:
            return
        member = payload.get("member")
        member_user = member.get("user") if isinstance(member, dict) else None
        username = ""
        if isinstance(member_user, dict):
            username = str(member_user.get("username", "") or "").strip()
        if not self._is_payload_authorized(
            payload=payload,
            user_id=user_id,
            username=username,
            role_ids=self._role_ids_from_payload(payload),
            author_is_bot=False,
        ):
            self._policy_blocked_count += 1
            return
        self._policy_allowed_count += 1
        emoji_data = payload.get("emoji") or {}
        emoji_name = str(emoji_data.get("name", "") or "").strip()
        emoji_id = str(emoji_data.get("id", "") or "").strip()
        emoji_str = f"{emoji_name}:{emoji_id}" if emoji_id else emoji_name
        if not emoji_str:
            return
        guild_id = str(payload.get("guild_id", "") or "").strip()
        metadata = {
            "channel": "discord",
            "channel_id": channel_id,
            "guild_id": guild_id,
            "message_id": str(payload.get("message_id", "") or "").strip(),
            "event_type": "reaction_add",
            "emoji": emoji_str,
        }
        session_id = self._derive_session_id(
            channel_id=channel_id,
            guild_id=guild_id,
            user_id=user_id,
        )
        session_id = await self._apply_bound_session(
            channel_id=channel_id,
            fallback_session_id=session_id,
            metadata=metadata,
        )
        metadata["session_key"] = session_id
        await self.emit(
            session_id=session_id,
            user_id=user_id,
            text=f"[reaction: {emoji_str}]",
            metadata=metadata,
        )

    async def _handle_interaction_create(self, payload: dict[str, Any]) -> None:
        """Handle Discord INTERACTION_CREATE — slash commands (type 2) and button clicks (type 3)."""
        interaction_id = str(payload.get("id", "") or "").strip()
        interaction_token = str(payload.get("token", "") or "").strip()
        interaction_type = int(payload.get("type", 0) or 0)
        channel_id = str(payload.get("channel_id", "") or "").strip()
        data = payload.get("data") or {}
        member = payload.get("member") or {}
        user = payload.get("user") or member.get("user") or {}
        user_id = str(user.get("id", "") or "").strip()
        username = str(user.get("username", "") or "").strip()

        if not interaction_id or not interaction_token:
            return

        # ACK the interaction immediately (type 5 = deferred channel message)
        asyncio.create_task(self._ack_interaction(interaction_id, interaction_token))

        if not self._is_payload_authorized(
            payload=payload,
            user_id=user_id,
            username=username,
            role_ids=self._role_ids_from_payload(payload),
            author_is_bot=bool(user.get("bot")),
            ignore_mention_policy=True,
        ):
            self._policy_blocked_count += 1
            return
        self._policy_allowed_count += 1

        guild_id = str(payload.get("guild_id", "") or "").strip()
        session_id = self._derive_interaction_session_id(
            channel_id=channel_id,
            guild_id=guild_id,
            user_id=user_id,
            interaction_type=interaction_type,
        )

        if interaction_type == 2:
            # APPLICATION_COMMAND (slash command)
            command_name = str(data.get("name", "") or "").strip()
            options = data.get("options") or []
            args_text = " ".join(
                f"{o.get('name')}={o.get('value')}" for o in options if isinstance(o, dict)
            )
            text = f"/{command_name}" + (f" {args_text}" if args_text else "")
            metadata = {
                "channel": "discord",
                "channel_id": channel_id,
                "update_kind": "slash_command",
                "command_name": command_name,
                "command_options": options,
                "interaction_id": interaction_id,
                "interaction_token": interaction_token,
                "user_id": user_id,
                "username": username,
                "text": text,
                "guild_id": guild_id,
                "session_key": session_id,
            }
            session_id = await self._apply_bound_session(
                channel_id=channel_id,
                fallback_session_id=session_id,
                metadata=metadata,
            )
            metadata["session_key"] = session_id
            await self.emit(
                session_id=session_id,
                user_id=user_id,
                text=text,
                metadata=metadata,
            )

        elif interaction_type == 3:
            # MESSAGE_COMPONENT (buttons and selects)
            custom_id = str(data.get("custom_id", "") or "").strip()
            component_type = int(data.get("component_type", 0) or 0)
            selected_values = self._normalize_component_values(data.get("values"))
            selected_labels = self._component_selected_labels(
                component_type=component_type,
                values=selected_values,
                data=data if isinstance(data, dict) else {},
            )
            message = payload.get("message") or {}
            message_id = str(message.get("id", "") or "").strip()
            text = self._component_event_text(
                component_type=component_type,
                custom_id=custom_id,
                values=selected_values,
                labels=selected_labels,
            )
            metadata = {
                "channel": "discord",
                "channel_id": channel_id,
                "update_kind": self._component_update_kind(component_type),
                "custom_id": custom_id,
                "component_type": component_type,
                "selected_values": list(selected_values),
                "selected_labels": list(selected_labels),
                "message_id": message_id,
                "interaction_id": interaction_id,
                "interaction_token": interaction_token,
                "user_id": user_id,
                "username": username,
                "text": text,
                "guild_id": guild_id,
                "session_key": session_id,
            }
            session_id = await self._apply_bound_session(
                channel_id=channel_id,
                fallback_session_id=session_id,
                metadata=metadata,
            )
            metadata["session_key"] = session_id
            await self.emit(
                session_id=session_id,
                user_id=user_id,
                text=text,
                metadata=metadata,
            )

        elif interaction_type == 5:
            # MODAL_SUBMIT
            custom_id = str(data.get("custom_id", "") or "").strip()
            modal_fields = self._normalize_modal_fields(data.get("components"))
            text = self._modal_event_text(custom_id=custom_id, fields=modal_fields)
            metadata = {
                "channel": "discord",
                "channel_id": channel_id,
                "update_kind": "modal_submit",
                "custom_id": custom_id,
                "interaction_id": interaction_id,
                "interaction_token": interaction_token,
                "user_id": user_id,
                "username": username,
                "text": text,
                "guild_id": guild_id,
                "modal_field_ids": self._modal_field_ids(modal_fields),
                "modal_field_labels": self._modal_field_labels(modal_fields),
                "modal_fields": modal_fields,
                "session_key": session_id,
            }
            session_id = await self._apply_bound_session(
                channel_id=channel_id,
                fallback_session_id=session_id,
                metadata=metadata,
            )
            metadata["session_key"] = session_id
            await self.emit(
                session_id=session_id,
                user_id=user_id,
                text=text,
                metadata=metadata,
            )

    async def _ack_interaction(self, interaction_id: str, interaction_token: str) -> None:
        """Immediately ACK a Discord interaction with deferred response (type 5)."""
        try:
            await self._post_json(
                url=f"{self.api_base}/interactions/{interaction_id}/{interaction_token}/callback",
                payload={"type": 5},
                error_prefix="discord_interaction_ack",
            )
        except Exception:
            pass  # ACK failure is non-fatal; Discord will timeout gracefully

    async def register_slash_command(
        self,
        *,
        name: str,
        description: str,
        options: list[dict[str, Any]] | None = None,
        guild_id: str | None = None,
    ) -> dict[str, Any]:
        """Register (or overwrite) a global or guild slash command."""
        app_id = self._application_id
        if not app_id:
            raise RuntimeError("discord_application_id_unknown — wait for READY event")
        clean_guild = str(guild_id or "").strip()
        if clean_guild:
            url = f"{self.api_base}/applications/{app_id}/guilds/{clean_guild}/commands"
        else:
            url = f"{self.api_base}/applications/{app_id}/commands"
        body: dict[str, Any] = {
            "name": str(name or "").strip(),
            "description": str(description or "").strip(),
            "type": 1,  # CHAT_INPUT
        }
        if options:
            body["options"] = options
        response = await self._post_json(url=url, payload=body, error_prefix="discord_register_slash")
        try:
            return dict(response.json() if response.content else {})
        except Exception:
            return {}

    async def list_slash_commands(self, *, guild_id: str | None = None) -> list[dict[str, Any]]:
        """List registered global or guild slash commands."""
        app_id = self._application_id
        if not app_id:
            return []
        clean_guild = str(guild_id or "").strip()
        if clean_guild:
            url = f"{self.api_base}/applications/{app_id}/guilds/{clean_guild}/commands"
        else:
            url = f"{self.api_base}/applications/{app_id}/commands"
        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                response = await client.get(
                    url,
                    headers={"Authorization": f"Bot {self.token}", "Content-Type": "application/json"},
                )
            return list(response.json() if response.content else [])
        except Exception:
            return []

    async def reply_interaction(
        self,
        *,
        interaction_id: str,
        interaction_token: str,
        text: str,
        components: list[dict[str, Any]] | None = None,
        embeds: list[dict[str, Any]] | None = None,
        ephemeral: bool = False,
    ) -> str:
        """Edit the deferred interaction reply (follow-up to ACK type 5)."""
        url = f"{self.api_base}/webhooks/{self._application_id}/{interaction_token}/messages/@original"
        body: dict[str, Any] = {"content": str(text or "")}
        if components:
            body["components"] = components
        if embeds:
            body["embeds"] = embeds
        if ephemeral:
            body["flags"] = 64  # EPHEMERAL
        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                response = await client.patch(
                    url,
                    json=body,
                    headers={"Authorization": f"Bot {self.token}", "Content-Type": "application/json"},
                )
            data = response.json() if response.content else {}
            return str(data.get("id", "") or "")
        except Exception:
            return ""

    @staticmethod
    def _generate_placeholder_waveform() -> str:
        """Generate a placeholder sine-wave waveform (base64, 256 samples)."""
        import base64
        import math
        samples = [
            min(255, max(0, round(128 + 64 * math.sin((i / DISCORD_VOICE_WAVEFORM_SAMPLES) * math.pi * 8))))
            for i in range(DISCORD_VOICE_WAVEFORM_SAMPLES)
        ]
        return base64.b64encode(bytes(samples)).decode("ascii")

    async def _generate_waveform_from_audio(self, audio_bytes: bytes) -> str:
        """Generate waveform by sampling raw PCM via ffmpeg. Falls back to placeholder."""
        import base64
        import os
        import struct
        import tempfile
        try:
            with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
                f.write(audio_bytes)
                tmp_in = f.name
            tmp_pcm = tmp_in + ".raw"
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-y", "-i", tmp_in, "-vn", "-f", "s16le",
                "-acodec", "pcm_s16le", "-ac", "1", "-ar", "8000", tmp_pcm,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.communicate()
            if proc.returncode != 0:
                return self._generate_placeholder_waveform()
            with open(tmp_pcm, "rb") as fpcm:
                pcm_data = fpcm.read()
            samples_raw = struct.unpack(f"{len(pcm_data) // 2}h", pcm_data)
            step = max(1, len(samples_raw) // DISCORD_VOICE_WAVEFORM_SAMPLES)
            waveform = []
            for i in range(DISCORD_VOICE_WAVEFORM_SAMPLES):
                chunk = samples_raw[i * step:(i + 1) * step] or (0,)
                avg = sum(abs(s) for s in chunk) / len(chunk)
                waveform.append(min(255, round((avg / 32767) * 255)))
            while len(waveform) < DISCORD_VOICE_WAVEFORM_SAMPLES:
                waveform.append(0)
            return base64.b64encode(bytes(waveform)).decode("ascii")
        except Exception:
            return self._generate_placeholder_waveform()
        finally:
            for p in (tmp_in, tmp_pcm):  # type: ignore[possibly-undefined]
                try:
                    os.unlink(p)
                except Exception:
                    pass

    async def send_voice_message(
        self,
        *,
        channel_id: str,
        audio_bytes: bytes,
        duration_secs: float,
        waveform: str | None = None,
        reply_to_message_id: str | None = None,
        silent: bool = False,
    ) -> str:
        """Send a Discord voice message (OGG/Opus, IS_VOICE_MESSAGE flag).

        Three-step protocol:
        1. POST /channels/{id}/attachments → get upload_url + upload_filename
        2. PUT {upload_url} with audio bytes
        3. POST /channels/{id}/messages with flag 8192 + attachment metadata
        """
        if not channel_id:
            raise ValueError("channel_id is required")
        clean_channel = str(channel_id).strip()
        resolved_waveform = waveform or await self._generate_waveform_from_audio(audio_bytes)

        # Step 1: Request upload URL
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            r1 = await client.post(
                f"{self.api_base}/channels/{clean_channel}/attachments",
                json={"files": [{"filename": "voice-message.ogg", "file_size": len(audio_bytes), "id": "0"}]},
                headers={"Authorization": f"Bot {self.token}", "Content-Type": "application/json"},
            )
        r1.raise_for_status()
        attachment_info = r1.json().get("attachments", [{}])[0]
        upload_url = str(attachment_info.get("upload_url", "") or "")
        upload_filename = str(attachment_info.get("upload_filename", "") or "")
        if not upload_url:
            raise RuntimeError("discord_voice_upload_url_missing")

        # Step 2: Upload the audio
        async with httpx.AsyncClient(timeout=max(30.0, self.timeout_s)) as client:
            r2 = await client.put(upload_url, content=audio_bytes, headers={"Content-Type": "audio/ogg"})
        r2.raise_for_status()

        # Step 3: Send message with voice flag
        flags = DISCORD_VOICE_MESSAGE_FLAG
        if silent:
            flags |= (1 << 12)  # SUPPRESS_NOTIFICATIONS
        msg_body: dict[str, Any] = {
            "flags": flags,
            "attachments": [{
                "id": "0",
                "filename": "voice-message.ogg",
                "uploaded_filename": upload_filename,
                "duration_secs": round(float(duration_secs or 0), 2),
                "waveform": resolved_waveform,
            }],
        }
        if reply_to_message_id:
            msg_body["message_reference"] = {
                "message_id": reply_to_message_id,
                "fail_if_not_exists": False,
            }

        response = await self._post_json(
            url=f"{self.api_base}/channels/{clean_channel}/messages",
            payload=msg_body,
            error_prefix="discord_voice_message",
        )
        try:
            data = response.json() if response.content else {}
        except Exception:
            data = {}
        message_id = str(data.get("id", "") or "").strip() or "unknown"
        return f"discord:voice:{message_id}"

    async def create_webhook(
        self, *, channel_id: str, name: str, avatar: str | None = None
    ) -> dict[str, Any]:
        """Create a webhook in a channel. Returns {id, token, name, ...}."""
        body: dict[str, Any] = {"name": str(name or "clawlite").strip()[:80]}
        if avatar:
            body["avatar"] = str(avatar)
        response = await self._post_json(
            url=f"{self.api_base}/channels/{channel_id}/webhooks",
            payload=body,
            error_prefix="discord_create_webhook",
        )
        try:
            return dict(response.json() if response.content else {})
        except Exception:
            return {}

    async def execute_webhook(
        self,
        *,
        webhook_id: str,
        webhook_token: str,
        text: str = "",
        username: str | None = None,
        avatar_url: str | None = None,
        embeds: list[dict[str, Any]] | None = None,
        components: list[dict[str, Any]] | None = None,
    ) -> str:
        """Execute (post via) a webhook. Returns message_id or empty string."""
        body: dict[str, Any] = {"content": str(text or "")}
        if username:
            body["username"] = str(username)[:80]
        if avatar_url:
            body["avatar_url"] = str(avatar_url)
        if embeds:
            body["embeds"] = embeds
        if components:
            body["components"] = components
        response = await self._post_json(
            url=f"{self.api_base}/webhooks/{webhook_id}/{webhook_token}?wait=true",
            payload=body,
            error_prefix="discord_execute_webhook",
        )
        try:
            data = response.json() if response.content else {}
            return str(data.get("id", "") or "")
        except Exception:
            return ""

    async def create_poll(
        self,
        *,
        channel_id: str,
        question: str,
        answers: list[str],
        duration_hours: int = 24,
        allow_multiselect: bool = False,
    ) -> str:
        """Create a Discord poll in a channel. Returns message_id."""
        clean_answers = [str(a).strip()[:55] for a in answers if str(a).strip()][:10]
        payload: dict[str, Any] = {
            "poll": {
                "question": {"text": str(question)[:300]},
                "answers": [{"poll_media": {"text": a}} for a in clean_answers],
                "duration": max(1, int(duration_hours or 24)),
                "allow_multiselect": bool(allow_multiselect),
                "layout_type": 1,
            }
        }
        response = await self._post_json(
            url=f"{self.api_base}/channels/{channel_id}/messages",
            payload=payload,
            error_prefix="discord_create_poll",
        )
        try:
            data = response.json() if response.content else {}
            return str(data.get("id", "") or "")
        except Exception:
            return ""

    async def _patch_json(self, *, url: str, payload: dict[str, Any]) -> httpx.Response:
        """PATCH JSON to Discord API with auth headers."""
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            return await client.patch(
                url,
                json=payload,
                headers={"Authorization": f"Bot {self.token}", "Content-Type": "application/json"},
            )

    async def send_streaming(
        self,
        *,
        channel_id: str,
        chunks: Any,  # AsyncGenerator[ProviderChunk, None]
        min_edit_interval_s: float = 0.8,
    ) -> str:
        """Stream response to Discord: create placeholder message, edit as chunks arrive.

        Args:
            channel_id: target Discord channel
            chunks: async generator yielding ProviderChunk objects
            min_edit_interval_s: minimum seconds between edits (avoid rate limits)
        Returns:
            discord:streamed:{message_id}
        """
        clean_channel = str(channel_id).strip()

        # Create initial placeholder
        response = await self._post_json(
            url=f"{self.api_base}/channels/{clean_channel}/messages",
            payload={"content": "…"},
            error_prefix="discord_stream_create",
        )
        try:
            msg_id = str((response.json() if response.content else {}).get("id", "") or "")
        except Exception:
            msg_id = ""

        if not msg_id:
            return ""

        accumulated = ""
        last_edit_time = 0.0
        last_sent_text = "…"
        edit_url = f"{self.api_base}/channels/{clean_channel}/messages/{msg_id}"

        async for chunk in chunks:
            if chunk.text:
                accumulated = chunk.accumulated or (accumulated + chunk.text)
            now = time.monotonic()
            should_edit = (
                accumulated != last_sent_text
                and (chunk.done or (now - last_edit_time) >= min_edit_interval_s)
            )
            if should_edit and accumulated:
                try:
                    await self._patch_json(url=edit_url, payload={"content": accumulated})
                    last_sent_text = accumulated
                    last_edit_time = now
                except Exception:
                    pass
            if chunk.done:
                break

        # Final edit to ensure complete text
        if accumulated and accumulated != last_sent_text:
            try:
                await self._patch_json(url=edit_url, payload={"content": accumulated})
            except Exception:
                pass

        return f"discord:streamed:{msg_id}"

    async def _typing_loop(self, channel_id: str) -> None:
        client = self._client
        if client is None:
            return
        url = f"{self.api_base}/channels/{channel_id}/typing"
        while self._running:
            try:
                await client.post(url)
            except asyncio.CancelledError:
                raise
            except Exception:
                return
            await asyncio.sleep(self.typing_interval_s)

    async def _start_typing(self, channel_id: str) -> None:
        if not self.typing_enabled:
            return
        if not channel_id:
            return
        existing = self._typing_tasks.get(channel_id)
        if existing is not None and not existing.done():
            return
        self._typing_tasks[channel_id] = asyncio.create_task(
            self._typing_loop(channel_id)
        )

    async def _stop_typing(self, channel_id: str) -> None:
        task = self._typing_tasks.pop(channel_id, None)
        await cancel_task(task)

    @staticmethod
    def _task_state(task: asyncio.Task[Any] | None) -> str:
        if task is None:
            return "stopped"
        if task.cancelled():
            return "cancelled"
        if task.done():
            exc = task.exception()
            return "failed" if exc is not None else "finished"
        return "running"

    def operator_status(self) -> dict[str, Any]:
        gateway_task_state = self._task_state(self._gateway_task)
        heartbeat_task_state = self._task_state(self._heartbeat_task)
        hints: list[str] = []
        if self.on_message is not None and gateway_task_state != "running":
            hints.append("Discord gateway listener is not running; refresh transport to reconnect the gateway loop.")
        if self._last_error:
            hints.append("Discord recorded a recent transport or HTTP error; inspect the error and consider refreshing transport.")
        if not self._session_id and gateway_task_state == "running":
            hints.append("Discord gateway is running without an active session id yet; wait for READY/RESUMED or refresh transport.")
        return {
            "running": bool(self._running),
            "connected": self._ws is not None,
            "gateway_task_state": gateway_task_state,
            "heartbeat_task_state": heartbeat_task_state,
            "session_id": self._session_id,
            "resume_url": self._resume_url,
            "sequence": self._sequence,
            "bot_user_id": self._bot_user_id,
            "dm_cache_size": len(self._dm_channel_ids),
            "typing_tasks": len(self._typing_tasks),
            "last_error": str(self._last_error or ""),
            "dm_policy": self.dm_policy,
            "group_policy": self.group_policy,
            "allow_bots": self.allow_bots,
            "reply_to_mode": self.reply_to_mode,
            "slash_isolated_sessions": self.slash_isolated_sessions,
            "presence_status": self.presence_status,
            "presence_activity": self.presence_activity,
            "presence_activity_type": self.presence_activity_type,
            "presence_activity_url": self.presence_activity_url,
            "auto_presence_enabled": self.auto_presence_enabled,
            "auto_presence_interval_s": self.auto_presence_interval_s,
            "auto_presence_min_update_interval_s": self.auto_presence_min_update_interval_s,
            "auto_presence_task_state": self._task_state(self._auto_presence_task),
            "auto_presence_healthy_text": self.auto_presence_healthy_text,
            "auto_presence_degraded_text": self.auto_presence_degraded_text,
            "auto_presence_exhausted_text": self.auto_presence_exhausted_text,
            "presence_last_state": self._presence_last_state,
            "presence_last_error": self._presence_last_error,
            "guild_allowlist_count": len(self.guilds),
            "policy_allowed_count": self._policy_allowed_count,
            "policy_blocked_count": self._policy_blocked_count,
            "thread_bindings_enabled": self.thread_bindings_enabled,
            "thread_binding_state_path": str(self.thread_binding_state_path or ""),
            "thread_binding_idle_timeout_s": self.thread_binding_idle_timeout_s,
            "thread_binding_max_age_s": self.thread_binding_max_age_s,
            "thread_binding_count": len(self._thread_bindings),
            "hints": hints,
        }

    def _build_presence_payload(
        self,
        *,
        status: str,
        activity: str = "",
        activity_type: int = 4,
        activity_url: str = "",
    ) -> dict[str, Any] | None:
        normalized_status = str(status or "").strip().lower()
        normalized_activity = str(activity or "").strip()
        normalized_activity_url = str(activity_url or "").strip()
        if not normalized_status and not normalized_activity:
            return None
        payload: dict[str, Any] = {
            "status": normalized_status or "online",
            "since": 0,
            "afk": False,
            "activities": [],
        }
        if not normalized_activity:
            return payload

        normalized_type = min(5, max(0, int(activity_type or 0)))
        activity_payload: dict[str, Any] = {"type": normalized_type}
        if normalized_type == 4:
            activity_payload["name"] = "Custom Status"
            activity_payload["state"] = normalized_activity
        else:
            activity_payload["name"] = normalized_activity
            if normalized_type == 1 and normalized_activity_url:
                activity_payload["url"] = normalized_activity_url
        payload["activities"] = [activity_payload]
        return payload

    def _derive_auto_presence(self) -> tuple[str, dict[str, Any] | None]:
        if not self.auto_presence_enabled:
            return ("disabled", None)
        gateway_task_state = self._task_state(self._gateway_task)
        if self._ws is None or not self._running or gateway_task_state != "running":
            state = "exhausted"
            text = self.auto_presence_exhausted_text or self.presence_activity
            return (
                state,
                self._build_presence_payload(
                    status="dnd",
                    activity=text,
                    activity_type=4 if text and self.auto_presence_exhausted_text else self.presence_activity_type,
                    activity_url="" if self.auto_presence_exhausted_text else self.presence_activity_url,
                ),
            )
        if self._last_error or not self._session_id:
            state = "degraded"
            text = self.auto_presence_degraded_text or self.presence_activity
            return (
                state,
                self._build_presence_payload(
                    status="idle",
                    activity=text,
                    activity_type=4 if text and self.auto_presence_degraded_text else self.presence_activity_type,
                    activity_url="" if self.auto_presence_degraded_text else self.presence_activity_url,
                ),
            )
        state = "healthy"
        text = self.auto_presence_healthy_text or self.presence_activity
        return (
            state,
            self._build_presence_payload(
                status="online",
                activity=text,
                activity_type=4 if text and self.auto_presence_healthy_text else self.presence_activity_type,
                activity_url="" if self.auto_presence_healthy_text else self.presence_activity_url,
            ),
        )

    def _presence_payload(self) -> dict[str, Any] | None:
        if self.auto_presence_enabled:
            state, payload = self._derive_auto_presence()
            self._presence_last_state = state
            return payload
        self._presence_last_state = "static"
        return self._build_presence_payload(
            status=self.presence_status,
            activity=self.presence_activity,
            activity_type=self.presence_activity_type,
            activity_url=self.presence_activity_url,
        )

    async def _update_presence(self, *, force: bool = False) -> dict[str, Any]:
        payload = self._presence_payload()
        if payload is None:
            return {"ok": False, "sent": False, "reason": "presence_not_configured"}
        ws = self._ws
        if ws is None:
            return {"ok": False, "sent": False, "reason": "discord_gateway_unavailable"}
        signature = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        now = time.monotonic()
        if not force:
            if signature == self._presence_last_payload_signature:
                return {"ok": True, "sent": False, "reason": "unchanged"}
            if (now - self._presence_last_sent_at) < self.auto_presence_min_update_interval_s:
                return {"ok": True, "sent": False, "reason": "min_interval"}
        try:
            await self._send_ws_json({"op": 3, "d": payload})
        except Exception as exc:
            self._presence_last_error = str(exc)
            self._last_error = str(exc)
            return {"ok": False, "sent": False, "reason": "send_failed", "error": str(exc)}
        self._presence_last_payload_signature = signature
        self._presence_last_sent_at = now
        self._presence_last_error = ""
        return {"ok": True, "sent": True, "reason": "updated", "state": self._presence_last_state}

    async def _auto_presence_loop(self) -> None:
        while self._running:
            try:
                if self._ws is not None:
                    await self._update_presence(force=False)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._presence_last_error = str(exc)
                self._last_error = str(exc)
            await asyncio.sleep(max(1.0, self.auto_presence_interval_s))

    async def operator_refresh_presence(self) -> dict[str, Any]:
        result = await self._update_presence(force=True)
        return result | {"status": self.operator_status()}

    async def operator_refresh_transport(self) -> dict[str, Any]:
        was_running = bool(self._running)
        was_gateway_running = self._gateway_task is not None and not self._gateway_task.done()
        summary: dict[str, Any] = {
            "ok": True,
            "was_running": was_running,
            "gateway_restarted": False,
            "last_error": "",
        }
        try:
            await cancel_task(self._gateway_task)
            self._gateway_task = None
            await cancel_task(self._heartbeat_task)
            self._heartbeat_task = None
            ws = self._ws
            self._ws = None
            if ws is not None:
                close_fn = getattr(ws, "close", None)
                if callable(close_fn):
                    result = close_fn()
                    if asyncio.iscoroutine(result):
                        await result
            self._session_id = ""
            self._resume_url = ""
            self._sequence = None
            self._bot_user_id = ""
            self._last_error = ""
            if was_running and (self.on_message is not None or was_gateway_running):
                await self.start()
                summary["gateway_restarted"] = True
        except Exception as exc:
            self._last_error = str(exc)
            summary["ok"] = False
            summary["last_error"] = str(exc)
        return summary | {"status": self.operator_status()}
