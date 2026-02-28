from __future__ import annotations

import logging
from typing import Any

from clawlite.runtime.pairing import is_sender_allowed, issue_pairing_code
from clawlite.channels.base import BaseChannel

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

logger = logging.getLogger(__name__)


class WhatsAppChannel(BaseChannel):
    """
    Integração com WhatsApp via Meta Cloud API Oficial.
    (Neste formato, requer um webhook externo apontando para o servidor,
    ou polling usando provedores de ponte).
    
    Esta classe encapsula a lógica de disparar mensagens via httpx
    para a Graph API do WhatsApp.
    """

    def __init__(
        self,
        token: str,
        phone_number_id: str = "",
        allowed_numbers: list[str] = None,
        pairing_enabled: bool = False,
        **kwargs: Any,
    ) -> None:
        # Compat: o ChannelManager pode injetar `name`.
        kwargs.pop("name", None)
        super().__init__("whatsapp", token, **kwargs)
        self.phone_number_id = phone_number_id or kwargs.get("phone_number_id", "")
        self.allowed_numbers = allowed_numbers or []
        self.pairing_enabled = bool(pairing_enabled)
        self._client: httpx.AsyncClient | None = None

    def _is_sender_allowed(self, sender: str) -> bool:
        candidates = [str(sender).strip()]
        return is_sender_allowed("whatsapp", candidates, self.allowed_numbers)

    def _pairing_text(self, sender: str) -> str:
        req = issue_pairing_code("whatsapp", str(sender), display=str(sender))
        return (
            "⛔ Este número ainda não foi aprovado.\n"
            f"Código de pairing: {req['code']}\n"
            f"Aprove com: clawlite pairing approve whatsapp {req['code']}"
        )

    async def start(self) -> None:
        if not HAS_HTTPX:
            logger.error("httpx não instalado. WhatsAppChannel não iniciará.")
            return

        if not self.phone_number_id:
            logger.warning("WhatsAppChannel: phone_number_id não fornecido. Envio pode falhar.")

        self._client = httpx.AsyncClient(
            base_url=f"https://graph.facebook.com/v19.0/{self.phone_number_id}",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            }
        )
        self.running = True
        logger.info("Canal WhatsApp configurado (modo webhook/Cloud API).")

    async def stop(self) -> None:
        if self._client and self.running:
            await self._client.aclose()
            self.running = False
            logger.info("Canal WhatsApp encerrado.")

    async def process_webhook_payload(self, payload: dict[str, Any]) -> None:
        """Chamado pelo router HTTP quando o webhook receber eventos."""
        if not self._on_message_callback:
            return

        try:
            entries = payload.get("entry", [])
            for entry in entries:
                changes = entry.get("changes", [])
                for change in changes:
                    value = change.get("value", {})
                    messages = value.get("messages", [])
                    for msg in messages:
                        if msg.get("type") == "text":
                            text = msg.get("text", {}).get("body", "")
                            sender = msg.get("from", "")

                            if not self._is_sender_allowed(sender):
                                if self.pairing_enabled:
                                    await self.send_message(f"wa_{sender}", self._pairing_text(sender))
                                continue

                            session_id = f"wa_{sender}"
                            
                            # Dispara callback do core
                            reply = await self._on_message_callback(session_id, text)
                            if reply:
                                await self.send_message(session_id, reply)
        except Exception as exc:
            logger.error(f"Erro processando webhook de WhatsApp: {exc}")

    async def send_message(self, session_id: str, text: str) -> None:
        if not self._client or not self.running:
            return
            
        if session_id.startswith("wa_"):
            phone_number = session_id[3:]
            try:
                response = await self._client.post(
                    "/messages",
                    json={
                        "messaging_product": "whatsapp",
                        "recipient_type": "individual",
                        "to": phone_number,
                        "type": "text",
                        "text": {"preview_url": False, "body": text}
                    }
                )
                response.raise_for_status()
            except Exception as e:
                logger.error(f"Falha ao enviar mensagem WhatsApp: {e}")
