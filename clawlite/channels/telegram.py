from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from clawlite.runtime.pairing import is_sender_allowed, issue_pairing_code

try:
    from telegram import Update
    from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

    HAS_TELEGRAM = True
except ImportError:
    HAS_TELEGRAM = False

from clawlite.channels.base import BaseChannel
from clawlite.channels.telegram_runtime import (
    TELEGRAM_TEXT_LIMIT,
    TelegramUpdateDedupe,
    TelegramUpdateOffsetStore,
    send_telegram_chunks_with_bot,
)

logger = logging.getLogger(__name__)


class TelegramChannel(BaseChannel):
    """
    Integração real com o Telegram via python-telegram-bot.
    Processa mensagens de usuários e envia as respostas de volta.
    """

    def __init__(
        self,
        token: str,
        allowed_accounts: list[str] | None = None,
        pairing_enabled: bool = False,
        mode: str = "polling",
        webhook_secret: str = "",
        webhook_path: str = "/api/webhooks/telegram",
        poll_interval_s: float = 1.0,
        poll_timeout_s: int = 30,
        reconnect_initial_s: float = 2.0,
        reconnect_max_s: float = 30.0,
        account_id: str = "",
        **kwargs: Any,
    ) -> None:
        # Compat: o ChannelManager pode injetar `name`.
        kwargs.pop("name", None)
        super().__init__("telegram", token, **kwargs)
        self.allowed_accounts = allowed_accounts or []
        self.pairing_enabled = bool(pairing_enabled)
        self.mode = str(mode or "polling").strip().lower()
        if self.mode not in {"polling", "webhook"}:
            self.mode = "polling"
        self.webhook_secret = str(webhook_secret or "").strip()
        self.webhook_path = str(webhook_path or "/api/webhooks/telegram").strip() or "/api/webhooks/telegram"
        self.poll_interval_s = max(0.2, float(poll_interval_s))
        self.poll_timeout_s = max(5, int(poll_timeout_s))
        self.reconnect_initial_s = max(1.0, float(reconnect_initial_s))
        self.reconnect_max_s = max(self.reconnect_initial_s, float(reconnect_max_s))

        self._app: Application | None = None
        self._runner_task: asyncio.Task[None] | None = None
        self._stop_event: asyncio.Event | None = None
        self._startup_event: asyncio.Event | None = None
        self._startup_error: str | None = None
        self._offset_store = TelegramUpdateOffsetStore(
            token=token,
            account_id=account_id,
        )
        self._last_update_id = self._offset_store.read()
        self._update_dedupe = TelegramUpdateDedupe()

    def is_webhook_mode(self) -> bool:
        return self.mode == "webhook"

    def _build_application(self) -> Application:
        app = Application.builder().token(self.token).build()
        app.add_handler(CommandHandler("start", self._command_start))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_text_message))
        return app

    @staticmethod
    def _normalize_chat_id(chat_id: str | int) -> str | int:
        raw = str(chat_id).strip()
        if raw and raw.lstrip("-").isdigit():
            try:
                return int(raw)
            except ValueError:
                return raw
        return raw

    @staticmethod
    def _parse_session_target(session_id: str) -> tuple[str | int | None, int | None]:
        raw = str(session_id or "").strip()
        if raw.startswith("tg_"):
            raw = raw[3:]
        if not raw:
            return None, None

        thread_id: int | None = None
        chat_raw = raw
        if ":topic:" in raw:
            chat_raw, _, tail = raw.partition(":topic:")
            if tail.strip().isdigit():
                thread_id = int(tail.strip())
        elif ":" in raw:
            # Compat com sessão no formato "chat:thread"
            head, _, tail = raw.partition(":")
            if tail.strip().isdigit():
                chat_raw = head
                thread_id = int(tail.strip())

        chat_id = TelegramChannel._normalize_chat_id(chat_raw)
        if chat_id in {"", None}:
            return None, None
        return chat_id, thread_id

    def _should_process_update(self, update_id: int | None) -> bool:
        if update_id is None:
            return True
        if self._update_dedupe.seen(update_id):
            return False
        if self._last_update_id is not None and update_id <= self._last_update_id:
            return False

        self._update_dedupe.add(update_id)
        self._last_update_id = update_id
        try:
            self._offset_store.write(update_id)
        except Exception as exc:
            logger.debug("Falha ao persistir offset do Telegram: %s", exc)
        return True

    async def _send_text(
        self,
        *,
        chat_id: str | int,
        text: str,
        message_thread_id: int | None = None,
    ) -> None:
        if not self._app or not self._app.bot:
            return
        await send_telegram_chunks_with_bot(
            self._app.bot,
            chat_id=chat_id,
            text=text,
            chunk_limit=TELEGRAM_TEXT_LIMIT,
            message_thread_id=message_thread_id,
        )

    async def _shutdown_application(self, app: Application | None) -> None:
        if not app:
            return
        try:
            if app.updater and app.updater.running:
                await app.updater.stop()
        except Exception:
            logger.debug("Falha ao parar updater do Telegram.", exc_info=True)
        try:
            await app.stop()
        except Exception:
            logger.debug("Falha ao parar app do Telegram.", exc_info=True)
        try:
            await app.shutdown()
        except Exception:
            logger.debug("Falha ao finalizar app do Telegram.", exc_info=True)

    async def _run_polling_supervisor(self) -> None:
        first_cycle = True
        backoff_s = self.reconnect_initial_s

        while self._stop_event and not self._stop_event.is_set():
            app = self._build_application()
            try:
                await app.initialize()
                await app.start()
                if not app.updater:
                    raise RuntimeError("Updater do Telegram indisponível.")
                await app.updater.start_polling(
                    poll_interval=self.poll_interval_s,
                    timeout=self.poll_timeout_s,
                    drop_pending_updates=False,
                )
                self._app = app
                self.running = True
                backoff_s = self.reconnect_initial_s
                if first_cycle and self._startup_event:
                    self._startup_event.set()
                    first_cycle = False
                logger.info("Canal Telegram iniciado no modo polling.")

                while self._stop_event and not self._stop_event.is_set():
                    if not app.updater.running:
                        raise RuntimeError("Polling do Telegram foi interrompido.")
                    await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.running = False
                if first_cycle:
                    self._startup_error = str(exc)
                    if self._startup_event:
                        self._startup_event.set()
                    first_cycle = False
                logger.error("Falha no loop do Telegram (%s): %s", self.mode, exc)
                if self._stop_event and self._stop_event.is_set():
                    break
                wait_s = min(backoff_s, self.reconnect_max_s)
                backoff_s = min(backoff_s * 1.8, self.reconnect_max_s)
                try:
                    if self._stop_event:
                        await asyncio.wait_for(self._stop_event.wait(), timeout=wait_s)
                except TimeoutError:
                    pass
            finally:
                await self._shutdown_application(app)
                if self._app is app:
                    self._app = None

        if first_cycle:
            self._startup_error = "Canal Telegram encerrou antes da primeira conexão."
            if self._startup_event:
                self._startup_event.set()

    async def start(self) -> None:
        if not HAS_TELEGRAM:
            logger.error("python-telegram-bot não instalado. O canal Telegram não iniciará.")
            return
        if self.running:
            return

        self._stop_event = asyncio.Event()
        self._startup_event = asyncio.Event()
        self._startup_error = None

        if self.mode == "webhook":
            app = self._build_application()
            await app.initialize()
            await app.start()
            self._app = app
            self.running = True
            logger.info("Canal Telegram iniciado no modo webhook (path=%s).", self.webhook_path)
            return

        self._runner_task = asyncio.create_task(self._run_polling_supervisor())
        assert self._startup_event is not None
        await asyncio.wait_for(self._startup_event.wait(), timeout=max(10.0, self.reconnect_initial_s * 3))
        if self._startup_error:
            raise RuntimeError(self._startup_error)

    async def stop(self) -> None:
        if self._stop_event:
            self._stop_event.set()

        if self._runner_task:
            try:
                await asyncio.wait_for(self._runner_task, timeout=15.0)
            except TimeoutError:
                self._runner_task.cancel()
                with contextlib.suppress(Exception):
                    await self._runner_task
            finally:
                self._runner_task = None

        if self.mode == "webhook":
            await self._shutdown_application(self._app)
            self._app = None

        self.running = False
        logger.info("Canal Telegram encerrado.")

    async def process_webhook_payload(self, payload: dict[str, Any]) -> None:
        if self.mode != "webhook":
            raise RuntimeError("Canal Telegram está configurado em modo polling.")
        if not self._app or not self._app.bot:
            raise RuntimeError("Canal Telegram não inicializado.")
        update = Update.de_json(payload, self._app.bot)
        if not update:
            return
        update_id = getattr(update, "update_id", None)
        if not self._should_process_update(update_id):
            return
        await self._app.process_update(update)

    def _is_allowed(self, user_id: str, username: str | None) -> bool:
        candidates = [str(user_id).strip()]
        if username:
            raw_user = str(username).strip()
            if raw_user:
                candidates.append(raw_user)
                candidates.append("@" + raw_user.lstrip("@"))
        return is_sender_allowed("telegram", candidates, self.allowed_accounts)

    def _pairing_text(self, user_id: str, username: str | None) -> str:
        req = issue_pairing_code("telegram", str(user_id), display=str(username or "").strip())
        return (
            "⛔ Acesso pendente de aprovação.\n"
            f"Código de pairing: {req['code']}\n"
            f"Aprove com: clawlite pairing approve telegram {req['code']}"
        )

    async def _command_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        if not update.effective_user or not update.message:
            return

        user_id = str(update.effective_user.id)
        username = update.effective_user.username
        if not self._is_allowed(user_id, username):
            if self.pairing_enabled:
                await update.message.reply_text(self._pairing_text(user_id, username))
            else:
                await update.message.reply_text("⛔ Acesso não autorizado a este bot.")
            return

        await update.message.reply_text("👋 Sou o ClawLite! Envie suas mensagens e eu irei processá-las.")

    async def _handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        if not update.effective_user or not update.message or not update.message.text:
            return
        update_id = getattr(update, "update_id", None)
        if not self._should_process_update(update_id):
            return

        user_id = str(update.effective_user.id)
        username = update.effective_user.username
        if not self._is_allowed(user_id, username):
            if self.pairing_enabled:
                await update.message.reply_text(self._pairing_text(user_id, username))
            else:
                await update.message.reply_text("⛔ Acesso não autorizado.")
            return

        text = update.message.text
        chat_id = str(update.message.chat_id)
        thread_id = str(getattr(update.message, "message_thread_id", "") or "")

        # O session ID será o chat_id para manter o histórico
        session_id = f"tg_{chat_id}:topic:{thread_id}" if thread_id else f"tg_{chat_id}"

        # Se houver uma função de callback registrada pelo runtime, delega
        if self._on_message_callback:
            # Em background task para não travar o loop de polling
            asyncio.create_task(
                self._process_and_reply(
                    session_id=session_id,
                    text=text,
                    chat_id=chat_id,
                    thread_id=(int(thread_id) if thread_id.isdigit() else None),
                )
            )
        else:
            await update.message.reply_text("O núcleo ClawLite não está escutando no momento.")

    async def _process_and_reply(
        self,
        *,
        session_id: str,
        text: str,
        chat_id: str,
        thread_id: int | None = None,
    ) -> None:
        """Invoca a callback principal da engine e envia o resultado pelo bot."""
        if not self._on_message_callback or not self._app or not self._app.bot:
            return

        try:
            # Chama o core (aqui preenche e lida com requests à LLM/Skills)
            # Espera-se que a callback retorne a string final gerada pelo modelo.
            reply_text = await self._on_message_callback(session_id, text)
            if reply_text:
                await self._send_text(chat_id=chat_id, text=reply_text, message_thread_id=thread_id)
        except Exception as exc:
            logger.error(f"Telegram agent erro: {exc}")
            await self._send_text(
                chat_id=chat_id,
                text="Houve um erro interno ao processar sua mensagem.",
                message_thread_id=thread_id,
            )

    async def send_message(self, session_id: str, text: str) -> None:
        if not self.running:
            return
        chat_id, thread_id = self._parse_session_target(session_id)
        if chat_id is None:
            return
        try:
            await self._send_text(chat_id=chat_id, text=text, message_thread_id=thread_id)
        except Exception as exc:
            logger.error("Falha ao enviar mensagem Telegram para %s: %s", chat_id, exc)
