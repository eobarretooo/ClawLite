from __future__ import annotations

import asyncio
import logging
from typing import Any

from clawlite.channels.base import BaseChannel

try:
    from slack_bolt.app.async_app import AsyncApp
    from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
    HAS_SLACK = True
except ImportError:
    HAS_SLACK = False

logger = logging.getLogger(__name__)


class SlackChannel(BaseChannel):
    """
    Integração com Slack via Socket Mode (slack-bolt).
    Ideal para cenários locais sem webhook público.
    Requer duas credenciais: SLACK_BOT_TOKEN e SLACK_APP_TOKEN.
    *Assumimos que o 'token' seja o bot_token e que app_token venha em kwargs.
    """

    def __init__(self, token: str, app_token: str = "", allowed_channels: list[str] = None, **kwargs: Any) -> None:
        super().__init__("slack", token, **kwargs)
        self.app_token = app_token or kwargs.get("app_token", "")
        self.allowed_channels = allowed_channels or []
        self._app: AsyncApp | None = None
        self._handler: AsyncSocketModeHandler | None = None
        self._app_task: asyncio.Task | None = None

    async def start(self) -> None:
        if not HAS_SLACK:
            logger.error("slack-bolt não instalado. O canal Slack não iniciará.")
            return

        if not self.app_token:
            logger.error("Falha ao iniciar SlackChannel: app_token é obrigatório para Socket Mode (xapp-...).")
            return

        self._app = AsyncApp(token=self.token)

        @self._app.event("message")
        async def handle_message_events(body: dict[str, Any], say: Any, logger_obj: logging.Logger) -> None:
            event = body.get("event", {})
            # Ignora mensagens de bots
            if event.get("bot_id"):
                return

            text = event.get("text", "").strip()
            channel_id = event.get("channel", "")
            
            if self.allowed_channels and channel_id not in self.allowed_channels:
                return
                
            if not text:
                return

            session_id = f"sl_{channel_id}"
            
            if self._on_message_callback:
                # O SocketModeHandler gerencia concurrency internamente de forma asyncio safe
                asyncio.create_task(self._process_and_reply(session_id, text, say, channel_id))

        self._handler = AsyncSocketModeHandler(self._app, self.app_token)
        self._app_task = asyncio.create_task(self._handler.start_async())
        self.running = True
        logger.info("Canal Slack iniciado no Socket Mode.")

    async def _process_and_reply(self, session_id: str, text: str, say: Any, channel_id: str) -> None:
        if not self._on_message_callback:
            return
            
        try:
            reply_text = await self._on_message_callback(session_id, text)
            if reply_text:
                await say(text=reply_text, channel=channel_id)
        except Exception as exc:
            logger.error(f"Erro processando mensagem Slack: {exc}")
            await say(text="⚠️ Houve um erro processando sua requisição.", channel=channel_id)

    async def stop(self) -> None:
        if self._handler and self.running:
            await self._handler.close_async()
            if self._app_task:
                self._app_task.cancel()
            self.running = False
            logger.info("Canal Slack encerrado.")

    async def send_message(self, session_id: str, text: str) -> None:
        if not self._app or not self.running:
            return
            
        if session_id.startswith("sl_"):
            channel_id = session_id[3:]
            try:
                await self._app.client.chat_postMessage(channel=channel_id, text=text)
            except Exception as e:
                logger.error(f"Falha ao enviar mensagem Slack: {e}")
