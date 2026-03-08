from __future__ import annotations

import asyncio
from typing import Any

from clawlite.channels.whatsapp import WhatsAppChannel


def test_whatsapp_receive_hook_emits_text_message_with_full_chat_id() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict[str, Any]]] = []

        async def _on_message(
            session_id: str,
            user_id: str,
            text: str,
            metadata: dict[str, Any],
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = WhatsAppChannel(
            config={"bridge_url": "http://localhost:3001"},
            on_message=_on_message,
        )

        processed = await channel.receive_hook(
            {
                "from": "5511999999999@c.us",
                "body": "hello from bridge",
                "type": "text",
                "messageId": "wa-1",
            }
        )

        assert processed is True
        assert len(emitted) == 1
        session_id, user_id, text, metadata = emitted[0]
        assert session_id == "whatsapp:5511999999999@c.us"
        assert user_id == "5511999999999"
        assert text == "hello from bridge"
        assert metadata["chat_id"] == "5511999999999@c.us"
        assert metadata["sender_id"] == "5511999999999"
        assert metadata["message_id"] == "wa-1"
        assert metadata["media_type"] == "text"
        assert metadata["media_url"] == ""

    asyncio.run(_scenario())


def test_whatsapp_receive_hook_supports_media_placeholder_and_dedupes() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict[str, Any]]] = []

        async def _on_message(
            session_id: str,
            user_id: str,
            text: str,
            metadata: dict[str, Any],
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = WhatsAppChannel(
            config={"bridge_url": "http://localhost:3001"},
            on_message=_on_message,
        )

        first = await channel.receive_hook(
            {
                "from": "5511888888888@c.us",
                "type": "image",
                "mediaUrl": "https://cdn.example/image.jpg",
                "messageId": "wa-media-1",
            }
        )
        duplicate = await channel.receive_hook(
            {
                "from": "5511888888888@c.us",
                "type": "image",
                "mediaUrl": "https://cdn.example/image.jpg",
                "messageId": "wa-media-1",
            }
        )

        assert first is True
        assert duplicate is False
        assert len(emitted) == 1
        session_id, user_id, text, metadata = emitted[0]
        assert session_id == "whatsapp:5511888888888@c.us"
        assert user_id == "5511888888888"
        assert text == "[whatsapp image]"
        assert metadata["media_type"] == "image"
        assert metadata["media_url"] == "https://cdn.example/image.jpg"

    asyncio.run(_scenario())


def test_whatsapp_receive_hook_filters_self_and_acl() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict[str, Any]]] = []

        async def _on_message(
            session_id: str,
            user_id: str,
            text: str,
            metadata: dict[str, Any],
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = WhatsAppChannel(
            config={
                "bridge_url": "http://localhost:3001",
                "allow_from": ["5511777777777", "@5511666666666"],
            },
            on_message=_on_message,
        )

        own_message = await channel.receive_hook(
            {
                "from": "5511777777777@c.us",
                "body": "ignore me",
                "messageId": "wa-self-1",
                "fromMe": True,
            }
        )
        blocked = await channel.receive_hook(
            {
                "from": "5511555555555@c.us",
                "body": "blocked",
                "messageId": "wa-block-1",
            }
        )
        allowed = await channel.receive_hook(
            {
                "from": "5511666666666@c.us",
                "body": "allowed",
                "messageId": "wa-allow-1",
            }
        )

        assert own_message is False
        assert blocked is False
        assert allowed is True
        assert len(emitted) == 1
        assert emitted[0][0] == "whatsapp:5511666666666@c.us"
        assert emitted[0][1] == "5511666666666"
        assert emitted[0][2] == "allowed"

    asyncio.run(_scenario())


def test_whatsapp_receive_hook_rejects_invalid_payloads() -> None:
    async def _scenario() -> None:
        channel = WhatsAppChannel(config={"bridge_url": "http://localhost:3001"})

        assert await channel.receive_hook({}) is False
        assert await channel.receive_hook({"from": "5511999999999@c.us"}) is False
        assert await channel.receive_hook({"body": "missing sender"}) is False

    asyncio.run(_scenario())
