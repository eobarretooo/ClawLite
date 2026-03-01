from __future__ import annotations

import logging
from typing import Any

from clawlite.channels.base import BaseChannel
from clawlite.channels.outbound_resilience import OutboundResilience
from clawlite.runtime.pairing import is_sender_allowed, issue_pairing_code

try:
    import httpx

    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

logger = logging.getLogger(__name__)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


class GoogleChatChannel(BaseChannel):
    """
    Canal Google Chat baseado em webhook HTTP.
    O reply principal é síncrono no retorno do webhook.
    """

    def __init__(
        self,
        token: str = "",
        allowed_users: list[str] | None = None,
        allowed_spaces: list[str] | None = None,
        require_mention: bool = True,
        bot_user: str = "",
        outbound_webhook_url: str = "",
        send_timeout_s: float = 8.0,
        send_backoff_base_s: float = 0.25,
        send_circuit_failure_threshold: int = 5,
        send_circuit_cooldown_s: float = 30.0,
        pairing_enabled: bool = False,
        **kwargs: Any,
    ) -> None:
        kwargs.pop("name", None)
        super().__init__("googlechat", token, **kwargs)
        self.allowed_users = allowed_users or []
        self.allowed_spaces = allowed_spaces or []
        self.require_mention = bool(require_mention)
        self.bot_user = str(bot_user).strip().lower()
        self.outbound_webhook_url = str(outbound_webhook_url).strip()
        self.pairing_enabled = bool(pairing_enabled)
        self._outbound_client: httpx.AsyncClient | None = None
        self._outbound = OutboundResilience(
            "googlechat",
            timeout_s=send_timeout_s,
            max_attempts=3,
            base_backoff_s=send_backoff_base_s,
            breaker_failure_threshold=send_circuit_failure_threshold,
            breaker_cooldown_s=send_circuit_cooldown_s,
        )

    async def start(self) -> None:
        if self.outbound_webhook_url and HAS_HTTPX:
            self._outbound_client = httpx.AsyncClient()
        self.running = True
        logger.info("Canal Google Chat iniciado (modo webhook).")

    async def stop(self) -> None:
        if self._outbound_client:
            await self._outbound_client.aclose()
            self._outbound_client = None
        self.running = False
        logger.info("Canal Google Chat encerrado.")

    def _sender_candidates(self, sender: dict[str, Any]) -> list[str]:
        values: list[str] = []
        for key in ("name", "displayName", "email"):
            value = str(sender.get(key, "")).strip()
            if value:
                values.append(value)
        return values

    def _pairing_text(self, sender_id: str) -> str:
        req = issue_pairing_code("googlechat", str(sender_id), display=str(sender_id))
        return (
            "⛔ Acesso pendente de aprovação.\n"
            f"Código: {req['code']}\n"
            f"Aprove com: clawlite pairing approve googlechat {req['code']}"
        )

    def _extract_message_payload(self, payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        message = _as_dict(payload.get("message"))
        if not message:
            message = payload
        sender = _as_dict(message.get("sender"))
        space = _as_dict(message.get("space"))
        if not space:
            space = _as_dict(payload.get("space"))
        return message, sender, space

    def _message_text(self, message: dict[str, Any]) -> str:
        argument_text = str(message.get("argumentText", "")).strip()
        if argument_text:
            return argument_text
        return str(message.get("text", "")).strip()

    def _mentions_bot(self, raw_text: str) -> bool:
        text = str(raw_text or "").lower()
        if self.bot_user and self.bot_user in text:
            return True
        if "@clawlite" in text or "@openclaw" in text:
            return True
        return False

    async def process_webhook_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.running:
            return {}
        if not self._on_message_callback:
            return {}

        event_type = str(payload.get("type", "")).strip().upper()
        if event_type and event_type not in {"MESSAGE", "ADDED_TO_SPACE"}:
            return {}
        if event_type == "ADDED_TO_SPACE":
            return {"text": "👋 ClawLite conectado. Mencione o bot para começar."}

        message, sender, space = self._extract_message_payload(payload)
        text = self._message_text(message)
        if not text:
            return {}

        sender_candidates = self._sender_candidates(sender)
        sender_id = sender_candidates[0] if sender_candidates else "unknown"

        space_name = str(space.get("name", "")).strip()
        space_type = str(space.get("type", "")).strip().upper()
        is_dm = space_type == "DM"

        if self.allowed_spaces and space_name and space_name not in self.allowed_spaces:
            return {}

        if not is_sender_allowed("googlechat", sender_candidates, self.allowed_users):
            if self.pairing_enabled and is_dm:
                return {"text": self._pairing_text(sender_id)}
            return {}

        if not is_dm and self.require_mention and not str(message.get("argumentText", "")).strip():
            if not self._mentions_bot(str(message.get("text", ""))):
                return {}

        session_scope = "dm" if is_dm else "group"
        session_id = f"gc_{session_scope}_{space_name or 'unknown'}"

        try:
            reply = await self._on_message_callback(session_id, text)
        except Exception as exc:
            logger.error(f"Erro processando mensagem Google Chat: {exc}")
            return {"text": "⚠️ Erro interno ao processar a mensagem."}
        if not reply:
            return {}
        return {"text": str(reply)}

    async def send_message(self, session_id: str, text: str) -> None:
        if not self.outbound_webhook_url:
            self._outbound.unavailable(
                logger=logger,
                provider="googlechat-webhook",
                target=session_id,
                text=text,
                reason="outboundWebhookUrl não configurada",
                fallback="resposta apenas via webhook inbound",
            )
            return
        if not HAS_HTTPX:
            self._outbound.unavailable(
                logger=logger,
                provider="googlechat-webhook",
                target=session_id,
                text=text,
                reason="dependência httpx indisponível",
                fallback="resposta apenas via webhook inbound",
            )
            return
        if self._outbound_client is None:
            self._outbound_client = httpx.AsyncClient()

        idem_key = self._outbound.make_idempotency_key(session_id, text)

        async def _post() -> None:
            response = await self._outbound_client.post(
                self.outbound_webhook_url,
                json={"text": str(text)},
                headers={"X-Idempotency-Key": idem_key},
            )
            response.raise_for_status()

        await self._outbound.deliver(
            logger=logger,
            provider="googlechat-webhook",
            target=session_id,
            text=text,
            operation=_post,
            fallback="mensagem não entregue por indisponibilidade do webhook",
            idempotency_key=idem_key,
        )

    def outbound_metrics_snapshot(self) -> dict[str, Any]:
        return self._outbound.metrics_snapshot()
