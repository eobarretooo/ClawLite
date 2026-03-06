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
from clawlite.config.schema import TelegramChannelConfig

MAX_MESSAGE_LEN = 4000
TELEGRAM_ALLOWED_UPDATES = [
    "message",
    "edited_message",
    "callback_query",
    "message_reaction",
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
    from_parameters = _coerce_retry_after_seconds(getattr(parameters, "retry_after", None))
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


def markdown_to_telegram_html(text: str) -> str:
    if not text:
        return ""

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
    text = re.sub(r"^[-*]\s+", "• ", text, flags=re.MULTILINE)

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
        self.dm_allow_from = self._normalize_allow_from_values(telegram_config.dm_allow_from)
        self.group_allow_from = self._normalize_allow_from_values(telegram_config.group_allow_from)
        self.topic_allow_from = self._normalize_allow_from_values(telegram_config.topic_allow_from)
        self.group_overrides = {
            str(key): dict(value)
            for key, value in telegram_config.group_overrides.items()
            if isinstance(value, dict)
        }
        self.bot: Any | None = None
        self.mode = self._normalize_mode(str(config.get("mode", "polling") or "polling"))
        self.webhook_enabled = bool(config.get("webhook_enabled", config.get("webhookEnabled", False)))
        self.webhook_secret = str(config.get("webhook_secret", config.get("webhookSecret", "")) or "").strip()
        self.webhook_path = self._normalize_webhook_path(
            str(config.get("webhook_path", config.get("webhookPath", "/api/webhooks/telegram")) or "/api/webhooks/telegram")
        )
        self.webhook_url = str(config.get("webhook_url", config.get("webhookUrl", "")) or "").strip()
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
        self.send_timeout_s = float(config.get("send_timeout_s", config.get("sendTimeoutSec", 15.0)) or 15.0)
        self.send_retry_attempts = int(config.get("send_retry_attempts", config.get("sendRetryAttempts", 3)) or 3)
        self.send_backoff_base_s = float(config.get("send_backoff_base_s", config.get("sendBackoffBaseSec", 0.35)) or 0.35)
        self.send_backoff_max_s = float(config.get("send_backoff_max_s", config.get("sendBackoffMaxSec", 8.0)) or 8.0)
        self.send_backoff_jitter = float(config.get("send_backoff_jitter", config.get("sendBackoffJitter", 0.2)) or 0.2)
        self.send_circuit_failure_threshold = int(
            config.get("send_circuit_failure_threshold", config.get("sendCircuitFailureThreshold", 1)) or 1
        )
        self.send_circuit_cooldown_s = float(config.get("send_circuit_cooldown_s", config.get("sendCircuitCooldownSec", 60.0)) or 60.0)
        self.typing_enabled = bool(config.get("typing_enabled", config.get("typingEnabled", True)))
        self.typing_interval_s = float(config.get("typing_interval_s", config.get("typingIntervalS", 2.5)) or 2.5)
        self.typing_max_ttl_s = float(config.get("typing_max_ttl_s", config.get("typingMaxTtlS", 120.0)) or 120.0)
        self.typing_timeout_s = float(config.get("typing_timeout_s", config.get("typingTimeoutS", 5.0)) or 5.0)
        self.typing_circuit_failure_threshold = int(
            config.get("typing_circuit_failure_threshold", config.get("typingCircuitFailureThreshold", 1)) or 1
        )
        self.typing_circuit_cooldown_s = float(
            config.get("typing_circuit_cooldown_s", config.get("typingCircuitCooldownS", 60.0)) or 60.0
        )
        self.reaction_notifications = self._normalize_reaction_notifications(
            str(config.get("reaction_notifications", config.get("reactionNotifications", "own")) or "own")
        )
        self.reaction_own_cache_limit = max(
            1,
            int(config.get("reaction_own_cache_limit", config.get("reactionOwnCacheLimit", 4096)) or 4096),
        )
        self.dedupe_state_path = self._normalize_state_path(
            str(getattr(telegram_config, "dedupe_state_path", "") or "")
        )
        self.callback_signing_enabled = bool(getattr(telegram_config, "callback_signing_enabled", False))
        self.callback_signing_secret = str(getattr(telegram_config, "callback_signing_secret", "") or "")
        self.callback_require_signed = bool(getattr(telegram_config, "callback_require_signed", False))
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
        self.drop_pending_updates = bool(config.get("drop_pending_updates", config.get("dropPendingUpdates", True)))
        self.handle_commands = bool(config.get("handle_commands", config.get("handleCommands", True)))
        self._task: asyncio.Task[Any] | None = None
        self._typing_tasks: dict[str, asyncio.Task[Any]] = {}
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
            "offset_persist_error_count": 0,
            "offset_load_error_count": 0,
            "message_reaction_received_count": 0,
            "message_reaction_ignored_bot_count": 0,
            "message_reaction_blocked_count": 0,
            "message_reaction_emitted_count": 0,
            "policy_blocked_count": 0,
            "policy_allowed_count": 0,
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
        self._dedupe_persist_task: asyncio.Task[Any] | None = None
        self._own_sent_message_keys: set[tuple[str, int]] = set()
        self._own_sent_message_order: deque[tuple[str, int]] = deque()
        self._message_signatures: dict[tuple[str, int], str] = {}
        self._signature_limit = 4096
        self._send_auth_breaker_seen_open = False
        self._typing_auth_breaker_seen_open = False
        self._load_update_dedupe_state()

    @staticmethod
    def _normalize_state_path(raw: str) -> Path:
        value = str(raw or "").strip()
        if not value:
            return Path.home() / ".clawlite" / "state" / "telegram-dedupe.json"
        return Path(value).expanduser()

    @property
    def _callback_signing_active(self) -> bool:
        return self.callback_signing_enabled and bool(self.callback_signing_secret)

    def _session_id_for_chat(self, *, chat_id: str, chat_type: str = "", message_thread_id: int | None = None) -> str:
        normalized_chat_id = str(chat_id or "").strip()
        thread_id = self._coerce_thread_id(message_thread_id)
        normalized_chat_type = str(chat_type or "").strip().lower()
        if normalized_chat_type == "supergroup" and thread_id is not None:
            return f"telegram:{normalized_chat_id}:topic:{thread_id}"
        return f"telegram:{normalized_chat_id}"

    def _dedupe_state_payload(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
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
            logger.warning("telegram dedupe state load failed path={} error={}", path, exc)

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
            logger.debug("telegram dedupe state persist failed path={} error={}", path, exc)
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
        if self._dedupe_persist_task is not None and not self._dedupe_persist_task.done():
            return
        self._dedupe_persist_task = loop.create_task(self._persist_update_dedupe_state())

    def _callback_sign_payload(self, callback_data: str) -> str:
        nonce = base64.urlsafe_b64encode(secrets.token_bytes(6)).decode("ascii").rstrip("=")
        data = str(callback_data or "")
        encoded_data = base64.urlsafe_b64encode(data.encode("utf-8")).decode("ascii").rstrip("=")
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
        if not nonce or not encoded_data or not provided_signature or not self.callback_signing_secret:
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
        expected_signature = base64.urlsafe_b64encode(digest[:12]).decode("ascii").rstrip("=")
        if not hmac.compare_digest(expected_signature, provided_signature):
            return False, "", True
        return True, decoded_data, True

    def _sync_auth_breaker_signal_transition(self, *, breaker: TelegramAuthCircuitBreaker, key_prefix: str) -> None:
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
        self._sync_auth_breaker_signal_transition(breaker=self._send_auth_breaker, key_prefix="send")

    def _on_typing_auth_failure(self) -> None:
        was_open = self._typing_auth_breaker.is_open
        self._typing_auth_breaker.on_auth_failure()
        if not was_open and self._typing_auth_breaker.is_open:
            self._signals["typing_auth_breaker_open_count"] += 1
            self._typing_auth_breaker_seen_open = True

    def _on_typing_auth_success(self) -> None:
        self._typing_auth_breaker.on_success()
        self._sync_auth_breaker_signal_transition(breaker=self._typing_auth_breaker, key_prefix="typing")

    def signals(self) -> dict[str, Any]:
        self._sync_auth_breaker_signal_transition(breaker=self._send_auth_breaker, key_prefix="send")
        self._sync_auth_breaker_signal_transition(breaker=self._typing_auth_breaker, key_prefix="typing")
        return {
            **self._signals,
            "send_auth_breaker_open": self._send_auth_breaker.is_open,
            "typing_auth_breaker_open": self._typing_auth_breaker.is_open,
            "typing_keepalive_active": len(self._typing_tasks),
            "webhook_mode_active": self._webhook_mode_active,
        }

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
            return SimpleNamespace(**{key: TelegramChannel._to_namespace(item) for key, item in value.items()})
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

        callback_query = self._field(update, "callback_query")
        callback_query_id = str(self._field(callback_query, "id") or "").strip()
        if callback_query_id:
            return f"callback:{callback_query_id}"

        for field_name, is_edit in (
            ("message", False),
            ("edited_message", True),
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

    def _commit_update_dedupe_key(self, dedupe_key: str) -> None:
        key = str(dedupe_key or "").strip()
        if not key or key in self._seen_update_keys:
            return
        self._seen_update_keys.add(key)
        self._seen_update_order.append(key)
        while len(self._seen_update_order) > self._update_dedupe_limit:
            oldest = self._seen_update_order.popleft()
            self._seen_update_keys.discard(oldest)
        self._schedule_dedupe_state_persist()

    def _remember_update_dedupe_key(self, dedupe_key: str, *, source: str) -> bool:
        if self._is_duplicate_update_dedupe_key(dedupe_key, source=source):
            return False
        self._commit_update_dedupe_key(dedupe_key)
        return True

    async def _ensure_bot(self) -> Any:
        if self.bot is not None:
            return self.bot
        from telegram import Bot  # lazy import for environments without dependency during tests

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
                logger.warning("telegram webhook delete failed reason={} error={}", reason, exc)
                return False
            try:
                await bot.delete_webhook()
                self._signals["webhook_delete_count"] += 1
                logger.info("telegram webhook deleted reason={} legacy=true", reason)
                return True
            except Exception as legacy_exc:  # pragma: no cover
                logger.warning("telegram webhook delete failed reason={} error={}", reason, legacy_exc)
                return False
        except Exception as exc:  # pragma: no cover
            logger.warning("telegram webhook delete failed reason={} error={}", reason, exc)
            return False

    async def _activate_webhook_mode(self) -> bool:
        if not self.webhook_url or not self.webhook_secret:
            missing = []
            if not self.webhook_url:
                missing.append("webhook_url")
            if not self.webhook_secret:
                missing.append("webhook_secret")
            logger.warning("telegram webhook activation skipped missing={}", ",".join(missing))
            return False
        try:
            bot = await self._ensure_bot()
        except Exception as exc:  # pragma: no cover
            self._last_error = str(exc)
            logger.warning("telegram webhook bot init failed error={}", exc)
            return False
        if not hasattr(bot, "set_webhook"):
            logger.warning("telegram webhook activation skipped reason=bot_missing_set_webhook")
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
            logger.info("telegram connected polling=false webhook=true path={}", self.webhook_path)
            return True
        except Exception as exc:
            self._last_error = str(exc)
            logger.warning("telegram webhook activation failed error={}", exc)
            return False

    def _remember_message_signature(self, *, msg_key: tuple[str, int], signature: str) -> None:
        self._message_signatures[msg_key] = signature
        if len(self._message_signatures) > self._signature_limit:
            oldest_key = next(iter(self._message_signatures))
            self._message_signatures.pop(oldest_key, None)

    def _remember_own_sent_message_ids(self, *, chat_id: str, message_ids: list[int]) -> None:
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
    def _added_reaction_tokens(cls, *, old_reaction: Any, new_reaction: Any) -> list[str]:
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

    async def _typing_loop(self, *, chat_id: str, message_thread_id: int | None = None) -> None:
        started_at = time.monotonic()
        max_ttl_s = max(1.0, float(self.typing_max_ttl_s))
        interval_s = max(0.2, float(self.typing_interval_s))
        timeout_s = max(0.1, float(self.typing_timeout_s))
        typing_key = self._typing_key(chat_id=chat_id, message_thread_id=message_thread_id)
        try:
            while True:
                remaining_s = max_ttl_s - (time.monotonic() - started_at)
                if remaining_s <= 0:
                    self._signals["typing_ttl_stop_count"] += 1
                    return

                if self._typing_auth_breaker.is_open:
                    self._sync_auth_breaker_signal_transition(breaker=self._typing_auth_breaker, key_prefix="typing")
                    await asyncio.sleep(min(interval_s, remaining_s))
                    continue
                self._sync_auth_breaker_signal_transition(breaker=self._typing_auth_breaker, key_prefix="typing")

                bot = self.bot
                if bot is None:
                    await asyncio.sleep(min(interval_s, remaining_s))
                    continue

                try:
                    payload: dict[str, Any] = {
                        "chat_id": chat_id,
                        "action": "typing",
                    }
                    if message_thread_id is not None:
                        payload["message_thread_id"] = message_thread_id
                    await asyncio.wait_for(
                        bot.send_chat_action(**payload),
                        timeout=timeout_s,
                    )
                    self._on_typing_auth_success()
                except TypeError as exc:
                    if message_thread_id is None or "message_thread_id" not in str(exc):
                        raise
                    await asyncio.wait_for(
                        bot.send_chat_action(chat_id=chat_id, action="typing"),
                        timeout=timeout_s,
                    )
                    self._on_typing_auth_success()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    if _is_auth_failure(exc):
                        self._on_typing_auth_failure()
                    logger.debug("telegram typing keepalive failed chat={} error={}", chat_id, exc)

                remaining_s = max_ttl_s - (time.monotonic() - started_at)
                if remaining_s <= 0:
                    return
                await asyncio.sleep(min(interval_s, remaining_s))
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover
            logger.warning("telegram typing keepalive crashed chat={} error={}", chat_id, exc)
        finally:
            task = self._typing_tasks.get(typing_key)
            if task is asyncio.current_task():
                self._typing_tasks.pop(typing_key, None)
            self._typing_start_guard.discard(typing_key)

    def _start_typing_keepalive(self, *, chat_id: str, message_thread_id: int | None = None) -> None:
        if not self.typing_enabled or not self._running:
            return
        if not chat_id:
            return
        typing_key = self._typing_key(chat_id=chat_id, message_thread_id=message_thread_id)
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
                self._typing_loop(chat_id=chat_id, message_thread_id=message_thread_id)
            )
            self._typing_tasks[typing_key] = created_task
        finally:
            if created_task is None:
                self._typing_start_guard.discard(typing_key)

    async def _stop_typing_keepalive(self, *, chat_id: str, message_thread_id: int | None = None) -> None:
        typing_key = self._typing_key(chat_id=chat_id, message_thread_id=message_thread_id)
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
                self._offset = max(self._offset, int(updates[-1].update_id) + 1)
            if dropped:
                self._save_offset()
            logger.info("telegram startup pending updates dropped={} offset={}", dropped, self._offset)
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
        if policy not in {"open", "allowlist", "disabled"}:
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

    def _is_authorized_context(
        self,
        *,
        chat_type: str,
        chat_id: str,
        message_thread_id: int | None,
        user_id: str,
        username: str,
    ) -> bool:
        if not self._is_allowed_sender(user_id, username):
            return False

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
                    group_allow_from_raw = group_override.get("allow_from", group_override.get("allowFrom", []))
                    active_allow_from = self._normalize_allow_from_values(group_allow_from_raw)

                if normalized_thread_id is not None:
                    topics = group_override.get("topics")
                    if isinstance(topics, dict):
                        topic_override = topics.get(str(normalized_thread_id))
                        if isinstance(topic_override, dict):
                            topic_policy = topic_override.get("policy")
                            if topic_policy is not None:
                                active_policy = self._normalize_access_policy(topic_policy)
                            if "allow_from" in topic_override or "allowFrom" in topic_override:
                                topic_allow_from_raw = topic_override.get(
                                    "allow_from",
                                    topic_override.get("allowFrom", []),
                                )
                                active_allow_from = self._normalize_allow_from_values(topic_allow_from_raw)

        active_policy = self._normalize_access_policy(active_policy)
        if active_policy == "disabled":
            return False
        if active_policy == "open":
            return True

        if not active_allow_from:
            return False
        allowed = {item.strip() for item in active_allow_from if item.strip()}
        if not allowed:
            return False
        candidates = self._sender_candidates(user_id=user_id, username=username)
        return any(candidate in allowed for candidate in candidates)

    def _authorize_inbound_context(
        self,
        *,
        chat_type: str,
        chat_id: str,
        message_thread_id: int | None,
        user_id: str,
        username: str,
    ) -> bool:
        allowed = self._is_authorized_context(
            chat_type=chat_type,
            chat_id=chat_id,
            message_thread_id=message_thread_id,
            user_id=user_id,
            username=username,
        )
        if allowed:
            self._signals["policy_allowed_count"] += 1
        else:
            self._signals["policy_blocked_count"] += 1
        return allowed

    def _offset_path(self) -> Path:
        key = hashlib.sha256(self.token.encode("utf-8")).hexdigest()[:16]
        path = Path.home() / ".clawlite" / "state" / "telegram"
        path.mkdir(parents=True, exist_ok=True)
        return path / f"offset-{key}.json"

    def _load_offset(self) -> int:
        path = self._offset_path()
        if not path.exists():
            return 0
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                offset_raw = data.get("offset", 0)
            elif isinstance(data, int):
                offset_raw = data
            else:
                raise ValueError("offset payload must be object or int")
            offset = int(offset_raw or 0)
            return max(0, offset)
        except (json.JSONDecodeError, OSError, ValueError, TypeError) as exc:
            self._signals["offset_load_error_count"] += 1
            logger.warning("telegram offset load failed path={} error={}", path, exc)
            return 0

    def _save_offset(self) -> None:
        path = self._offset_path()
        payload = {
            "schema_version": 2,
            "offset": max(0, int(self._offset or 0)),
            "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "token_fingerprint": hashlib.sha256(self.token.encode("utf-8")).hexdigest()[:12],
        }
        tmp_path = path.with_suffix(f"{path.suffix}.tmp")
        try:
            tmp_path.write_text(json.dumps(payload), encoding="utf-8")
            tmp_path.replace(path)
        except OSError as exc:
            self._signals["offset_persist_error_count"] += 1
            logger.warning("telegram offset persist failed path={} error={}", path, exc)
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except OSError:
                pass

    async def _poll_loop(self) -> None:
        backoff = self.reconnect_initial_s
        while self._running:
            try:
                if self.bot is None:
                    await self._ensure_bot()
                    logger.info("telegram bot initialized poll_timeout_s={}", self.poll_timeout_s)
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
                    if dedupe_key and self._is_duplicate_update_dedupe_key(dedupe_key, source="polling"):
                        continue
                    update_id = self._coerce_update_id(getattr(item, "update_id", None))
                    if update_id is not None and update_id < self._offset:
                        self._signals["polling_stale_update_skip_count"] += 1
                        continue
                    processed_ok = await self._handle_update(item)
                    if not processed_ok:
                        raise RuntimeError("telegram update processing failed")
                    if dedupe_key:
                        self._commit_update_dedupe_key(dedupe_key)
                    if update_id is None:
                        continue
                    self._offset = max(self._offset, update_id + 1)
                    self._save_offset()
                await asyncio.sleep(self.poll_interval_s)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover
                self._last_error = str(exc)
                self._connected = False
                self.bot = None
                self._signals["reconnect_count"] += 1
                logger.error("telegram polling error error={} backoff_s={}", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self.reconnect_max_s)

    async def _handle_update(self, item: Any) -> bool:
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
            callback_user_id = str(getattr(callback_from_user, "id", "") or callback_chat_id)
            callback_username = str(getattr(callback_from_user, "username", "") or "").strip()
            callback_thread_id = self._coerce_thread_id(getattr(callback_message, "message_thread_id", None))

            if self.bot is not None and callback_query_id and hasattr(self.bot, "answer_callback_query"):
                try:
                    await self.bot.answer_callback_query(callback_query_id=callback_query_id)
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

            callback_valid, callback_normalized_data, callback_signed = self._callback_verify_payload(callback_data)
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
                "is_callback_query": True,
                "callback_query_id": callback_query_id,
                "callback_data": callback_data,
                "callback_signed": callback_signed,
                "callback_chat_instance": str(getattr(callback_query, "chat_instance", "") or ""),
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

            reactor = getattr(message_reaction, "user", None) or getattr(message_reaction, "from_user", None)
            reactor_user_id = str(getattr(reactor, "id", "") or chat_id)
            reactor_username = str(getattr(reactor, "username", "") or "").strip()
            reaction_thread_id = self._coerce_thread_id(getattr(message_reaction, "message_thread_id", None))
            if bool(getattr(reactor, "is_bot", False)):
                self._signals["message_reaction_ignored_bot_count"] += 1
                return True

            if self.reaction_notifications == "off":
                self._signals["message_reaction_blocked_count"] += 1
                return True

            if self.reaction_notifications == "own":
                if message_id <= 0 or (chat_id, message_id) not in self._own_sent_message_keys:
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
            reaction_added = self._added_reaction_tokens(old_reaction=old_reaction, new_reaction=new_reaction)
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
        is_edit = False
        if message is None:
            message = getattr(item, "edited_message", None)
            is_edit = message is not None
        if message is None:
            message = getattr(item, "channel_post", None)
            is_edit = False
        if message is None:
            message = getattr(item, "edited_channel_post", None)
            is_edit = message is not None
        if message is None:
            message = getattr(item, "effective_message", None)
            is_edit = bool(getattr(item, "edited_message", None))
        if message is None:
            return True

        media_info = self._extract_media_info(message)
        text = (getattr(message, "text", "") or getattr(message, "caption", "") or "").strip()
        if not text and media_info["has_media"]:
            text = self._build_media_placeholder(media_info)
        if not text:
            return True

        chat_id = str(getattr(message, "chat_id", "") or "")
        message_thread_id = self._coerce_thread_id(getattr(message, "message_thread_id", None))
        if not chat_id:
            return True
        user = getattr(message, "from_user", None)
        chat = getattr(message, "chat", None)
        chat_type = str(getattr(chat, "type", "") or "")
        user_id = str(getattr(user, "id", "") or chat_id)
        username = str(getattr(user, "username", "") or "").strip()
        if not self._authorize_inbound_context(
            chat_type=chat_type,
            chat_id=chat_id,
            message_thread_id=message_thread_id,
            user_id=user_id,
            username=username,
        ):
            logger.debug("telegram inbound blocked user={} chat={}", user_id, chat_id)
            return True

        message_id = int(getattr(message, "message_id", 0) or 0)
        signature = hashlib.sha256(text.encode("utf-8")).hexdigest()
        msg_key = (chat_id, message_id)
        previous_signature = self._message_signatures.get(msg_key)
        if previous_signature == signature:
            logger.debug("telegram inbound duplicate skipped chat={} message_id={} is_edit={}", chat_id, message_id, is_edit)
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
            command=command,
            command_args=command_args,
            media_info=media_info,
        )
        logger.info(
            "telegram inbound received chat={} user={} chars={} edit={} command={}",
            chat_id,
            user_id,
            len(text),
            is_edit,
            command or "",
        )
        self._start_typing_keepalive(chat_id=chat_id, message_thread_id=message_thread_id)
        try:
            await self.emit(session_id=session_id, user_id=user_id, text=text, metadata=metadata)
        except Exception:
            await self._stop_typing_keepalive(chat_id=chat_id, message_thread_id=message_thread_id)
            raise
        self._remember_message_signature(msg_key=msg_key, signature=signature)
        return True

    def _build_metadata(
        self,
        *,
        item: Any,
        message: Any,
        text: str,
        is_edit: bool,
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
        }
        message_thread_id = self._coerce_thread_id(getattr(message, "message_thread_id", None))
        if message_thread_id is not None:
            metadata["message_thread_id"] = message_thread_id
        if command:
            metadata["command"] = command
            metadata["command_args"] = command_args
        if reply is not None:
            metadata["reply_to_message_id"] = int(getattr(reply, "message_id", 0) or 0)
            metadata["reply_to_text"] = (
                str(getattr(reply, "text", "") or getattr(reply, "caption", "") or "")[:500]
            )
            metadata["reply_to_user_id"] = int(getattr(reply_user, "id", 0) or 0)
            metadata["reply_to_username"] = str(getattr(reply_user, "username", "") or "")
        return metadata

    def _extract_media_info(self, message: Any) -> dict[str, Any]:
        counts: dict[str, int] = {}

        photos = getattr(message, "photo", None)
        if photos:
            counts["photo"] = len(photos)

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
            if getattr(message, media_type, None) is not None:
                counts[media_type] = counts.get(media_type, 0) + 1

        media_types = sorted(counts.keys())
        total_count = sum(counts.values())
        return {
            "has_media": bool(counts),
            "types": media_types,
            "counts": counts,
            "total_count": total_count,
        }

    def _build_media_placeholder(self, media_info: dict[str, Any]) -> str:
        if not media_info.get("has_media"):
            return ""
        counts = dict(media_info.get("counts", {}))
        details = ", ".join(
            f"{media_type}({counts[media_type]})" if counts[media_type] > 1 else media_type
            for media_type in sorted(counts.keys())
        )
        if not details:
            return "[telegram media message]"
        return f"[telegram media message: {details}]"

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
                "ClawLite commands:\\n"
                "/help - Show this help\\n"
                "/stop - Stop active task"
            ),
        )

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._webhook_mode_active = False
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
        if self._webhook_mode_active:
            await self._try_delete_webhook(reason="webhook_stop")
        await cancel_task(self._task)
        await cancel_task(self._dedupe_persist_task)
        self._dedupe_persist_task = None
        self._task = None
        self._webhook_mode_active = False
        self._connected = False
        logger.info("telegram channel stopped")

    async def handle_webhook_update(self, payload: dict[str, Any]) -> bool:
        if not isinstance(payload, dict):
            self._signals["webhook_update_parse_error_count"] += 1
            return False

        self._signals["webhook_update_received_count"] += 1
        normalized = self._normalize_webhook_payload(payload)
        dedupe_key = self._build_update_dedupe_key(normalized)
        if dedupe_key and self._is_duplicate_update_dedupe_key(dedupe_key, source="webhook"):
            return False

        try:
            item = self._to_namespace(normalized)
        except Exception:
            self._signals["webhook_update_parse_error_count"] += 1
            return False

        try:
            processed = bool(await self._handle_update(item))
            if processed and dedupe_key:
                self._commit_update_dedupe_key(dedupe_key)
            return processed
        except Exception as exc:
            self._last_error = str(exc)
            logger.warning("telegram webhook update processing failed error={}", exc)
            return False

    async def send(self, *, target: str, text: str, metadata: dict[str, Any] | None = None) -> str:
        chat_id, target_thread_id = self._parse_target(str(target))
        if not chat_id:
            raise ValueError("telegram target(chat_id) is required")
        caller_metadata = metadata if isinstance(metadata, dict) else None
        metadata_payload = dict(caller_metadata or {})
        action = str(metadata_payload.get("_telegram_action", metadata_payload.get("telegram_action", "send")) or "send").strip().lower()
        if action not in {"send", "reply", "edit", "delete", "react", "create_topic"}:
            action = "send"

        if self.bot is None:
            from telegram import Bot

            self.bot = Bot(token=self.token)

        action_message_id = metadata_payload.get(
            "_telegram_action_message_id",
            metadata_payload.get("telegram_action_message_id", metadata_payload.get("message_id")),
        )
        try:
            action_message_id = int(action_message_id) if action_message_id is not None else None
        except (TypeError, ValueError):
            action_message_id = None

        action_emoji = str(
            metadata_payload.get(
                "_telegram_action_emoji",
                metadata_payload.get("telegram_action_emoji", metadata_payload.get("emoji", "")),
            )
            or ""
        ).strip()
        action_topic_name = str(
            metadata_payload.get(
                "_telegram_action_topic_name",
                metadata_payload.get("telegram_action_topic_name", metadata_payload.get("topic_name", "")),
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
            action_topic_icon_color = int(action_topic_icon_color) if action_topic_icon_color is not None else None
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
            thread_id = self._coerce_thread_id(getattr(topic_result, "message_thread_id", None)) or 0
            self._signals["action_create_topic_count"] += 1
            return f"telegram:topic_created:{thread_id}"

        if action == "reply" and metadata_payload.get("reply_to_message_id") is None and action_message_id is not None:
            metadata_payload["reply_to_message_id"] = action_message_id
        message_thread_id = self._coerce_thread_id(metadata_payload.get("message_thread_id", target_thread_id))
        await self._stop_typing_keepalive(chat_id=chat_id, message_thread_id=message_thread_id)
        chunks = split_message(text)
        policy = self._send_retry_policy.normalized()
        reply_to_message_id = metadata_payload.get("reply_to_message_id", metadata_payload.get("message_id"))
        try:
            reply_to_message_id = int(reply_to_message_id) if reply_to_message_id is not None else None
        except (TypeError, ValueError):
            reply_to_message_id = None
        message_ids: list[int] = []

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

        reply_markup = self._build_inline_keyboard_reply_markup(metadata_payload)

        for idx, chunk in enumerate(chunks, start=1):
            html_payload = markdown_to_telegram_html(chunk)
            payload_text = html_payload
            payload_parse_mode: str | None = "HTML"
            formatting_fallback_used = False

            for attempt in range(1, policy.max_attempts + 1):
                self._sync_auth_breaker_signal_transition(breaker=self._send_auth_breaker, key_prefix="send")
                if self._send_auth_breaker.is_open:
                    raise TelegramCircuitOpenError("telegram auth circuit is open")
                try:
                    payload: dict[str, Any] = {
                        "chat_id": chat_id,
                        "text": payload_text,
                        "parse_mode": payload_parse_mode,
                        "reply_to_message_id": reply_to_message_id,
                    }
                    if reply_markup is not None:
                        payload["reply_markup"] = reply_markup
                    if message_thread_id is not None:
                        payload["message_thread_id"] = message_thread_id
                    send_result = await asyncio.wait_for(
                        self.bot.send_message(**payload),
                        timeout=max(1.0, float(self.send_timeout_s)),
                    )
                    _remember_message_id(send_result)
                    self._on_send_auth_success()
                    break
                except TypeError as exc:
                    if message_thread_id is None or "message_thread_id" not in str(exc):
                        raise
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
                    if payload_parse_mode and not formatting_fallback_used and _is_formatting_error(exc):
                        payload_text = html.escape(chunk, quote=False)
                        payload_parse_mode = None
                        formatting_fallback_used = True
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
        if caller_metadata is not None:
            receipt: dict[str, Any] = {
                "channel": "telegram",
                "chat_id": chat_id,
                "chunks": len(chunks),
                "message_ids": list(message_ids),
                "last_message_id": message_ids[-1] if message_ids else 0,
            }
            if message_thread_id is not None:
                receipt["message_thread_id"] = message_thread_id
            caller_metadata["_delivery_receipt"] = receipt
        if message_ids:
            self._remember_own_sent_message_ids(chat_id=chat_id, message_ids=message_ids)
        logger.info("telegram outbound sent chat={} chunks={} chars={}", chat_id, len(chunks), len(text))
        return f"telegram:sent:{len(chunks)}"

    def _build_inline_keyboard_reply_markup(self, metadata: dict[str, Any]) -> Any | None:
        keyboard_source = metadata.get("_telegram_inline_keyboard")
        if keyboard_source is None:
            keyboard_source = metadata.get("telegram_inline_keyboard")
        if keyboard_source is None:
            return None
        if not isinstance(keyboard_source, list):
            logger.debug("telegram outbound inline keyboard ignored reason=invalid_root_type")
            return None

        inline_keyboard_rows: list[list[dict[str, str]]] = []
        for row in keyboard_source:
            if not isinstance(row, list):
                logger.debug("telegram outbound inline keyboard ignored reason=invalid_row_type")
                return None
            inline_row: list[dict[str, str]] = []
            for button in row:
                if not isinstance(button, dict):
                    logger.debug("telegram outbound inline keyboard ignored reason=invalid_button_type")
                    return None
                text = str(button.get("text", "") or "").strip()
                callback_data = button.get("callback_data")
                url = button.get("url")
                if not text:
                    logger.debug("telegram outbound inline keyboard ignored reason=missing_button_text")
                    return None
                if bool(callback_data) == bool(url):
                    logger.debug("telegram outbound inline keyboard ignored reason=invalid_button_action")
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
            logger.debug("telegram outbound inline keyboard ignored reason=empty_keyboard")
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
