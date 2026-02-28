from __future__ import annotations

import logging
from typing import Any

from clawlite.channels.base import BaseChannel
from clawlite.channels.telegram import TelegramChannel
from clawlite.channels.discord import DiscordChannel
from clawlite.channels.slack import SlackChannel
from clawlite.channels.whatsapp import WhatsAppChannel
from clawlite.config.settings import load_config
from clawlite.core.agent import run_task_with_meta

logger = logging.getLogger(__name__)

# Registry of available channel classes
CHANNEL_CLASSES: dict[str, type[BaseChannel]] = {
    "telegram": TelegramChannel,
    "discord": DiscordChannel,
    "slack": SlackChannel,
    "whatsapp": WhatsAppChannel,
}


class ChannelManager:
    """Gerencia o ciclo de vida dos canais de comunicação."""

    def __init__(self) -> None:
        self.active_channels: dict[str, BaseChannel] = {}

    async def _handle_message(self, session_id: str, text: str) -> str:
        """
        Callback central para processar mensagens recebidas de qualquer canal.
        Roteia diretamente para o core LLM.
        """
        import asyncio
        # O run_task_with_meta é síncrono, então rodamos em uma thread
        prompt = text.strip()
        try:
            output, meta = await asyncio.to_thread(run_task_with_meta, prompt)
            return output
        except Exception as exc:
            logger.error(f"Erro no processamento da mensagem do canal: {exc}")
            return "Ocorreu um erro interno ao processar a requisição."

    async def start_all(self) -> None:
        """Inicia todos os canais configurados e habilitados."""
        cfg = load_config()
        channels_cfg = cfg.get("channels", {})

        for ch_name, ch_data in channels_cfg.items():
            if not isinstance(ch_data, dict):
                continue
                
            enabled = bool(ch_data.get("enabled", False))
            token = str(ch_data.get("token", "")).strip()
            
            if not enabled or not token:
                continue

            channel_cls = CHANNEL_CLASSES.get(ch_name.lower())
            if not channel_cls:
                logger.warning(f"Tipo de canal não suportado: {ch_name}")
                continue

            try:
                # Instancia o canal
                channel = channel_cls(token=token, name=ch_name)
                # Registra o roteador de mensagens central
                channel.on_message(self._handle_message)
                
                await channel.start()
                self.active_channels[ch_name] = channel
                logger.info(f"Canal '{ch_name}' habilitado e conectado.")
            except Exception as exc:
                logger.error(f"Falha ao iniciar canal '{ch_name}': {exc}")

    async def stop_all(self) -> None:
        """Para todos os canais ativos."""
        for ch_name, channel in self.active_channels.items():
            try:
                await channel.stop()
                logger.info(f"Canal '{ch_name}' desconectado.")
            except Exception as exc:
                logger.error(f"Erro ao parar canal '{ch_name}': {exc}")
        self.active_channels.clear()

# Global manager instance
manager = ChannelManager()
