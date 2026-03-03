from __future__ import annotations

import asyncio
import html
import hashlib
import json
import math
import random
import re
import time
from email.utils import parsedate_to_datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger

from clawlite.channels.base import BaseChannel, cancel_task
from clawlite.config.schema import ChannelConfig
from clawlite.utils.logging import setup_logging

MAX_MESSAGE_LEN = 4000

setup_logging()


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

    code_blocks: list[str] = []

    def save_code_block(match: re.Match[str]) -> str:
        code_blocks.append(match.group(1))
        return f"\x00CB{len(code_blocks) - 1}\x00"

    text = re.sub(r"```[\w]*\n?([\s\S]*?)```", save_code_block, text)

    inline_codes: list[str] = []

    def save_inline_code(match: re.Match[str]) -> str:
        inline_codes.append(match.group(1))
        return f"\x00IC{len(inline_codes) - 1}\x00"

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

    for idx, code in enumerate(inline_codes):
        escaped = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = text.replace(f"\x00IC{idx}\x00", f"<code>{escaped}</code>")

    for idx, code in enumerate(code_blocks):
        escaped = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = text.replace(f"\x00CB{idx}\x00", f"<pre><code>{escaped}</code></pre>")

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
        self.token = token
        self.allow_from = ChannelConfig.from_dict(config).allow_from
        self.bot: Any | None = None
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
        self._offset = self._load_offset()
        self._connected = False
        self._startup_drop_done = False
        self._message_signatures: dict[tuple[str, int], str] = {}
        self._signature_limit = 4096
        self._signals: dict[str, int] = {
            "send_retry_count": 0,
            "send_retry_after_count": 0,
            "send_auth_breaker_open_count": 0,
            "send_auth_breaker_close_count": 0,
            "typing_auth_breaker_open_count": 0,
            "typing_auth_breaker_close_count": 0,
            "typing_ttl_stop_count": 0,
            "reconnect_count": 0,
        }

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

    def _on_send_auth_failure(self) -> None:
        was_open = self._send_auth_breaker.is_open
        self._send_auth_breaker.on_auth_failure()
        if not was_open and self._send_auth_breaker.is_open:
            self._signals["send_auth_breaker_open_count"] += 1

    def _on_send_auth_success(self) -> None:
        was_open = self._send_auth_breaker.is_open
        self._send_auth_breaker.on_success()
        if was_open:
            self._signals["send_auth_breaker_close_count"] += 1

    def _on_typing_auth_failure(self) -> None:
        was_open = self._typing_auth_breaker.is_open
        self._typing_auth_breaker.on_auth_failure()
        if not was_open and self._typing_auth_breaker.is_open:
            self._signals["typing_auth_breaker_open_count"] += 1

    def _on_typing_auth_success(self) -> None:
        was_open = self._typing_auth_breaker.is_open
        self._typing_auth_breaker.on_success()
        if was_open:
            self._signals["typing_auth_breaker_close_count"] += 1

    def signals(self) -> dict[str, Any]:
        return {
            **self._signals,
            "send_auth_breaker_open": self._send_auth_breaker.is_open,
            "typing_auth_breaker_open": self._typing_auth_breaker.is_open,
            "typing_keepalive_active": len(self._typing_tasks),
        }

    def _remember_message_signature(self, *, msg_key: tuple[str, int], signature: str) -> None:
        self._message_signatures[msg_key] = signature
        if len(self._message_signatures) > self._signature_limit:
            oldest_key = next(iter(self._message_signatures))
            self._message_signatures.pop(oldest_key, None)

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
                    await asyncio.sleep(min(interval_s, remaining_s))
                    continue

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

    def _start_typing_keepalive(self, *, chat_id: str, message_thread_id: int | None = None) -> None:
        if not self.typing_enabled or not self._running:
            return
        if not chat_id:
            return
        typing_key = self._typing_key(chat_id=chat_id, message_thread_id=message_thread_id)
        task = self._typing_tasks.get(typing_key)
        if task is not None and not task.done():
            return
        self._typing_tasks[typing_key] = asyncio.create_task(
            self._typing_loop(chat_id=chat_id, message_thread_id=message_thread_id)
        )

    async def _stop_typing_keepalive(self, *, chat_id: str, message_thread_id: int | None = None) -> None:
        typing_key = self._typing_key(chat_id=chat_id, message_thread_id=message_thread_id)
        task = self._typing_tasks.pop(typing_key, None)
        await cancel_task(task)

    async def _stop_all_typing_keepalive(self) -> None:
        tasks = list(self._typing_tasks.values())
        self._typing_tasks.clear()
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
                    allowed_updates=["message", "edited_message"],
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
        candidates = {str(user_id).strip()}
        if username:
            uname = username.strip()
            if uname:
                candidates.add(uname)
                candidates.add(f"@{uname}")
        return any(candidate in allowed for candidate in candidates)

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
        except (json.JSONDecodeError, OSError):
            return 0
        return int(data.get("offset", 0) or 0)

    def _save_offset(self) -> None:
        path = self._offset_path()
        path.write_text(json.dumps({"offset": self._offset}), encoding="utf-8")

    async def _poll_loop(self) -> None:
        backoff = self.reconnect_initial_s
        while self._running:
            try:
                if self.bot is None:
                    from telegram import Bot  # lazy import for environments without dependency during tests

                    self.bot = Bot(token=self.token)
                    logger.info("telegram bot initialized poll_timeout_s={}", self.poll_timeout_s)
                    if self.drop_pending_updates and not self._startup_drop_done:
                        await self._drop_pending_updates()
                        self._startup_drop_done = True
                updates = await self.bot.get_updates(
                    offset=self._offset,
                    timeout=self.poll_timeout_s,
                    allowed_updates=["message", "edited_message"],
                )
                if not self._connected:
                    self._connected = True
                    logger.info("telegram connected polling=true")
                backoff = self.reconnect_initial_s
                for item in updates:
                    processed_ok = await self._handle_update(item)
                    if not processed_ok:
                        raise RuntimeError("telegram update processing failed")
                    update_id = getattr(item, "update_id", None)
                    if update_id is None:
                        continue
                    self._offset = max(self._offset, int(update_id) + 1)
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
        message = getattr(item, "message", None)
        is_edit = False
        if message is None:
            message = getattr(item, "edited_message", None)
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
        user_id = str(getattr(user, "id", "") or chat_id)
        username = str(getattr(user, "username", "") or "").strip()
        if not self._is_allowed_sender(user_id, username):
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

        session_id = f"telegram:{chat_id}"
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

        for media_type in ("voice", "audio", "document"):
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
        logger.info("telegram channel starting")
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        self._running = False
        await self._stop_all_typing_keepalive()
        await cancel_task(self._task)
        self._task = None
        self._connected = False
        logger.info("telegram channel stopped")

    async def send(self, *, target: str, text: str, metadata: dict[str, Any] | None = None) -> str:
        chat_id, target_thread_id = self._parse_target(str(target))
        if not chat_id:
            raise ValueError("telegram target(chat_id) is required")
        metadata = dict(metadata or {})
        message_thread_id = self._coerce_thread_id(metadata.get("message_thread_id", target_thread_id))
        await self._stop_typing_keepalive(chat_id=chat_id, message_thread_id=message_thread_id)
        if self.bot is None:
            from telegram import Bot

            self.bot = Bot(token=self.token)
        chunks = split_message(text)
        policy = self._send_retry_policy.normalized()
        reply_to_message_id = metadata.get("reply_to_message_id", metadata.get("message_id"))
        try:
            reply_to_message_id = int(reply_to_message_id) if reply_to_message_id is not None else None
        except (TypeError, ValueError):
            reply_to_message_id = None

        for idx, chunk in enumerate(chunks, start=1):
            html_payload = markdown_to_telegram_html(chunk)
            payload_text = html_payload
            payload_parse_mode: str | None = "HTML"
            formatting_fallback_used = False

            for attempt in range(1, policy.max_attempts + 1):
                if self._send_auth_breaker.is_open:
                    raise TelegramCircuitOpenError("telegram auth circuit is open")
                try:
                    payload: dict[str, Any] = {
                        "chat_id": chat_id,
                        "text": payload_text,
                        "parse_mode": payload_parse_mode,
                        "reply_to_message_id": reply_to_message_id,
                    }
                    if message_thread_id is not None:
                        payload["message_thread_id"] = message_thread_id
                    await asyncio.wait_for(
                        self.bot.send_message(**payload),
                        timeout=max(1.0, float(self.send_timeout_s)),
                    )
                    self._on_send_auth_success()
                    break
                except TypeError as exc:
                    if message_thread_id is None or "message_thread_id" not in str(exc):
                        raise
                    await asyncio.wait_for(
                        self.bot.send_message(
                            chat_id=chat_id,
                            text=payload_text,
                            parse_mode=payload_parse_mode,
                            reply_to_message_id=reply_to_message_id,
                        ),
                        timeout=max(1.0, float(self.send_timeout_s)),
                    )
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
        logger.info("telegram outbound sent chat={} chunks={} chars={}", chat_id, len(chunks), len(text))
        return f"telegram:sent:{len(chunks)}"
