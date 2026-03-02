from __future__ import annotations

import asyncio
from typing import Any, Callable

from clawlite.bus.events import InboundEvent, OutboundEvent
from clawlite.bus.queue import MessageQueue
from clawlite.channels.base import BaseChannel
from clawlite.channels.dingtalk import DingTalkChannel
from clawlite.channels.discord import DiscordChannel
from clawlite.channels.email import EmailChannel
from clawlite.channels.feishu import FeishuChannel
from clawlite.channels.googlechat import GoogleChatChannel
from clawlite.channels.imessage import IMessageChannel
from clawlite.channels.irc import IRCChannel
from clawlite.channels.matrix import MatrixChannel
from clawlite.channels.mochat import MochatChannel
from clawlite.channels.qq import QQChannel
from clawlite.channels.signal import SignalChannel
from clawlite.channels.slack import SlackChannel
from clawlite.channels.telegram import TelegramChannel
from clawlite.channels.whatsapp import WhatsAppChannel


class EngineProtocol:
    async def run(self, *, session_id: str, user_text: str): ...


class ChannelManager:
    """Owns channel lifecycle and bridges channels <-> bus <-> engine."""

    def __init__(self, *, bus: MessageQueue, engine: EngineProtocol) -> None:
        self.bus = bus
        self.engine = engine
        self._registry: dict[str, type[BaseChannel]] = {
            "telegram": TelegramChannel,
            "discord": DiscordChannel,
            "slack": SlackChannel,
            "whatsapp": WhatsAppChannel,
            "signal": SignalChannel,
            "googlechat": GoogleChatChannel,
            "email": EmailChannel,
            "matrix": MatrixChannel,
            "irc": IRCChannel,
            "imessage": IMessageChannel,
            "dingtalk": DingTalkChannel,
            "feishu": FeishuChannel,
            "mochat": MochatChannel,
            "qq": QQChannel,
        }
        self._channels: dict[str, BaseChannel] = {}
        self._dispatcher_task: asyncio.Task[Any] | None = None

    def register(self, name: str, channel_cls: type[BaseChannel]) -> None:
        self._registry[name] = channel_cls

    async def _on_channel_message(self, session_id: str, user_id: str, text: str, metadata: dict[str, Any]) -> None:
        channel = str(metadata.get("channel", "")).strip() or session_id.split(":", 1)[0]
        await self.bus.publish_inbound(
            InboundEvent(
                channel=channel,
                session_id=session_id,
                user_id=user_id,
                text=text,
                metadata=metadata,
            )
        )

    async def _dispatch_loop(self) -> None:
        while True:
            event = await self.bus.next_inbound()
            result = await self.engine.run(session_id=event.session_id, user_text=event.text)

            target = str(event.metadata.get("chat_id") or event.user_id)
            outbound = OutboundEvent(
                channel=event.channel,
                session_id=event.session_id,
                target=target,
                text=result.text,
                metadata={"model": getattr(result, "model", "")},
            )
            await self.bus.publish_outbound(outbound)
            channel = self._channels.get(event.channel)
            if channel is not None:
                await channel.send(target=target, text=result.text)

    async def start(self, config: dict[str, Any]) -> None:
        channels_cfg = config.get("channels", {}) if isinstance(config, dict) else {}
        for name, row in channels_cfg.items():
            if not isinstance(row, dict):
                continue
            if not row.get("enabled", False):
                continue
            cls = self._registry.get(name)
            if cls is None:
                continue
            channel = cls(config=row, on_message=self._on_channel_message)
            self._channels[name] = channel
            await channel.start()

        if self._dispatcher_task is None:
            self._dispatcher_task = asyncio.create_task(self._dispatch_loop())

    async def stop(self) -> None:
        if self._dispatcher_task is not None:
            self._dispatcher_task.cancel()
            try:
                await self._dispatcher_task
            except asyncio.CancelledError:
                pass
            self._dispatcher_task = None

        for channel in list(self._channels.values()):
            await channel.stop()
        self._channels.clear()

    def status(self) -> dict[str, dict[str, Any]]:
        return {
            name: {
                "running": ch.running,
                "last_error": ch.health().last_error,
            }
            for name, ch in self._channels.items()
        }
