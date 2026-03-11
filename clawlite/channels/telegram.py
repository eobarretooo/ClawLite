from __future__ import annotations

import asyncio
import base64
import datetime as dt
import html
import hashlib
import hmac
import json
import math
import os
import random
import re
import secrets
import time
from collections import deque
from email.utils import parsedate_to_datetime
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from loguru import logger

from clawlite.channels.base import BaseChannel, cancel_task
from clawlite.channels.telegram_offset_store import TelegramOffsetStore
from clawlite.channels.telegram_pairing import TelegramPairingStore
from clawlite.config.schema import TelegramChannelConfig

MAX_MESSAGE_LEN = 4000
MAX_CAPTION_LEN = 1024
MEDIA_GROUP_FLUSH_DELAY_S = 0.6
TELEGRAM_ALLOWED_UPDATES = [
    "message",
    "edited_message",
    "inline_query",
    "chosen_inline_result",
    "business_message",
    "edited_business_message",
    "deleted_business_messages",
    "business_connection",
    "callback_query",
    "shipping_query",
    "pre_checkout_query",
    "poll",
    "poll_answer",
    "my_chat_member",
    "chat_member",
    "chat_join_request",
    "message_reaction",
    "message_reaction_count",
    "chat_boost",
    "removed_chat_boost",
    "purchased_paid_media",
    "channel_post",
    "edited_channel_post",
]


@dataclass(slots=True)
class TelegramRetryPolicy:
    max_attempts: int = 3
    base_backoff_s: float = 0.35
    max_backoff_s: float = 8.0
    jitter_ratio: float = 0.2

    def normalized(self) -> "TelegramRetryPolicy":
        max_attempts = max(1, int(self.max_attempts))
        base_backoff_s = max(0.0, float(self.base_backoff_s))
        max_backoff_s = max(base_backoff_s, float(self.max_backoff_s))
        jitter_ratio = min(0.9, max(0.0, float(self.jitter_ratio)))
        return TelegramRetryPolicy(
            max_attempts=max_attempts,
            base_backoff_s=base_backoff_s,
            max_backoff_s=max_backoff_s,
            jitter_ratio=jitter_ratio,
        )


class TelegramCircuitOpenError(RuntimeError):
    pass


class TelegramAuthCircuitBreaker:
    def __init__(self, *, failure_threshold: int = 1, cooldown_s: float = 60.0) -> None:
        self.failure_threshold = max(1, int(failure_threshold))
        self.cooldown_s = max(1.0, float(cooldown_s))
        self._consecutive_failures = 0
        self._open_until_monotonic: float | None = None

    @property
    def is_open(self) -> bool:
        if self._open_until_monotonic is None:
            return False
        return time.monotonic() < self._open_until_monotonic

    def on_success(self) -> None:
        self._consecutive_failures = 0
        self._open_until_monotonic = None

    def on_auth_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.failure_threshold:
            self._open_until_monotonic = time.monotonic() + self.cooldown_s


def _status_code_from_exc(exc: Exception) -> int | None:
    for attr in ("status_code", "error_code"):
        value = getattr(exc, attr, None)
        try:
            if value is not None:
                return int(value)
        except (TypeError, ValueError):
            pass

    response = getattr(exc, "response", None)
    if response is not None:
        value = getattr(response, "status_code", None)
        try:
            if value is not None:
                return int(value)
        except (TypeError, ValueError):
            pass
    return None


def _exception_text(exc: Exception) -> str:
    return str(exc or "").strip().lower()


def _is_auth_failure(exc: Exception) -> bool:
    status_code = _status_code_from_exc(exc)
    if status_code in {401, 403}:
        return True
    name = exc.__class__.__name__.lower()
    return "unauthorized" in name or "forbidden" in name


def _is_transient_failure(exc: Exception) -> bool:
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError, ConnectionError, OSError)):
        return True

    status_code = _status_code_from_exc(exc)
    if status_code == 429:
        return True

    name = exc.__class__.__name__.lower()
    if any(part in name for part in ("timeout", "network", "retryafter")):
        return True

    text = _exception_text(exc)
    return any(
        snippet in text
        for snippet in (
            "timed out",
            "timeout",
            "temporary failure",
            "connection reset",
            "too many requests",
            "retry after",
            "network",
        )
    )


def _is_formatting_error(exc: Exception) -> bool:
    if _status_code_from_exc(exc) != 400:
        return False
    text = _exception_text(exc)
    return "can't parse entities" in text or "parse entities" in text


def _is_thread_not_found_error(exc: Exception) -> bool:
    status_code = _status_code_from_exc(exc)
    if status_code not in {None, 400}:
        return False
    return "message thread not found" in _exception_text(exc)


def _retry_delay_s(policy: TelegramRetryPolicy, attempt: int) -> float:
    normalized = policy.normalized()
    base = normalized.base_backoff_s * (2 ** max(0, int(attempt) - 1))
    capped = min(base, normalized.max_backoff_s)
    if capped <= 0:
        return 0.0
    jitter_span = capped * normalized.jitter_ratio
    jitter = (random.random() * 2.0 - 1.0) * jitter_span
    return max(0.0, capped + jitter)


def _coerce_retry_after_seconds(value: Any) -> float | None:
    if value is None:
        return None
    if hasattr(value, "total_seconds"):
        try:
            seconds = float(value.total_seconds())
            if math.isfinite(seconds) and seconds > 0:
                return seconds
        except (TypeError, ValueError):
            pass
    try:
        seconds = float(value)
        if math.isfinite(seconds) and seconds > 0:
            return seconds
    except (TypeError, ValueError):
        pass
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            seconds = float(text)
            if math.isfinite(seconds) and seconds > 0:
                return seconds
        except ValueError:
            pass
        try:
            when = parsedate_to_datetime(text)
            if when.tzinfo is None:
                return None
            seconds = when.timestamp() - time.time()
            if math.isfinite(seconds) and seconds > 0:
                return seconds
        except (TypeError, ValueError, IndexError):
            return None
    return None


def _retry_after_delay_s(exc: Exception) -> float | None:
    direct = _coerce_retry_after_seconds(getattr(exc, "retry_after", None))
    if direct is not None:
        return direct

    parameters = getattr(exc, "parameters", None)
    from_parameters = _coerce_retry_after_seconds(
        getattr(parameters, "retry_after", None)
    )
    if from_parameters is not None:
        return from_parameters

    response = getattr(exc, "response", None)
    if response is None:
        return None

    headers = getattr(response, "headers", None)
    if headers is None and isinstance(response, dict):
        headers = response.get("headers")
    if headers is None:
        return None

    if hasattr(headers, "get"):
        for key in ("retry-after", "Retry-After", "RETRY-AFTER"):
            value = headers.get(key)
            delay = _coerce_retry_after_seconds(value)
            if delay is not None:
                return delay
    return None


def split_message(text: str, max_len: int = MAX_MESSAGE_LEN) -> list[str]:
    content = text or ""
    if len(content) <= max_len:
        return [content]
    parts: list[str] = []
    current = ""
    for line in content.splitlines(True):
        if len(current) + len(line) <= max_len:
            current += line
            continue
        if current:
            parts.append(current)
        if len(line) <= max_len:
            current = line
            continue
        start = 0
        while start < len(line):
            end = start + max_len
            parts.append(line[start:end])
            start = end
        current = ""
    if current:
        parts.append(current)
    return parts


def _normalize_telegram_markdown(text: str) -> str:
    normalized = str(text or "").replace("\r\n", "\n").strip()
    if not normalized:
        return ""

    normalized = re.sub(r":\s+-\s+", ":\n- ", normalized)
    lines: list[str] = []
    for raw_line in normalized.split("\n"):
        line = raw_line.rstrip()
        stripped = line.lstrip()
        indent = line[: len(line) - len(stripped)]
        if stripped.startswith(("- ", "* ")) and " - " in stripped[2:]:
            bullet = stripped[0]
            items = [item.strip() for item in stripped[2:].split(" - ") if item.strip()]
            if len(items) > 1:
                for item in items:
                    lines.append(f"{indent}{bullet} {item}")
                continue
        lines.append(line)
    normalized = "\n".join(lines)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized


def markdown_to_telegram_html(text: str) -> str:
    if not text:
        return ""

    text = _normalize_telegram_markdown(text)
    original_text = text
    token_map: dict[str, str] = {}

    def _reserve_token(prefix: str) -> str:
        while True:
            candidate = f"\x00TG_{prefix}_{secrets.token_hex(8)}\x00"
            if candidate in token_map:
                continue
            if candidate in original_text:
                continue
            return candidate

    def save_code_block(match: re.Match[str]) -> str:
        code = match.group(1)
        token = _reserve_token("CB")
        escaped = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        token_map[token] = f"<pre><code>{escaped}</code></pre>"
        return token

    text = re.sub(r"```[\w]*\n?([\s\S]*?)```", save_code_block, text)

    def save_inline_code(match: re.Match[str]) -> str:
        code = match.group(1)
        token = _reserve_token("IC")
        escaped = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        token_map[token] = f"<code>{escaped}</code>"
        return token

    text = re.sub(r"`([^`]+)`", save_inline_code, text)
    text = re.sub(r"^#{1,6}\s+(.+)$", r"\1", text, flags=re.MULTILINE)
    text = re.sub(r"^>\s*(.*)$", r"\1", text, flags=re.MULTILINE)
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)
    text = re.sub(r"(?<![a-zA-Z0-9])_([^_]+)_(?![a-zA-Z0-9])", r"<i>\1</i>", text)
    text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text)
    text = re.sub(r"^[-*]\s+", "&#8226; ", text, flags=re.MULTILINE)

    for token, rendered in token_map.items():
        text = text.replace(token, rendered)

    return text


def parse_command(text: str) -> tuple[str, str]:
    stripped = str(text or "").strip()
    if not stripped.startswith("/"):
        return "", ""
    head, _, tail = stripped.partition(" ")
    cmd = head[1:]
    if "@" in cmd:
        cmd = cmd.split("@", 1)[0]
    return cmd.lower(), tail.strip()


class TelegramChannel(BaseChannel):
    def __init__(self, *, config: dict[str, Any], on_message=None) -> None:
        super().__init__(name="telegram", config=config, on_message=on_message)
        token = str(config.get("token", "")).strip()
        if not token:
            raise ValueError("telegram token is required")
        telegram_config = TelegramChannelConfig.from_dict(config)
        self.token = token
        self.allow_from = telegram_config.allow_from
        self.dm_policy = self._normalize_access_policy(telegram_config.dm_policy)
        self.group_policy = self._normalize_access_policy(telegram_config.group_policy)
        self.topic_policy = self._normalize_access_policy(telegram_config.topic_policy)
        self.dm_allow_from = self._normalize_allow_from_values(
            telegram_config.dm_allow_from
        )
        self.group_allow_from = self._normalize_allow_from_values(
            telegram_config.group_allow_from
        )
        self.topic_allow_from = self._normalize_allow_from_values(
            telegram_config.topic_allow_from
        )
        self.group_overrides = {
            str(key): dict(value)
            for key, value in telegram_config.group_overrides.items()
            if isinstance(value, dict)
        }
        self.bot: Any | None = None
        self.mode = self._normalize_mode(
            str(config.get("mode", "polling") or "polling")
        )
        self.webhook_enabled = bool(
            config.get("webhook_enabled", config.get("webhookEnabled", False))
        )
        self.webhook_secret = str(
            config.get("webhook_secret", config.get("webhookSecret", "")) or ""
        ).strip()
        self.webhook_path = self._normalize_webhook_path(
            str(
                config.get(
                    "webhook_path", config.get("webhookPath", "/api/webhooks/telegram")
                )
                or "/api/webhooks/telegram"
            )
        )
        self.webhook_url = str(
            config.get("webhook_url", config.get("webhookUrl", "")) or ""
        ).strip()
        self.webhook_fail_fast_on_error = bool(
            config.get(
                "webhook_fail_fast_on_error",
                config.get(
                    "webhookFailFastOnError",
                    getattr(telegram_config, "webhook_fail_fast_on_error", False),
                ),
            )
        )
        self.poll_interval_s = float(config.get("poll_interval_s", 1.0) or 1.0)
        self.poll_timeout_s = int(config.get("poll_timeout_s", 20) or 20)
        self.reconnect_initial_s = float(config.get("reconnect_initial_s", 2.0) or 2.0)
        self.reconnect_max_s = float(config.get("reconnect_max_s", 30.0) or 30.0)
        self.send_timeout_s = float(
            config.get("send_timeout_s", config.get("sendTimeoutSec", 15.0)) or 15.0
        )
        self.send_retry_attempts = int(
            config.get("send_retry_attempts", config.get("sendRetryAttempts", 3)) or 3
        )
        self.send_backoff_base_s = float(
            config.get("send_backoff_base_s", config.get("sendBackoffBaseSec", 0.35))
            or 0.35
        )
        self.send_backoff_max_s = float(
            config.get("send_backoff_max_s", config.get("sendBackoffMaxSec", 8.0))
            or 8.0
        )
        self.send_backoff_jitter = float(
            config.get("send_backoff_jitter", config.get("sendBackoffJitter", 0.2))
            or 0.2
        )
        self.send_circuit_failure_threshold = int(
            config.get(
                "send_circuit_failure_threshold",
                config.get("sendCircuitFailureThreshold", 1),
            )
            or 1
        )
        self.send_circuit_cooldown_s = float(
            config.get(
                "send_circuit_cooldown_s", config.get("sendCircuitCooldownSec", 60.0)
            )
            or 60.0
        )
        self.typing_enabled = bool(
            config.get("typing_enabled", config.get("typingEnabled", True))
        )
        self.typing_interval_s = float(
            config.get("typing_interval_s", config.get("typingIntervalS", 2.5)) or 2.5
        )
        self.typing_max_ttl_s = float(
            config.get("typing_max_ttl_s", config.get("typingMaxTtlS", 120.0)) or 120.0
        )
        self.typing_timeout_s = float(
            config.get("typing_timeout_s", config.get("typingTimeoutS", 5.0)) or 5.0
        )
        self.typing_circuit_failure_threshold = int(
            config.get(
                "typing_circuit_failure_threshold",
                config.get("typingCircuitFailureThreshold", 1),
            )
            or 1
        )
        self.typing_circuit_cooldown_s = float(
            config.get(
                "typing_circuit_cooldown_s", config.get("typingCircuitCooldownS", 60.0)
            )
            or 60.0
        )
        self.reaction_notifications = self._normalize_reaction_notifications(
            str(
                config.get(
                    "reaction_notifications", config.get("reactionNotifications", "own")
                )
                or "own"
            )
        )
        self.reaction_own_cache_limit = max(
            1,
            int(
                config.get(
                    "reaction_own_cache_limit",
                    config.get("reactionOwnCacheLimit", 4096),
                )
                or 4096
            ),
        )
        self.dedupe_state_path = self._normalize_state_path(
            str(getattr(telegram_config, "dedupe_state_path", "") or "")
        )
        self.offset_state_path = self._normalize_optional_path(
            str(getattr(telegram_config, "offset_state_path", "") or "")
        )
        self.media_download_dir_path = self._normalize_optional_path(
            str(getattr(telegram_config, "media_download_dir", "") or "")
        )
        self.transcribe_voice = bool(
            getattr(telegram_config, "transcribe_voice", True)
        )
        self.transcribe_audio = bool(
            getattr(telegram_config, "transcribe_audio", True)
        )
        configured_transcription_key = str(
            getattr(telegram_config, "transcription_api_key", "") or ""
        ).strip()
        self.transcription_api_key = configured_transcription_key or str(
            os.getenv("GROQ_API_KEY", "") or ""
        ).strip()
        self.transcription_base_url = str(
            getattr(telegram_config, "transcription_base_url", "")
            or "https://api.groq.com/openai/v1"
        ).strip()
        self.transcription_model = str(
            getattr(telegram_config, "transcription_model", "")
            or "whisper-large-v3-turbo"
        ).strip()
        self.transcription_language = str(
            getattr(telegram_config, "transcription_language", "") or "pt"
        ).strip()
        self.transcription_timeout_s = max(
            0.1,
            float(getattr(telegram_config, "transcription_timeout_s", 90.0) or 90.0),
        )
        self.pairing_notice_cooldown_s = max(
            0.0,
            float(getattr(telegram_config, "pairing_notice_cooldown_s", 30.0) or 30.0),
        )
        self._pairing_store = TelegramPairingStore(
            token=self.token,
            state_path=str(getattr(telegram_config, "pairing_state_path", "") or ""),
        )
        self._offset_store = TelegramOffsetStore(
            token=self.token,
            state_path=self.offset_state_path,
        )
        self._transcription_provider: Any | None = None
        self.callback_signing_enabled = bool(
            getattr(telegram_config, "callback_signing_enabled", False)
        )
        self.callback_signing_secret = str(
            getattr(telegram_config, "callback_signing_secret", "") or ""
        )
        self.callback_require_signed = bool(
            getattr(telegram_config, "callback_require_signed", False)
        )
        self._send_retry_policy = TelegramRetryPolicy(
            max_attempts=self.send_retry_attempts,
            base_backoff_s=self.send_backoff_base_s,
            max_backoff_s=self.send_backoff_max_s,
            jitter_ratio=self.send_backoff_jitter,
        ).normalized()
        self._send_auth_breaker = TelegramAuthCircuitBreaker(
            failure_threshold=self.send_circuit_failure_threshold,
            cooldown_s=self.send_circuit_cooldown_s,
        )
        self._typing_auth_breaker = TelegramAuthCircuitBreaker(
            failure_threshold=self.typing_circuit_failure_threshold,
            cooldown_s=self.typing_circuit_cooldown_s,
        )
        self.drop_pending_updates = bool(
            config.get("drop_pending_updates", config.get("dropPendingUpdates", True))
        )
        self.handle_commands = bool(
            config.get("handle_commands", config.get("handleCommands", True))
        )
        self._task: asyncio.Task[Any] | None = None
        self._typing_tasks: dict[str, asyncio.Task[Any]] = {}
        self._media_group_tasks: dict[str, asyncio.Task[Any]] = {}
        self._media_group_buffers: dict[str, dict[str, Any]] = {}
        self._typing_start_guard: set[str] = set()
        self._signals: dict[str, int] = {
            "send_retry_count": 0,
            "send_retry_after_count": 0,
            "send_auth_breaker_open_count": 0,
            "send_auth_breaker_close_count": 0,
            "typing_auth_breaker_open_count": 0,
            "typing_auth_breaker_close_count": 0,
            "typing_ttl_stop_count": 0,
            "reconnect_count": 0,
            "callback_query_received_count": 0,
            "callback_query_blocked_count": 0,
            "callback_query_ack_error_count": 0,
            "callback_query_signature_accepted_count": 0,
            "callback_query_signature_blocked_count": 0,
            "callback_query_unsigned_allowed_count": 0,
            "inline_query_received_count": 0,
            "inline_query_answered_count": 0,
            "inline_query_answer_error_count": 0,
            "shipping_query_received_count": 0,
            "shipping_query_rejected_count": 0,
            "shipping_query_answer_error_count": 0,
            "pre_checkout_query_received_count": 0,
            "pre_checkout_query_rejected_count": 0,
            "pre_checkout_query_answer_error_count": 0,
            "poll_received_count": 0,
            "poll_answer_received_count": 0,
            "chat_member_received_count": 0,
            "my_chat_member_received_count": 0,
            "chat_join_request_received_count": 0,
            "message_reaction_count_received_count": 0,
            "business_connection_received_count": 0,
            "deleted_business_messages_received_count": 0,
            "chat_boost_received_count": 0,
            "removed_chat_boost_received_count": 0,
            "purchased_paid_media_received_count": 0,
            "chosen_inline_result_received_count": 0,
            "unhandled_update_received_count": 0,
            "webhook_set_count": 0,
            "webhook_delete_count": 0,
            "webhook_fallback_to_polling_count": 0,
            "webhook_update_received_count": 0,
            "webhook_update_duplicate_count": 0,
            "webhook_update_parse_error_count": 0,
            "update_duplicate_skip_count": 0,
            "update_dedupe_state_load_error_count": 0,
            "update_dedupe_state_save_error_count": 0,
            "polling_stale_update_skip_count": 0,
            "webhook_stale_update_skip_count": 0,
            "offset_persist_error_count": 0,
            "offset_load_error_count": 0,
            "offset_safe_advance_count": 0,
            "media_download_count": 0,
            "media_download_error_count": 0,
            "media_transcription_count": 0,
            "media_transcription_error_count": 0,
            "media_group_buffered_count": 0,
            "media_group_flush_count": 0,
            "message_reaction_received_count": 0,
            "message_reaction_ignored_bot_count": 0,
            "message_reaction_blocked_count": 0,
            "message_reaction_emitted_count": 0,
            "policy_blocked_count": 0,
            "policy_allowed_count": 0,
            "pairing_required_count": 0,
            "pairing_notice_sent_count": 0,
            "pairing_request_created_count": 0,
            "pairing_request_reused_count": 0,
            "action_edit_count": 0,
            "action_delete_count": 0,
            "action_react_count": 0,
            "action_create_topic_count": 0,
        }
        self._offset = self._load_offset()
        self._connected = False
        self._webhook_mode_active = False
        self._startup_drop_done = False
        self._update_dedupe_limit = max(
            32,
            int(getattr(telegram_config, "update_dedupe_limit", 4096) or 4096),
        )
        self._seen_update_keys: set[str] = set()
        self._seen_update_order: deque[str] = deque()
        # In-flight set: prevents concurrent webhook workers from processing the
        # same update_id simultaneously (closes TOCTOU between check and commit).
        # Removed on failure so retries are allowed; only moved to _seen on success.
        self._inflight_update_keys: set[str] = set()
        self._dedupe_persist_task: asyncio.Task[Any] | None = None
        self._own_sent_message_keys: set[tuple[str, int]] = set()
        self._own_sent_message_order: deque[tuple[str, int]] = deque()
        self._message_signatures: dict[tuple[str, int], str] = {}
        self._signature_limit = 4096
        self._pairing_notice_sent_at: dict[str, float] = {}
        self._send_auth_breaker_seen_open = False
        self._typing_auth_breaker_seen_open = False
        self._load_update_dedupe_state()

    @staticmethod
    def _normalize_state_path(raw: str) -> Path:
        value = str(raw or "").strip()
        if not value:
            return Path.home() / ".clawlite" / "state" / "telegram-dedupe.json"
        return Path(value).expanduser()

    @staticmethod
    def _normalize_optional_path(raw: str) -> Path | None:
        value = str(raw or "").strip()
        if not value:
            return None
        return Path(value).expanduser()

    @property
    def _callback_signing_active(self) -> bool:
        return self.callback_signing_enabled and bool(self.callback_signing_secret)

    def _session_id_for_chat(
        self, *, chat_id: str, chat_type: str = "", message_thread_id: int | None = None
    ) -> str:
        normalized_chat_id = str(chat_id or "").strip()
        thread_id = self._coerce_thread_id(message_thread_id)
        normalized_chat_type = str(chat_type or "").strip().lower()
        if normalized_chat_type == "supergroup" and thread_id is not None:
            return f"telegram:{normalized_chat_id}:topic:{thread_id}"
        if normalized_chat_type == "private" and thread_id is not None:
            return f"telegram:{normalized_chat_id}:thread:{thread_id}"
        return f"telegram:{normalized_chat_id}"

    def _dedupe_state_payload(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(
                timespec="seconds"
            ),
            "keys": list(self._seen_update_order),
        }

    def _load_update_dedupe_state(self) -> None:
        path = self.dedupe_state_path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            return
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            keys_raw = data.get("keys", []) if isinstance(data, dict) else []
            if not isinstance(keys_raw, list):
                return
            normalized: deque[str] = deque(maxlen=self._update_dedupe_limit)
            seen_local: set[str] = set()
            for item in keys_raw:
                key = str(item or "").strip()
                if key.startswith("polling:") or key.startswith("webhook:"):
                    _, _, maybe_key = key.partition(":")
                    key = maybe_key.strip()
                if not key or key in seen_local:
                    continue
                seen_local.add(key)
                normalized.append(key)
            self._seen_update_order = deque(normalized)
            self._seen_update_keys = set(self._seen_update_order)
        except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
            self._signals["update_dedupe_state_load_error_count"] += 1
            logger.warning(
                "telegram dedupe state load failed path={} error={}", path, exc
            )

    def _refresh_update_dedupe_state(self) -> None:
        path = self.dedupe_state_path
        try:
            if not path.exists():
                return
            data = json.loads(path.read_text(encoding="utf-8"))
            keys_raw = data.get("keys", []) if isinstance(data, dict) else []
            if not isinstance(keys_raw, list):
                return
        except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
            self._signals["update_dedupe_state_load_error_count"] += 1
            logger.warning(
                "telegram dedupe state refresh failed path={} error={}", path, exc
            )
            return

        changed = False
        for item in keys_raw:
            key = str(item or "").strip()
            if key.startswith("polling:") or key.startswith("webhook:"):
                _, _, maybe_key = key.partition(":")
                key = maybe_key.strip()
            if not key or key in self._seen_update_keys:
                continue
            self._seen_update_keys.add(key)
            self._seen_update_order.append(key)
            changed = True
        if not changed:
            return
        while len(self._seen_update_order) > self._update_dedupe_limit:
            oldest = self._seen_update_order.popleft()
            self._seen_update_keys.discard(oldest)

    async def _persist_update_dedupe_state(self) -> None:
        path = self.dedupe_state_path
        tmp_path = path.with_suffix(f"{path.suffix}.tmp.{secrets.token_hex(4)}")
        dir_fd: int | None = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = self._dedupe_state_payload()
            encoded_payload = json.dumps(payload).encode("utf-8")
            with tmp_path.open("wb") as handle:
                handle.write(encoded_payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, path)
            try:
                open_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                dir_fd = os.open(str(path.parent), open_flags)
                os.fsync(dir_fd)
            except OSError:
                pass
        except (OSError, TypeError, ValueError) as exc:
            self._signals["update_dedupe_state_save_error_count"] += 1
            logger.debug(
                "telegram dedupe state persist failed path={} error={}", path, exc
            )
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except OSError:
                pass
        finally:
            if dir_fd is not None:
                try:
                    os.close(dir_fd)
                except OSError:
                    pass

    def _schedule_dedupe_state_persist(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if (
            self._dedupe_persist_task is not None
            and not self._dedupe_persist_task.done()
        ):
            return
        self._dedupe_persist_task = loop.create_task(
            self._persist_update_dedupe_state()
        )

    def _callback_sign_payload(self, callback_data: str) -> str:
        nonce = (
            base64.urlsafe_b64encode(secrets.token_bytes(6)).decode("ascii").rstrip("=")
        )
        data = str(callback_data or "")
        encoded_data = (
            base64.urlsafe_b64encode(data.encode("utf-8")).decode("ascii").rstrip("=")
        )
        digest = hmac.new(
            self.callback_signing_secret.encode("utf-8"),
            f"{nonce}.{encoded_data}".encode("utf-8"),
            hashlib.sha256,
        ).digest()
        signature = base64.urlsafe_b64encode(digest[:12]).decode("ascii").rstrip("=")
        return f"s1.{nonce}.{encoded_data}.{signature}"

    @staticmethod
    def _urlsafe_b64decode(data: str) -> bytes:
        padded = data + ("=" * ((4 - len(data) % 4) % 4))
        return base64.urlsafe_b64decode(padded.encode("ascii"))

    def _callback_verify_payload(self, callback_data: str) -> tuple[bool, str, bool]:
        raw = str(callback_data or "")
        if not raw.startswith("s1."):
            return False, raw, False
        parts = raw.split(".", 3)
        if len(parts) != 4:
            return False, "", True
        _, nonce, encoded_data, provided_signature = parts
        if (
            not nonce
            or not encoded_data
            or not provided_signature
            or not self.callback_signing_secret
        ):
            return False, "", True
        try:
            decoded_data = self._urlsafe_b64decode(encoded_data).decode("utf-8")
        except Exception:
            return False, "", True
        digest = hmac.new(
            self.callback_signing_secret.encode("utf-8"),
            f"{nonce}.{encoded_data}".encode("utf-8"),
            hashlib.sha256,
        ).digest()
        expected_signature = (
            base64.urlsafe_b64encode(digest[:12]).decode("ascii").rstrip("=")
        )
        if not hmac.compare_digest(expected_signature, provided_signature):
            return False, "", True
        return True, decoded_data, True

    def _sync_auth_breaker_signal_transition(
        self, *, breaker: TelegramAuthCircuitBreaker, key_prefix: str
    ) -> None:
        seen_open_attr = f"_{key_prefix}_auth_breaker_seen_open"
        seen_open = bool(getattr(self, seen_open_attr, False))
        is_open = breaker.is_open
        if is_open:
            setattr(self, seen_open_attr, True)
            return
        if seen_open:
            self._signals[f"{key_prefix}_auth_breaker_close_count"] += 1
            setattr(self, seen_open_attr, False)

    @staticmethod
    def _coerce_thread_id(value: Any) -> int | None:
        if value is None:
            return None
        try:
            thread_id = int(value)
        except (TypeError, ValueError):
            return None
        return thread_id if thread_id > 0 else None

    @staticmethod
    def _parse_target(target: str) -> tuple[str, int | None]:
        raw_target = str(target).strip()
        if not raw_target:
            return "", None
        if raw_target.startswith("telegram:"):
            payload = raw_target.split(":", 1)[1].strip()
            if ":topic:" in payload:
                chat_id, _, maybe_thread = payload.partition(":topic:")
                return (
                    chat_id.strip(),
                    TelegramChannel._coerce_thread_id(maybe_thread.strip()),
                )
            if ":thread:" in payload:
                chat_id, _, maybe_thread = payload.partition(":thread:")
                return (
                    chat_id.strip(),
                    TelegramChannel._coerce_thread_id(maybe_thread.strip()),
                )
            raw_target = payload
        elif raw_target.startswith("tg_"):
            payload = raw_target[3:].strip()
            if ":topic:" in payload:
                chat_id, _, maybe_thread = payload.partition(":topic:")
                return (
                    chat_id.strip(),
                    TelegramChannel._coerce_thread_id(maybe_thread.strip()),
                )
            if ":thread:" in payload:
                chat_id, _, maybe_thread = payload.partition(":thread:")
                return (
                    chat_id.strip(),
                    TelegramChannel._coerce_thread_id(maybe_thread.strip()),
                )
            raw_target = payload
        chat_id, sep, maybe_thread = raw_target.partition(":")
        if not sep:
            return chat_id.strip(), None
        thread_id = TelegramChannel._coerce_thread_id(maybe_thread.strip())
        return chat_id.strip(), thread_id

    @staticmethod
    def _typing_key(*, chat_id: str, message_thread_id: int | None) -> str:
        if message_thread_id is None:
            return chat_id
        return f"{chat_id}:{message_thread_id}"

    @staticmethod
    def _threadless_retry_allowed(*, chat_id: str) -> bool:
        return not str(chat_id or "").strip().startswith("-")

    def _normalize_api_message_thread_id(
        self, *, chat_id: str, message_thread_id: Any
    ) -> int | None:
        thread_id = self._coerce_thread_id(message_thread_id)
        if thread_id is None:
            return None
        if str(chat_id or "").strip().startswith("-") and thread_id == 1:
            return None
        return thread_id

    @staticmethod
    def _typing_task_is_active(task: asyncio.Task[Any] | None) -> bool:
        if task is None:
            return False
        cancelling = getattr(task, "cancelling", None)
        if callable(cancelling) and cancelling() > 0:
            return True
        return not task.done()

    def _on_send_auth_failure(self) -> None:
        was_open = self._send_auth_breaker.is_open
        self._send_auth_breaker.on_auth_failure()
        if not was_open and self._send_auth_breaker.is_open:
            self._signals["send_auth_breaker_open_count"] += 1
            self._send_auth_breaker_seen_open = True

    def _on_send_auth_success(self) -> None:
        self._send_auth_breaker.on_success()
        self._sync_auth_breaker_signal_transition(
            breaker=self._send_auth_breaker, key_prefix="send"
        )

    def _on_typing_auth_failure(self) -> None:
        was_open = self._typing_auth_breaker.is_open
        self._typing_auth_breaker.on_auth_failure()
        if not was_open and self._typing_auth_breaker.is_open:
            self._signals["typing_auth_breaker_open_count"] += 1
            self._typing_auth_breaker_seen_open = True

    def _on_typing_auth_success(self) -> None:
        self._typing_auth_breaker.on_success()
        self._sync_auth_breaker_signal_transition(
            breaker=self._typing_auth_breaker, key_prefix="typing"
        )

    def signals(self) -> dict[str, Any]:
        self._sync_auth_breaker_signal_transition(
            breaker=self._send_auth_breaker, key_prefix="send"
        )
        self._sync_auth_breaker_signal_transition(
            breaker=self._typing_auth_breaker, key_prefix="typing"
        )
        offset_snapshot = self._offset_store.snapshot()
        return {
            **self._signals,
            "send_auth_breaker_open": self._send_auth_breaker.is_open,
            "typing_auth_breaker_open": self._typing_auth_breaker.is_open,
            "typing_keepalive_active": len(self._typing_tasks),
            "webhook_mode_active": self._webhook_mode_active,
            "offset_next": offset_snapshot.next_offset,
            "offset_watermark_update_id": offset_snapshot.safe_update_id,
            "offset_highest_completed_update_id": offset_snapshot.highest_completed_update_id,
            "offset_pending_count": offset_snapshot.pending_count,
            "offset_min_pending_update_id": offset_snapshot.min_pending_update_id,
        }

    def operator_status(self) -> dict[str, Any]:
        offset_snapshot = self._offset_store.snapshot()
        try:
            pending_requests = list(self._pairing_store.list_pending())
            pairing_pending = len(pending_requests)
        except Exception as exc:
            logger.warning("telegram pairing pending snapshot failed error={}", exc)
            pending_requests = []
            pairing_pending = 0
        try:
            pairing_approved = len(self._pairing_store.approved_entries())
        except Exception as exc:
            logger.warning("telegram pairing approved snapshot failed error={}", exc)
            pairing_approved = 0
        return {
            "mode": self.mode,
            "webhook_requested": self._webhook_requested(),
            "webhook_mode_active": self._webhook_mode_active,
            "webhook_path": self.webhook_path,
            "webhook_url_configured": bool(self.webhook_url),
            "webhook_secret_configured": bool(self.webhook_secret),
            "offset_path": str(self._offset_path()),
            "offset_next": offset_snapshot.next_offset,
            "offset_watermark_update_id": offset_snapshot.safe_update_id,
            "offset_highest_completed_update_id": offset_snapshot.highest_completed_update_id,
            "offset_pending_count": offset_snapshot.pending_count,
            "offset_min_pending_update_id": offset_snapshot.min_pending_update_id,
            "pairing_pending_count": pairing_pending,
            "pairing_approved_count": pairing_approved,
            "pairing_pending": pending_requests,
            "connected": bool(self._connected),
            "running": bool(self._running),
            "last_error": str(self._last_error or ""),
        }

    async def operator_approve_pairing(self, code: str) -> dict[str, Any]:
        normalized_code = str(code or "").strip().upper()
        if not normalized_code:
            return {"ok": False, "error": "pairing_code_required"}
        approved = self._pairing_store.approve(normalized_code)
        if approved is None:
            return {"ok": False, "code": normalized_code, "error": "pairing_code_not_found"}
        return {
            "ok": True,
            "code": normalized_code,
            "approved_entries": list(approved.get("approved_entries", [])),
            "request": dict(approved.get("request", {})),
            "status": self.operator_status(),
        }

    async def operator_reject_pairing(self, code: str) -> dict[str, Any]:
        normalized_code = str(code or "").strip().upper()
        if not normalized_code:
            return {"ok": False, "error": "pairing_code_required"}
        rejected = self._pairing_store.reject(normalized_code)
        if rejected is None:
            return {"ok": False, "code": normalized_code, "error": "pairing_code_not_found"}
        return {
            "ok": True,
            "code": normalized_code,
            "approved_entries": list(rejected.get("approved_entries", [])),
            "request": dict(rejected.get("request", {})),
            "status": self.operator_status(),
        }

    async def operator_force_commit_offset(self, update_id: int) -> dict[str, Any]:
        normalized = self._coerce_update_id(update_id)
        self._force_commit_offset_update(normalized)
        return {
            "ok": True,
            "update_id": normalized,
            "status": self.operator_status(),
        }

    async def operator_refresh_transport(self) -> dict[str, Any]:
        summary: dict[str, Any] = {
            "mode": self.mode,
            "webhook_requested": self._webhook_requested(),
            "offset_reloaded": False,
            "webhook_deleted": False,
            "webhook_activated": False,
            "bot_initialized": False,
            "connected": bool(self._connected),
            "webhook_mode_active": bool(self._webhook_mode_active),
            "last_error": "",
        }
        try:
            self._load_offset()
            summary["offset_reloaded"] = True
            bot = await self._ensure_bot()
            summary["bot_initialized"] = bot is not None
            if self._webhook_requested():
                summary["webhook_deleted"] = await self._try_delete_webhook(reason="operator_refresh")
                summary["webhook_activated"] = await self._activate_webhook_mode()
            summary["connected"] = bool(self._connected)
            summary["webhook_mode_active"] = bool(self._webhook_mode_active)
        except Exception as exc:
            self._last_error = str(exc)
            summary["last_error"] = str(exc)
            logger.warning("telegram operator transport refresh failed error={}", exc)
        return summary | {"status": self.operator_status()}

    @property
    def webhook_mode_active(self) -> bool:
        return bool(self._webhook_mode_active)

    @staticmethod
    def _normalize_mode(value: str) -> str:
        mode = str(value or "polling").strip().lower()
        return mode if mode in {"polling", "webhook"} else "polling"

    @staticmethod
    def _normalize_webhook_path(value: str) -> str:
        raw = str(value or "").strip() or "/api/webhooks/telegram"
        return raw if raw.startswith("/") else f"/{raw}"

    @staticmethod
    def _normalize_reaction_notifications(value: str) -> str:
        mode = str(value or "own").strip().lower()
        if mode not in {"off", "own", "all"}:
            return "own"
        return mode

    def _webhook_requested(self) -> bool:
        return self.mode == "webhook" or self.webhook_enabled

    @staticmethod
    def _normalize_webhook_payload(value: Any) -> Any:
        if isinstance(value, dict):
            normalized: dict[str, Any] = {}
            for raw_key, raw_item in value.items():
                key = "from_user" if str(raw_key) == "from" else str(raw_key)
                normalized[key] = TelegramChannel._normalize_webhook_payload(raw_item)
            chat = normalized.get("chat")
            if isinstance(chat, dict) and "chat_id" not in normalized and "id" in chat:
                normalized["chat_id"] = chat.get("id")
            return normalized
        if isinstance(value, list):
            return [TelegramChannel._normalize_webhook_payload(item) for item in value]
        return value

    @staticmethod
    def _to_namespace(value: Any) -> Any:
        if isinstance(value, dict):
            return SimpleNamespace(
                **{
                    key: TelegramChannel._to_namespace(item)
                    for key, item in value.items()
                }
            )
        if isinstance(value, list):
            return [TelegramChannel._to_namespace(item) for item in value]
        return value

    @staticmethod
    def _field(value: Any, name: str) -> Any:
        if isinstance(value, dict):
            return value.get(name)
        return getattr(value, name, None)

    @staticmethod
    def _coerce_update_id(value: Any) -> int | None:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed >= 0 else None

    def _build_update_dedupe_key(self, update: Any) -> str | None:
        update_id = self._coerce_update_id(self._field(update, "update_id"))
        if update_id is not None:
            return f"update:{update_id}"

        inline_query = self._field(update, "inline_query")
        inline_query_id = str(self._field(inline_query, "id") or "").strip()
        if inline_query_id:
            return f"inline:{inline_query_id}"

        callback_query = self._field(update, "callback_query")
        callback_query_id = str(self._field(callback_query, "id") or "").strip()
        if callback_query_id:
            return f"callback:{callback_query_id}"

        shipping_query = self._field(update, "shipping_query")
        shipping_query_id = str(self._field(shipping_query, "id") or "").strip()
        if shipping_query_id:
            return f"shipping:{shipping_query_id}"

        pre_checkout_query = self._field(update, "pre_checkout_query")
        pre_checkout_query_id = str(self._field(pre_checkout_query, "id") or "").strip()
        if pre_checkout_query_id:
            return f"pre_checkout:{pre_checkout_query_id}"

        chosen_inline_result = self._field(update, "chosen_inline_result")
        chosen_inline_result_id = str(
            self._field(chosen_inline_result, "result_id") or ""
        ).strip()
        if chosen_inline_result_id:
            return f"chosen_inline:{chosen_inline_result_id}"

        poll = self._field(update, "poll")
        poll_id = str(self._field(poll, "id") or "").strip()
        if poll_id:
            return f"poll:{poll_id}"

        poll_answer = self._field(update, "poll_answer")
        poll_answer_poll_id = str(self._field(poll_answer, "poll_id") or "").strip()
        if poll_answer_poll_id:
            poll_user = self._field(poll_answer, "user") or self._field(
                poll_answer, "voter_chat"
            )
            poll_user_id = str(self._field(poll_user, "id") or "").strip()
            return f"poll_answer:{poll_answer_poll_id}:{poll_user_id or 'unknown'}"

        chat_join_request = self._field(update, "chat_join_request")
        if chat_join_request is not None:
            join_chat = self._field(chat_join_request, "chat")
            join_user = self._field(chat_join_request, "from_user")
            join_chat_id = str(
                self._field(join_chat, "id")
                or self._field(chat_join_request, "chat_id")
                or ""
            ).strip()
            join_user_id = str(self._field(join_user, "id") or "").strip()
            join_date = str(self._field(chat_join_request, "date") or "").strip()
            if join_chat_id and join_user_id:
                return f"join:{join_chat_id}:{join_user_id}:{join_date}"

        business_connection = self._field(update, "business_connection")
        business_connection_id = str(
            self._field(business_connection, "id") or ""
        ).strip()
        if business_connection_id:
            return f"business_connection:{business_connection_id}"

        deleted_business_messages = self._field(update, "deleted_business_messages")
        if deleted_business_messages is not None:
            deleted_connection_id = str(
                self._field(deleted_business_messages, "business_connection_id") or ""
            ).strip()
            deleted_chat = self._field(deleted_business_messages, "chat")
            deleted_chat_id = str(
                self._field(deleted_chat, "id")
                or self._field(deleted_business_messages, "chat_id")
                or ""
            ).strip()
            message_ids = self._field(deleted_business_messages, "message_ids")
            ids_repr = (
                ",".join(str(item) for item in message_ids)
                if isinstance(message_ids, list)
                else ""
            )
            if deleted_connection_id or deleted_chat_id or ids_repr:
                return f"deleted_business:{deleted_connection_id}:{deleted_chat_id}:{ids_repr}"

        for field_name in ("chat_member", "my_chat_member"):
            member_update = self._field(update, field_name)
            if member_update is None:
                continue
            member_chat = self._field(member_update, "chat")
            member_actor = self._field(member_update, "from_user")
            new_member = self._field(member_update, "new_chat_member")
            target_user = self._field(new_member, "user")
            chat_id = str(
                self._field(member_chat, "id")
                or self._field(member_update, "chat_id")
                or ""
            ).strip()
            actor_id = str(self._field(member_actor, "id") or "").strip()
            target_user_id = str(
                self._field(target_user, "id")
                or self._field(new_member, "user_id")
                or ""
            ).strip()
            member_status = str(self._field(new_member, "status") or "").strip()
            member_date = str(self._field(member_update, "date") or "").strip()
            if chat_id or actor_id or target_user_id:
                return f"{field_name}:{chat_id}:{target_user_id or actor_id}:{member_status}:{member_date}"

        message_reaction_count = self._field(update, "message_reaction_count")
        if message_reaction_count is not None:
            reaction_chat = self._field(message_reaction_count, "chat")
            reaction_chat_id = str(
                self._field(reaction_chat, "id")
                or self._field(message_reaction_count, "chat_id")
                or ""
            ).strip()
            reaction_message_id = str(
                self._field(message_reaction_count, "message_id") or ""
            ).strip()
            reaction_date = str(
                self._field(message_reaction_count, "date") or ""
            ).strip()
            if reaction_chat_id or reaction_message_id:
                return f"reaction_count:{reaction_chat_id}:{reaction_message_id}:{reaction_date}"

        for field_name in ("chat_boost", "removed_chat_boost"):
            boost_update = self._field(update, field_name)
            if boost_update is None:
                continue
            boost_chat = self._field(boost_update, "chat")
            boost_row = self._field(boost_update, "boost") or boost_update
            boost_source = self._field(boost_row, "source")
            boost_user = self._field(boost_source, "user") or self._field(
                boost_source, "from_user"
            )
            boost_chat_id = str(
                self._field(boost_chat, "id")
                or self._field(boost_update, "chat_id")
                or ""
            ).strip()
            boost_id = str(
                self._field(boost_row, "boost_id")
                or self._field(boost_update, "boost_id")
                or ""
            ).strip()
            boost_user_id = str(self._field(boost_user, "id") or "").strip()
            boost_date = str(
                self._field(boost_row, "add_date")
                or self._field(boost_row, "remove_date")
                or self._field(boost_update, "date")
                or ""
            ).strip()
            if boost_chat_id or boost_id or boost_user_id:
                return f"{field_name}:{boost_chat_id}:{boost_id}:{boost_user_id}:{boost_date}"

        purchased_paid_media = self._field(update, "purchased_paid_media")
        if purchased_paid_media is not None:
            paid_media_chat = self._field(purchased_paid_media, "chat")
            paid_media_user = self._field(
                purchased_paid_media, "from_user"
            ) or self._field(purchased_paid_media, "user")
            paid_media_chat_id = str(
                self._field(paid_media_chat, "id")
                or self._field(purchased_paid_media, "chat_id")
                or ""
            ).strip()
            paid_media_user_id = str(self._field(paid_media_user, "id") or "").strip()
            paid_media_payload = str(
                self._field(purchased_paid_media, "payload")
                or self._field(purchased_paid_media, "paid_media_payload")
                or ""
            ).strip()
            paid_media_date = str(
                self._field(purchased_paid_media, "date") or ""
            ).strip()
            if paid_media_chat_id or paid_media_user_id or paid_media_payload:
                return f"paid_media:{paid_media_chat_id}:{paid_media_user_id}:{paid_media_payload}:{paid_media_date}"

        for field_name, is_edit in (
            ("message", False),
            ("edited_message", True),
            ("business_message", False),
            ("edited_business_message", True),
            ("channel_post", False),
            ("edited_channel_post", True),
        ):
            message = self._field(update, field_name)
            if message is None:
                continue
            chat_id = self._field(message, "chat_id")
            if chat_id in {None, ""}:
                chat = self._field(message, "chat")
                chat_id = self._field(chat, "id")
            message_id = self._coerce_update_id(self._field(message, "message_id"))
            if chat_id in {None, ""} or message_id is None:
                continue
            is_edit_int = 1 if is_edit else 0
            return f"message:{chat_id}:{message_id}:{is_edit_int}"
        return None

    def _is_duplicate_update_dedupe_key(self, dedupe_key: str, *, source: str) -> bool:
        key = str(dedupe_key or "").strip()
        if not key:
            return False
        normalized_source = str(source or "").strip().lower() or "unknown"
        if key in self._seen_update_keys:
            self._signals["update_duplicate_skip_count"] += 1
            if normalized_source == "webhook":
                self._signals["webhook_update_duplicate_count"] += 1
            return True
        return False

    def _commit_update_dedupe_key(
        self, dedupe_key: str, *, schedule_persist: bool = True
    ) -> None:
        key = str(dedupe_key or "").strip()
        if not key or key in self._seen_update_keys:
            return
        self._seen_update_keys.add(key)
        self._seen_update_order.append(key)
        while len(self._seen_update_order) > self._update_dedupe_limit:
            oldest = self._seen_update_order.popleft()
            self._seen_update_keys.discard(oldest)
        if schedule_persist:
            self._schedule_dedupe_state_persist()

    def _remember_update_dedupe_key(self, dedupe_key: str, *, source: str) -> bool:
        if self._is_duplicate_update_dedupe_key(dedupe_key, source=source):
            return False
        self._commit_update_dedupe_key(dedupe_key)
        return True

    @staticmethod
    def _media_type_supports_caption(media_type: str) -> bool:
        return media_type in {
            "animation",
            "audio",
            "document",
            "photo",
            "video",
            "voice",
        }

    async def _ensure_bot(self) -> Any:
        if self.bot is not None:
            return self.bot
        from telegram import (
            Bot,
        )  # lazy import for environments without dependency during tests

        self.bot = Bot(token=self.token)
        return self.bot

    async def _try_delete_webhook(self, *, reason: str) -> bool:
        bot = self.bot
        if bot is None or not hasattr(bot, "delete_webhook"):
            return False
        try:
            await bot.delete_webhook(drop_pending_updates=False)
            self._signals["webhook_delete_count"] += 1
            logger.info("telegram webhook deleted reason={}", reason)
            return True
        except TypeError as exc:
            if "drop_pending_updates" not in str(exc):
                logger.warning(
                    "telegram webhook delete failed reason={} error={}", reason, exc
                )
                return False
            try:
                await bot.delete_webhook()
                self._signals["webhook_delete_count"] += 1
                logger.info("telegram webhook deleted reason={} legacy=true", reason)
                return True
            except Exception as legacy_exc:  # pragma: no cover
                logger.warning(
                    "telegram webhook delete failed reason={} error={}",
                    reason,
                    legacy_exc,
                )
                return False
        except Exception as exc:  # pragma: no cover
            logger.warning(
                "telegram webhook delete failed reason={} error={}", reason, exc
            )
            return False

    async def _activate_webhook_mode(self) -> bool:
        if not self.webhook_url or not self.webhook_secret:
            missing = []
            if not self.webhook_url:
                missing.append("webhook_url")
            if not self.webhook_secret:
                missing.append("webhook_secret")
            logger.warning(
                "telegram webhook activation skipped missing={}", ",".join(missing)
            )
            return False
        try:
            bot = await self._ensure_bot()
        except Exception as exc:  # pragma: no cover
            self._last_error = str(exc)
            logger.warning("telegram webhook bot init failed error={}", exc)
            return False
        if not hasattr(bot, "set_webhook"):
            logger.warning(
                "telegram webhook activation skipped reason=bot_missing_set_webhook"
            )
            return False
        try:
            await bot.set_webhook(
                url=self.webhook_url,
                secret_token=self.webhook_secret,
                allowed_updates=TELEGRAM_ALLOWED_UPDATES,
            )
            self._signals["webhook_set_count"] += 1
            self._connected = True
            self._webhook_mode_active = True
            logger.info(
                "telegram connected polling=false webhook=true path={}",
                self.webhook_path,
            )
            return True
        except Exception as exc:
            self._last_error = str(exc)
            logger.warning("telegram webhook activation failed error={}", exc)
            return False

    def _remember_message_signature(
        self, *, msg_key: tuple[str, int], signature: str
    ) -> None:
        self._message_signatures[msg_key] = signature
        if len(self._message_signatures) > self._signature_limit:
            oldest_key = next(iter(self._message_signatures))
            self._message_signatures.pop(oldest_key, None)

    def _remember_own_sent_message_ids(
        self, *, chat_id: str, message_ids: list[int]
    ) -> None:
        normalized_chat_id = str(chat_id or "").strip()
        if not normalized_chat_id:
            return
        for raw_message_id in message_ids:
            try:
                message_id = int(raw_message_id)
            except (TypeError, ValueError):
                continue
            if message_id <= 0:
                continue
            key = (normalized_chat_id, message_id)
            if key in self._own_sent_message_keys:
                continue
            self._own_sent_message_keys.add(key)
            self._own_sent_message_order.append(key)
        while len(self._own_sent_message_order) > self.reaction_own_cache_limit:
            oldest = self._own_sent_message_order.popleft()
            self._own_sent_message_keys.discard(oldest)

    @staticmethod
    def _reaction_token(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()

        emoji = getattr(value, "emoji", None)
        if emoji is None and isinstance(value, dict):
            emoji = value.get("emoji")
        if emoji:
            return str(emoji)

        custom_emoji_id = getattr(value, "custom_emoji_id", None)
        if custom_emoji_id is None and isinstance(value, dict):
            custom_emoji_id = value.get("custom_emoji_id")
        if custom_emoji_id:
            return f"custom:{custom_emoji_id}"

        reaction_type = getattr(value, "type", None)
        if reaction_type is None and isinstance(value, dict):
            reaction_type = value.get("type")
        if reaction_type:
            return str(reaction_type)

        return ""

    @classmethod
    def _reaction_tokens(cls, payload: Any) -> list[str]:
        if payload is None:
            return []
        if not isinstance(payload, list):
            payload = [payload]
        tokens: list[str] = []
        for item in payload:
            token = cls._reaction_token(item)
            if token:
                tokens.append(token)
        return tokens

    @classmethod
    def _added_reaction_tokens(
        cls, *, old_reaction: Any, new_reaction: Any
    ) -> list[str]:
        old_tokens = cls._reaction_tokens(old_reaction)
        new_tokens = cls._reaction_tokens(new_reaction)
        if not new_tokens:
            return []
        old_counts: dict[str, int] = {}
        for token in old_tokens:
            old_counts[token] = old_counts.get(token, 0) + 1
        added: list[str] = []
        for token in new_tokens:
            count = old_counts.get(token, 0)
            if count > 0:
                old_counts[token] = count - 1
                continue
            added.append(token)
        return added

    async def _typing_loop(
        self, *, chat_id: str, message_thread_id: int | None = None
    ) -> None:
        started_at = time.monotonic()
        max_ttl_s = max(1.0, float(self.typing_max_ttl_s))
        interval_s = max(0.2, float(self.typing_interval_s))
        timeout_s = max(0.1, float(self.typing_timeout_s))
        active_thread_id = self._normalize_api_message_thread_id(
            chat_id=chat_id,
            message_thread_id=message_thread_id,
        )
        typing_key = self._typing_key(
            chat_id=chat_id, message_thread_id=active_thread_id
        )
        try:
            while True:
                remaining_s = max_ttl_s - (time.monotonic() - started_at)
                if remaining_s <= 0:
                    self._signals["typing_ttl_stop_count"] += 1
                    return

                if self._typing_auth_breaker.is_open:
                    self._sync_auth_breaker_signal_transition(
                        breaker=self._typing_auth_breaker, key_prefix="typing"
                    )
                    await asyncio.sleep(min(interval_s, remaining_s))
                    continue
                self._sync_auth_breaker_signal_transition(
                    breaker=self._typing_auth_breaker, key_prefix="typing"
                )

                bot = self.bot
                if bot is None:
                    await asyncio.sleep(min(interval_s, remaining_s))
                    continue

                try:
                    payload: dict[str, Any] = {
                        "chat_id": chat_id,
                        "action": "typing",
                    }
                    if active_thread_id is not None:
                        payload["message_thread_id"] = active_thread_id
                    await asyncio.wait_for(
                        bot.send_chat_action(**payload),
                        timeout=timeout_s,
                    )
                    self._on_typing_auth_success()
                except TypeError as exc:
                    if active_thread_id is None or "message_thread_id" not in str(exc):
                        raise
                    active_thread_id = None
                    await asyncio.wait_for(
                        bot.send_chat_action(chat_id=chat_id, action="typing"),
                        timeout=timeout_s,
                    )
                    self._on_typing_auth_success()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    if (
                        active_thread_id is not None
                        and self._threadless_retry_allowed(chat_id=chat_id)
                        and _is_thread_not_found_error(exc)
                    ):
                        logger.debug(
                            "telegram typing thread not found chat={}; retrying without message_thread_id",
                            chat_id,
                        )
                        active_thread_id = None
                        try:
                            await asyncio.wait_for(
                                bot.send_chat_action(chat_id=chat_id, action="typing"),
                                timeout=timeout_s,
                            )
                            self._on_typing_auth_success()
                            remaining_s = max_ttl_s - (time.monotonic() - started_at)
                            if remaining_s <= 0:
                                return
                            await asyncio.sleep(min(interval_s, remaining_s))
                            continue
                        except asyncio.CancelledError:
                            raise
                        except Exception as retry_exc:
                            exc = retry_exc
                    if _is_auth_failure(exc):
                        self._on_typing_auth_failure()
                    logger.debug(
                        "telegram typing keepalive failed chat={} error={}",
                        chat_id,
                        exc,
                    )

                remaining_s = max_ttl_s - (time.monotonic() - started_at)
                if remaining_s <= 0:
                    return
                await asyncio.sleep(min(interval_s, remaining_s))
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover
            logger.warning(
                "telegram typing keepalive crashed chat={} error={}", chat_id, exc
            )
        finally:
            task = self._typing_tasks.get(typing_key)
            if task is asyncio.current_task():
                self._typing_tasks.pop(typing_key, None)
            self._typing_start_guard.discard(typing_key)

    def _start_typing_keepalive(
        self, *, chat_id: str, message_thread_id: int | None = None
    ) -> None:
        if not self.typing_enabled or not self._running:
            return
        if not chat_id:
            return
        normalized_thread_id = self._normalize_api_message_thread_id(
            chat_id=chat_id,
            message_thread_id=message_thread_id,
        )
        typing_key = self._typing_key(
            chat_id=chat_id, message_thread_id=normalized_thread_id
        )
        if typing_key in self._typing_start_guard:
            return
        task = self._typing_tasks.get(typing_key)
        if self._typing_task_is_active(task):
            return

        self._typing_start_guard.add(typing_key)
        created_task: asyncio.Task[Any] | None = None
        try:
            latest_task = self._typing_tasks.get(typing_key)
            if self._typing_task_is_active(latest_task):
                return
            created_task = asyncio.create_task(
                self._typing_loop(
                    chat_id=chat_id, message_thread_id=normalized_thread_id
                )
            )
            self._typing_tasks[typing_key] = created_task
        finally:
            if created_task is None:
                self._typing_start_guard.discard(typing_key)

    async def _stop_typing_keepalive(
        self, *, chat_id: str, message_thread_id: int | None = None
    ) -> None:
        normalized_thread_id = self._normalize_api_message_thread_id(
            chat_id=chat_id,
            message_thread_id=message_thread_id,
        )
        typing_key = self._typing_key(
            chat_id=chat_id, message_thread_id=normalized_thread_id
        )
        task = self._typing_tasks.pop(typing_key, None)
        self._typing_start_guard.discard(typing_key)
        await cancel_task(task)

    async def _stop_all_typing_keepalive(self) -> None:
        tasks = list(self._typing_tasks.values())
        self._typing_tasks.clear()
        self._typing_start_guard.clear()
        for task in tasks:
            await cancel_task(task)

    async def _drop_pending_updates(self) -> None:
        if self.bot is None:
            return
        dropped = 0
        try:
            while True:
                updates = await self.bot.get_updates(
                    offset=self._offset,
                    timeout=0,
                    allowed_updates=TELEGRAM_ALLOWED_UPDATES,
                )
                if not updates:
                    break
                dropped += len(updates)
                update_id = self._coerce_update_id(
                    getattr(updates[-1], "update_id", None)
                )
                if update_id is not None:
                    self._force_commit_offset_update(update_id)
            if dropped:
                self._offset = self._offset_store.next_offset
            logger.info(
                "telegram startup pending updates dropped={} offset={}",
                dropped,
                self._offset,
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("telegram startup drop pending updates failed error={}", exc)

    def _is_allowed_sender(self, user_id: str, username: str = "") -> bool:
        if not self.allow_from:
            return True
        allowed = {item.strip() for item in self.allow_from if item.strip()}
        candidates = self._sender_candidates(user_id=user_id, username=username)
        return any(candidate in allowed for candidate in candidates)

    @staticmethod
    def _normalize_access_policy(value: Any) -> str:
        policy = str(value or "open").strip().lower()
        if policy not in {"open", "allowlist", "disabled", "pairing"}:
            return "open"
        return policy

    @staticmethod
    def _sender_candidates(*, user_id: Any, username: str = "") -> set[str]:
        candidates = {str(user_id).strip()}
        uname = str(username or "").strip()
        if uname:
            candidates.add(uname)
            candidates.add(f"@{uname}")
        return {item for item in candidates if item}

    @staticmethod
    def _normalize_allow_from_values(raw: Any) -> list[str]:
        if not isinstance(raw, list):
            return []
        out: list[str] = []
        for item in raw:
            value = str(item).strip()
            if value:
                out.append(value)
        return out

    def _pairing_allow_from_values(self) -> list[str]:
        try:
            return list(self._pairing_store.approved_entries())
        except Exception as exc:
            logger.warning("telegram pairing allowlist read failed error={}", exc)
            return []

    @staticmethod
    def _sender_matches_allow_from(
        *,
        user_id: str,
        username: str,
        allowed_entries: list[str],
    ) -> bool:
        allowed = {item.strip() for item in allowed_entries if str(item or "").strip()}
        if not allowed:
            return False
        candidates = TelegramChannel._sender_candidates(
            user_id=user_id, username=username
        )
        return any(candidate in allowed for candidate in candidates)

    def _authorization_decision(
        self,
        *,
        chat_type: str,
        chat_id: str,
        message_thread_id: int | None,
        user_id: str,
        username: str,
    ) -> str:
        normalized_chat_type = str(chat_type or "").strip().lower()
        normalized_chat_id = str(chat_id or "").strip()
        normalized_thread_id = self._coerce_thread_id(message_thread_id)

        if normalized_chat_type == "private":
            active_policy = self.dm_policy
            active_allow_from = list(self.dm_allow_from)
        elif normalized_thread_id is None:
            active_policy = self.group_policy
            active_allow_from = list(self.group_allow_from)
        else:
            active_policy = self.topic_policy
            active_allow_from = list(self.topic_allow_from)

        if normalized_chat_type != "private":
            group_override = self.group_overrides.get(normalized_chat_id)
            if isinstance(group_override, dict):
                group_policy = group_override.get("policy")
                if group_policy is not None:
                    active_policy = self._normalize_access_policy(group_policy)
                if "allow_from" in group_override or "allowFrom" in group_override:
                    group_allow_from_raw = group_override.get(
                        "allow_from", group_override.get("allowFrom", [])
                    )
                    active_allow_from = self._normalize_allow_from_values(
                        group_allow_from_raw
                    )

                if normalized_thread_id is not None:
                    topics = group_override.get("topics")
                    if isinstance(topics, dict):
                        topic_override = topics.get(str(normalized_thread_id))
                        if isinstance(topic_override, dict):
                            topic_policy = topic_override.get("policy")
                            if topic_policy is not None:
                                active_policy = self._normalize_access_policy(
                                    topic_policy
                                )
                            if (
                                "allow_from" in topic_override
                                or "allowFrom" in topic_override
                            ):
                                topic_allow_from_raw = topic_override.get(
                                    "allow_from",
                                    topic_override.get("allowFrom", []),
                                )
                                active_allow_from = self._normalize_allow_from_values(
                                    topic_allow_from_raw
                                )

        active_policy = self._normalize_access_policy(active_policy)
        pairing_allow_from: list[str] = []
        if normalized_chat_type == "private" and active_policy == "pairing":
            pairing_allow_from = self._pairing_allow_from_values()

        if self.allow_from:
            global_allow_from = list(self.allow_from)
            if pairing_allow_from:
                global_allow_from.extend(pairing_allow_from)
            if not self._sender_matches_allow_from(
                user_id=user_id,
                username=username,
                allowed_entries=global_allow_from,
            ):
                return "block"

        if active_policy == "disabled":
            return "block"
        if active_policy == "open":
            return "allow"

        effective_allow_from = list(active_allow_from)
        if pairing_allow_from:
            effective_allow_from.extend(pairing_allow_from)
        if self._sender_matches_allow_from(
            user_id=user_id,
            username=username,
            allowed_entries=effective_allow_from,
        ):
            return "allow"

        if active_policy == "pairing" and normalized_chat_type == "private":
            return "pairing"
        return "block"

    def _is_authorized_context(
        self,
        *,
        chat_type: str,
        chat_id: str,
        message_thread_id: int | None,
        user_id: str,
        username: str,
    ) -> bool:
        return (
            self._authorization_decision(
                chat_type=chat_type,
                chat_id=chat_id,
                message_thread_id=message_thread_id,
                user_id=user_id,
                username=username,
            )
            == "allow"
        )

    def _authorize_inbound_context(
        self,
        *,
        chat_type: str,
        chat_id: str,
        message_thread_id: int | None,
        user_id: str,
        username: str,
    ) -> bool:
        decision = self._authorization_decision(
            chat_type=chat_type,
            chat_id=chat_id,
            message_thread_id=message_thread_id,
            user_id=user_id,
            username=username,
        )
        if decision == "allow":
            self._signals["policy_allowed_count"] += 1
        else:
            self._signals["policy_blocked_count"] += 1
            if decision == "pairing":
                self._signals["pairing_required_count"] += 1
        return decision == "allow"

    def _should_send_pairing_notice(self, *, chat_id: str, user_id: str) -> bool:
        cooldown_s = max(0.0, float(self.pairing_notice_cooldown_s))
        if cooldown_s <= 0:
            return True
        key = f"{chat_id}:{user_id}"
        last_sent_at = float(self._pairing_notice_sent_at.get(key, 0.0) or 0.0)
        now = time.monotonic()
        if now - last_sent_at < cooldown_s:
            return False
        self._pairing_notice_sent_at[key] = now
        return True

    async def _handle_pairing_required(
        self,
        *,
        chat_id: str,
        user_id: str,
        username: str,
        first_name: str,
    ) -> None:
        try:
            request, created = self._pairing_store.issue_request(
                chat_id=chat_id,
                user_id=user_id,
                username=username,
                first_name=first_name,
            )
        except Exception as exc:
            logger.warning(
                "telegram pairing request failed chat={} user={} error={}",
                chat_id,
                user_id,
                exc,
            )
            return

        if created:
            self._signals["pairing_request_created_count"] += 1
        else:
            self._signals["pairing_request_reused_count"] += 1

        if not created and not self._should_send_pairing_notice(
            chat_id=chat_id, user_id=user_id
        ):
            return

        code = str(request.get("code", "") or "").strip().upper()
        sender_label = f"@{username}" if username else user_id
        pairing_text = "\n".join(
            [
                "ClawLite: access not configured.",
                "",
                f"Sender: {sender_label}",
                f"Pairing code: {code}",
                "",
                "Ask the bot owner to approve with:",
                f"`clawlite pairing approve telegram {code}`",
            ]
        )
        try:
            await self.send(target=chat_id, text=pairing_text)
            self._signals["pairing_notice_sent_count"] += 1
        except Exception as exc:
            logger.warning(
                "telegram pairing notice send failed chat={} user={} error={}",
                chat_id,
                user_id,
                exc,
            )

    def _offset_path(self) -> Path:
        return self._offset_store.path

    def _media_download_dir(self) -> Path:
        path = self.media_download_dir_path or (
            Path.home() / ".clawlite" / "state" / "telegram" / "media"
        )
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _transcription_requested_for(self, media_type: str) -> bool:
        normalized = str(media_type or "").strip().lower()
        if normalized == "voice":
            return self.transcribe_voice
        if normalized == "audio":
            return self.transcribe_audio
        return False

    @staticmethod
    def _compact_text(value: Any, *, limit: int = 1600) -> str:
        text = " ".join(str(value or "").split()).strip()
        if limit > 3 and len(text) > limit:
            return text[: limit - 3].rstrip() + "..."
        return text

    def _resolve_transcription_provider(self) -> Any | None:
        if not self.transcription_api_key:
            return None
        if self._transcription_provider is not None:
            return self._transcription_provider
        from clawlite.providers.transcription import TranscriptionProvider

        self._transcription_provider = TranscriptionProvider(
            api_key=self.transcription_api_key,
            base_url=self.transcription_base_url,
            model=self.transcription_model,
            timeout_s=self.transcription_timeout_s,
        )
        return self._transcription_provider

    async def _maybe_transcribe_media_item(
        self,
        *,
        chat_id: str,
        message_id: int,
        item: dict[str, Any],
    ) -> None:
        media_type = str(item.get("type", "") or "").strip().lower()
        if not self._transcription_requested_for(media_type):
            return
        local_path = str(item.get("local_path", "") or "").strip()
        if not local_path:
            return
        provider = self._resolve_transcription_provider()
        if provider is None:
            return
        language = self.transcription_language or "pt"
        try:
            transcript = await provider.transcribe(local_path, language=language)
        except Exception as exc:
            self._signals["media_transcription_error_count"] += 1
            item["transcription_error"] = exc.__class__.__name__
            logger.debug(
                "telegram media transcription failed chat={} message_id={} type={} error={}",
                chat_id,
                message_id,
                media_type,
                exc,
            )
            return
        cleaned = self._compact_text(transcript)
        if not cleaned:
            return
        item["transcription"] = cleaned
        item["transcription_language"] = language
        self._signals["media_transcription_count"] += 1

    def _build_media_text_suffix_lines(self, media_info: dict[str, Any]) -> list[str]:
        lines: list[str] = []
        for item in media_info.get("items", []):
            if not isinstance(item, dict):
                continue
            transcript = self._compact_text(item.get("transcription", ""))
            if not transcript:
                continue
            media_type = str(item.get("type", "media") or "media").strip().lower()
            lines.append(f"[{media_type} transcription: {transcript}]")
        return lines

    def _compose_inbound_text(self, *, base_text: str, media_info: dict[str, Any]) -> str:
        text = str(base_text or "").strip()
        if not text and media_info.get("has_media"):
            text = self._build_media_placeholder(media_info)
        suffix_lines = self._build_media_text_suffix_lines(media_info)
        if suffix_lines:
            suffix = "\n".join(suffix_lines)
            text = "\n\n".join(part for part in (text, suffix) if part.strip())
        return text

    @staticmethod
    def _media_group_key(message: Any) -> str:
        group_id = str(getattr(message, "media_group_id", "") or "").strip()
        if not group_id:
            return ""
        chat_id = str(getattr(message, "chat_id", "") or "").strip()
        if not chat_id:
            return ""
        return f"{chat_id}:{group_id}"

    @staticmethod
    def _merge_media_counts(target: dict[str, int], counts: dict[str, Any]) -> None:
        for media_type, raw_count in dict(counts or {}).items():
            normalized_type = str(media_type or "").strip().lower()
            if not normalized_type:
                continue
            try:
                count = max(0, int(raw_count or 0))
            except (TypeError, ValueError):
                continue
            if count <= 0:
                continue
            target[normalized_type] = int(target.get(normalized_type, 0) or 0) + count

    @staticmethod
    def _append_unique_text(rows: list[str], text: str) -> None:
        normalized = str(text or "").strip()
        if not normalized:
            return
        if normalized in rows:
            return
        rows.append(normalized)

    async def _flush_media_group(self, group_key: str) -> None:
        try:
            await asyncio.sleep(MEDIA_GROUP_FLUSH_DELAY_S)
            buffer = self._media_group_buffers.pop(group_key, None)
            if not isinstance(buffer, dict):
                return
            texts = list(buffer.get("texts", []))
            counts = dict(buffer.get("media_counts", {}))
            media_types = sorted(counts.keys())
            media_items = list(buffer.get("media_items", []))
            if counts:
                placeholder = self._build_media_placeholder(
                    {"has_media": True, "counts": counts}
                )
                if placeholder and placeholder not in texts:
                    texts.insert(0, placeholder)
            combined_text = "\n\n".join(
                text for text in texts if isinstance(text, str) and text.strip()
            ).strip()
            if not combined_text:
                return
            metadata = dict(buffer.get("metadata", {}))
            metadata["text"] = combined_text
            metadata["media_present"] = bool(counts)
            metadata["media_types"] = media_types
            metadata["media_counts"] = counts
            metadata["media_total_count"] = int(sum(counts.values()))
            metadata["media_items"] = media_items
            metadata["media_group_id"] = str(buffer.get("media_group_id", "") or "")
            metadata["message_ids"] = list(buffer.get("message_ids", []))
            metadata["update_ids"] = list(buffer.get("update_ids", []))
            metadata["media_group_message_count"] = len(metadata["message_ids"])
            chat_id = str(metadata.get("chat_id", "") or "")
            message_thread_id = self._coerce_thread_id(
                metadata.get("message_thread_id")
            )
            if chat_id:
                self._start_typing_keepalive(
                    chat_id=chat_id, message_thread_id=message_thread_id
                )
            try:
                await self.emit(
                    session_id=str(buffer.get("session_id", "") or ""),
                    user_id=str(buffer.get("user_id", "") or ""),
                    text=combined_text,
                    metadata=metadata,
                )
            finally:
                if chat_id:
                    await self._stop_typing_keepalive(
                        chat_id=chat_id, message_thread_id=message_thread_id
                    )
            self._signals["media_group_flush_count"] += 1
        finally:
            self._media_group_tasks.pop(group_key, None)

    def _buffer_media_group_message(
        self,
        *,
        session_id: str,
        user_id: str,
        text: str,
        metadata: dict[str, Any],
        media_info: dict[str, Any],
        message: Any,
    ) -> bool:
        group_key = self._media_group_key(message)
        if not group_key:
            return False
        group_id = str(getattr(message, "media_group_id", "") or "").strip()
        message_id = int(getattr(message, "message_id", 0) or 0)
        update_id = int(metadata.get("update_id", 0) or 0)
        buffer = self._media_group_buffers.get(group_key)
        if buffer is None:
            buffer = {
                "session_id": session_id,
                "user_id": user_id,
                "media_group_id": group_id,
                "texts": [],
                "media_counts": {},
                "media_items": [],
                "message_ids": [],
                "update_ids": [],
                "metadata": dict(metadata),
            }
            self._media_group_buffers[group_key] = buffer
        self._append_unique_text(buffer["texts"], text)
        self._merge_media_counts(buffer["media_counts"], media_info.get("counts", {}))
        for item in media_info.get("items", []):
            if isinstance(item, dict):
                buffer["media_items"].append(dict(item))
        if message_id > 0 and message_id not in buffer["message_ids"]:
            buffer["message_ids"].append(message_id)
        if update_id > 0 and update_id not in buffer["update_ids"]:
            buffer["update_ids"].append(update_id)
        active_task = self._media_group_tasks.get(group_key)
        if active_task is None or active_task.done():
            self._media_group_tasks[group_key] = asyncio.create_task(
                self._flush_media_group(group_key)
            )
        self._signals["media_group_buffered_count"] += 1
        return True

    async def _flush_all_media_groups(self) -> None:
        tasks = list(self._media_group_tasks.values())
        self._media_group_tasks = {}
        for task in tasks:
            await cancel_task(task)
        pending_keys = list(self._media_group_buffers.keys())
        for key in pending_keys:
            buffer = self._media_group_buffers.pop(key, None)
            if not isinstance(buffer, dict):
                continue
            texts = list(buffer.get("texts", []))
            counts = dict(buffer.get("media_counts", {}))
            if counts:
                placeholder = self._build_media_placeholder(
                    {"has_media": True, "counts": counts}
                )
                if placeholder and placeholder not in texts:
                    texts.insert(0, placeholder)
            combined_text = "\n\n".join(
                text for text in texts if isinstance(text, str) and text.strip()
            ).strip()
            if not combined_text:
                continue
            metadata = dict(buffer.get("metadata", {}))
            metadata["text"] = combined_text
            metadata["media_present"] = bool(counts)
            metadata["media_types"] = sorted(counts.keys())
            metadata["media_counts"] = counts
            metadata["media_total_count"] = int(sum(counts.values()))
            metadata["media_items"] = list(buffer.get("media_items", []))
            metadata["media_group_id"] = str(buffer.get("media_group_id", "") or "")
            metadata["message_ids"] = list(buffer.get("message_ids", []))
            metadata["update_ids"] = list(buffer.get("update_ids", []))
            metadata["media_group_message_count"] = len(metadata["message_ids"])
            await self.emit(
                session_id=str(buffer.get("session_id", "") or ""),
                user_id=str(buffer.get("user_id", "") or ""),
                text=combined_text,
                metadata=metadata,
            )
            self._signals["media_group_flush_count"] += 1

    def _load_offset(self) -> int:
        try:
            snapshot = self._offset_store.refresh_from_disk()
        except (json.JSONDecodeError, OSError, ValueError, TypeError) as exc:
            self._signals["offset_load_error_count"] += 1
            self._offset_store.reset_runtime_state()
            logger.warning(
                "telegram offset load failed path={} error={}",
                self._offset_path(),
                exc,
            )
            return 0
        return self._apply_offset_snapshot(snapshot, count_signal=False)

    def _save_offset(self) -> None:
        try:
            snapshot = self._offset_store.sync_next_offset(
                max(0, int(self._offset or 0))
            )
        except (json.JSONDecodeError, OSError, ValueError, TypeError) as exc:
            self._signals["offset_persist_error_count"] += 1
            logger.warning(
                "telegram offset persist failed path={} error={}",
                self._offset_path(),
                exc,
            )
            return
        self._apply_offset_snapshot(snapshot, count_signal=False)

    def _apply_offset_snapshot(
        self, snapshot: Any, *, count_signal: bool = True
    ) -> int:
        previous_offset = max(0, int(getattr(self, "_offset", 0) or 0))
        next_offset = max(0, int(getattr(snapshot, "next_offset", 0) or 0))
        if count_signal and next_offset > previous_offset:
            self._signals["offset_safe_advance_count"] += 1
        self._offset = next_offset
        return next_offset

    def _persist_offset_operation(self, action: str, callback) -> Any:
        try:
            snapshot = callback()
        except (json.JSONDecodeError, OSError, ValueError, TypeError) as exc:
            self._signals["offset_persist_error_count"] += 1
            logger.warning(
                "telegram offset persist failed path={} action={} error={}",
                self._offset_path(),
                action,
                exc,
            )
            raise
        self._apply_offset_snapshot(snapshot)
        return snapshot

    def _begin_safe_offset_update(self, update_id: int) -> None:
        self._persist_offset_operation(
            "begin",
            lambda: self._offset_store.begin(update_id),
        )

    def _complete_safe_offset_update(
        self, update_id: int, *, tracked_pending: bool = True
    ) -> None:
        self._persist_offset_operation(
            "complete",
            lambda: self._offset_store.mark_completed(
                update_id,
                tracked_pending=tracked_pending,
            ),
        )

    def _force_commit_offset_update(self, update_id: int) -> None:
        self._persist_offset_operation(
            "force_commit",
            lambda: self._offset_store.force_commit(update_id),
        )

    def _is_stale_offset_update(self, update_id: int) -> bool:
        return self._offset_store.is_safe_committed(update_id)

    def _should_begin_webhook_offset_tracking(self, update_id: int) -> bool:
        return update_id == self._offset or self._offset_store.is_pending(update_id)

    def _webhook_offset_completion_policy(self, update_id: int) -> tuple[bool, bool]:
        return True, bool(
            self._offset_store.is_pending(update_id) or update_id == self._offset
        )

    @staticmethod
    def _metadata_user_id(value: Any) -> int | str:
        text = str(value or "").strip()
        if not text:
            return ""
        if text.isdigit() or (text.startswith("-") and text[1:].isdigit()):
            try:
                return int(text)
            except ValueError:
                return text
        return text

    async def _emit_aux_update_event(
        self,
        *,
        item: Any,
        update_kind: str,
        chat_id: str,
        chat_type: str,
        user_id: str,
        username: str,
        text: str,
        message_thread_id: int | None = None,
        extra_metadata: dict[str, Any] | None = None,
        authorize: bool = True,
    ) -> bool:
        normalized_chat_id = str(chat_id or "").strip()
        normalized_text = str(text or "").strip()
        normalized_user_id = (
            str(user_id or normalized_chat_id).strip() or normalized_chat_id
        )
        normalized_chat_type = str(chat_type or "").strip()
        normalized_username = str(username or "").strip()
        if not normalized_chat_id or not normalized_text:
            return True
        if authorize and not self._authorize_inbound_context(
            chat_type=normalized_chat_type,
            chat_id=normalized_chat_id,
            message_thread_id=message_thread_id,
            user_id=normalized_user_id,
            username=normalized_username,
        ):
            return True

        session_id = self._session_id_for_chat(
            chat_id=normalized_chat_id,
            chat_type=normalized_chat_type,
            message_thread_id=message_thread_id,
        )
        metadata: dict[str, Any] = {
            "channel": "telegram",
            "chat_id": normalized_chat_id,
            "chat_type": normalized_chat_type,
            "is_group": normalized_chat_type != "private",
            "update_id": int(getattr(item, "update_id", 0) or 0),
            "update_kind": str(update_kind or "event"),
            "text": normalized_text,
            "user_id": self._metadata_user_id(normalized_user_id),
            "username": normalized_username,
        }
        if message_thread_id is not None:
            metadata["message_thread_id"] = message_thread_id
        if isinstance(extra_metadata, dict):
            metadata.update(extra_metadata)
        await self.emit(
            session_id=session_id,
            user_id=normalized_user_id,
            text=normalized_text,
            metadata=metadata,
        )
        return True

    async def _poll_loop(self) -> None:
        backoff = self.reconnect_initial_s
        while self._running:
            try:
                if self.bot is None:
                    await self._ensure_bot()
                    logger.info(
                        "telegram bot initialized poll_timeout_s={}",
                        self.poll_timeout_s,
                    )
                    await self._try_delete_webhook(reason="polling_start")
                    if self.drop_pending_updates and not self._startup_drop_done:
                        await self._drop_pending_updates()
                        self._startup_drop_done = True
                updates = await self.bot.get_updates(
                    offset=self._offset,
                    timeout=self.poll_timeout_s,
                    allowed_updates=TELEGRAM_ALLOWED_UPDATES,
                )
                if not self._connected:
                    self._connected = True
                    logger.info("telegram connected polling=true")
                backoff = self.reconnect_initial_s
                for item in updates:
                    dedupe_key = self._build_update_dedupe_key(item)
                    update_id = self._coerce_update_id(getattr(item, "update_id", None))
                    if update_id is not None and self._is_stale_offset_update(
                        update_id
                    ):
                        self._signals["polling_stale_update_skip_count"] += 1
                        continue
                    if dedupe_key and self._is_duplicate_update_dedupe_key(
                        dedupe_key, source="polling"
                    ):
                        if update_id is not None:
                            self._complete_safe_offset_update(
                                update_id,
                                tracked_pending=self._offset_store.is_pending(
                                    update_id
                                ),
                            )
                        continue
                    if update_id is not None:
                        self._begin_safe_offset_update(update_id)
                    processed_ok = await self._handle_update(item)
                    if not processed_ok:
                        raise RuntimeError("telegram update processing failed")
                    if dedupe_key:
                        self._commit_update_dedupe_key(dedupe_key)
                    if update_id is None:
                        continue
                    self._complete_safe_offset_update(update_id)
                await asyncio.sleep(self.poll_interval_s)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover
                self._last_error = str(exc)
                self._connected = False
                self.bot = None
                self._signals["reconnect_count"] += 1
                logger.error(
                    "telegram polling error error={} backoff_s={}", exc, backoff
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self.reconnect_max_s)

    async def _handle_update(self, item: Any) -> bool:
        inline_query = getattr(item, "inline_query", None)
        if inline_query is not None:
            self._signals["inline_query_received_count"] += 1
            inline_query_id = str(getattr(inline_query, "id", "") or "").strip()
            if (
                self.bot is not None
                and inline_query_id
                and hasattr(self.bot, "answer_inline_query")
            ):
                try:
                    await self.bot.answer_inline_query(
                        inline_query_id=inline_query_id,
                        results=[],
                        cache_time=0,
                        is_personal=True,
                    )
                    self._signals["inline_query_answered_count"] += 1
                except TypeError:
                    try:
                        await self.bot.answer_inline_query(
                            inline_query_id=inline_query_id,
                            results=[],
                        )
                        self._signals["inline_query_answered_count"] += 1
                    except Exception as exc:
                        self._signals["inline_query_answer_error_count"] += 1
                        logger.debug(
                            "telegram inline_query answer failed id={} error={}",
                            inline_query_id,
                            exc,
                        )
                except Exception as exc:
                    self._signals["inline_query_answer_error_count"] += 1
                    logger.debug(
                        "telegram inline_query answer failed id={} error={}",
                        inline_query_id,
                        exc,
                    )
            return True

        shipping_query = getattr(item, "shipping_query", None)
        if shipping_query is not None:
            self._signals["shipping_query_received_count"] += 1
            shipping_query_id = str(getattr(shipping_query, "id", "") or "").strip()
            if (
                self.bot is not None
                and shipping_query_id
                and hasattr(self.bot, "answer_shipping_query")
            ):
                try:
                    await self.bot.answer_shipping_query(
                        shipping_query_id=shipping_query_id,
                        ok=False,
                        error_message="Telegram payments are not enabled for this bot.",
                    )
                    self._signals["shipping_query_rejected_count"] += 1
                except Exception as exc:
                    self._signals["shipping_query_answer_error_count"] += 1
                    logger.debug(
                        "telegram shipping_query answer failed id={} error={}",
                        shipping_query_id,
                        exc,
                    )
            return True

        pre_checkout_query = getattr(item, "pre_checkout_query", None)
        if pre_checkout_query is not None:
            self._signals["pre_checkout_query_received_count"] += 1
            pre_checkout_query_id = str(
                getattr(pre_checkout_query, "id", "") or ""
            ).strip()
            if (
                self.bot is not None
                and pre_checkout_query_id
                and hasattr(self.bot, "answer_pre_checkout_query")
            ):
                try:
                    await self.bot.answer_pre_checkout_query(
                        pre_checkout_query_id=pre_checkout_query_id,
                        ok=False,
                        error_message="Telegram payments are not enabled for this bot.",
                    )
                    self._signals["pre_checkout_query_rejected_count"] += 1
                except Exception as exc:
                    self._signals["pre_checkout_query_answer_error_count"] += 1
                    logger.debug(
                        "telegram pre_checkout_query answer failed id={} error={}",
                        pre_checkout_query_id,
                        exc,
                    )
            return True

        chosen_inline_result = getattr(item, "chosen_inline_result", None)
        if chosen_inline_result is not None:
            self._signals["chosen_inline_result_received_count"] += 1
            return True

        poll = getattr(item, "poll", None)
        if poll is not None:
            self._signals["poll_received_count"] += 1
            return True

        poll_answer = getattr(item, "poll_answer", None)
        if poll_answer is not None:
            self._signals["poll_answer_received_count"] += 1
            return True

        chat_member_update = getattr(item, "chat_member", None)
        if chat_member_update is not None:
            self._signals["chat_member_received_count"] += 1
            member_chat = getattr(chat_member_update, "chat", None)
            member_actor = getattr(chat_member_update, "from_user", None)
            new_member = getattr(chat_member_update, "new_chat_member", None)
            target_user = getattr(new_member, "user", None)
            member_chat_id = str(
                getattr(chat_member_update, "chat_id", "")
                or getattr(member_chat, "id", "")
                or ""
            )
            member_chat_type = str(getattr(member_chat, "type", "") or "")
            member_user_id = str(
                getattr(target_user, "id", "")
                or getattr(member_actor, "id", "")
                or member_chat_id
            )
            member_username = str(
                getattr(target_user, "username", "")
                or getattr(member_actor, "username", "")
                or ""
            ).strip()
            old_member = getattr(chat_member_update, "old_chat_member", None)
            old_status = str(getattr(old_member, "status", "") or "").strip().lower()
            new_status = str(getattr(new_member, "status", "") or "").strip().lower()
            return await self._emit_aux_update_event(
                item=item,
                update_kind="chat_member",
                chat_id=member_chat_id,
                chat_type=member_chat_type,
                user_id=member_user_id,
                username=member_username,
                text=f"[telegram chat member] {old_status or '-'} -> {new_status or '-'}",
                extra_metadata={
                    "member_user_id": self._metadata_user_id(member_user_id),
                    "old_status": old_status,
                    "new_status": new_status,
                    "is_chat_member_update": True,
                },
            )

        my_chat_member_update = getattr(item, "my_chat_member", None)
        if my_chat_member_update is not None:
            self._signals["my_chat_member_received_count"] += 1
            new_state = getattr(my_chat_member_update, "new_chat_member", None)
            new_status = str(getattr(new_state, "status", "") or "").strip().lower()
            if new_status in {"kicked", "left"}:
                self._connected = False
            elif new_status:
                self._connected = True
            return True

        chat_join_request = getattr(item, "chat_join_request", None)
        if chat_join_request is not None:
            self._signals["chat_join_request_received_count"] += 1
            join_chat = getattr(chat_join_request, "chat", None)
            join_user = getattr(chat_join_request, "from_user", None)
            join_chat_id = str(
                getattr(chat_join_request, "chat_id", "")
                or getattr(join_chat, "id", "")
                or ""
            )
            join_chat_type = str(getattr(join_chat, "type", "") or "")
            join_user_id = str(getattr(join_user, "id", "") or join_chat_id)
            join_username = str(getattr(join_user, "username", "") or "").strip()
            return await self._emit_aux_update_event(
                item=item,
                update_kind="chat_join_request",
                chat_id=join_chat_id,
                chat_type=join_chat_type,
                user_id=join_user_id,
                username=join_username,
                text="[telegram chat join request]",
                extra_metadata={
                    "is_chat_join_request": True,
                    "bio": str(getattr(chat_join_request, "bio", "") or "").strip(),
                    "invite_link": str(
                        getattr(chat_join_request, "invite_link", "") or ""
                    ).strip(),
                },
            )

        business_connection = getattr(item, "business_connection", None)
        if business_connection is not None:
            self._signals["business_connection_received_count"] += 1
            return True

        deleted_business_messages = getattr(item, "deleted_business_messages", None)
        if deleted_business_messages is not None:
            self._signals["deleted_business_messages_received_count"] += 1
            deleted_chat = getattr(deleted_business_messages, "chat", None)
            deleted_chat_id = str(
                getattr(deleted_business_messages, "chat_id", "")
                or getattr(deleted_chat, "id", "")
                or ""
            )
            deleted_chat_type = str(getattr(deleted_chat, "type", "") or "")
            deleted_message_ids = getattr(
                deleted_business_messages, "message_ids", None
            )
            normalized_deleted_ids = (
                [int(item_id) for item_id in deleted_message_ids]
                if isinstance(deleted_message_ids, list)
                else []
            )
            return await self._emit_aux_update_event(
                item=item,
                update_kind="deleted_business_messages",
                chat_id=deleted_chat_id,
                chat_type=deleted_chat_type,
                user_id=deleted_chat_id,
                username="",
                text="[telegram deleted business messages]",
                extra_metadata={
                    "is_deleted_business_messages": True,
                    "business_connection_id": str(
                        getattr(deleted_business_messages, "business_connection_id", "")
                        or ""
                    ).strip(),
                    "message_ids": normalized_deleted_ids,
                },
                authorize=False,
            )

        message_reaction_count = getattr(item, "message_reaction_count", None)
        if message_reaction_count is not None:
            self._signals["message_reaction_count_received_count"] += 1
            reaction_count_chat = getattr(message_reaction_count, "chat", None)
            reaction_count_chat_id = str(
                getattr(message_reaction_count, "chat_id", "")
                or getattr(reaction_count_chat, "id", "")
                or ""
            )
            reaction_count_chat_type = str(
                getattr(reaction_count_chat, "type", "") or ""
            )
            try:
                reaction_count_message_id = int(
                    getattr(message_reaction_count, "message_id", 0) or 0
                )
            except (TypeError, ValueError):
                reaction_count_message_id = 0
            return await self._emit_aux_update_event(
                item=item,
                update_kind="message_reaction_count",
                chat_id=reaction_count_chat_id,
                chat_type=reaction_count_chat_type,
                user_id=reaction_count_chat_id,
                username="",
                text="[telegram reaction count]",
                extra_metadata={
                    "is_message_reaction_count": True,
                    "message_id": reaction_count_message_id,
                },
                authorize=False,
            )

        chat_boost = getattr(item, "chat_boost", None)
        if chat_boost is not None:
            self._signals["chat_boost_received_count"] += 1
            boost_chat = getattr(chat_boost, "chat", None)
            boost_row = getattr(chat_boost, "boost", None) or chat_boost
            boost_source = getattr(boost_row, "source", None)
            boost_user = getattr(boost_source, "user", None) or getattr(
                boost_source, "from_user", None
            )
            boost_chat_id = str(
                getattr(boost_chat, "id", "")
                or getattr(chat_boost, "chat_id", "")
                or ""
            )
            boost_chat_type = str(getattr(boost_chat, "type", "") or "")
            boost_user_id = str(getattr(boost_user, "id", "") or boost_chat_id)
            boost_username = str(getattr(boost_user, "username", "") or "").strip()
            return await self._emit_aux_update_event(
                item=item,
                update_kind="chat_boost",
                chat_id=boost_chat_id,
                chat_type=boost_chat_type,
                user_id=boost_user_id,
                username=boost_username,
                text="[telegram chat boost]",
                extra_metadata={
                    "is_chat_boost": True,
                    "boost_id": str(getattr(boost_row, "boost_id", "") or "").strip(),
                },
                authorize=False,
            )

        removed_chat_boost = getattr(item, "removed_chat_boost", None)
        if removed_chat_boost is not None:
            self._signals["removed_chat_boost_received_count"] += 1
            removed_chat = getattr(removed_chat_boost, "chat", None)
            removed_boost = (
                getattr(removed_chat_boost, "boost", None) or removed_chat_boost
            )
            removed_source = getattr(removed_boost, "source", None)
            removed_user = getattr(removed_source, "user", None) or getattr(
                removed_source, "from_user", None
            )
            removed_chat_id = str(
                getattr(removed_chat, "id", "")
                or getattr(removed_chat_boost, "chat_id", "")
                or ""
            )
            removed_chat_type = str(getattr(removed_chat, "type", "") or "")
            removed_user_id = str(getattr(removed_user, "id", "") or removed_chat_id)
            removed_username = str(getattr(removed_user, "username", "") or "").strip()
            return await self._emit_aux_update_event(
                item=item,
                update_kind="removed_chat_boost",
                chat_id=removed_chat_id,
                chat_type=removed_chat_type,
                user_id=removed_user_id,
                username=removed_username,
                text="[telegram removed chat boost]",
                extra_metadata={
                    "is_removed_chat_boost": True,
                    "boost_id": str(
                        getattr(removed_boost, "boost_id", "") or ""
                    ).strip(),
                },
                authorize=False,
            )

        purchased_paid_media = getattr(item, "purchased_paid_media", None)
        if purchased_paid_media is not None:
            self._signals["purchased_paid_media_received_count"] += 1
            paid_media_chat = getattr(purchased_paid_media, "chat", None)
            paid_media_user = getattr(
                purchased_paid_media, "from_user", None
            ) or getattr(purchased_paid_media, "user", None)
            paid_media_chat_id = str(
                getattr(purchased_paid_media, "chat_id", "")
                or getattr(paid_media_chat, "id", "")
                or ""
            )
            paid_media_chat_type = str(getattr(paid_media_chat, "type", "") or "")
            paid_media_user_id = str(
                getattr(paid_media_user, "id", "") or paid_media_chat_id
            )
            paid_media_username = str(
                getattr(paid_media_user, "username", "") or ""
            ).strip()
            return await self._emit_aux_update_event(
                item=item,
                update_kind="purchased_paid_media",
                chat_id=paid_media_chat_id,
                chat_type=paid_media_chat_type,
                user_id=paid_media_user_id,
                username=paid_media_username,
                text="[telegram purchased paid media]",
                extra_metadata={
                    "is_purchased_paid_media": True,
                    "payload": str(
                        getattr(purchased_paid_media, "payload", "") or ""
                    ).strip(),
                },
                authorize=False,
            )

        callback_query = getattr(item, "callback_query", None)
        if callback_query is not None:
            self._signals["callback_query_received_count"] += 1
            callback_query_id = str(getattr(callback_query, "id", "") or "")
            callback_data_raw = getattr(callback_query, "data", "")
            callback_data = str(callback_data_raw or "")
            callback_text = callback_data.strip() or "[telegram callback_query]"
            callback_message = getattr(callback_query, "message", None)
            callback_message_chat = getattr(callback_message, "chat", None)
            callback_chat_type = str(getattr(callback_message_chat, "type", "") or "")
            callback_chat_id = str(
                getattr(callback_message, "chat_id", "")
                or getattr(callback_message_chat, "id", "")
                or ""
            )
            if not callback_chat_id:
                logger.debug("telegram callback_query skipped reason=missing_chat_id")
                return True

            callback_from_user = getattr(callback_query, "from_user", None)
            callback_user_id = str(
                getattr(callback_from_user, "id", "") or callback_chat_id
            )
            callback_username = str(
                getattr(callback_from_user, "username", "") or ""
            ).strip()
            callback_thread_id = self._coerce_thread_id(
                getattr(callback_message, "message_thread_id", None)
            )

            if (
                self.bot is not None
                and callback_query_id
                and hasattr(self.bot, "answer_callback_query")
            ):
                try:
                    await self.bot.answer_callback_query(
                        callback_query_id=callback_query_id
                    )
                except Exception as exc:
                    self._signals["callback_query_ack_error_count"] += 1
                    logger.debug(
                        "telegram callback_query ack failed id={} chat={} error={}",
                        callback_query_id,
                        callback_chat_id,
                        exc,
                    )

            if not self._authorize_inbound_context(
                chat_type=callback_chat_type,
                chat_id=callback_chat_id,
                message_thread_id=callback_thread_id,
                user_id=callback_user_id,
                username=callback_username,
            ):
                self._signals["callback_query_blocked_count"] += 1
                logger.debug(
                    "telegram callback_query blocked user={} chat={} id={}",
                    callback_user_id,
                    callback_chat_id,
                    callback_query_id,
                )
                return True

            callback_valid, callback_normalized_data, callback_signed = (
                self._callback_verify_payload(callback_data)
            )
            callback_blocked = False
            if callback_signed:
                if callback_valid:
                    callback_data = callback_normalized_data
                    callback_text = callback_data.strip() or "[telegram callback_query]"
                    self._signals["callback_query_signature_accepted_count"] += 1
                else:
                    callback_blocked = True
            else:
                if self.callback_require_signed:
                    callback_blocked = True
                else:
                    self._signals["callback_query_unsigned_allowed_count"] += 1

            if callback_blocked:
                self._signals["callback_query_blocked_count"] += 1
                self._signals["callback_query_signature_blocked_count"] += 1
                logger.debug(
                    "telegram callback_query blocked signature chat={} id={} signed={} require_signed={}",
                    callback_chat_id,
                    callback_query_id,
                    callback_signed,
                    self.callback_require_signed,
                )
                return True

            session_id = self._session_id_for_chat(
                chat_id=callback_chat_id,
                chat_type=callback_chat_type,
                message_thread_id=callback_thread_id,
            )
            metadata: dict[str, Any] = {
                "channel": "telegram",
                "chat_id": callback_chat_id,
                "chat_type": callback_chat_type,
                "is_group": callback_chat_type != "private",
                "update_kind": "callback_query",
                "is_callback_query": True,
                "callback_query_id": callback_query_id,
                "callback_data": callback_data,
                "callback_signed": callback_signed,
                "callback_chat_instance": str(
                    getattr(callback_query, "chat_instance", "") or ""
                ),
                "user_id": int(getattr(callback_from_user, "id", 0) or 0),
                "username": callback_username,
                "text": callback_text,
                "update_id": int(getattr(item, "update_id", 0) or 0),
            }
            callback_message_id = getattr(callback_message, "message_id", None)
            try:
                callback_message_id_int = int(callback_message_id)
            except (TypeError, ValueError):
                callback_message_id_int = 0
            if callback_message_id_int > 0:
                metadata["message_id"] = callback_message_id_int

            if callback_thread_id is not None:
                metadata["message_thread_id"] = callback_thread_id

            logger.info(
                "telegram callback_query received chat={} user={} chars={} id={}",
                callback_chat_id,
                callback_user_id,
                len(callback_text),
                callback_query_id,
            )
            await self.emit(
                session_id=session_id,
                user_id=callback_user_id,
                text=callback_text,
                metadata=metadata,
            )
            return True

        message_reaction = getattr(item, "message_reaction", None)
        if message_reaction is not None:
            self._signals["message_reaction_received_count"] += 1
            reaction_chat = getattr(message_reaction, "chat", None)
            reaction_chat_type = str(getattr(reaction_chat, "type", "") or "")
            chat_id = str(
                getattr(message_reaction, "chat_id", "")
                or getattr(reaction_chat, "id", "")
                or ""
            )
            if not chat_id:
                return True

            try:
                message_id = int(getattr(message_reaction, "message_id", 0) or 0)
            except (TypeError, ValueError):
                message_id = 0

            reactor = getattr(message_reaction, "user", None) or getattr(
                message_reaction, "from_user", None
            )
            reactor_user_id = str(getattr(reactor, "id", "") or chat_id)
            reactor_username = str(getattr(reactor, "username", "") or "").strip()
            reaction_thread_id = self._coerce_thread_id(
                getattr(message_reaction, "message_thread_id", None)
            )
            if bool(getattr(reactor, "is_bot", False)):
                self._signals["message_reaction_ignored_bot_count"] += 1
                return True

            if self.reaction_notifications == "off":
                self._signals["message_reaction_blocked_count"] += 1
                return True

            if self.reaction_notifications == "own":
                if (
                    message_id <= 0
                    or (chat_id, message_id) not in self._own_sent_message_keys
                ):
                    self._signals["message_reaction_blocked_count"] += 1
                    return True

            if not self._authorize_inbound_context(
                chat_type=reaction_chat_type,
                chat_id=chat_id,
                message_thread_id=reaction_thread_id,
                user_id=reactor_user_id,
                username=reactor_username,
            ):
                self._signals["message_reaction_blocked_count"] += 1
                return True

            old_reaction = getattr(message_reaction, "old_reaction", None)
            new_reaction = getattr(message_reaction, "new_reaction", None)
            reaction_added = self._added_reaction_tokens(
                old_reaction=old_reaction, new_reaction=new_reaction
            )
            if not reaction_added:
                return True

            reaction_new_tokens = self._reaction_tokens(new_reaction)
            reaction_old_tokens = self._reaction_tokens(old_reaction)
            reaction_marker = " ".join(reaction_added)
            reaction_text = f"[telegram reaction] {reaction_marker}".strip()
            session_id = self._session_id_for_chat(
                chat_id=chat_id,
                chat_type=reaction_chat_type,
                message_thread_id=reaction_thread_id,
            )
            metadata = {
                "channel": "telegram",
                "chat_id": chat_id,
                "chat_type": reaction_chat_type,
                "is_group": reaction_chat_type != "private",
                "update_kind": "message_reaction",
                "is_message_reaction": True,
                "message_id": message_id,
                "user_id": reactor_user_id,
                "username": reactor_username,
                "reaction_added": reaction_added,
                "reaction_new": reaction_new_tokens,
                "reaction_old": reaction_old_tokens,
                "update_id": int(getattr(item, "update_id", 0) or 0),
                "text": reaction_text,
            }
            if reaction_thread_id is not None:
                metadata["message_thread_id"] = reaction_thread_id
            await self.emit(
                session_id=session_id,
                user_id=reactor_user_id,
                text=reaction_text,
                metadata=metadata,
            )
            self._signals["message_reaction_emitted_count"] += 1
            return True

        message = getattr(item, "message", None)
        update_kind = "message"
        is_edit = False
        if message is None:
            message = getattr(item, "edited_message", None)
            is_edit = message is not None
            if message is not None:
                update_kind = "edited_message"
        if message is None:
            message = getattr(item, "business_message", None)
            is_edit = False
            if message is not None:
                update_kind = "business_message"
        if message is None:
            message = getattr(item, "edited_business_message", None)
            is_edit = message is not None
            if message is not None:
                update_kind = "edited_business_message"
        if message is None:
            message = getattr(item, "channel_post", None)
            is_edit = False
            if message is not None:
                update_kind = "channel_post"
        if message is None:
            message = getattr(item, "edited_channel_post", None)
            is_edit = message is not None
            if message is not None:
                update_kind = "edited_channel_post"
        if message is None:
            message = getattr(item, "effective_message", None)
            is_edit = bool(
                getattr(item, "edited_message", None)
                or getattr(item, "edited_business_message", None)
                or getattr(item, "edited_channel_post", None)
            )
            if message is not None:
                update_kind = "effective_message"
        if message is None:
            self._signals["unhandled_update_received_count"] += 1
            return True

        media_info = self._extract_media_info(message)
        base_text = (
            getattr(message, "text", "") or getattr(message, "caption", "") or ""
        ).strip()

        chat_id = str(getattr(message, "chat_id", "") or "")
        message_thread_id = self._coerce_thread_id(
            getattr(message, "message_thread_id", None)
        )
        if not chat_id:
            return True
        user = getattr(message, "from_user", None)
        chat = getattr(message, "chat", None)
        chat_type = str(getattr(chat, "type", "") or "")
        user_id = str(getattr(user, "id", "") or chat_id)
        username = str(getattr(user, "username", "") or "").strip()
        auth_decision = self._authorization_decision(
            chat_type=chat_type,
            chat_id=chat_id,
            message_thread_id=message_thread_id,
            user_id=user_id,
            username=username,
        )
        if auth_decision == "allow":
            self._signals["policy_allowed_count"] += 1
        else:
            self._signals["policy_blocked_count"] += 1
            if auth_decision == "pairing":
                self._signals["pairing_required_count"] += 1
                await self._handle_pairing_required(
                    chat_id=chat_id,
                    user_id=user_id,
                    username=username,
                    first_name=str(getattr(user, "first_name", "") or "").strip(),
                )
            logger.debug("telegram inbound blocked user={} chat={}", user_id, chat_id)
            return True

        message_id = int(getattr(message, "message_id", 0) or 0)
        await self._download_media_items(
            chat_id=chat_id, message_id=message_id, media_info=media_info
        )
        text = self._compose_inbound_text(base_text=base_text, media_info=media_info)
        if not text:
            return True
        signature = hashlib.sha256(text.encode("utf-8")).hexdigest()
        msg_key = (chat_id, message_id)
        previous_signature = self._message_signatures.get(msg_key)
        if previous_signature == signature:
            logger.debug(
                "telegram inbound duplicate skipped chat={} message_id={} is_edit={}",
                chat_id,
                message_id,
                is_edit,
            )
            return True

        command, command_args = parse_command(text)
        is_command = bool(command)
        if is_command and self.handle_commands:
            if command == "start":
                await self._send_start_message(chat_id=chat_id)
                self._remember_message_signature(msg_key=msg_key, signature=signature)
                return True
            if command == "help":
                await self._send_help_message(chat_id=chat_id)
                self._remember_message_signature(msg_key=msg_key, signature=signature)
                return True

        session_id = self._session_id_for_chat(
            chat_id=chat_id,
            chat_type=chat_type,
            message_thread_id=message_thread_id,
        )
        metadata = self._build_metadata(
            item=item,
            message=message,
            text=text,
            is_edit=is_edit,
            update_kind=update_kind,
            command=command,
            command_args=command_args,
            media_info=media_info,
        )
        if self._buffer_media_group_message(
            session_id=session_id,
            user_id=user_id,
            text=text,
            metadata=metadata,
            media_info=media_info,
            message=message,
        ):
            self._remember_message_signature(msg_key=msg_key, signature=signature)
            return True
        logger.info(
            "telegram inbound received chat={} user={} chars={} edit={} command={}",
            chat_id,
            user_id,
            len(text),
            is_edit,
            command or "",
        )
        self._start_typing_keepalive(
            chat_id=chat_id, message_thread_id=message_thread_id
        )
        try:
            await self.emit(
                session_id=session_id, user_id=user_id, text=text, metadata=metadata
            )
        except Exception:
            await self._stop_typing_keepalive(
                chat_id=chat_id, message_thread_id=message_thread_id
            )
            raise
        await self._stop_typing_keepalive(
            chat_id=chat_id, message_thread_id=message_thread_id
        )
        self._remember_message_signature(msg_key=msg_key, signature=signature)
        return True

    def _build_metadata(
        self,
        *,
        item: Any,
        message: Any,
        text: str,
        is_edit: bool,
        update_kind: str,
        command: str,
        command_args: str,
        media_info: dict[str, Any],
    ) -> dict[str, Any]:
        user = getattr(message, "from_user", None)
        chat = getattr(message, "chat", None)
        reply = getattr(message, "reply_to_message", None)
        reply_user = getattr(reply, "from_user", None) if reply else None

        metadata: dict[str, Any] = {
            "channel": "telegram",
            "chat_id": str(getattr(message, "chat_id", "") or ""),
            "chat_type": str(getattr(chat, "type", "") or ""),
            "is_group": str(getattr(chat, "type", "") or "") != "private",
            "message_id": int(getattr(message, "message_id", 0) or 0),
            "update_id": int(getattr(item, "update_id", 0) or 0),
            "update_kind": str(update_kind or "message"),
            "is_edit": is_edit,
            "is_command": bool(command),
            "text": text,
            "user_id": int(getattr(user, "id", 0) or 0),
            "username": str(getattr(user, "username", "") or ""),
            "first_name": str(getattr(user, "first_name", "") or ""),
            "language_code": str(getattr(user, "language_code", "") or ""),
            "date": str(getattr(message, "date", "") or ""),
            "edit_date": str(getattr(message, "edit_date", "") or ""),
            "media_present": bool(media_info.get("has_media", False)),
            "media_types": list(media_info.get("types", [])),
            "media_counts": dict(media_info.get("counts", {})),
            "media_total_count": int(media_info.get("total_count", 0) or 0),
            "media_items": list(media_info.get("items", [])),
        }
        business_connection_id = str(
            getattr(message, "business_connection_id", "") or ""
        ).strip()
        if business_connection_id:
            metadata["business_connection_id"] = business_connection_id
        message_thread_id = self._coerce_thread_id(
            getattr(message, "message_thread_id", None)
        )
        if message_thread_id is not None:
            metadata["message_thread_id"] = message_thread_id
        if command:
            metadata["command"] = command
            metadata["command_args"] = command_args
        if reply is not None:
            metadata["reply_to_message_id"] = int(getattr(reply, "message_id", 0) or 0)
            metadata["reply_to_text"] = str(
                getattr(reply, "text", "") or getattr(reply, "caption", "") or ""
            )[:500]
            metadata["reply_to_user_id"] = int(getattr(reply_user, "id", 0) or 0)
            metadata["reply_to_username"] = str(
                getattr(reply_user, "username", "") or ""
            )
        return metadata

    @staticmethod
    def _build_media_item(
        *, media_type: str, raw: Any, index: int | None = None
    ) -> dict[str, Any]:
        item: dict[str, Any] = {"type": media_type}
        if index is not None:
            item["index"] = index

        for field_name in (
            "file_id",
            "file_unique_id",
            "file_name",
            "mime_type",
            "file_size",
            "duration",
            "width",
            "height",
            "length",
            "emoji",
            "set_name",
            "phone_number",
            "first_name",
            "last_name",
            "user_id",
            "latitude",
            "longitude",
            "horizontal_accuracy",
            "live_period",
            "heading",
            "proximity_alert_radius",
            "title",
            "address",
        ):
            value = getattr(raw, field_name, None)
            if value is None:
                continue
            if isinstance(value, (str, int, float, bool)):
                item[field_name] = value
        return item

    def _extract_media_info(self, message: Any) -> dict[str, Any]:
        counts: dict[str, int] = {}
        items: list[dict[str, Any]] = []

        photos = getattr(message, "photo", None)
        if photos:
            largest_photo = photos[-1]
            counts["photo"] = 1
            photo_item = self._build_media_item(
                media_type="photo", raw=largest_photo, index=1
            )
            photo_item["variant_count"] = len(photos)
            items.append(photo_item)

        for media_type in (
            "voice",
            "audio",
            "document",
            "video",
            "animation",
            "video_note",
            "sticker",
            "contact",
            "location",
        ):
            raw = getattr(message, media_type, None)
            if raw is not None:
                counts[media_type] = counts.get(media_type, 0) + 1
                items.append(self._build_media_item(media_type=media_type, raw=raw))

        media_types = sorted(counts.keys())
        total_count = sum(counts.values())
        return {
            "has_media": bool(counts),
            "types": media_types,
            "counts": counts,
            "total_count": total_count,
            "items": items,
        }

    def _build_media_placeholder(self, media_info: dict[str, Any]) -> str:
        if not media_info.get("has_media"):
            return ""
        counts = dict(media_info.get("counts", {}))
        details = ", ".join(
            f"{media_type}({counts[media_type]})"
            if counts[media_type] > 1
            else media_type
            for media_type in sorted(counts.keys())
        )
        if not details:
            return "[telegram media message]"
        return f"[telegram media message: {details}]"

    @staticmethod
    def _media_download_extension(*, media_type: str, item: dict[str, Any]) -> str:
        file_name = str(item.get("file_name", "") or "").strip()
        suffix = Path(file_name).suffix.strip()
        if suffix:
            return suffix
        mime_type = str(item.get("mime_type", "") or "").strip().lower()
        mime_map = {
            "audio/mp4": ".m4a",
            "audio/mpeg": ".mp3",
            "audio/ogg": ".ogg",
            "audio/wav": ".wav",
            "image/gif": ".gif",
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
            "video/mp4": ".mp4",
            "application/pdf": ".pdf",
        }
        if mime_type in mime_map:
            return mime_map[mime_type]
        type_map = {
            "animation": ".gif",
            "audio": ".mp3",
            "document": "",
            "photo": ".jpg",
            "sticker": ".webp",
            "video": ".mp4",
            "video_note": ".mp4",
            "voice": ".ogg",
        }
        return type_map.get(media_type, "")

    async def _download_media_items(
        self, *, chat_id: str, message_id: int, media_info: dict[str, Any]
    ) -> None:
        if not media_info.get("has_media"):
            return
        if self.bot is None or not hasattr(self.bot, "get_file"):
            return

        base_dir = self._media_download_dir()
        safe_chat_id = re.sub(r"[^0-9A-Za-z_-]+", "_", chat_id or "") or "chat"
        chat_dir = base_dir / safe_chat_id
        try:
            await asyncio.to_thread(chat_dir.mkdir, parents=True, exist_ok=True)
        except OSError as exc:
            logger.debug(
                "telegram media download mkdir failed chat={} error={}", chat_id, exc
            )
            return

        for item in media_info.get("items", []):
            if not isinstance(item, dict):
                continue
            file_id = str(item.get("file_id", "") or "").strip()
            media_type = str(item.get("type", "") or "").strip().lower()
            if not file_id or not media_type:
                continue
            extension = self._media_download_extension(media_type=media_type, item=item)
            safe_file_id = re.sub(r"[^0-9A-Za-z_-]+", "_", file_id)[:24] or "file"
            target = chat_dir / f"{message_id}-{media_type}-{safe_file_id}{extension}"
            try:
                remote_file = await self.bot.get_file(file_id)
                await remote_file.download_to_drive(str(target))
                item["local_path"] = str(target)
                self._signals["media_download_count"] += 1
                await self._maybe_transcribe_media_item(
                    chat_id=chat_id,
                    message_id=message_id,
                    item=item,
                )
            except Exception as exc:
                self._signals["media_download_error_count"] += 1
                logger.debug(
                    "telegram media download failed chat={} message_id={} type={} error={}",
                    chat_id,
                    message_id,
                    media_type,
                    exc,
                )

    @staticmethod
    def _split_media_caption(text: str) -> tuple[str | None, str | None]:
        trimmed = str(text or "").strip()
        if not trimmed:
            return None, None
        if len(trimmed) > MAX_CAPTION_LEN:
            return None, trimmed
        return trimmed, None

    @staticmethod
    def _normalize_outbound_parse_mode(metadata: dict[str, Any]) -> str:
        raw_value = metadata.get("_telegram_parse_mode")
        if raw_value is None:
            raw_value = metadata.get("telegram_parse_mode")
        if raw_value is None:
            raw_value = metadata.get("parse_mode")
        normalized = str(raw_value or "").strip().lower()
        aliases = {
            "": "markdown",
            "default": "markdown",
            "markdown": "markdown",
            "markdownv2": "markdown",
            "md": "markdown",
            "html": "html",
            "raw_html": "html",
            "plain": "plain",
            "text": "plain",
            "none": "plain",
        }
        return aliases.get(normalized, "markdown")

    @staticmethod
    def _render_outbound_text(text: str, *, parse_mode: str) -> tuple[str, str | None]:
        if parse_mode == "html":
            return text, "HTML"
        if parse_mode == "plain":
            return text, None
        return markdown_to_telegram_html(text), "HTML"

    @staticmethod
    def _normalize_outbound_media_items(
        metadata: dict[str, Any],
    ) -> list[dict[str, Any]]:
        media_source = metadata.get("_telegram_media")
        if media_source is None:
            media_source = metadata.get("telegram_media")
        if media_source is None:
            media_source = metadata.get("media")
        if media_source is None:
            return []

        if isinstance(media_source, dict):
            media_items = [media_source]
        elif isinstance(media_source, list):
            media_items = media_source
        else:
            raise ValueError("telegram media must be an object or list of objects")

        allowed_types = {
            "animation",
            "audio",
            "document",
            "photo",
            "sticker",
            "video",
            "video_note",
            "voice",
        }
        normalized: list[dict[str, Any]] = []
        for index, raw_item in enumerate(media_items, start=1):
            if not isinstance(raw_item, dict):
                raise ValueError("telegram media items must be objects")
            media_type = str(raw_item.get("type", "") or "").strip().lower()
            if media_type not in allowed_types:
                raise ValueError(f"telegram media item {index} has invalid type")

            file_id = str(raw_item.get("file_id", "") or "").strip()
            url = str(raw_item.get("url", "") or "").strip()
            path = str(raw_item.get("path", "") or "").strip()
            value = raw_item.get(
                "source", raw_item.get("value", raw_item.get("payload"))
            )

            item: dict[str, Any] = {"type": media_type}
            if path:
                item["path"] = path
                filename = (
                    str(raw_item.get("filename", "") or "").strip() or Path(path).name
                )
                if filename:
                    item["filename"] = filename
            elif file_id:
                item["payload"] = file_id
            elif url:
                item["payload"] = url
            elif value is not None:
                item["payload"] = value
                filename = str(raw_item.get("filename", "") or "").strip()
                if filename:
                    item["filename"] = filename
            else:
                raise ValueError(
                    f"telegram media item {index} requires file_id, url, path, source, value, or payload"
                )
            normalized.append(item)
        return normalized

    async def _resolve_outbound_media_payload(self, item: dict[str, Any]) -> Any:
        path_value = str(item.get("path", "") or "").strip()
        if path_value:
            path = Path(path_value).expanduser()
            try:
                payload_bytes = await asyncio.to_thread(path.read_bytes)
            except OSError as exc:
                raise ValueError(f"telegram media path unreadable: {path}") from exc
            from telegram import InputFile

            filename = (
                str(item.get("filename", "") or "").strip()
                or path.name
                or f"{item['type']}.bin"
            )
            return InputFile(payload_bytes, filename=filename)

        payload = item.get("payload")
        if isinstance(payload, bytearray):
            payload = bytes(payload)
        if isinstance(payload, bytes):
            from telegram import InputFile

            filename = (
                str(item.get("filename", "") or "").strip() or f"{item['type']}.bin"
            )
            return InputFile(payload, filename=filename)
        return payload

    @staticmethod
    def _resolve_media_sender(bot: Any, media_type: str) -> tuple[Any, str]:
        mapping = {
            "animation": ("send_animation", "animation"),
            "audio": ("send_audio", "audio"),
            "document": ("send_document", "document"),
            "photo": ("send_photo", "photo"),
            "sticker": ("send_sticker", "sticker"),
            "video": ("send_video", "video"),
            "video_note": ("send_video_note", "video_note"),
            "voice": ("send_voice", "voice"),
        }
        method_name, payload_key = mapping[media_type]
        sender = getattr(bot, method_name, None)
        if not callable(sender):
            raise ValueError(f"telegram:action_unsupported:{media_type}")
        return sender, payload_key

    async def _send_text_chunks(
        self,
        *,
        chat_id: str,
        text: str,
        outbound_parse_mode: str,
        reply_to_message_id: int | None,
        thread_state: dict[str, int | None],
        reply_markup: Any | None,
        message_ids: list[int],
    ) -> int:
        chunks = split_message(text)
        policy = self._send_retry_policy.normalized()

        def _remember_message_id(result: Any) -> None:
            if result is None:
                return
            raw_message_id = getattr(result, "message_id", None)
            try:
                message_id = int(raw_message_id)
            except (TypeError, ValueError):
                return
            if message_id > 0:
                message_ids.append(message_id)

        for idx, chunk in enumerate(chunks, start=1):
            payload_text, payload_parse_mode = self._render_outbound_text(
                chunk, parse_mode=outbound_parse_mode
            )
            formatting_fallback_used = False

            for attempt in range(1, policy.max_attempts + 1):
                self._sync_auth_breaker_signal_transition(
                    breaker=self._send_auth_breaker, key_prefix="send"
                )
                if self._send_auth_breaker.is_open:
                    raise TelegramCircuitOpenError("telegram auth circuit is open")
                active_thread_id = self._normalize_api_message_thread_id(
                    chat_id=chat_id,
                    message_thread_id=thread_state.get("message_thread_id"),
                )
                try:
                    payload: dict[str, Any] = {
                        "chat_id": chat_id,
                        "text": payload_text,
                        "parse_mode": payload_parse_mode,
                        "reply_to_message_id": reply_to_message_id,
                    }
                    if reply_markup is not None:
                        payload["reply_markup"] = reply_markup
                    if active_thread_id is not None:
                        payload["message_thread_id"] = active_thread_id
                    send_result = await asyncio.wait_for(
                        self.bot.send_message(**payload),
                        timeout=max(1.0, float(self.send_timeout_s)),
                    )
                    _remember_message_id(send_result)
                    self._on_send_auth_success()
                    break
                except TypeError as exc:
                    if active_thread_id is None or "message_thread_id" not in str(exc):
                        raise
                    thread_state["message_thread_id"] = None
                    send_result = await asyncio.wait_for(
                        self.bot.send_message(
                            chat_id=chat_id,
                            text=payload_text,
                            parse_mode=payload_parse_mode,
                            reply_to_message_id=reply_to_message_id,
                            reply_markup=reply_markup,
                        ),
                        timeout=max(1.0, float(self.send_timeout_s)),
                    )
                    _remember_message_id(send_result)
                    self._on_send_auth_success()
                    break
                except Exception as exc:
                    if (
                        payload_parse_mode
                        and not formatting_fallback_used
                        and _is_formatting_error(exc)
                    ):
                        payload_text = chunk
                        payload_parse_mode = None
                        formatting_fallback_used = True
                        continue
                    if (
                        active_thread_id is not None
                        and self._threadless_retry_allowed(chat_id=chat_id)
                        and _is_thread_not_found_error(exc)
                    ):
                        logger.warning(
                            "telegram outbound thread not found chat={} chunk={}/{}; retrying without message_thread_id",
                            chat_id,
                            idx,
                            len(chunks),
                        )
                        thread_state["message_thread_id"] = None
                        continue

                    if _is_auth_failure(exc):
                        self._on_send_auth_failure()
                        raise

                    logger.error(
                        "telegram outbound failed chat={} chunk={}/{} attempt={}/{} error={}",
                        chat_id,
                        idx,
                        len(chunks),
                        attempt,
                        policy.max_attempts,
                        exc,
                    )
                    if attempt >= policy.max_attempts or not _is_transient_failure(exc):
                        raise

                    self._signals["send_retry_count"] += 1
                    delay_s = _retry_after_delay_s(exc)
                    if delay_s is None:
                        delay_s = _retry_delay_s(policy, attempt)
                    else:
                        self._signals["send_retry_after_count"] += 1
                    if delay_s > 0:
                        await asyncio.sleep(delay_s)
        return len(chunks)

    async def _send_media_items(
        self,
        *,
        chat_id: str,
        items: list[dict[str, Any]],
        caption_text: str | None,
        outbound_parse_mode: str,
        reply_to_message_id: int | None,
        thread_state: dict[str, int | None],
        reply_markup: Any | None,
        message_ids: list[int],
    ) -> int:
        policy = self._send_retry_policy.normalized()
        caption_index: int | None = None
        if caption_text:
            for idx, item in enumerate(items, start=1):
                if self._media_type_supports_caption(
                    str(item.get("type", "") or "").strip()
                ):
                    caption_index = idx
                    break

        def _remember_message_id(result: Any) -> None:
            if result is None:
                return
            raw_message_id = getattr(result, "message_id", None)
            try:
                message_id = int(raw_message_id)
            except (TypeError, ValueError):
                return
            if message_id > 0:
                message_ids.append(message_id)

        for idx, item in enumerate(items, start=1):
            sender, payload_key = self._resolve_media_sender(
                self.bot, str(item["type"])
            )
            raw_caption = caption_text if idx == caption_index else None
            if raw_caption:
                caption_payload, caption_parse_mode = self._render_outbound_text(
                    raw_caption,
                    parse_mode=outbound_parse_mode,
                )
            else:
                caption_payload, caption_parse_mode = None, None
            formatting_fallback_used = False

            for attempt in range(1, policy.max_attempts + 1):
                self._sync_auth_breaker_signal_transition(
                    breaker=self._send_auth_breaker, key_prefix="send"
                )
                if self._send_auth_breaker.is_open:
                    raise TelegramCircuitOpenError("telegram auth circuit is open")
                active_thread_id = self._normalize_api_message_thread_id(
                    chat_id=chat_id,
                    message_thread_id=thread_state.get("message_thread_id"),
                )
                try:
                    media_payload = await self._resolve_outbound_media_payload(item)
                    payload: dict[str, Any] = {
                        "chat_id": chat_id,
                        payload_key: media_payload,
                    }
                    if idx == 1 and reply_to_message_id is not None:
                        payload["reply_to_message_id"] = reply_to_message_id
                    if idx == 1 and reply_markup is not None:
                        payload["reply_markup"] = reply_markup
                    if active_thread_id is not None:
                        payload["message_thread_id"] = active_thread_id
                    if caption_payload is not None:
                        payload["caption"] = caption_payload
                        payload["parse_mode"] = caption_parse_mode
                    send_result = await asyncio.wait_for(
                        sender(**payload),
                        timeout=max(1.0, float(self.send_timeout_s)),
                    )
                    _remember_message_id(send_result)
                    self._on_send_auth_success()
                    break
                except TypeError as exc:
                    if active_thread_id is None or "message_thread_id" not in str(exc):
                        raise
                    thread_state["message_thread_id"] = None
                    media_payload = await self._resolve_outbound_media_payload(item)
                    payload = {
                        "chat_id": chat_id,
                        payload_key: media_payload,
                    }
                    if idx == 1 and reply_to_message_id is not None:
                        payload["reply_to_message_id"] = reply_to_message_id
                    if idx == 1 and reply_markup is not None:
                        payload["reply_markup"] = reply_markup
                    if caption_payload is not None:
                        payload["caption"] = caption_payload
                        payload["parse_mode"] = caption_parse_mode
                    send_result = await asyncio.wait_for(
                        sender(**payload),
                        timeout=max(1.0, float(self.send_timeout_s)),
                    )
                    _remember_message_id(send_result)
                    self._on_send_auth_success()
                    break
                except Exception as exc:
                    if (
                        caption_parse_mode
                        and not formatting_fallback_used
                        and _is_formatting_error(exc)
                    ):
                        caption_payload = raw_caption
                        caption_parse_mode = None
                        formatting_fallback_used = True
                        continue
                    if (
                        active_thread_id is not None
                        and self._threadless_retry_allowed(chat_id=chat_id)
                        and _is_thread_not_found_error(exc)
                    ):
                        logger.warning(
                            "telegram outbound media thread not found chat={} media={}/{} type={}; retrying without message_thread_id",
                            chat_id,
                            idx,
                            len(items),
                            item["type"],
                        )
                        thread_state["message_thread_id"] = None
                        continue

                    if _is_auth_failure(exc):
                        self._on_send_auth_failure()
                        raise

                    logger.error(
                        "telegram outbound media failed chat={} media={}/{} type={} attempt={}/{} error={}",
                        chat_id,
                        idx,
                        len(items),
                        item["type"],
                        attempt,
                        policy.max_attempts,
                        exc,
                    )
                    if attempt >= policy.max_attempts or not _is_transient_failure(exc):
                        raise

                    self._signals["send_retry_count"] += 1
                    delay_s = _retry_after_delay_s(exc)
                    if delay_s is None:
                        delay_s = _retry_delay_s(policy, attempt)
                    else:
                        self._signals["send_retry_after_count"] += 1
                    if delay_s > 0:
                        await asyncio.sleep(delay_s)
        return len(items)

    async def _send_start_message(self, *, chat_id: str) -> None:
        await self.send(
            target=chat_id,
            text=(
                "Hi! I am ClawLite.\\n\\n"
                "Send a message to start.\\n"
                "Commands: /help, /stop"
            ),
        )

    async def _send_help_message(self, *, chat_id: str) -> None:
        await self.send(
            target=chat_id,
            text=(
                "ClawLite commands:\\n/help - Show this help\\n/stop - Stop active task"
            ),
        )

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._webhook_mode_active = False
        self._startup_drop_done = False
        logger.info("telegram channel starting mode={}", self.mode)
        if self._webhook_requested():
            activated = await self._activate_webhook_mode()
            if activated:
                return
            self._signals["webhook_fallback_to_polling_count"] += 1
            logger.warning("telegram webhook requested but falling back to polling")
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        self._running = False
        await self._stop_all_typing_keepalive()
        await self._flush_all_media_groups()
        if self._webhook_mode_active:
            await self._try_delete_webhook(reason="webhook_stop")
        await cancel_task(self._task)
        pending_dedupe_persist_task = self._dedupe_persist_task
        self._dedupe_persist_task = None
        await cancel_task(pending_dedupe_persist_task)
        try:
            await self._persist_update_dedupe_state()
        except Exception as exc:
            logger.debug("telegram dedupe state shutdown persist failed error={}", exc)
        self._dedupe_persist_task = None
        self._task = None
        self._webhook_mode_active = False
        self._connected = False
        self._startup_drop_done = False
        logger.info("telegram channel stopped")

    async def handle_webhook_update(self, payload: dict[str, Any]) -> bool:
        if not isinstance(payload, dict):
            self._signals["webhook_update_parse_error_count"] += 1
            return False

        self._signals["webhook_update_received_count"] += 1
        self._refresh_update_dedupe_state()
        normalized = self._normalize_webhook_payload(payload)
        dedupe_key = self._build_update_dedupe_key(normalized)
        update_id = self._coerce_update_id(self._field(normalized, "update_id"))

        if update_id is not None and self._is_stale_offset_update(update_id):
            self._signals["webhook_stale_update_skip_count"] += 1
            self._signals["update_duplicate_skip_count"] += 1
            self._signals["webhook_update_duplicate_count"] += 1
            return False

        # Check committed deduplication first (permanent after success).
        if dedupe_key and self._is_duplicate_update_dedupe_key(
            dedupe_key, source="webhook"
        ):
            if update_id is not None:
                should_record, tracked_pending = self._webhook_offset_completion_policy(
                    update_id
                )
                if should_record:
                    self._complete_safe_offset_update(
                        update_id,
                        tracked_pending=tracked_pending,
                    )
            return False

        # Check in-flight set to prevent TOCTOU: two concurrent webhook coroutines
        # could both pass the committed-dedupe check and process the same update.
        # The in-flight key is cleared on failure so retries remain possible.
        if dedupe_key and dedupe_key in self._inflight_update_keys:
            self._signals["update_duplicate_skip_count"] += 1
            self._signals["webhook_update_duplicate_count"] += 1
            return False
        if dedupe_key:
            self._inflight_update_keys.add(dedupe_key)

        try:
            item = self._to_namespace(normalized)
        except Exception:
            self._signals["webhook_update_parse_error_count"] += 1
            if dedupe_key:
                self._inflight_update_keys.discard(dedupe_key)
            return False

        try:
            if update_id is not None and self._should_begin_webhook_offset_tracking(
                update_id
            ):
                self._begin_safe_offset_update(update_id)
            processed = bool(await self._handle_update(item))
            if processed and dedupe_key:
                self._commit_update_dedupe_key(dedupe_key, schedule_persist=False)
                await self._persist_update_dedupe_state()
            if processed and update_id is not None:
                should_record, tracked_pending = self._webhook_offset_completion_policy(
                    update_id
                )
                if should_record:
                    self._complete_safe_offset_update(
                        update_id,
                        tracked_pending=tracked_pending,
                    )
            return processed
        except Exception as exc:
            self._last_error = str(exc)
            logger.warning("telegram webhook update processing failed error={}", exc)
            return False
        finally:
            if dedupe_key:
                self._inflight_update_keys.discard(dedupe_key)

    async def send(
        self, *, target: str, text: str, metadata: dict[str, Any] | None = None
    ) -> str:
        chat_id, target_thread_id = self._parse_target(str(target))
        if not chat_id:
            raise ValueError("telegram target(chat_id) is required")
        caller_metadata = metadata if isinstance(metadata, dict) else None
        metadata_payload = dict(caller_metadata or {})
        action = (
            str(
                metadata_payload.get(
                    "_telegram_action", metadata_payload.get("telegram_action", "send")
                )
                or "send"
            )
            .strip()
            .lower()
        )
        if action not in {"send", "reply", "edit", "delete", "react", "create_topic"}:
            action = "send"

        if self.bot is None:
            from telegram import Bot

            self.bot = Bot(token=self.token)

        action_message_id = metadata_payload.get(
            "_telegram_action_message_id",
            metadata_payload.get(
                "telegram_action_message_id", metadata_payload.get("message_id")
            ),
        )
        try:
            action_message_id = (
                int(action_message_id) if action_message_id is not None else None
            )
        except (TypeError, ValueError):
            action_message_id = None

        action_emoji = str(
            metadata_payload.get(
                "_telegram_action_emoji",
                metadata_payload.get(
                    "telegram_action_emoji", metadata_payload.get("emoji", "")
                ),
            )
            or ""
        ).strip()
        action_topic_name = str(
            metadata_payload.get(
                "_telegram_action_topic_name",
                metadata_payload.get(
                    "telegram_action_topic_name", metadata_payload.get("topic_name", "")
                ),
            )
            or ""
        ).strip()
        action_topic_icon_custom_emoji_id = str(
            metadata_payload.get(
                "_telegram_action_topic_icon_custom_emoji_id",
                metadata_payload.get("telegram_action_topic_icon_custom_emoji_id", ""),
            )
            or ""
        ).strip()
        action_topic_icon_color = metadata_payload.get(
            "_telegram_action_topic_icon_color",
            metadata_payload.get("telegram_action_topic_icon_color"),
        )
        try:
            action_topic_icon_color = (
                int(action_topic_icon_color)
                if action_topic_icon_color is not None
                else None
            )
        except (TypeError, ValueError):
            action_topic_icon_color = None

        if action == "edit":
            if action_message_id is None:
                raise ValueError("telegram action edit requires message_id")
            if not str(text or "").strip():
                raise ValueError("telegram action edit requires non-empty text")
            if not hasattr(self.bot, "edit_message_text"):
                raise ValueError("telegram:action_unsupported:edit")
            payload_text = markdown_to_telegram_html(text)
            payload_parse_mode: str | None = "HTML"
            try:
                await self.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=action_message_id,
                    text=payload_text,
                    parse_mode=payload_parse_mode,
                )
            except Exception as exc:
                if not _is_formatting_error(exc):
                    raise
                await self.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=action_message_id,
                    text=html.escape(text, quote=False),
                    parse_mode=None,
                )
            self._signals["action_edit_count"] += 1
            return f"telegram:edited:{action_message_id}"

        if action == "delete":
            if action_message_id is None:
                raise ValueError("telegram action delete requires message_id")
            if not hasattr(self.bot, "delete_message"):
                raise ValueError("telegram:action_unsupported:delete")
            await self.bot.delete_message(chat_id=chat_id, message_id=action_message_id)
            self._signals["action_delete_count"] += 1
            return f"telegram:deleted:{action_message_id}"

        if action == "react":
            if action_message_id is None:
                raise ValueError("telegram action react requires message_id")
            if not action_emoji:
                raise ValueError("telegram action react requires emoji")
            if not hasattr(self.bot, "set_message_reaction"):
                raise ValueError("telegram:action_unsupported:react")
            await self.bot.set_message_reaction(
                chat_id=chat_id,
                message_id=action_message_id,
                reaction=[{"type": "emoji", "emoji": action_emoji}],
            )
            self._signals["action_react_count"] += 1
            return f"telegram:reacted:{action_message_id}"

        if action == "create_topic":
            if not action_topic_name:
                raise ValueError("telegram action create_topic requires topic_name")
            if not hasattr(self.bot, "create_forum_topic"):
                raise ValueError("telegram:action_unsupported:create_topic")
            payload: dict[str, Any] = {"chat_id": chat_id, "name": action_topic_name}
            if action_topic_icon_color is not None:
                payload["icon_color"] = action_topic_icon_color
            if action_topic_icon_custom_emoji_id:
                payload["icon_custom_emoji_id"] = action_topic_icon_custom_emoji_id
            topic_result = await self.bot.create_forum_topic(**payload)
            thread_id = (
                self._coerce_thread_id(getattr(topic_result, "message_thread_id", None))
                or 0
            )
            self._signals["action_create_topic_count"] += 1
            return f"telegram:topic_created:{thread_id}"

        if (
            action == "reply"
            and metadata_payload.get("reply_to_message_id") is None
            and action_message_id is not None
        ):
            metadata_payload["reply_to_message_id"] = action_message_id
        message_thread_id = self._normalize_api_message_thread_id(
            chat_id=chat_id,
            message_thread_id=metadata_payload.get(
                "message_thread_id", target_thread_id
            ),
        )
        thread_state: dict[str, int | None] = {"message_thread_id": message_thread_id}
        await self._stop_typing_keepalive(
            chat_id=chat_id, message_thread_id=message_thread_id
        )
        reply_to_message_id = metadata_payload.get(
            "reply_to_message_id", metadata_payload.get("message_id")
        )
        try:
            reply_to_message_id = (
                int(reply_to_message_id) if reply_to_message_id is not None else None
            )
        except (TypeError, ValueError):
            reply_to_message_id = None
        message_ids: list[int] = []
        reply_markup = self._build_inline_keyboard_reply_markup(metadata_payload)
        media_items = self._normalize_outbound_media_items(metadata_payload)
        outbound_parse_mode = self._normalize_outbound_parse_mode(metadata_payload)
        total_messages = 0
        if media_items:
            caption_text, follow_up_text = self._split_media_caption(text)
            if caption_text and not any(
                self._media_type_supports_caption(
                    str(item.get("type", "") or "").strip()
                )
                for item in media_items
            ):
                follow_up_text = (
                    "\n\n".join(
                        chunk
                        for chunk in (caption_text, follow_up_text)
                        if isinstance(chunk, str) and chunk.strip()
                    )
                    or None
                )
                caption_text = None
            total_messages += await self._send_media_items(
                chat_id=chat_id,
                items=media_items,
                caption_text=caption_text,
                outbound_parse_mode=outbound_parse_mode,
                reply_to_message_id=reply_to_message_id,
                thread_state=thread_state,
                reply_markup=None if follow_up_text else reply_markup,
                message_ids=message_ids,
            )
            if follow_up_text:
                total_messages += await self._send_text_chunks(
                    chat_id=chat_id,
                    text=follow_up_text,
                    outbound_parse_mode=outbound_parse_mode,
                    reply_to_message_id=None,
                    thread_state=thread_state,
                    reply_markup=reply_markup,
                    message_ids=message_ids,
                )
        else:
            total_messages += await self._send_text_chunks(
                chat_id=chat_id,
                text=text,
                outbound_parse_mode=outbound_parse_mode,
                reply_to_message_id=reply_to_message_id,
                thread_state=thread_state,
                reply_markup=reply_markup,
                message_ids=message_ids,
            )
        if caller_metadata is not None:
            receipt: dict[str, Any] = {
                "channel": "telegram",
                "chat_id": chat_id,
                "chunks": total_messages,
                "message_ids": list(message_ids),
                "last_message_id": message_ids[-1] if message_ids else 0,
            }
            final_thread_id = self._normalize_api_message_thread_id(
                chat_id=chat_id,
                message_thread_id=thread_state.get("message_thread_id"),
            )
            if final_thread_id is not None:
                receipt["message_thread_id"] = final_thread_id
            if media_items:
                receipt["media_count"] = len(media_items)
                receipt["media_types"] = [str(item["type"]) for item in media_items]
            caller_metadata["_delivery_receipt"] = receipt
        if message_ids:
            self._remember_own_sent_message_ids(
                chat_id=chat_id, message_ids=message_ids
            )
        logger.info(
            "telegram outbound sent chat={} chunks={} chars={}",
            chat_id,
            total_messages,
            len(text),
        )
        return f"telegram:sent:{total_messages}"

    def _build_inline_keyboard_reply_markup(
        self, metadata: dict[str, Any]
    ) -> Any | None:
        keyboard_source = metadata.get("_telegram_inline_keyboard")
        if keyboard_source is None:
            keyboard_source = metadata.get("telegram_inline_keyboard")
        if keyboard_source is None:
            return None
        if not isinstance(keyboard_source, list):
            logger.debug(
                "telegram outbound inline keyboard ignored reason=invalid_root_type"
            )
            return None

        inline_keyboard_rows: list[list[dict[str, str]]] = []
        for row in keyboard_source:
            if not isinstance(row, list):
                logger.debug(
                    "telegram outbound inline keyboard ignored reason=invalid_row_type"
                )
                return None
            inline_row: list[dict[str, str]] = []
            for button in row:
                if not isinstance(button, dict):
                    logger.debug(
                        "telegram outbound inline keyboard ignored reason=invalid_button_type"
                    )
                    return None
                text = str(button.get("text", "") or "").strip()
                callback_data = button.get("callback_data")
                url = button.get("url")
                if not text:
                    logger.debug(
                        "telegram outbound inline keyboard ignored reason=missing_button_text"
                    )
                    return None
                if bool(callback_data) == bool(url):
                    logger.debug(
                        "telegram outbound inline keyboard ignored reason=invalid_button_action"
                    )
                    return None
                inline_button: dict[str, str] = {"text": text}
                if callback_data:
                    callback_raw = str(callback_data)
                    if self._callback_signing_active:
                        callback_raw = self._callback_sign_payload(callback_raw)
                    inline_button["callback_data"] = callback_raw
                if url:
                    inline_button["url"] = str(url)
                inline_row.append(inline_button)
            if inline_row:
                inline_keyboard_rows.append(inline_row)

        if not inline_keyboard_rows:
            logger.debug(
                "telegram outbound inline keyboard ignored reason=empty_keyboard"
            )
            return None

        try:
            from telegram import InlineKeyboardButton
            from telegram import InlineKeyboardMarkup

            telegram_rows = [
                [InlineKeyboardButton(**button) for button in row]
                for row in inline_keyboard_rows
            ]
            return InlineKeyboardMarkup(telegram_rows)
        except Exception:
            return {"inline_keyboard": inline_keyboard_rows}
