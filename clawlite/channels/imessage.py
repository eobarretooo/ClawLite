from __future__ import annotations

import asyncio
import logging
import re
import shutil
import subprocess
from typing import Any

from clawlite.channels.base import BaseChannel
from clawlite.channels.outbound_resilience import OutboundResilience
from clawlite.runtime.pairing import is_sender_allowed, issue_pairing_code

logger = logging.getLogger(__name__)

_SAFE_ID = re.compile(r"[^a-zA-Z0-9_-]+")


def _safe_part(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "unknown"
    return _SAFE_ID.sub("_", raw)


class IMessageChannel(BaseChannel):
    """
    Canal iMessage (legacy) via imsg CLI.
    Inbound é recebido por bridge webhook (/api/webhooks/imessage).
    """

    def __init__(
        self,
        token: str = "",
        cli_path: str = "imsg",
        service: str = "auto",
        allowed_handles: list[str] | None = None,
        send_timeout_s: float = 15.0,
        send_backoff_base_s: float = 0.25,
        send_circuit_failure_threshold: int = 5,
        send_circuit_cooldown_s: float = 30.0,
        pairing_enabled: bool = False,
        **kwargs: Any,
    ) -> None:
        kwargs.pop("name", None)
        super().__init__("imessage", token, **kwargs)
        self.cli_path = str(cli_path).strip() or "imsg"
        self.service = str(service).strip().lower() or "auto"
        self.allowed_handles = allowed_handles or []
        self.pairing_enabled = bool(pairing_enabled)
        self.send_timeout_s = max(0.1, float(send_timeout_s))
        self._session_targets: dict[str, str] = {}
        self._outbound = OutboundResilience(
            "imessage",
            timeout_s=self.send_timeout_s,
            max_attempts=3,
            base_backoff_s=send_backoff_base_s,
            breaker_failure_threshold=send_circuit_failure_threshold,
            breaker_cooldown_s=send_circuit_cooldown_s,
        )

    async def start(self) -> None:
        if shutil.which(self.cli_path) is None:
            logger.warning(
                "Canal iMessage ativo sem binário '%s'. "
                "Inbound via webhook funciona, mas outbound por CLI ficará indisponível.",
                self.cli_path,
            )
        self.running = True
        logger.info("Canal iMessage iniciado.")

    async def stop(self) -> None:
        self.running = False
        logger.info("Canal iMessage encerrado.")

    def _pairing_text(self, sender: str) -> str:
        req = issue_pairing_code("imessage", str(sender), display=str(sender))
        return (
            "⛔ Acesso pendente de aprovação.\n"
            f"Código: {req['code']}\n"
            f"Aprove com: clawlite pairing approve imessage {req['code']}"
        )

    async def _send_via_cli(self, target: str, text: str) -> None:
        if not target:
            return
        if shutil.which(self.cli_path) is None:
            self._outbound.unavailable(
                logger=logger,
                provider="imessage-cli",
                target=target,
                text=text,
                reason=f"binário '{self.cli_path}' não encontrado",
                fallback="mensagem não entregue no iMessage",
            )
            return

        cmd = [self.cli_path, "send", str(target), str(text)]
        if self.service in {"imessage", "sms", "auto"}:
            cmd.extend(["--service", self.service])

        idem_key = self._outbound.make_idempotency_key(target, text)

        async def _run() -> None:
            def _call() -> None:
                subprocess.run(
                    cmd,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=self.send_timeout_s,
                )

            await asyncio.to_thread(_call)

        await self._outbound.deliver(
            logger=logger,
            provider="imessage-cli",
            target=target,
            text=text,
            operation=_run,
            fallback="mensagem não entregue no iMessage",
            idempotency_key=idem_key,
        )

    async def process_webhook_payload(self, payload: dict[str, Any]) -> None:
        if not self.running or not self._on_message_callback:
            return

        text = str(payload.get("text") or payload.get("message") or "").strip()
        sender = str(payload.get("from") or payload.get("handle") or "").strip()
        chat_id = str(payload.get("chat_id") or payload.get("chatId") or "").strip()
        is_group = bool(payload.get("is_group") or payload.get("isGroup"))

        if not text:
            return
        if not sender and not chat_id:
            return

        candidates = [c for c in [sender, chat_id] if c]
        if not is_sender_allowed("imessage", candidates, self.allowed_handles):
            if self.pairing_enabled and not is_group:
                await self._send_via_cli(sender or chat_id, self._pairing_text(sender or chat_id))
            return

        target = chat_id if is_group and chat_id else (sender or chat_id)
        session_id = f"imessage_{'group' if is_group else 'dm'}_{_safe_part(target)}"
        self._session_targets[session_id] = target

        try:
            reply = await self._on_message_callback(session_id, text)
        except Exception as exc:
            logger.error(f"Erro processando mensagem iMessage: {exc}")
            await self._send_via_cli(target, "⚠️ Erro interno ao processar a mensagem.")
            return
        if reply:
            await self._send_via_cli(target, str(reply))

    async def send_message(self, session_id: str, text: str) -> None:
        target = self._session_targets.get(session_id, "")
        if not target and session_id.startswith("imessage_dm_"):
            target = session_id[len("imessage_dm_") :]
        if not target and session_id.startswith("imessage_group_"):
            target = session_id[len("imessage_group_") :]
        await self._send_via_cli(target, text)

    def outbound_metrics_snapshot(self) -> dict[str, Any]:
        return self._outbound.metrics_snapshot()
