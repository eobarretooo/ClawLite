from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from clawlite.channels.base import BaseChannel
from clawlite.runtime.pairing import is_sender_allowed, issue_pairing_code

try:
    import httpx

    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

logger = logging.getLogger(__name__)

_SAFE_ID = re.compile(r"[^a-zA-Z0-9_-]+")


def _safe_part(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "unknown"
    return _SAFE_ID.sub("_", raw)


class IrcChannel(BaseChannel):
    """
    Canal IRC em modo bridge:
    - Inbound por webhook (/api/webhooks/irc)
    - Outbound opcional via relay HTTP (relay_url)
    """

    def __init__(
        self,
        token: str = "",
        host: str = "",
        port: int = 6697,
        tls: bool = True,
        nick: str = "clawlite-bot",
        channels: list[str] | None = None,
        allowed_senders: list[str] | None = None,
        allowed_channels: list[str] | None = None,
        require_mention: bool = True,
        relay_url: str = "",
        pairing_enabled: bool = False,
        **kwargs: Any,
    ) -> None:
        kwargs.pop("name", None)
        super().__init__("irc", token, **kwargs)
        self.host = str(host).strip()
        self.port = int(port)
        self.tls = bool(tls)
        self.nick = str(nick).strip() or "clawlite-bot"
        self.channels = channels or []
        self.allowed_senders = allowed_senders or []
        self.allowed_channels = allowed_channels or []
        self.require_mention = bool(require_mention)
        self.relay_url = str(relay_url).strip()
        self.pairing_enabled = bool(pairing_enabled)
        self._relay_client: httpx.AsyncClient | None = None
        self._session_targets: dict[str, str] = {}

    async def start(self) -> None:
        if self.relay_url and HAS_HTTPX:
            self._relay_client = httpx.AsyncClient(timeout=15.0)
        self.running = True
        logger.info("Canal IRC iniciado em modo bridge.")

    async def stop(self) -> None:
        if self._relay_client:
            await self._relay_client.aclose()
        self.running = False
        logger.info("Canal IRC encerrado.")

    def _mentions_bot(self, text: str) -> bool:
        probe = str(text or "").lower()
        nick = self.nick.lower()
        return f"{nick}:" in probe or f"@{nick}" in probe or nick in probe

    def _strip_mention(self, text: str) -> str:
        value = str(text or "").strip()
        nick = re.escape(self.nick)
        value = re.sub(rf"^\s*@?{nick}[:,]?\s*", "", value, flags=re.IGNORECASE)
        return value.strip()

    def _pairing_text(self, sender: str) -> str:
        req = issue_pairing_code("irc", str(sender), display=str(sender))
        return (
            "⛔ Acesso pendente de aprovação.\n"
            f"Código: {req['code']}\n"
            f"Aprove com: clawlite pairing approve irc {req['code']}"
        )

    async def _send_to_target(self, target: str, text: str) -> None:
        if not target:
            return
        if self._relay_client and self.relay_url:
            try:
                await self._relay_client.post(
                    self.relay_url,
                    json={"target": target, "text": str(text)},
                )
                return
            except Exception as exc:
                logger.error(f"Falha ao enviar para relay IRC: {exc}")
        logger.info("IRC outbound sem relay configurado; target=%s text=%s", target, str(text)[:120])

    async def process_webhook_payload(self, payload: dict[str, Any]) -> None:
        if not self.running:
            return
        if not self._on_message_callback:
            return

        text = str(payload.get("text") or payload.get("message") or "").strip()
        sender = str(payload.get("sender") or payload.get("nick") or "").strip()
        channel_name = str(payload.get("channel") or "").strip()
        is_dm = bool(payload.get("is_dm", False)) or not channel_name
        target = str(payload.get("target") or sender or channel_name).strip()

        if not text or not sender:
            return
        if self.allowed_channels and not is_dm and channel_name not in self.allowed_channels:
            return
        if not is_sender_allowed("irc", [sender], self.allowed_senders):
            if self.pairing_enabled and is_dm:
                await self._send_to_target(target, self._pairing_text(sender))
            return
        if not is_dm and self.require_mention and not self._mentions_bot(text):
            return

        clean_text = self._strip_mention(text) if self.require_mention else text
        if not clean_text:
            clean_text = text

        session_id = f"irc_{'dm' if is_dm else 'group'}_{_safe_part(target)}"
        self._session_targets[session_id] = target

        try:
            reply = await self._on_message_callback(session_id, clean_text)
        except Exception as exc:
            logger.error(f"Erro processando mensagem IRC: {exc}")
            await self._send_to_target(target, "⚠️ Erro interno ao processar a mensagem.")
            return

        if reply:
            await self._send_to_target(target, str(reply))

    async def send_message(self, session_id: str, text: str) -> None:
        target = self._session_targets.get(session_id, "")
        if not target and session_id.startswith("irc_dm_"):
            target = session_id[len("irc_dm_") :]
        if not target and session_id.startswith("irc_group_"):
            target = session_id[len("irc_group_") :]
        await self._send_to_target(target, text)

