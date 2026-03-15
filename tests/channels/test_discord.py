from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from clawlite.channels.discord import DiscordChannel


def _response(
    *,
    status: int,
    url: str,
    payload: dict[str, Any] | None = None,
) -> httpx.Response:
    request = httpx.Request("POST", url)
    if payload is None:
        return httpx.Response(status, request=request)
    return httpx.Response(status, json=payload, request=request)


class _FakeClient:
    def __init__(self, responses: list[httpx.Response]) -> None:
        self._responses = list(responses)
        self.posts: list[tuple[str, dict[str, Any]]] = []
        self.closed = False

    async def post(
        self, url: str, json: dict[str, Any] | None = None
    ) -> httpx.Response:
        self.posts.append((url, dict(json or {})))
        if not self._responses:
            raise AssertionError("unexpected discord post")
        return self._responses.pop(0)

    async def aclose(self) -> None:
        self.closed = True


class _FakeWebSocket:
    def __init__(self, frames: list[dict[str, Any]]) -> None:
        self._frames = [json.dumps(frame) for frame in frames]
        self.sent: list[dict[str, Any]] = []

    def __aiter__(self):
        return self

    async def __anext__(self) -> str:
        if not self._frames:
            raise StopAsyncIteration
        return self._frames.pop(0)

    async def send(self, raw: str) -> None:
        self.sent.append(json.loads(raw))

    async def close(self) -> None:
        return None


def test_discord_channel_reuses_persistent_client_across_sends(monkeypatch) -> None:
    async def _scenario() -> None:
        client = _FakeClient(
            [
                _response(
                    status=200,
                    url="https://discord.com/api/v10/channels/123/messages",
                    payload={"id": "m1"},
                ),
                _response(
                    status=200,
                    url="https://discord.com/api/v10/channels/123/messages",
                    payload={"id": "m2"},
                ),
            ]
        )
        created: list[_FakeClient] = []

        def _factory(*args, **kwargs):
            del args, kwargs
            created.append(client)
            return client

        monkeypatch.setattr(httpx, "AsyncClient", _factory)

        channel = DiscordChannel(config={"token": "bot-token"})
        await channel.start()

        first = await channel.send(target="123", text="hello")
        second = await channel.send(target="123", text="again")

        await channel.stop()

        assert first == "discord:sent:m1"
        assert second == "discord:sent:m2"
        assert len(created) == 1
        assert len(client.posts) == 2
        assert client.closed is True

    asyncio.run(_scenario())


def test_discord_send_retries_429_using_retry_after(monkeypatch) -> None:
    async def _scenario() -> None:
        first = _response(
            status=429,
            url="https://discord.com/api/v10/channels/123/messages",
            payload={"retry_after": 1.25},
        )
        second = _response(
            status=200,
            url="https://discord.com/api/v10/channels/123/messages",
            payload={"id": "ok-1"},
        )
        client = _FakeClient([first, second])

        def _factory(*args, **kwargs):
            del args, kwargs
            return client

        monkeypatch.setattr(httpx, "AsyncClient", _factory)

        channel = DiscordChannel(
            config={"token": "bot-token", "send_retry_attempts": 2}
        )
        await channel.start()

        sleep_mock = AsyncMock()
        with patch("clawlite.channels.discord.asyncio.sleep", new=sleep_mock):
            out = await channel.send(target="123", text="hello")

        await channel.stop()

        assert out == "discord:sent:ok-1"
        assert len(client.posts) == 2
        assert sleep_mock.await_count == 1
        assert sleep_mock.await_args.args == (1.25,)

    asyncio.run(_scenario())


def test_discord_send_user_target_creates_dm_channel(monkeypatch) -> None:
    async def _scenario() -> None:
        client = _FakeClient(
            [
                _response(
                    status=200,
                    url="https://discord.com/api/v10/users/@me/channels",
                    payload={"id": "dm-123"},
                ),
                _response(
                    status=200,
                    url="https://discord.com/api/v10/channels/dm-123/messages",
                    payload={"id": "m-dm-1"},
                ),
            ]
        )

        def _factory(*args, **kwargs):
            del args, kwargs
            return client

        monkeypatch.setattr(httpx, "AsyncClient", _factory)

        channel = DiscordChannel(config={"token": "bot-token"})
        await channel.start()

        out = await channel.send(target="user:746561804100042812", text="hello")

        await channel.stop()

        assert out == "discord:sent:m-dm-1"
        assert client.posts[0] == (
            "https://discord.com/api/v10/users/@me/channels",
            {"recipient_id": "746561804100042812"},
        )
        assert client.posts[1][0] == "https://discord.com/api/v10/channels/dm-123/messages"
        assert client.posts[1][1]["content"] == "hello"

    asyncio.run(_scenario())


def test_discord_send_channel_target_accepts_prefix(monkeypatch) -> None:
    async def _scenario() -> None:
        client = _FakeClient(
            [
                _response(
                    status=200,
                    url="https://discord.com/api/v10/channels/123/messages",
                    payload={"id": "m-chan-1"},
                )
            ]
        )

        def _factory(*args, **kwargs):
            del args, kwargs
            return client

        monkeypatch.setattr(httpx, "AsyncClient", _factory)

        channel = DiscordChannel(config={"token": "bot-token"})
        await channel.start()

        out = await channel.send(target="channel:123", text="hello")

        await channel.stop()

        assert out == "discord:sent:m-chan-1"
        assert client.posts == [
            ("https://discord.com/api/v10/channels/123/messages", {"content": "hello"})
        ]

    asyncio.run(_scenario())


def test_discord_send_ambiguous_target_404_falls_back_to_dm(monkeypatch) -> None:
    async def _scenario() -> None:
        client = _FakeClient(
            [
                _response(
                    status=404,
                    url="https://discord.com/api/v10/channels/746561804100042812/messages",
                ),
                _response(
                    status=200,
                    url="https://discord.com/api/v10/users/@me/channels",
                    payload={"id": "dm-404"},
                ),
                _response(
                    status=200,
                    url="https://discord.com/api/v10/channels/dm-404/messages",
                    payload={"id": "m-fallback"},
                ),
            ]
        )

        def _factory(*args, **kwargs):
            del args, kwargs
            return client

        monkeypatch.setattr(httpx, "AsyncClient", _factory)

        channel = DiscordChannel(config={"token": "bot-token"})
        await channel.start()

        out = await channel.send(target="746561804100042812", text="hello")

        await channel.stop()

        assert out == "discord:sent:m-fallback"
        assert client.posts[0][0] == "https://discord.com/api/v10/channels/746561804100042812/messages"
        assert client.posts[1] == (
            "https://discord.com/api/v10/users/@me/channels",
            {"recipient_id": "746561804100042812"},
        )
        assert client.posts[2][0] == "https://discord.com/api/v10/channels/dm-404/messages"

    asyncio.run(_scenario())


def test_discord_gateway_loop_identifies_and_emits_message() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict[str, Any]]] = []

        async def _on_message(
            session_id: str,
            user_id: str,
            text: str,
            metadata: dict[str, Any],
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = DiscordChannel(config={"token": "bot-token"}, on_message=_on_message)
        channel._running = True
        channel._ws = _FakeWebSocket(
            [
                {"op": 10, "d": {"heartbeat_interval": 30000}},
                {
                    "op": 0,
                    "t": "READY",
                    "s": 1,
                    "d": {
                        "session_id": "sess-1",
                        "resume_gateway_url": "wss://resume.example",
                        "user": {"id": "bot-1"},
                    },
                },
                {
                    "op": 0,
                    "t": "MESSAGE_CREATE",
                    "s": 2,
                    "d": {
                        "id": "m1",
                        "channel_id": "123",
                        "guild_id": "456",
                        "content": "hello from discord",
                        "attachments": [],
                        "author": {"id": "user-1", "username": "alice", "bot": False},
                    },
                },
            ]
        )

        with patch.object(channel, "_start_heartbeat", AsyncMock()) as start_heartbeat:
            with patch.object(channel, "_start_typing", AsyncMock()) as start_typing:
                with patch.object(channel, "_stop_typing", AsyncMock()) as stop_typing:
                    await channel._gateway_loop()

        assert start_heartbeat.await_count == 1
        assert channel._session_id == "sess-1"
        assert channel._resume_url == "wss://resume.example"
        assert channel._bot_user_id == "bot-1"
        assert channel._ws.sent[0]["op"] == 2
        assert len(emitted) == 1
        session_id, user_id, text, metadata = emitted[0]
        assert session_id == "discord:123"
        assert user_id == "user-1"
        assert text == "hello from discord"
        assert metadata["channel"] == "discord"
        assert metadata["channel_id"] == "123"
        assert metadata["guild_id"] == "456"
        start_typing.assert_awaited_once_with("123")
        stop_typing.assert_awaited_once_with("123")

    asyncio.run(_scenario())


def test_discord_message_create_filters_self_and_acl() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict[str, Any]]] = []

        async def _on_message(
            session_id: str,
            user_id: str,
            text: str,
            metadata: dict[str, Any],
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = DiscordChannel(
            config={"token": "bot-token", "allow_from": ["@allowed"]},
            on_message=_on_message,
        )
        channel._bot_user_id = "bot-1"

        with patch.object(channel, "_start_typing", AsyncMock()):
            with patch.object(channel, "_stop_typing", AsyncMock()):
                await channel._handle_message_create(
                    {
                        "id": "m1",
                        "channel_id": "123",
                        "content": "blocked",
                        "attachments": [],
                        "author": {
                            "id": "bot-1",
                            "username": "clawlite",
                            "bot": False,
                        },
                    }
                )
                await channel._handle_message_create(
                    {
                        "id": "m2",
                        "channel_id": "123",
                        "content": "blocked acl",
                        "attachments": [],
                        "author": {"id": "u-2", "username": "bob", "bot": False},
                    }
                )
                await channel._handle_message_create(
                    {
                        "id": "m3",
                        "channel_id": "123",
                        "content": "",
                        "attachments": [{"id": "a1", "filename": "image.png", "url": "https://cdn.example/image.png"}],
                        "author": {
                            "id": "u-3",
                            "username": "allowed",
                            "bot": False,
                        },
                    }
                )

        assert len(emitted) == 1
        assert emitted[0][2] == "[discord attachment: image.png]"
        assert emitted[0][3]["attachments"][0]["filename"] == "image.png"

    asyncio.run(_scenario())


def test_discord_operator_status_reports_gateway_state() -> None:
    channel = DiscordChannel(config={"token": "bot-token"})
    channel._running = True
    channel._session_id = "sess-1"
    channel._resume_url = "wss://resume.example"
    channel._sequence = 42
    channel._bot_user_id = "bot-1"

    payload = channel.operator_status()

    assert payload["running"] is True
    assert payload["session_id"] == "sess-1"
    assert payload["resume_url"] == "wss://resume.example"
    assert payload["sequence"] == 42
    assert payload["bot_user_id"] == "bot-1"


def test_discord_operator_refresh_transport_resets_gateway_state() -> None:
    async def _scenario() -> None:
        channel = DiscordChannel(config={"token": "bot-token"})
        channel._running = True
        channel._session_id = "sess-1"
        channel._resume_url = "wss://resume.example"
        channel._sequence = 42
        channel._bot_user_id = "bot-1"
        gateway_task = asyncio.create_task(asyncio.sleep(3600))
        heartbeat_task = asyncio.create_task(asyncio.sleep(3600))
        channel._gateway_task = gateway_task
        channel._heartbeat_task = heartbeat_task

        with patch.object(channel, "start", AsyncMock()) as start_mock:
            payload = await channel.operator_refresh_transport()

        assert payload["ok"] is True
        assert payload["gateway_restarted"] is True
        assert start_mock.await_count == 1
        assert channel._session_id == ""
        assert channel._resume_url == ""
        assert channel._sequence is None
        assert channel._bot_user_id == ""

    asyncio.run(_scenario())


# --- New tests for reaction intents, add_reaction(), and REACTION_ADD handler ---


def _make_channel():
    return DiscordChannel(config={"token": "test-token"})


def test_discord_gateway_intents_include_reactions():
    from clawlite.channels.discord import DISCORD_DEFAULT_GATEWAY_INTENTS
    assert DISCORD_DEFAULT_GATEWAY_INTENTS & 1024, "Missing GUILD_MESSAGE_REACTIONS"
    assert DISCORD_DEFAULT_GATEWAY_INTENTS & 8192, "Missing DIRECT_MESSAGE_REACTIONS"


@pytest.mark.asyncio
async def test_add_reaction_success():
    ch = _make_channel()
    ch._running = True
    mock_resp = MagicMock()
    mock_resp.status_code = 204
    mock_client = AsyncMock()
    mock_client.put = AsyncMock(return_value=mock_resp)
    ch._client = mock_client

    result = await ch.add_reaction("111", "222", "👍")
    assert result is True
    mock_client.put.assert_called_once()
    call_url = mock_client.put.call_args[0][0]
    assert "/channels/111/messages/222/reactions/" in call_url
    assert "/@me" in call_url


@pytest.mark.asyncio
async def test_add_reaction_not_running_returns_false():
    ch = _make_channel()
    ch._running = False
    result = await ch.add_reaction("111", "222", "👍")
    assert result is False


@pytest.mark.asyncio
async def test_add_reaction_empty_emoji_returns_false():
    ch = _make_channel()
    ch._running = True
    ch._client = AsyncMock()
    result = await ch.add_reaction("111", "222", "")
    assert result is False


@pytest.mark.asyncio
async def test_gateway_handles_reaction_add_event():
    received = []
    async def on_msg(session_id, user_id, text, metadata):
        received.append((session_id, user_id, text, metadata))

    ch = _make_channel()
    ch.on_message = on_msg
    ch._bot_user_id = "bot-999"

    reaction_payload = {
        "op": 0, "t": "MESSAGE_REACTION_ADD", "s": 1,
        "d": {
            "user_id": "user-1",
            "channel_id": "chan-1",
            "message_id": "msg-1",
            "guild_id": "guild-1",
            "emoji": {"name": "👍", "id": None},
        }
    }
    result = await ch._handle_gateway_payload(reaction_payload)
    assert result is True
    assert len(received) == 1
    session_id, user_id, text, metadata = received[0]
    assert session_id == "discord:chan-1"
    assert user_id == "user-1"
    assert text == "[reaction: 👍]"
    assert metadata["event_type"] == "reaction_add"
    assert metadata["emoji"] == "👍"


@pytest.mark.asyncio
async def test_reaction_add_bot_user_ignored():
    """Reactions from the bot itself should be ignored."""
    received = []
    async def on_msg(session_id, user_id, text, metadata):
        received.append((session_id, user_id, text, metadata))

    ch = _make_channel()
    ch.on_message = on_msg
    ch._bot_user_id = "bot-999"

    await ch._handle_message_reaction_add({
        "user_id": "bot-999",
        "channel_id": "chan-1",
        "message_id": "msg-1",
        "emoji": {"name": "👍", "id": None},
    })
    assert received == []
