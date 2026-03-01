from __future__ import annotations

import abc
from typing import Any, Callable, Coroutine


class BaseChannel(abc.ABC):
    """
    Interface abstrata base para todos os canais de comunicação do ClawLite.
    Garante que qualquer integração (Telegram, Discord, Slack, etc.) 
    siga o mesmo contrato operacional.
    """

    def __init__(self, name: str, token: str, **kwargs: Any) -> None:
        self.name = name
        self.token = token
        self.running = False
        self._on_message_callback: Callable[[str, str], Coroutine[Any, Any, None]] | None = None

    def on_message(self, callback: Callable[[str, str], Coroutine[Any, Any, None]]) -> None:
        """Registra o callback que processará as mensagens recebidas."""
        self._on_message_callback = callback

    @abc.abstractmethod
    async def start(self) -> None:
        """Inicia a conexão com o provedor do canal."""
        pass

    @abc.abstractmethod
    async def stop(self) -> None:
        """Encerra a conexão com o provedor do canal de forma gracefully."""
        pass

    @abc.abstractmethod
    async def send_message(self, session_id: str, text: str) -> None:
        """Envia uma mensagem de volta para o usuário no canal."""
        pass
