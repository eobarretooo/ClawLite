from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import websockets

from clawlite.channels.base import BaseChannel, cancel_task


class SlackChannel(BaseChannel):
    def __init__(self, *, config: dict[str, Any], on_message=None) -> None:
        super().__init__(name="slack", config=config, on_message=on_message)
        bot_token = str(config.get("bot_token", config.get("botToken", "")) or "").strip()
        if not bot_token:
            raise ValueError("slack bot_token is required")
        self.bot_token = bot_token
        self.app_token = str(config.get("app_token", config.get("appToken", "")) or "").strip()
        self.allow_from = self._normalize_allow_from(
            config.get("allow_from", config.get("allowFrom", []))
        )
        self.api_base = str(
            config.get("api_base", config.get("apiBase", "https://slack.com/api"))
            or "https://slack.com/api"
        ).strip().rstrip("/")
        self.timeout_s = max(0.1, float(config.get("timeout_s", config.get("timeoutS", 10.0)) or 10.0))
        self.send_retry_attempts = max(
            1,
            int(config.get("send_retry_attempts", config.get("sendRetryAttempts", 3)) or 3),
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
        self.socket_mode_enabled = bool(
            config.get("socket_mode_enabled", config.get("socketModeEnabled", True))
        )
        self.socket_backoff_base_s = max(
            0.0,
            float(config.get("socket_backoff_base_s", config.get("socketBackoffBaseS", 1.0)) or 1.0),
        )
        self.socket_backoff_max_s = max(
            self.socket_backoff_base_s,
            float(config.get("socket_backoff_max_s", config.get("socketBackoffMaxS", 30.0)) or 30.0),
        )
        self.typing_enabled = bool(
            config.get("typing_enabled", config.get("typingEnabled", True))
        )
        self.working_indicator_enabled = bool(
            config.get(
                "working_indicator_enabled",
                config.get("workingIndicatorEnabled", self.typing_enabled),
            )
        )
        self.working_indicator_emoji = str(
            config.get(
                "working_indicator_emoji",
                config.get("workingIndicatorEmoji", "hourglass_flowing_sand"),
            )
            or "hourglass_flowing_sand"
        ).strip() or "hourglass_flowing_sand"
        self._headers = {
            "Authorization": f"Bearer {self.bot_token}",
            "Content-Type": "application/json; charset=utf-8",
        }
        self._client: httpx.AsyncClient | None = None
        self._socket_task: asyncio.Task[Any] | None = None
        self._typing_tasks: dict[str, asyncio.Task[Any]] = {}
        self._latest_inbound_ts: dict[str, str] = {}
        self._working_markers: dict[str, str] = {}

    @staticmethod
    def _normalize_allow_from(raw: Any) -> list[str]:
        if not isinstance(raw, list):
            return []
        return [str(item).strip() for item in raw if str(item).strip()]

    def _is_allowed_user(self, user_id: str) -> bool:
        if not self.allow_from:
            return True
        normalized = str(user_id or "").strip()
        if not normalized:
            return False
        candidates = {normalized, f"@{normalized}"}
        allowed = {str(item or "").strip() for item in self.allow_from if str(item or "").strip()}
        return any(candidate in allowed for candidate in candidates)

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

    def _extract_retry_after(self, *, response: httpx.Response, payload: dict[str, Any] | None = None) -> float:
        header_retry_after = self._parse_retry_after(response.headers.get("Retry-After", ""))
        if header_retry_after is not None:
            return header_retry_after
        if isinstance(payload, dict):
            body_retry_after = self._parse_retry_after(str(payload.get("retry_after", "")))
            if body_retry_after is not None:
                return body_retry_after
        return self.send_retry_after_default_s

    async def start(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout_s, headers=self._headers)
        self._running = True
        if self.app_token and self.on_message is not None and self.socket_mode_enabled:
            existing = self._socket_task
            if existing is None or existing.done():
                self._socket_task = asyncio.create_task(self._socket_mode_runner())

    async def stop(self) -> None:
        for task in list(self._typing_tasks.values()):
            await cancel_task(task)
        self._typing_tasks.clear()
        self._working_markers.clear()
        await cancel_task(self._socket_task)
        self._socket_task = None
        client = self._client
        self._client = None
        if client is not None:
            close_fn = getattr(client, "aclose", None)
            if callable(close_fn):
                await close_fn()
        self._running = False

    async def send(self, *, target: str, text: str, metadata: dict[str, Any] | None = None) -> str:
        del metadata
        if not self._running:
            raise RuntimeError("slack_not_running")

        channel = str(target or "").strip()
        if not channel:
            raise ValueError("slack target(channel) is required")

        url = f"{self.api_base}/chat.postMessage"
        payload = {
            "channel": channel,
            "text": str(text or ""),
        }
        client = self._client
        if client is None:
            raise RuntimeError("slack_not_running")

        for attempt in range(1, self.send_retry_attempts + 1):
            try:
                response = await client.post(url, json=payload)
            except httpx.HTTPError as exc:
                self._last_error = str(exc)
                raise RuntimeError("slack_send_request_error") from exc

            data: dict[str, Any] | None = None
            if response.content:
                try:
                    parsed = response.json()
                except Exception:
                    parsed = None
                if isinstance(parsed, dict):
                    data = parsed

            if response.status_code == 429:
                self._last_error = "http:429"
                if attempt >= self.send_retry_attempts:
                    raise RuntimeError("slack_send_rate_limited")
                await asyncio.sleep(self._extract_retry_after(response=response, payload=data))
                continue

            if response.status_code < 200 or response.status_code >= 300:
                self._last_error = f"http:{response.status_code}"
                raise RuntimeError(f"slack_send_http_{response.status_code}")

            if data is None:
                self._last_error = "invalid_json"
                raise RuntimeError("slack_send_invalid_json")

            if not bool(data.get("ok", False)):
                code = str(data.get("error", "unknown") or "unknown").strip() or "unknown"
                self._last_error = code
                is_rate_limited = code in {"ratelimited", "rate_limited"}
                if is_rate_limited and attempt < self.send_retry_attempts:
                    await asyncio.sleep(self._extract_retry_after(response=response, payload=data))
                    continue
                raise RuntimeError(f"slack_send_api_error:{code}")

            ts = str(data.get("ts", "") or "").strip()
            if not ts:
                self._last_error = "missing_ts"
                raise RuntimeError("slack_send_missing_ts")
            self._last_error = ""
            return f"slack:sent:{channel}:{ts}"

        raise RuntimeError("slack_send_rate_limited")

    async def _socket_open_url(self) -> str:
        if not self.app_token:
            raise RuntimeError("slack_socket_mode_token_missing")
        client = self._client
        if client is None:
            raise RuntimeError("slack_not_running")
        response = await client.post(
            f"{self.api_base}/apps.connections.open",
            headers={"Authorization": f"Bearer {self.app_token}"},
            json={},
        )
        if response.status_code < 200 or response.status_code >= 300:
            raise RuntimeError(f"slack_socket_open_http_{response.status_code}")
        try:
            data = response.json() if response.content else {}
        except Exception as exc:
            raise RuntimeError("slack_socket_open_invalid_json") from exc
        if not isinstance(data, dict):
            raise RuntimeError("slack_socket_open_invalid_json")
        if not bool(data.get("ok", False)):
            code = str(data.get("error", "unknown") or "unknown").strip() or "unknown"
            raise RuntimeError(f"slack_socket_open_api_error:{code}")
        url = str(data.get("url", "") or "").strip()
        if not url:
            raise RuntimeError("slack_socket_open_missing_url")
        return url

    async def _ack_socket_envelope(self, ws: Any, envelope_id: str) -> None:
        if not envelope_id:
            return
        await ws.send(json.dumps({"envelope_id": envelope_id}, ensure_ascii=True))

    async def _handle_socket_envelope(self, ws: Any, payload: dict[str, Any]) -> bool:
        envelope_id = str(payload.get("envelope_id", "") or "").strip()
        if envelope_id:
            await self._ack_socket_envelope(ws, envelope_id)
        body = payload.get("payload")
        if not isinstance(body, dict):
            return False
        payload_type = str(payload.get("type", "") or "").strip()
        if payload_type not in {"events_api", "event_callback"}:
            return False
        return await self._handle_slack_event(body)

    async def _socket_mode_runner(self) -> None:
        backoff_s = max(0.1, float(self.socket_backoff_base_s))
        while self._running and self.app_token:
            try:
                url = await self._socket_open_url()
                async with websockets.connect(
                    url,
                    open_timeout=self.timeout_s,
                    close_timeout=self.timeout_s,
                    ping_interval=20.0,
                ) as ws:
                    self._last_error = ""
                    backoff_s = max(0.1, float(self.socket_backoff_base_s))
                    async for raw in ws:
                        if isinstance(raw, bytes):
                            raw = raw.decode("utf-8", errors="replace")
                        try:
                            payload = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        if not isinstance(payload, dict):
                            continue
                        await self._handle_socket_envelope(ws, payload)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._last_error = str(exc)
                if not self._running:
                    break
                await asyncio.sleep(backoff_s)
                backoff_s = min(
                    max(backoff_s, self.socket_backoff_base_s),
                    max(self.socket_backoff_base_s, self.socket_backoff_max_s),
                )
                backoff_s = min(self.socket_backoff_max_s, max(0.1, backoff_s * 2.0))

    async def _handle_slack_event(self, payload: dict[str, Any]) -> bool:
        event = payload.get("event")
        if not isinstance(event, dict):
            return False
        event_type = str(event.get("type", "") or "").strip()
        if event_type not in {"message", "app_mention"}:
            return False
        subtype = str(event.get("subtype", "") or "").strip()
        if subtype in {"bot_message", "message_changed", "message_deleted"}:
            return False
        if event.get("bot_id"):
            return False
        user = str(event.get("user", "") or "").strip()
        channel_id = str(event.get("channel", "") or "").strip()
        ts = str(event.get("ts", "") or "").strip()
        text = str(event.get("text", "") or "").strip()
        if not user or not channel_id or not text:
            return False
        if not self._is_allowed_user(user):
            return False
        self._latest_inbound_ts[channel_id] = ts
        metadata = {
            "channel": "slack",
            "chat_id": channel_id,
            "channel_id": channel_id,
            "user": user,
            "sender_id": user,
            "message_id": ts,
            "thread_ts": str(event.get("thread_ts", "") or "").strip(),
            "slack_event": dict(event),
        }
        await self.emit(
            session_id=f"slack:{channel_id}",
            user_id=user,
            text=text,
            metadata=metadata,
        )
        return True

    async def _set_working_indicator(self, *, channel_id: str, add: bool) -> None:
        if not self.working_indicator_enabled:
            return
        client = self._client
        if client is None:
            return
        ts = str(self._latest_inbound_ts.get(channel_id, "") or "").strip()
        if not ts:
            return
        endpoint = "reactions.add" if add else "reactions.remove"
        response = await client.post(
            f"{self.api_base}/{endpoint}",
            json={
                "channel": channel_id,
                "name": self.working_indicator_emoji,
                "timestamp": ts,
            },
        )
        if response.status_code < 200 or response.status_code >= 300:
            return
        if add:
            self._working_markers[channel_id] = ts
        else:
            self._working_markers.pop(channel_id, None)

    async def _typing_loop(self, channel_id: str) -> None:
        try:
            await self._set_working_indicator(channel_id=channel_id, add=True)
            while self._running:
                await asyncio.sleep(self.timeout_s)
        finally:
            try:
                await self._set_working_indicator(channel_id=channel_id, add=False)
            except Exception:
                return

    def _start_typing_keepalive(self, *, chat_id: str, message_thread_id: int | None = None) -> None:
        del message_thread_id
        if not self.typing_enabled or not self._running:
            return
        channel_id = str(chat_id or "").strip()
        if not channel_id:
            return
        existing = self._typing_tasks.get(channel_id)
        if existing is not None and not existing.done():
            return
        self._typing_tasks[channel_id] = asyncio.create_task(self._typing_loop(channel_id))

    async def _stop_typing_keepalive(
        self,
        *,
        chat_id: str,
        message_thread_id: int | None = None,
    ) -> None:
        del message_thread_id
        channel_id = str(chat_id or "").strip()
        if not channel_id:
            return
        task = self._typing_tasks.pop(channel_id, None)
        await cancel_task(task)
