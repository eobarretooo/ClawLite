from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
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


@dataclass(slots=True, frozen=True)
class _DiscordSendTarget:
    kind: str
    value: str


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
        self._headers = {
            "Authorization": f"Bot {self.token}",
            "Content-Type": "application/json",
        }
        self._client: httpx.AsyncClient | None = None
        self._ws: Any | None = None
        self._gateway_task: asyncio.Task[Any] | None = None
        self._heartbeat_task: asyncio.Task[Any] | None = None
        self._typing_tasks: dict[str, asyncio.Task[Any]] = {}
        self._dm_channel_ids: dict[str, str] = {}
        self._sequence: int | None = None
        self._session_id: str = ""
        self._resume_url: str = ""
        self._bot_user_id: str = ""

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

    def _is_allowed_sender(self, *, user_id: str, username: str = "") -> bool:
        if not self.allow_from:
            return True
        candidates = {str(user_id or "").strip()}
        normalized_username = str(username or "").strip().lstrip("@")
        if normalized_username:
            candidates.add(normalized_username)
            candidates.add(f"@{normalized_username}")
        allowed = {item.strip() for item in self.allow_from if str(item or "").strip()}
        return any(candidate in allowed for candidate in candidates)

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

    async def start(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout_s,
                headers=self._headers,
            )
        self._running = True
        if self.on_message is not None and (
            self._gateway_task is None or self._gateway_task.done()
        ):
            self._gateway_task = asyncio.create_task(self._gateway_runner())

    async def stop(self) -> None:
        self._running = False
        await cancel_task(self._gateway_task)
        self._gateway_task = None
        await cancel_task(self._heartbeat_task)
        self._heartbeat_task = None
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
            return True

        if event_type == "RESUMED":
            return True

        if event_type == "MESSAGE_CREATE":
            await self._handle_message_create(payload)
            return True

        if event_type == "MESSAGE_REACTION_ADD":
            await self._handle_message_reaction_add(payload)
            return True

        if event_type == "MESSAGE_REACTION_REMOVE":
            return True  # Silently acknowledged

        return True

    async def _send_ws_json(self, payload: dict[str, Any]) -> None:
        ws = self._ws
        if ws is None:
            return
        await ws.send(json.dumps(payload))

    async def _identify(self) -> None:
        await self._send_ws_json(
            {
                "op": 2,
                "d": {
                    "token": self.token,
                    "intents": self.gateway_intents,
                    "properties": {
                        "os": "clawlite",
                        "browser": "clawlite",
                        "device": "clawlite",
                    },
                },
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

    async def _handle_message_create(self, payload: dict[str, Any]) -> None:
        author = payload.get("author")
        if not isinstance(author, dict):
            return
        author_id = str(author.get("id", "") or "").strip()
        if not author_id:
            return
        if bool(author.get("bot")) or (
            self._bot_user_id and author_id == self._bot_user_id
        ):
            return

        channel_id = str(payload.get("channel_id", "") or "").strip()
        if not channel_id:
            return

        username = str(author.get("username", "") or "").strip()
        if not self._is_allowed_sender(user_id=author_id, username=username):
            return

        attachments = self._normalize_attachment_rows(payload.get("attachments"))
        content = str(payload.get("content", "") or "").strip()
        attachment_lines = [
            f"[discord attachment: {row['filename'] or row['id'] or 'file'}]"
            for row in attachments
        ]
        parts = [part for part in (content, "\n".join(attachment_lines)) if part]
        text = "\n\n".join(parts).strip()
        if not text:
            return

        metadata = {
            "channel": "discord",
            "channel_id": channel_id,
            "guild_id": str(payload.get("guild_id", "") or "").strip(),
            "message_id": str(payload.get("id", "") or "").strip(),
            "author_username": username,
            "author_global_name": str(author.get("global_name", "") or "").strip(),
            "attachments": attachments,
            "is_dm": not bool(payload.get("guild_id")),
        }

        await self._start_typing(channel_id)
        try:
            await self.emit(
                session_id=f"discord:{channel_id}",
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
        if not self._is_allowed_sender(user_id=user_id):
            return
        emoji_data = payload.get("emoji") or {}
        emoji_name = str(emoji_data.get("name", "") or "").strip()
        emoji_id = str(emoji_data.get("id", "") or "").strip()
        emoji_str = f"{emoji_name}:{emoji_id}" if emoji_id else emoji_name
        if not emoji_str:
            return
        metadata = {
            "channel": "discord",
            "channel_id": channel_id,
            "guild_id": str(payload.get("guild_id", "") or "").strip(),
            "message_id": str(payload.get("message_id", "") or "").strip(),
            "event_type": "reaction_add",
            "emoji": emoji_str,
        }
        await self.emit(
            session_id=f"discord:{channel_id}",
            user_id=user_id,
            text=f"[reaction: {emoji_str}]",
            metadata=metadata,
        )

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
            "hints": hints,
        }

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
