from __future__ import annotations

import hashlib
from typing import Any

import httpx

from clawlite.channels.base import BaseChannel


class WhatsAppChannel(BaseChannel):
    def __init__(self, *, config: dict[str, Any], on_message=None) -> None:
        super().__init__(name="whatsapp", config=config, on_message=on_message)
        bridge_url = str(config.get("bridge_url", config.get("bridgeUrl", "http://localhost:3001")) or "http://localhost:3001").strip()
        if not bridge_url:
            raise ValueError("whatsapp bridge_url is required")
        self.bridge_url = bridge_url
        self.bridge_token = str(config.get("bridge_token", config.get("bridgeToken", "")) or "").strip()
        self.timeout_s = max(0.1, float(config.get("timeout_s", config.get("timeoutS", 10.0)) or 10.0))

    @staticmethod
    def _normalize_bridge_url(raw: str) -> str:
        value = str(raw or "").strip().rstrip("/")
        if value.startswith("ws://"):
            value = "http://" + value[5:]
        elif value.startswith("wss://"):
            value = "https://" + value[6:]
        if value.endswith("/send"):
            return value
        return f"{value}/send"

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def send(self, *, target: str, text: str, metadata: dict[str, Any] | None = None) -> str:
        if not self._running:
            raise RuntimeError("whatsapp_not_running")

        phone = str(target or "").strip()
        if not phone:
            raise ValueError("whatsapp target(phone) is required")

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.bridge_token:
            headers["Authorization"] = f"Bearer {self.bridge_token}"
        url = self._normalize_bridge_url(self.bridge_url)
        payload = {
            "target": phone,
            "text": str(text or ""),
            "metadata": dict(metadata or {}),
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_s, headers=headers) as client:
                response = await client.post(url, json=payload)
        except httpx.HTTPError as exc:
            self._last_error = str(exc)
            raise RuntimeError("whatsapp_send_request_error") from exc

        if response.status_code < 200 or response.status_code >= 300:
            self._last_error = f"http:{response.status_code}"
            raise RuntimeError(f"whatsapp_send_http_{response.status_code}")

        message_id = ""
        if response.content:
            try:
                data = response.json()
            except Exception:
                data = {}
            message_id = str(data.get("id") or data.get("message_id") or data.get("messageId") or "").strip()
        if not message_id:
            digest = hashlib.sha256(f"{phone}:{text}".encode("utf-8")).hexdigest()[:16]
            message_id = f"fallback-{digest}"
        return f"whatsapp:sent:{message_id}"
