from __future__ import annotations

import hashlib
from typing import Any

import httpx

from clawlite.channels.base import BaseChannel


class DiscordChannel(BaseChannel):
    def __init__(self, *, config: dict[str, Any], on_message=None) -> None:
        super().__init__(name="discord", config=config, on_message=on_message)
        token = str(config.get("token", "") or "").strip()
        if not token:
            raise ValueError("discord token is required")
        self.token = token
        self.api_base = str(config.get("api_base", config.get("apiBase", "https://discord.com/api/v10")) or "https://discord.com/api/v10").strip().rstrip("/")
        self.timeout_s = max(0.1, float(config.get("timeout_s", config.get("timeoutS", 10.0)) or 10.0))

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def send(self, *, target: str, text: str, metadata: dict[str, Any] | None = None) -> str:
        if not self._running:
            raise RuntimeError("discord_not_running")

        channel_id = str(target or "").strip()
        if not channel_id:
            raise ValueError("discord target(channel_id) is required")

        payload = {"content": str(text or "")}
        url = f"{self.api_base}/channels/{channel_id}/messages"
        headers = {
            "Authorization": f"Bot {self.token}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_s, headers=headers) as client:
                response = await client.post(url, json=payload)
        except httpx.HTTPError as exc:
            self._last_error = str(exc)
            raise RuntimeError("discord_send_request_error") from exc

        if response.status_code < 200 or response.status_code >= 300:
            self._last_error = f"http:{response.status_code}"
            raise RuntimeError(f"discord_send_http_{response.status_code}")

        if response.content:
            try:
                data = response.json()
            except Exception:
                data = {}
        else:
            data = {}
        message_id = str(data.get("id", "") or "").strip()
        if not message_id:
            digest = hashlib.sha256(f"{channel_id}:{text}".encode("utf-8")).hexdigest()[:16]
            message_id = f"fallback-{digest}"
        return f"discord:sent:{message_id}"
