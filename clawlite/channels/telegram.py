from __future__ import annotations

import asyncio
import logging
from typing import Any

try:
    from telegram import Update
    from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
    HAS_TELEGRAM = True
except ImportError:
    HAS_TELEGRAM = False

from clawlite.channels.base import BaseChannel

logger = logging.getLogger(__name__)


class TelegramChannel(BaseChannel):
    """
    Integração real com o Telegram via python-telegram-bot.
    Processa mensagens de usuários e envia as respostas de volta.
    """

    def __init__(self, token: str, allowed_accounts: list[str] = None, **kwargs: Any) -> None:
        super().__init__("telegram", token, **kwargs)
        self.allowed_accounts = allowed_accounts or []
        self._app: Application | None = None

    async def start(self) -> None:
        if not HAS_TELEGRAM:
            logger.error("python-telegram-bot não instalado. O canal Telegram não iniciará.")
            return

        self._app = Application.builder().token(self.token).build()

        self._app.add_handler(CommandHandler("start", self._command_start))
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_text_message))

        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling()
        self.running = True
        logger.info("Canal Telegram iniciado no modo polling.")

    async def stop(self) -> None:
        if self._app and self.running:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            self.running = False
            logger.info("Canal Telegram encerrado.")

    def _is_allowed(self, username: str | None) -> bool:
        if not self.allowed_accounts:
            return True  # Se vazio, aceita tudo (cuidado)
        if not username:
            return False
        return username.lower() in [u.lower() for u in self.allowed_accounts]

    async def _command_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_user or not update.message:
            return
        
        username = update.effective_user.username
        if not self._is_allowed(username):
            await update.message.reply_text("⛔ Acesso não autorizado a este bot.")
            return
            
        await update.message.reply_text("👋 Sou o ClawLite! Envie suas mensagens e eu irei processá-las.")

    async def _handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_user or not update.message or not update.message.text:
            return

        username = update.effective_user.username
        if not self._is_allowed(username):
            await update.message.reply_text("⛔ Acesso não autorizado.")
            return

        text = update.message.text
        chat_id = str(update.message.chat_id)
        
        # O session ID será o chat_id para manter o histórico
        session_id = f"tg_{chat_id}"

        # Se houver uma função de callback registrada pelo runtime, delega
        if self._on_message_callback:
            # Em background task para não travar o loop de polling
            asyncio.create_task(self._process_and_reply(session_id, text, chat_id))
        else:
            await update.message.reply_text("O núcleo ClawLite não está escutando no momento.")

    async def _process_and_reply(self, session_id: str, text: str, chat_id: str) -> None:
        """Invoca a callback principal da engine e envia o resultado pelo bot."""
        if not self._on_message_callback or not self._app or not self._app.bot:
            return
            
        try:
            # Chama o core (aqui preenche e lida com requests à LLM/Skills)
            # Espera-se que a callback retorne a string final gerada pelo modelo.
            reply_text = await self._on_message_callback(session_id, text)
            if reply_text:
                await self._app.bot.send_message(chat_id=int(chat_id), text=reply_text)
        except Exception as exc:
            logger.error(f"Telegram agent erro: {exc}")
            await self._app.bot.send_message(chat_id=int(chat_id), text="Houve um erro interno ao processar sua mensagem.")

    async def send_message(self, session_id: str, text: str) -> None:
        if not self._app or not self._app.bot:
            return
        # Assumindo que o session_id tem o formato 'tg_{chat_id}'
        if session_id.startswith("tg_"):
            chat_id = session_id[3:]
            try:
                await self._app.bot.send_message(chat_id=int(chat_id), text=text)
            except Exception as e:
                logger.error(f"Falha ao enviar mensagem Telegram para {chat_id}: {e}")
