from __future__ import annotations

import hashlib
from collections import OrderedDict
from typing import Any

import httpx

from clawlite.channels.base import BaseChannel


class WhatsAppChannel(BaseChannel):
    def __init__(self, *, config: dict[str, Any], on_message=None) -> None:
        super().__init__(name="whatsapp", config=config, on_message=on_message)
        bridge_url = str(
            config.get("bridge_url", config.get("bridgeUrl", "http://localhost:3001"))
            or "http://localhost:3001"
        ).strip()
        if not bridge_url:
            raise ValueError("whatsapp bridge_url is required")
        self.bridge_url = bridge_url
        self.bridge_token = str(
            config.get("bridge_token", config.get("bridgeToken", "")) or ""
        ).strip()
        self.webhook_secret = str(
            config.get("webhook_secret", config.get("webhookSecret", "")) or ""
        ).strip()
        self.webhook_path = str(
            config.get("webhook_path", config.get("webhookPath", "/api/webhooks/whatsapp"))
            or "/api/webhooks/whatsapp"
        ).strip() or "/api/webhooks/whatsapp"
        self.timeout_s = max(
            0.1,
            float(config.get("timeout_s", config.get("timeoutS", 10.0)) or 10.0),
        )
        self.allow_from = self._normalize_allow_from(
            config.get("allow_from", config.get("allowFrom", []))
        )
        self._processed_message_ids: OrderedDict[str, None] = OrderedDict()
        self._processed_limit = 2048

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
    def _field(payload: dict[str, Any], *names: str) -> Any:
        for name in names:
            if name in payload:
                return payload.get(name)
        return None

    @staticmethod
    def _sender_id(sender: str) -> str:
        normalized = str(sender or "").strip()
        if "@" in normalized:
            normalized = normalized.split("@", 1)[0]
        return normalized

    def _is_allowed_sender(self, sender: str) -> bool:
        if not self.allow_from:
            return True
        raw = str(sender or "").strip()
        sender_id = self._sender_id(raw)
        candidates = {raw, sender_id, f"@{sender_id}"}
        allowed = {str(item or "").strip() for item in self.allow_from if str(item or "").strip()}
        return any(candidate in allowed for candidate in candidates)

    def _remember_message_id(self, message_id: str) -> bool:
        normalized = str(message_id or "").strip()
        if not normalized:
            return True
        if normalized in self._processed_message_ids:
            return False
        self._processed_message_ids[normalized] = None
        while len(self._processed_message_ids) > self._processed_limit:
            self._processed_message_ids.popitem(last=False)
        return True

    @staticmethod
    def _placeholder_for_media(media_type: str) -> str:
        normalized = str(media_type or "").strip().lower()
        placeholders = {
            "image": "[whatsapp image]",
            "audio": "[whatsapp audio]",
            "voice": "[whatsapp audio]",
            "document": "[whatsapp document]",
        }
        return placeholders.get(normalized, f"[whatsapp {normalized or 'message'}]")

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def send(
        self,
        *,
        target: str,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
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
            async with httpx.AsyncClient(
                timeout=self.timeout_s,
                headers=headers,
            ) as client:
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
            message_id = str(
                data.get("id")
                or data.get("message_id")
                or data.get("messageId")
                or ""
            ).strip()
        if not message_id:
            digest = hashlib.sha256(f"{phone}:{text}".encode("utf-8")).hexdigest()[:16]
            message_id = f"fallback-{digest}"
        self._last_error = ""
        return f"whatsapp:sent:{message_id}"

    async def receive_hook(self, payload: dict[str, Any]) -> bool:
        if not isinstance(payload, dict):
            return False

        sender = str(
            self._field(payload, "from", "sender", "chat_id", "chatId") or ""
        ).strip()
        if not sender:
            return False

        from_me = bool(self._field(payload, "fromMe", "from_me", "self", "isSelf"))
        if from_me:
            return False

        if not self._is_allowed_sender(sender):
            return False

        message_id = str(
            self._field(payload, "messageId", "message_id", "id") or ""
        ).strip()
        if not self._remember_message_id(message_id):
            return False

        message_type = str(
            self._field(payload, "type", "messageType", "message_type", "kind") or "text"
        ).strip().lower()
        media_url = str(
            self._field(payload, "mediaUrl", "media_url", "url") or ""
        ).strip()
        body = str(self._field(payload, "body", "text", "content") or "").strip()
        text = body or (
            self._placeholder_for_media(message_type) if media_url or message_type != "text" else ""
        )
        if not text:
            return False

        metadata = {
            "channel": "whatsapp",
            "chat_id": sender,
            "sender_id": self._sender_id(sender),
            "message_id": message_id,
            "media_type": message_type,
            "media_url": media_url,
            "bridge_payload": dict(payload),
            "is_group": bool(self._field(payload, "isGroup", "is_group")),
        }
        await self.emit(
            session_id=f"whatsapp:{sender}",
            user_id=self._sender_id(sender),
            text=text,
            metadata=metadata,
        )
        return True
