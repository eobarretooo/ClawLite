from __future__ import annotations

import asyncio
import logging
from typing import Any

from clawlite.runtime.pairing import is_sender_allowed, issue_pairing_code
from clawlite.channels.base import BaseChannel

try:
    import discord
    from discord.ext import commands
    HAS_DISCORD = True
except ImportError:
    HAS_DISCORD = False

logger = logging.getLogger(__name__)


class DiscordChannel(BaseChannel):
    """
    Integração real com o Discord via discord.py.
    """

    def __init__(
        self,
        token: str,
        allowed_channels: list[str] = None,
        allowed_users: list[str] = None,
        pairing_enabled: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__("discord", token, **kwargs)
        self.allowed_channels = allowed_channels or []
        self.allowed_users = allowed_users or []
        self.pairing_enabled = bool(pairing_enabled)
        self._client: discord.Client | None = None
        self._app_task: asyncio.Task | None = None

    def _is_user_allowed(self, user_id: str, username: str) -> bool:
        candidates = [str(user_id).strip(), str(username).strip()]
        return is_sender_allowed("discord", candidates, self.allowed_users)

    def _pairing_text(self, user_id: str, username: str) -> str:
        req = issue_pairing_code("discord", str(user_id), display=username)
        return (
            "⛔ Acesso pendente de aprovação.\n"
            f"Código: {req['code']}\n"
            f"Aprove com: clawlite pairing approve discord {req['code']}"
        )

    async def start(self) -> None:
        if not HAS_DISCORD:
            logger.error("discord.py não instalado. O canal Discord não iniciará.")
            return

        intents = discord.Intents.default()
        intents.message_content = True
        self._client = discord.Client(intents=intents)

        @self._client.event
        async def on_ready() -> None:
            logger.info(f"Canal Discord iniciado como {self._client.user}")

        @self._client.event
        async def on_message(message: discord.Message) -> None:
            # Ignora mensagens do próprio bot
            if message.author == self._client.user:
                return

            if self.allowed_channels and str(message.channel.id) not in self.allowed_channels:
                return

            text = message.content.strip()
            if not text:
                return

            author_id = str(message.author.id)
            author_name = getattr(message.author, "name", "") or author_id
            if not self._is_user_allowed(author_id, str(author_name)):
                if self.pairing_enabled:
                    try:
                        await message.channel.send(self._pairing_text(author_id, str(author_name)))
                    except Exception:
                        logger.exception("Falha ao enviar mensagem de pairing no Discord.")
                return

            chat_id = str(message.channel.id)
            session_id = f"dc_{chat_id}"

            if self._on_message_callback:
                # Dispara async no background context do event loop
                asyncio.create_task(self._process_and_reply(session_id, text, message.channel))

        # Discord.py start precisa rodar em background já que bloqueia
        self._app_task = asyncio.create_task(self._client.start(self.token))
        self.running = True

    async def _process_and_reply(self, session_id: str, text: str, channel: discord.abc.Messageable) -> None:
        if not self._on_message_callback:
            return
            
        try:
            # Exibe typing indicator enquanto a LLM processa
            async with channel.typing():
                reply_text = await self._on_message_callback(session_id, text)
                if reply_text:
                    # Discord tem limite de 2000 chars por mensagem, vamos truncar ou fazer chunks
                    # Aqui faremos chunks básicos se passar do limite
                    for chunk in [reply_text[i:i+1990] for i in range(0, len(reply_text), 1990)]:
                        await channel.send(chunk)
        except Exception as exc:
            logger.error(f"Erro processando mensagem Discord: {exc}")
            await channel.send("⚠️ Houve um erro processando sua requisição.")

    async def stop(self) -> None:
        if self._client and self.running:
            await self._client.close()
            if self._app_task:
                self._app_task.cancel()
            self.running = False
            logger.info("Canal Discord encerrado.")

    async def send_message(self, session_id: str, text: str) -> None:
        if not self._client or not self.running:
            return
            
        if session_id.startswith("dc_"):
            chat_id = int(session_id[3:])
            channel = self._client.get_channel(chat_id)
            if not channel:
                # Tenta fazer fetch caso não esteja no cache local
                try:
                    channel = await self._client.fetch_channel(chat_id)
                except Exception:
                    pass
                    
            if channel and hasattr(channel, 'send'):
                try:
                    for chunk in [text[i:i+1990] for i in range(0, len(text), 1990)]:
                        await channel.send(chunk)
                except Exception as e:
                    logger.error(f"Falha ao enviar mensagem Discord: {e}")
