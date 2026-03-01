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


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


class SignalChannel(BaseChannel):
    """
    Canal Signal com foco em compatibilidade:
    - Inbound por webhook/bridge (/api/webhooks/signal)
    - Outbound via signal-cli quando disponível
    """

    def __init__(
        self,
        token: str = "",
        account: str = "",
        cli_path: str = "signal-cli",
        http_url: str = "",
        allowed_numbers: list[str] | None = None,
        send_timeout_s: float = 15.0,
        send_backoff_base_s: float = 0.25,
        pairing_enabled: bool = False,
        **kwargs: Any,
    ) -> None:
        kwargs.pop("name", None)
        super().__init__("signal", token, **kwargs)
        self.account = str(account).strip()
        self.cli_path = str(cli_path).strip() or "signal-cli"
        self.http_url = str(http_url).strip()
        self.allowed_numbers = allowed_numbers or []
        self.pairing_enabled = bool(pairing_enabled)
        self.send_timeout_s = max(0.1, float(send_timeout_s))
        self._session_targets: dict[str, str] = {}
        self._http_client: httpx.AsyncClient | None = None
        self._outbound = OutboundResilience(
            "signal",
            timeout_s=self.send_timeout_s,
            max_attempts=3,
            base_backoff_s=send_backoff_base_s,
        )

    async def start(self) -> None:
        if self.http_url:
            if HAS_HTTPX:
                self._http_client = httpx.AsyncClient()
            logger.info("Canal Signal iniciado em modo daemon externo: %s", self.http_url)
            self.running = True
            return
        if shutil.which(self.cli_path) is None:
            logger.warning(
                "Canal Signal ativo sem binário '%s'. "
                "Inbound via webhook funciona, mas outbound por CLI ficará indisponível.",
                self.cli_path,
            )
        self.running = True
        logger.info("Canal Signal iniciado.")

    async def stop(self) -> None:
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
        self.running = False
        logger.info("Canal Signal encerrado.")

    def _pairing_text(self, sender: str) -> str:
        req = issue_pairing_code("signal", str(sender), display=str(sender))
        return (
            "⛔ Acesso pendente de aprovação.\n"
            f"Código: {req['code']}\n"
            f"Aprove com: clawlite pairing approve signal {req['code']}"
        )

    def _extract_payload(self, payload: dict[str, Any]) -> tuple[str, str, str]:
        envelope = _as_dict(payload.get("envelope"))
        data_message = _as_dict(envelope.get("dataMessage"))
        group_info = _as_dict(data_message.get("groupInfo"))

        text = str(
            payload.get("text")
            or payload.get("message")
            or data_message.get("message")
            or data_message.get("text")
            or ""
        ).strip()
        sender = str(
            payload.get("from")
            or payload.get("source")
            or envelope.get("source")
            or envelope.get("sourceNumber")
            or envelope.get("sourceUuid")
            or ""
        ).strip()
        group_id = str(
            payload.get("group_id")
            or payload.get("groupId")
            or group_info.get("groupId")
            or ""
        ).strip()
        return text, sender, group_id

    async def _send_via_http_relay(self, target: str, text: str) -> bool:
        if not self.http_url:
            return False
        if not HAS_HTTPX:
            self._outbound.unavailable(
                logger=logger,
                provider="signal-http-relay",
                target=target,
                text=text,
                reason="dependência httpx indisponível",
                fallback="tentando fallback para signal-cli",
            )
            return False
        if self._http_client is None:
            self._http_client = httpx.AsyncClient()

        idem_key = self._outbound.make_idempotency_key(target, text)

        async def _post() -> None:
            response = await self._http_client.post(
                self.http_url,
                json={
                    "target": target,
                    "text": str(text),
                    "account": self.account,
                    "idempotency_key": idem_key,
                },
                headers={"X-Idempotency-Key": idem_key},
            )
            response.raise_for_status()

        result = await self._outbound.deliver(
            logger=logger,
            provider="signal-http-relay",
            target=target,
            text=text,
            operation=_post,
            fallback="tentando fallback para signal-cli",
            idempotency_key=idem_key,
        )
        return bool(result.ok)

    async def _send_via_cli(self, target: str, text: str) -> None:
        if not target:
            return

        relay_sent = await self._send_via_http_relay(target, text)
        if relay_sent:
            return

        if shutil.which(self.cli_path) is None:
            self._outbound.unavailable(
                logger=logger,
                provider="signal-cli",
                target=target,
                text=text,
                reason=f"binário '{self.cli_path}' não encontrado",
                fallback="mensagem não entregue no Signal",
            )
            return

        is_group = target.startswith("signal:group:")
        clean_target = target.replace("signal:group:", "", 1) if is_group else target

        cmd: list[str] = [self.cli_path]
        if self.account:
            cmd.extend(["-a", self.account])
        cmd.extend(["send", "-m", str(text)])
        if is_group:
            cmd.extend(["-g", clean_target])
        else:
            cmd.append(clean_target)

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
            provider="signal-cli",
            target=target,
            text=text,
            operation=_run,
            fallback="mensagem não entregue no Signal",
            idempotency_key=idem_key,
        )

    async def process_webhook_payload(self, payload: dict[str, Any]) -> None:
        if not self.running or not self._on_message_callback:
            return

        text, sender, group_id = self._extract_payload(payload)
        if not text:
            return

        is_dm = not group_id
        sender_uuid = str(payload.get("source_uuid") or "").strip()
        candidates = [c for c in [sender, sender_uuid, f"uuid:{sender_uuid}" if sender_uuid else ""] if c]
        if not candidates:
            return

        reply_target = f"signal:group:{group_id}" if group_id else sender
        if not is_sender_allowed("signal", candidates, self.allowed_numbers):
            if self.pairing_enabled and is_dm:
                await self._send_via_cli(reply_target, self._pairing_text(candidates[0]))
            return

        session_id = f"signal_{'dm' if is_dm else 'group'}_{_safe_part(reply_target)}"
        self._session_targets[session_id] = reply_target

        try:
            reply = await self._on_message_callback(session_id, text)
        except Exception as exc:
            logger.error(f"Erro processando mensagem Signal: {exc}")
            await self._send_via_cli(reply_target, "⚠️ Erro interno ao processar a mensagem.")
            return

        if reply:
            await self._send_via_cli(reply_target, str(reply))

    async def send_message(self, session_id: str, text: str) -> None:
        target = self._session_targets.get(session_id, "")
        if not target and session_id.startswith("signal_dm_"):
            target = session_id[len("signal_dm_") :]
        if not target and session_id.startswith("signal_group_"):
            target = session_id[len("signal_group_") :]
        await self._send_via_cli(target, text)
