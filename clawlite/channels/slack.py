from __future__ import annotations

from typing import Any

import httpx

from clawlite.channels.base import BaseChannel


class SlackChannel(BaseChannel):
    def __init__(self, *, config: dict[str, Any], on_message=None) -> None:
        super().__init__(name="slack", config=config, on_message=on_message)
        bot_token = str(config.get("bot_token", config.get("botToken", "")) or "").strip()
        if not bot_token:
            raise ValueError("slack bot_token is required")
        self.bot_token = bot_token
        self.app_token = str(config.get("app_token", config.get("appToken", "")) or "").strip()
        self.api_base = str(config.get("api_base", config.get("apiBase", "https://slack.com/api")) or "https://slack.com/api").strip().rstrip("/")
        self.timeout_s = max(0.1, float(config.get("timeout_s", config.get("timeoutS", 10.0)) or 10.0))

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def send(self, *, target: str, text: str, metadata: dict[str, Any] | None = None) -> str:
        if not self._running:
            raise RuntimeError("slack_not_running")

        channel = str(target or "").strip()
        if not channel:
            raise ValueError("slack target(channel) is required")

        url = f"{self.api_base}/chat.postMessage"
        headers = {
            "Authorization": f"Bearer {self.bot_token}",
            "Content-Type": "application/json; charset=utf-8",
        }
        payload = {
            "channel": channel,
            "text": str(text or ""),
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_s, headers=headers) as client:
                response = await client.post(url, json=payload)
        except httpx.HTTPError as exc:
            self._last_error = str(exc)
            raise RuntimeError("slack_send_request_error") from exc

        if response.status_code < 200 or response.status_code >= 300:
            self._last_error = f"http:{response.status_code}"
            raise RuntimeError(f"slack_send_http_{response.status_code}")

        try:
            data = response.json()
        except Exception as exc:
            self._last_error = "invalid_json"
            raise RuntimeError("slack_send_invalid_json") from exc

        if not bool(data.get("ok", False)):
            code = str(data.get("error", "unknown") or "unknown").strip() or "unknown"
            self._last_error = code
            raise RuntimeError(f"slack_send_api_error:{code}")

        ts = str(data.get("ts", "") or "").strip()
        if not ts:
            self._last_error = "missing_ts"
            raise RuntimeError("slack_send_missing_ts")
        return f"slack:sent:{channel}:{ts}"
