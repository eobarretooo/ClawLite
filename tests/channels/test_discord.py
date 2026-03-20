from __future__ import annotations

import asyncio
import json
from pathlib import Path
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
        assert session_id == "discord:guild:456:channel:123"
        assert user_id == "user-1"
        assert text == "hello from discord"
        assert metadata["channel"] == "discord"
        assert metadata["channel_id"] == "123"
        assert metadata["guild_id"] == "456"
        assert metadata["session_key"] == "discord:guild:456:channel:123"
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
        assert emitted[0][2] == "[attachments: image.png]"
        assert emitted[0][3]["attachments"][0]["filename"] == "image.png"

    asyncio.run(_scenario())


def test_discord_dm_policy_disabled_blocks_private_message() -> None:
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
            config={"token": "bot-token", "dm_policy": "disabled"},
            on_message=_on_message,
        )

        with patch.object(channel, "_start_typing", AsyncMock()):
            with patch.object(channel, "_stop_typing", AsyncMock()):
                await channel._handle_message_create(
                    {
                        "id": "m1",
                        "channel_id": "dm-1",
                        "content": "hello",
                        "attachments": [],
                        "author": {"id": "u-1", "username": "alice", "bot": False},
                    }
                )

        assert emitted == []
        status = channel.operator_status()
        assert status["policy_blocked_count"] == 1
        assert status["policy_allowed_count"] == 0

    asyncio.run(_scenario())


def test_discord_group_policy_mention_requires_bot_mention() -> None:
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
            config={"token": "bot-token", "group_policy": "mention"},
            on_message=_on_message,
        )
        channel._bot_user_id = "bot-1"

        with patch.object(channel, "_start_typing", AsyncMock()):
            with patch.object(channel, "_stop_typing", AsyncMock()):
                await channel._handle_message_create(
                    {
                        "id": "m1",
                        "channel_id": "123",
                        "guild_id": "456",
                        "content": "no mention",
                        "attachments": [],
                        "author": {"id": "u-1", "username": "alice", "bot": False},
                        "mentions": [],
                    }
                )
                await channel._handle_message_create(
                    {
                        "id": "m2",
                        "channel_id": "123",
                        "guild_id": "456",
                        "content": "<@bot-1> hello",
                        "attachments": [],
                        "author": {"id": "u-1", "username": "alice", "bot": False},
                        "mentions": [{"id": "bot-1"}],
                    }
                )

        assert len(emitted) == 1
        assert emitted[0][0] == "discord:guild:456:channel:123"
        status = channel.operator_status()
        assert status["policy_blocked_count"] == 1
        assert status["policy_allowed_count"] == 1

    asyncio.run(_scenario())


def test_discord_group_policy_allowlist_honors_guild_channel_and_role_rules() -> None:
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
            config={
                "token": "bot-token",
                "group_policy": "allowlist",
                "guilds": {
                    "guild-1": {
                        "channels": {
                            "chan-1": {"allow": True, "roles": ["role-1"]},
                        }
                    }
                },
            },
            on_message=_on_message,
        )

        with patch.object(channel, "_start_typing", AsyncMock()):
            with patch.object(channel, "_stop_typing", AsyncMock()):
                await channel._handle_message_create(
                    {
                        "id": "m1",
                        "channel_id": "chan-2",
                        "guild_id": "guild-1",
                        "content": "wrong channel",
                        "attachments": [],
                        "author": {"id": "u-1", "username": "alice", "bot": False},
                        "member": {"roles": ["role-1"]},
                    }
                )
                await channel._handle_message_create(
                    {
                        "id": "m2",
                        "channel_id": "chan-1",
                        "guild_id": "guild-1",
                        "content": "wrong role",
                        "attachments": [],
                        "author": {"id": "u-2", "username": "bob", "bot": False},
                        "member": {"roles": ["role-2"]},
                    }
                )
                await channel._handle_message_create(
                    {
                        "id": "m3",
                        "channel_id": "chan-1",
                        "guild_id": "guild-1",
                        "content": "allowed",
                        "attachments": [],
                        "author": {"id": "u-3", "username": "carol", "bot": False},
                        "member": {"roles": ["role-1"]},
                    }
                )

        assert len(emitted) == 1
        assert emitted[0][0] == "discord:guild:guild-1:channel:chan-1"
        status = channel.operator_status()
        assert status["policy_blocked_count"] == 2
        assert status["policy_allowed_count"] == 1

    asyncio.run(_scenario())


def test_discord_interaction_honors_allowlisted_guild_channel_without_mention() -> None:
    emitted: list[dict[str, Any]] = []

    async def _on_message(session_id, user_id, text, metadata):
        emitted.append(
            {
                "session_id": session_id,
                "user_id": user_id,
                "text": text,
                "metadata": metadata,
            }
        )

    ch = DiscordChannel(
        config={
            "token": "tok",
            "group_policy": "allowlist",
            "guilds": {"guild-1": {"channels": {"chan-1": {"allow": True}}}},
        },
        on_message=_on_message,
    )
    ch._running = True
    payload = {
        "op": 0,
        "t": "INTERACTION_CREATE",
        "s": 2,
        "d": {
            "id": "inter002",
            "token": "tok2",
            "type": 3,
            "guild_id": "guild-1",
            "channel_id": "chan-1",
            "member": {"roles": [], "user": {"id": "u1", "username": "bob"}},
            "data": {"custom_id": "confirm_action", "component_type": 2},
            "message": {"id": "msg001"},
        },
    }

    async def _scenario():
        await ch._handle_gateway_payload(payload)

    asyncio.run(_scenario())

    assert emitted[0]["session_id"] == "discord:guild:guild-1:channel:chan-1"
    assert emitted[0]["metadata"]["session_key"] == "discord:guild:guild-1:channel:chan-1"
    assert emitted[0]["metadata"]["guild_id"] == "guild-1"


def test_discord_allow_bots_mentions_requires_bot_mention() -> None:
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
            config={"token": "bot-token", "allow_bots": "mentions"},
            on_message=_on_message,
        )
        channel._bot_user_id = "bot-1"

        with patch.object(channel, "_start_typing", AsyncMock()):
            with patch.object(channel, "_stop_typing", AsyncMock()):
                await channel._handle_message_create(
                    {
                        "id": "m1",
                        "channel_id": "123",
                        "guild_id": "456",
                        "content": "hello",
                        "attachments": [],
                        "author": {"id": "other-bot", "username": "helper", "bot": True},
                        "mentions": [],
                    }
                )
                await channel._handle_message_create(
                    {
                        "id": "m2",
                        "channel_id": "123",
                        "guild_id": "456",
                        "content": "<@bot-1> hello",
                        "attachments": [],
                        "author": {"id": "other-bot", "username": "helper", "bot": True},
                        "mentions": [{"id": "bot-1"}],
                    }
                )

        assert len(emitted) == 1
        assert emitted[0][0] == "discord:guild:456:channel:123"

    asyncio.run(_scenario())


def test_discord_operator_status_reports_gateway_state() -> None:
    channel = DiscordChannel(
        config={
            "token": "bot-token",
            "status": "idle",
            "activity": "Focus time",
            "activityType": 4,
        }
    )
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
    assert payload["presence_status"] == "idle"
    assert payload["presence_activity"] == "Focus time"
    assert payload["presence_activity_type"] == 4


def test_discord_identify_includes_presence_payload_when_configured() -> None:
    sent: list[dict[str, Any]] = []

    async def _scenario() -> None:
        channel = DiscordChannel(
            config={
                "token": "bot-token",
                "status": "dnd",
                "activity": "Live coding",
                "activityType": 1,
                "activityUrl": "https://twitch.tv/openclaw",
            }
        )

        async def _fake_send(payload: dict[str, Any]) -> None:
            sent.append(payload)

        channel._send_ws_json = _fake_send  # type: ignore[method-assign]
        await channel._identify()

    asyncio.run(_scenario())

    assert sent
    payload = sent[0]["d"]
    assert payload["presence"]["status"] == "dnd"
    assert payload["presence"]["activities"][0]["type"] == 1
    assert payload["presence"]["activities"][0]["name"] == "Live coding"
    assert payload["presence"]["activities"][0]["url"] == "https://twitch.tv/openclaw"


def test_discord_identify_includes_auto_presence_payload_when_enabled() -> None:
    sent: list[dict[str, Any]] = []

    async def _scenario() -> None:
        channel = DiscordChannel(
            config={
                "token": "bot-token",
                "activity": "Focus time",
                "autoPresence": {
                    "enabled": True,
                    "healthyText": "all systems nominal",
                },
            }
        )
        channel._running = True
        channel._ws = object()
        channel._session_id = "sess-1"
        channel._gateway_task = asyncio.create_task(asyncio.sleep(3600))

        async def _fake_send(payload: dict[str, Any]) -> None:
            sent.append(payload)

        channel._send_ws_json = _fake_send  # type: ignore[method-assign]
        await channel._identify()
        channel._gateway_task.cancel()
        try:
            await channel._gateway_task
        except asyncio.CancelledError:
            pass

    asyncio.run(_scenario())

    assert sent
    payload = sent[0]["d"]["presence"]
    assert payload["status"] == "online"
    assert payload["activities"][0]["type"] == 4
    assert payload["activities"][0]["state"] == "all systems nominal"


def test_discord_operator_refresh_presence_sends_status_update() -> None:
    sent: list[dict[str, Any]] = []

    async def _scenario() -> None:
        channel = DiscordChannel(
            config={
                "token": "bot-token",
                "activity": "Focus time",
                "autoPresence": {
                    "enabled": True,
                    "healthyText": "all systems nominal",
                },
            }
        )
        channel._running = True
        channel._ws = object()
        channel._session_id = "sess-1"
        channel._gateway_task = asyncio.create_task(asyncio.sleep(3600))

        async def _fake_send(payload: dict[str, Any]) -> None:
            sent.append(payload)

        channel._send_ws_json = _fake_send  # type: ignore[method-assign]
        result = await channel.operator_refresh_presence()
        assert result["ok"] is True
        assert result["sent"] is True
        channel._gateway_task.cancel()
        try:
            await channel._gateway_task
        except asyncio.CancelledError:
            pass

    asyncio.run(_scenario())

    assert sent
    assert sent[0]["op"] == 3
    assert sent[0]["d"]["status"] == "online"


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
    assert session_id == "discord:guild:guild-1:channel:chan-1"
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


@pytest.mark.asyncio
async def test_send_with_embeds():
    from clawlite.channels.discord import DiscordChannel
    ch = DiscordChannel(config={"token": "test-token"})
    ch._running = True
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b'{"id": "msg-abc"}'
    mock_resp.json = lambda: {"id": "msg-abc"}
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    ch._client = mock_client
    ch._typing_tasks = {}

    embed = {"title": "Hello", "description": "World", "color": 0x00FF00}
    result = await ch.send(
        target="channel:123",
        text="Check this embed",
        metadata={"discord_embeds": [embed]},
    )
    assert result.startswith("discord:sent:")
    posted = mock_client.post.call_args[1]["json"] if mock_client.post.call_args[1] else mock_client.post.call_args[0][1]
    assert "embeds" in posted
    assert posted["embeds"][0]["title"] == "Hello"


@pytest.mark.asyncio
async def test_create_thread_from_message():
    from clawlite.channels.discord import DiscordChannel
    ch = DiscordChannel(config={"token": "test-token"})
    ch._running = True
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b'{"id": "thread-999"}'
    mock_resp.json = lambda: {"id": "thread-999"}
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    ch._client = mock_client

    thread_id = await ch.create_thread(
        channel_id="chan-1",
        name="My Thread",
        message_id="msg-1",
    )
    assert thread_id == "thread-999"
    call_url = mock_client.post.call_args[0][0]
    assert "/messages/msg-1/threads" in call_url


@pytest.mark.asyncio
async def test_create_thread_standalone():
    from clawlite.channels.discord import DiscordChannel
    ch = DiscordChannel(config={"token": "test-token"})
    ch._running = True
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b'{"id": "thread-888"}'
    mock_resp.json = lambda: {"id": "thread-888"}
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    ch._client = mock_client

    thread_id = await ch.create_thread(channel_id="chan-1", name="Standalone Thread")
    assert thread_id == "thread-888"
    call_url = mock_client.post.call_args[0][0]
    assert "/channels/chan-1/threads" in call_url
    assert "messages" not in call_url


@pytest.mark.asyncio
async def test_download_attachment_returns_none_for_non_https():
    from clawlite.channels.discord import DiscordChannel
    ch = DiscordChannel(config={"token": "test-token"})
    result = await ch._download_attachment("http://example.com/file.txt")
    assert result is None

    result2 = await ch._download_attachment("")
    assert result2 is None


# ─── Interaction / slash / button tests ──────────────────────────────────────

def test_discord_handle_interaction_create_slash_emits_message() -> None:
    """INTERACTION_CREATE type=2 (slash command) is emitted as a message."""
    emitted: list[dict] = []

    async def _on_message(session_id, user_id, text, metadata):
        emitted.append({"session_id": session_id, "user_id": user_id, "text": text, "metadata": metadata})

    ch = DiscordChannel(config={"token": "tok"}, on_message=_on_message)
    ch._running = True
    ch._bot_user_id = "bot123"

    payload = {
        "op": 0,
        "t": "INTERACTION_CREATE",
        "s": 1,
        "d": {
            "id": "inter001",
            "token": "intertoken",
            "type": 2,
            "application_id": "app001",
            "channel_id": "chan001",
            "guild_id": "guild-1",
            "user": {"id": "user001", "username": "alice"},
            "data": {"id": "cmd001", "name": "ping", "options": []},
        },
    }

    async def _scenario():
        await ch._handle_gateway_payload(payload)

    asyncio.run(_scenario())

    assert len(emitted) == 1
    assert emitted[0]["session_id"] == "discord:guild:guild-1:channel:chan001:slash:user001"
    meta = emitted[0]["metadata"]
    assert meta["update_kind"] == "slash_command"
    assert meta["command_name"] == "ping"
    assert meta["interaction_id"] == "inter001"
    assert meta["interaction_token"] == "intertoken"
    assert meta["session_key"] == "discord:guild:guild-1:channel:chan001:slash:user001"


def test_discord_handle_interaction_create_button_emits_message() -> None:
    """INTERACTION_CREATE type=3 (button) is emitted with custom_id."""
    emitted: list[dict] = []

    async def _on_message(session_id, user_id, text, metadata):
        emitted.append({"session_id": session_id, "user_id": user_id, "text": text, "metadata": metadata})

    ch = DiscordChannel(config={"token": "tok"}, on_message=_on_message)
    ch._running = True

    payload = {
        "op": 0,
        "t": "INTERACTION_CREATE",
        "s": 2,
        "d": {
            "id": "inter002",
            "token": "tok2",
            "type": 3,
            "channel_id": "chan001",
            "user": {"id": "u1", "username": "bob"},
            "data": {"custom_id": "confirm_action", "component_type": 2},
            "message": {"id": "msg001"},
        },
    }

    async def _scenario():
        await ch._handle_gateway_payload(payload)

    asyncio.run(_scenario())

    assert emitted[0]["metadata"]["update_kind"] == "button_click"
    assert emitted[0]["metadata"]["custom_id"] == "confirm_action"


def test_discord_handle_interaction_create_string_select_emits_selected_values() -> None:
    emitted: list[dict[str, Any]] = []

    async def _on_message(session_id, user_id, text, metadata):
        emitted.append({"session_id": session_id, "user_id": user_id, "text": text, "metadata": metadata})

    ch = DiscordChannel(config={"token": "tok"}, on_message=_on_message)
    ch._running = True

    payload = {
        "id": "inter-select-1",
        "token": "tok-select-1",
        "type": 3,
        "channel_id": "chan001",
        "guild_id": "guild-1",
        "user": {"id": "u1", "username": "bob"},
        "data": {
            "custom_id": "priority",
            "component_type": 3,
            "values": ["high", "low"],
        },
        "message": {"id": "msg001"},
    }

    async def _scenario():
        await ch._handle_interaction_create(payload)

    asyncio.run(_scenario())

    assert emitted[0]["text"] == "[select:priority high, low]"
    assert emitted[0]["metadata"]["update_kind"] == "string_select"
    assert emitted[0]["metadata"]["custom_id"] == "priority"
    assert emitted[0]["metadata"]["selected_values"] == ["high", "low"]
    assert emitted[0]["metadata"]["selected_labels"] == ["high", "low"]


def test_discord_handle_interaction_create_user_select_uses_resolved_labels() -> None:
    emitted: list[dict[str, Any]] = []

    async def _on_message(session_id, user_id, text, metadata):
        emitted.append({"session_id": session_id, "user_id": user_id, "text": text, "metadata": metadata})

    ch = DiscordChannel(config={"token": "tok"}, on_message=_on_message)
    ch._running = True

    payload = {
        "id": "inter-select-2",
        "token": "tok-select-2",
        "type": 3,
        "channel_id": "chan001",
        "guild_id": "guild-1",
        "user": {"id": "u1", "username": "bob"},
        "data": {
            "custom_id": "assign",
            "component_type": 5,
            "values": ["u-1", "u-2"],
            "resolved": {
                "users": {
                    "u-1": {"id": "u-1", "username": "alice", "global_name": "Alice A"},
                    "u-2": {"id": "u-2", "username": "bob"},
                },
                "members": {
                    "u-2": {"nick": "Bobby"},
                },
            },
        },
        "message": {"id": "msg001"},
    }

    async def _scenario():
        await ch._handle_interaction_create(payload)

    asyncio.run(_scenario())

    assert emitted[0]["text"] == "[user_select:assign Alice A, Bobby]"
    assert emitted[0]["metadata"]["update_kind"] == "user_select"
    assert emitted[0]["metadata"]["selected_values"] == ["u-1", "u-2"]
    assert emitted[0]["metadata"]["selected_labels"] == ["Alice A", "Bobby"]


def test_discord_handle_interaction_create_modal_submit_emits_fields() -> None:
    emitted: list[dict[str, Any]] = []

    async def _on_message(session_id, user_id, text, metadata):
        emitted.append({"session_id": session_id, "user_id": user_id, "text": text, "metadata": metadata})

    ch = DiscordChannel(config={"token": "tok"}, on_message=_on_message)
    ch._running = True

    payload = {
        "id": "inter-modal-1",
        "token": "tok-modal-1",
        "type": 5,
        "channel_id": "chan001",
        "guild_id": "guild-1",
        "user": {"id": "u1", "username": "bob"},
        "data": {
            "custom_id": "ticket_modal",
            "components": [
                {
                    "type": 1,
                    "components": [
                        {
                            "type": 4,
                            "custom_id": "subject",
                            "label": "Subject",
                            "value": "Need help",
                        }
                    ],
                },
                {
                    "type": 1,
                    "components": [
                        {
                            "type": 4,
                            "custom_id": "details",
                            "label": "Details",
                            "value": "Please call back",
                        }
                    ],
                },
            ],
        },
    }

    async def _scenario():
        await ch._handle_interaction_create(payload)

    asyncio.run(_scenario())

    assert emitted[0]["text"] == "[modal_submit:ticket_modal]\nSubject: Need help\nDetails: Please call back"
    assert emitted[0]["metadata"]["update_kind"] == "modal_submit"
    assert emitted[0]["metadata"]["custom_id"] == "ticket_modal"
    assert emitted[0]["metadata"]["modal_field_ids"] == ["subject", "details"]
    assert emitted[0]["metadata"]["modal_field_labels"] == ["Subject", "Details"]
    assert emitted[0]["metadata"]["modal_fields"] == [
        {"component_type": 4, "custom_id": "subject", "label": "Subject", "value": "Need help"},
        {"component_type": 4, "custom_id": "details", "label": "Details", "value": "Please call back"},
    ]


def test_discord_handle_interaction_create_modal_submit_tolerates_missing_components() -> None:
    emitted: list[dict[str, Any]] = []

    async def _on_message(session_id, user_id, text, metadata):
        emitted.append({"session_id": session_id, "user_id": user_id, "text": text, "metadata": metadata})

    ch = DiscordChannel(config={"token": "tok"}, on_message=_on_message)
    ch._running = True

    payload = {
        "id": "inter-modal-2",
        "token": "tok-modal-2",
        "type": 5,
        "channel_id": "chan001",
        "user": {"id": "u1", "username": "bob"},
        "data": {
            "custom_id": "ticket_modal",
            "components": [{"type": 1, "components": "invalid"}],
        },
    }

    async def _scenario():
        await ch._handle_interaction_create(payload)

    asyncio.run(_scenario())

    assert emitted[0]["text"] == "[modal_submit:ticket_modal]"
    assert emitted[0]["metadata"]["update_kind"] == "modal_submit"
    assert emitted[0]["metadata"]["modal_field_ids"] == []
    assert emitted[0]["metadata"]["modal_field_labels"] == []
    assert emitted[0]["metadata"]["modal_fields"] == []


def test_discord_handle_interaction_create_slash_can_disable_isolated_sessions() -> None:
    emitted: list[dict[str, Any]] = []

    async def _on_message(session_id, user_id, text, metadata):
        emitted.append({"session_id": session_id, "user_id": user_id, "text": text, "metadata": metadata})

    ch = DiscordChannel(
        config={"token": "tok", "slash_isolated_sessions": False},
        on_message=_on_message,
    )
    ch._running = True
    ch._bot_user_id = "bot123"

    payload = {
        "id": "inter003",
        "token": "intertoken-3",
        "type": 2,
        "application_id": "app001",
        "channel_id": "chan001",
        "guild_id": "guild-1",
        "user": {"id": "user001", "username": "alice"},
        "data": {"id": "cmd001", "name": "ping", "options": []},
    }

    async def _scenario():
        await ch._handle_interaction_create(payload)

    asyncio.run(_scenario())

    assert emitted[0]["session_id"] == "discord:guild:guild-1:channel:chan001"
    assert emitted[0]["metadata"]["session_key"] == "discord:guild:guild-1:channel:chan001"


def test_discord_register_slash_command_posts_correct_payload() -> None:
    """register_slash_command posts to the correct application commands endpoint."""
    posted: list[tuple[str, dict]] = []

    async def _fake_post(url, payload, error_prefix=""):
        posted.append((url, payload))
        return _response(status=201, url=url, payload={"id": "cmd001", "name": payload["name"]})

    ch = DiscordChannel(config={"token": "tok"}, on_message=None)
    ch._application_id = "app001"
    ch._post_json = _fake_post  # type: ignore[method-assign]

    async def _scenario():
        return await ch.register_slash_command(
            name="ping",
            description="Ping the bot",
            options=[],
            guild_id=None,
        )

    result = asyncio.run(_scenario())
    assert result["name"] == "ping"
    url, body = posted[0]
    assert "/applications/app001/commands" in url
    assert body["name"] == "ping"


def test_discord_send_includes_components_from_metadata() -> None:
    """send() includes action_row components when metadata has discord_components."""
    posted: list[dict] = []

    async def _fake_post(url, payload, error_prefix=""):
        posted.append(payload)
        return _response(status=200, url=url, payload={"id": "msg001"})

    ch = DiscordChannel(config={"token": "tok"}, on_message=None)
    ch._running = True
    ch._post_json = _fake_post  # type: ignore[method-assign]

    components = [
        {
            "type": 1,
            "components": [
                {"type": 2, "style": 1, "label": "Yes", "custom_id": "yes"},
                {"type": 2, "style": 4, "label": "No", "custom_id": "no"},
            ],
        }
    ]

    async def _scenario():
        return await ch.send(
            target="#chan001",
            text="Confirm?",
            metadata={"discord_components": components},
        )

    asyncio.run(_scenario())

    assert len(posted) == 1
    assert "components" in posted[0]
    assert posted[0]["components"][0]["type"] == 1
    assert len(posted[0]["components"][0]["components"]) == 2


def test_discord_send_with_modal_metadata_adds_trigger_button() -> None:
    posted: list[dict[str, Any]] = []

    async def _fake_post(url, payload, error_prefix=""):
        posted.append(payload)
        return _response(status=200, url=url, payload={"id": "msg-modal"})

    ch = DiscordChannel(config={"token": "tok"}, on_message=None)
    ch._running = True
    ch._post_json = _fake_post  # type: ignore[method-assign]

    async def _scenario():
        return await ch.send(
            target="#chan001",
            text="Open the details form",
            metadata={
                "discord_modal": {
                    "title": "Details",
                    "trigger_label": "Open details",
                    "fields": [
                        {"label": "Subject", "custom_id": "subject"},
                        {"label": "Details", "custom_id": "details", "style": "paragraph"},
                    ],
                }
            },
        )

    asyncio.run(_scenario())

    assert len(posted) == 1
    assert "components" in posted[0]
    trigger = posted[0]["components"][-1]["components"][0]
    assert trigger["type"] == 2
    assert trigger["label"] == "Open details"
    assert trigger["custom_id"].startswith("clawlite:modal:open:")


def test_discord_modal_trigger_interaction_opens_registered_modal_without_emitting_message() -> None:
    emitted: list[dict[str, Any]] = []
    interaction_callbacks: list[dict[str, Any]] = []
    message_posts: list[dict[str, Any]] = []

    async def _on_message(session_id, user_id, text, metadata):
        emitted.append({"session_id": session_id, "user_id": user_id, "text": text, "metadata": metadata})

    async def _fake_post(url, payload, error_prefix=""):
        if "/interactions/" in url:
            interaction_callbacks.append(payload)
            return _response(status=204, url=url)
        message_posts.append(payload)
        return _response(status=200, url=url, payload={"id": "msg-modal"})

    ch = DiscordChannel(config={"token": "tok"}, on_message=_on_message)
    ch._running = True
    ch._post_json = _fake_post  # type: ignore[method-assign]
    ch._ack_interaction = AsyncMock()  # type: ignore[method-assign]

    async def _scenario():
        await ch.send(
            target="#chan001",
            text="Open the details form",
            metadata={
                "discord_modal": {
                    "title": "Details",
                    "fields": [
                        {"label": "Subject", "custom_id": "subject"},
                        {"label": "Details", "custom_id": "details", "style": "paragraph"},
                    ],
                }
            },
        )
        trigger_custom_id = message_posts[0]["components"][-1]["components"][0]["custom_id"]
        await ch._handle_interaction_create(
            {
                "id": "inter-modal-open-1",
                "token": "tok-modal-open-1",
                "type": 3,
                "channel_id": "chan001",
                "guild_id": "guild-1",
                "user": {"id": "u1", "username": "bob"},
                "data": {"custom_id": trigger_custom_id, "component_type": 2},
                "message": {"id": "msg001"},
            }
        )

    asyncio.run(_scenario())

    assert emitted == []
    assert ch._ack_interaction.await_count == 0
    assert len(interaction_callbacks) == 1
    assert interaction_callbacks[0]["type"] == 9
    modal_data = interaction_callbacks[0]["data"]
    assert modal_data["title"] == "Details"
    assert modal_data["custom_id"].startswith("clawlite:modal:submit:")
    assert modal_data["components"][0]["components"][0]["label"] == "Subject"
    assert modal_data["components"][1]["components"][0]["style"] == 2


def test_discord_send_with_poll_metadata() -> None:
    """send() includes poll field when metadata has discord_poll."""
    posted: list[dict] = []

    async def _fake_post(url, payload, error_prefix=""):
        posted.append(payload)
        return _response(status=200, url=url, payload={"id": "msg002"})

    ch = DiscordChannel(config={"token": "tok"}, on_message=None)
    ch._running = True
    ch._post_json = _fake_post  # type: ignore[method-assign]

    poll_meta = {
        "question": "Favorite color?",
        "answers": ["Red", "Blue", "Green"],
        "duration_hours": 24,
        "allow_multiselect": False,
    }

    asyncio.run(ch.send(target="#chan001", text="", metadata={"discord_poll": poll_meta}))

    assert "poll" in posted[0]
    assert posted[0]["poll"]["question"]["text"] == "Favorite color?"
    assert len(posted[0]["poll"]["answers"]) == 3
    assert posted[0]["poll"]["duration"] == 24


def test_discord_create_webhook_posts_to_channel() -> None:
    """create_webhook() posts to /channels/{id}/webhooks."""
    posted: list[tuple[str, dict]] = []

    async def _fake_post(url, payload, error_prefix=""):
        posted.append((url, payload))
        return _response(status=200, url=url, payload={"id": "wh001", "token": "wht001", "name": "MyBot"})

    ch = DiscordChannel(config={"token": "tok"}, on_message=None)
    ch._post_json = _fake_post  # type: ignore[method-assign]

    result = asyncio.run(ch.create_webhook(channel_id="chan001", name="MyBot"))
    assert result["id"] == "wh001"
    assert "/channels/chan001/webhooks" in posted[0][0]


def test_discord_execute_webhook_sends_message() -> None:
    """execute_webhook() posts to /webhooks/{id}/{token}."""
    posted: list[tuple[str, dict]] = []

    async def _fake_post(url, payload, error_prefix=""):
        posted.append((url, payload))
        return _response(status=204, url=url)

    ch = DiscordChannel(config={"token": "tok"}, on_message=None)
    ch._post_json = _fake_post  # type: ignore[method-assign]

    asyncio.run(ch.execute_webhook(webhook_id="wh001", webhook_token="wht001", text="Hello from webhook!"))
    assert "/webhooks/wh001/wht001" in posted[0][0]
    assert posted[0][1]["content"] == "Hello from webhook!"


def test_discord_send_voice_message_builds_correct_payload() -> None:
    """send_voice_message() uploads file and sends message with IS_VOICE_MESSAGE flag."""
    import unittest.mock as mock

    http_calls: list[tuple[str, str, Any]] = []

    class _FakeVoiceClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def post(self, url, *, json=None, headers=None, content=None):
            http_calls.append(("POST", url, json or content))
            if "attachments" in url:
                return _response(
                    status=200,
                    url=url,
                    payload={"attachments": [{"id": 0, "upload_url": "https://cdn/upload", "upload_filename": "voice.ogg"}]},
                )
            return _response(status=200, url=url, payload={"id": "msg001"})

        async def put(self, url, *, headers=None, content=None):
            http_calls.append(("PUT", url, None))
            return _response(status=200, url=url)

    ch = DiscordChannel(config={"token": "tok"}, on_message=None)
    ch._running = True

    async def _fake_post_json(url, payload, error_prefix=""):
        http_calls.append(("POST", url, payload))
        return _response(status=200, url=url, payload={"id": "msg001"})

    ch._post_json = _fake_post_json  # type: ignore[method-assign]

    with mock.patch("httpx.AsyncClient", return_value=_FakeVoiceClient()):
        async def _scenario():
            return await ch.send_voice_message(
                channel_id="chan001",
                audio_bytes=b"\x4f\x67\x67\x53" + b"\x00" * 100,
                duration_secs=2.5,
                waveform="AAAA",  # provide explicit waveform to skip ffmpeg
            )
        result = asyncio.run(_scenario())

    assert result.startswith("discord:voice:")
    assert any("attachments" in c[1] for c in http_calls if c[0] == "POST")
    assert any(c[0] == "PUT" for c in http_calls)
    msg_posts = [c for c in http_calls if c[0] == "POST" and "messages" in c[1]]
    assert msg_posts
    assert msg_posts[0][2]["flags"] == 8192


def test_discord_send_streaming_edits_message_in_place() -> None:
    """send_streaming() creates a message then edits it as chunks arrive."""
    from clawlite.core.engine import ProviderChunk

    calls: list[tuple[str, str, dict]] = []

    async def _fake_post(url, payload, error_prefix=""):
        calls.append(("POST", url, payload))
        return _response(status=200, url=url, payload={"id": "msg001"})

    async def _fake_patch(url, payload):
        calls.append(("PATCH", url, payload))
        return _response(status=200, url=url, payload={"id": "msg001"})

    async def fake_chunks():
        yield ProviderChunk(text="Hello ", accumulated="Hello ", done=False)
        yield ProviderChunk(text="world", accumulated="Hello world", done=False)
        yield ProviderChunk(text="!", accumulated="Hello world!", done=True)

    ch = DiscordChannel(config={"token": "tok"}, on_message=None)
    ch._running = True
    ch._post_json = _fake_post  # type: ignore[method-assign]
    ch._patch_json = _fake_patch  # type: ignore[method-assign]

    asyncio.run(ch.send_streaming(channel_id="chan001", chunks=fake_chunks()))

    posts = [c for c in calls if c[0] == "POST"]
    patches = [c for c in calls if c[0] == "PATCH"]
    assert len(posts) == 1
    assert len(patches) >= 1
    assert patches[-1][2]["content"] == "Hello world!"


def test_discord_send_interaction_reply_uses_original_response_path() -> None:
    replies: list[dict[str, Any]] = []

    async def _fake_reply_interaction(
        *,
        interaction_id: str,
        interaction_token: str,
        text: str,
        components: list[dict[str, Any]] | None = None,
        embeds: list[dict[str, Any]] | None = None,
        ephemeral: bool = False,
    ) -> str:
        replies.append(
            {
                "interaction_id": interaction_id,
                "interaction_token": interaction_token,
                "text": text,
                "components": list(components or []),
                "embeds": list(embeds or []),
                "ephemeral": ephemeral,
            }
        )
        return "original-1"

    ch = DiscordChannel(config={"token": "tok"}, on_message=None)
    ch._running = True
    ch._application_id = "app001"

    with patch.object(ch, "reply_interaction", side_effect=_fake_reply_interaction):
        out = asyncio.run(
            ch.send(
                target="channel:chan001",
                text="Hello from slash",
                metadata={
                    "interaction_id": "inter-1",
                    "interaction_token": "tok-1",
                    "discord_ephemeral": True,
                    "discord_components": [{"type": 1, "components": []}],
                },
            )
        )

    assert out == "discord:interaction:original-1"
    assert replies == [
        {
            "interaction_id": "inter-1",
            "interaction_token": "tok-1",
            "text": "Hello from slash",
            "components": [{"type": 1, "components": []}],
            "embeds": [],
            "ephemeral": True,
        }
    ]


def test_discord_placeholder_waveform_is_base64() -> None:
    """_generate_placeholder_waveform() returns valid base64 of 256 bytes."""
    import base64
    ch = DiscordChannel(config={"token": "tok"})
    wf = ch._generate_placeholder_waveform()
    decoded = base64.b64decode(wf)
    assert len(decoded) == 256


def test_discord_thread_binding_persists_and_routes_inbound_messages(tmp_path: Path) -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict[str, Any]]] = []
        state_path = tmp_path / "discord-thread-bindings.json"

        async def _on_message(
            session_id: str,
            user_id: str,
            text: str,
            metadata: dict[str, Any],
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = DiscordChannel(
            config={
                "token": "bot-token",
                "thread_binding_state_path": str(state_path),
            },
            on_message=_on_message,
        )
        await channel.bind_thread(
            channel_id="thread-1",
            session_id="discord:guild:guild-main:channel:chan-main",
            actor="discord:u-1",
            guild_id="guild-1",
            source_session_id="discord:guild:guild-1:channel:thread-1",
        )

        with patch.object(channel, "_start_typing", AsyncMock()):
            with patch.object(channel, "_stop_typing", AsyncMock()):
                await channel._handle_message_create(
                    {
                        "id": "m-thread-1",
                        "channel_id": "thread-1",
                        "guild_id": "guild-1",
                        "content": "thread hello",
                        "attachments": [],
                        "author": {"id": "u-1", "username": "alice", "bot": False},
                    }
                )

        assert len(emitted) == 1
        session_id, user_id, text, metadata = emitted[0]
        assert session_id == "discord:guild:guild-main:channel:chan-main"
        assert user_id == "u-1"
        assert text == "thread hello"
        assert metadata["session_key"] == "discord:guild:guild-main:channel:chan-main"
        assert metadata["discord_binding_active"] is True
        assert metadata["discord_binding_channel_id"] == "thread-1"
        assert metadata["discord_source_session_key"] == "discord:guild:guild-1:channel:thread-1"
        assert state_path.exists()

        restored = DiscordChannel(
            config={
                "token": "bot-token",
                "thread_binding_state_path": str(state_path),
            }
        )
        await restored.start()
        binding = restored.resolve_bound_session("thread-1")
        await restored.stop()

        assert binding is not None
        assert binding["session_id"] == "discord:guild:guild-main:channel:chan-main"
        assert binding["bound_by"] == "discord:u-1"

    asyncio.run(_scenario())


def test_discord_interaction_uses_bound_session_key() -> None:
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
        await channel.bind_thread(
            channel_id="thread-chan-1",
            session_id="discord:guild:guild-main:channel:chan-main",
            actor="discord:u-1",
            guild_id="guild-main",
            source_session_id="discord:guild:guild-main:channel:thread-chan-1",
        )

        with patch.object(channel, "_ack_interaction", AsyncMock()):
            await channel._handle_interaction_create(
                {
                    "id": "interaction-1",
                    "token": "token-1",
                    "type": 2,
                    "channel_id": "thread-chan-1",
                    "guild_id": "guild-main",
                    "data": {
                        "name": "focus",
                        "options": [{"name": "session", "value": "discord:guild:guild-main:channel:chan-main"}],
                    },
                    "member": {
                        "roles": [],
                        "user": {"id": "u-1", "username": "alice", "bot": False},
                    },
                }
            )

        assert len(emitted) == 1
        session_id, user_id, text, metadata = emitted[0]
        assert session_id == "discord:guild:guild-main:channel:chan-main"
        assert user_id == "u-1"
        assert text == "/focus session=discord:guild:guild-main:channel:chan-main"
        assert metadata["discord_binding_active"] is True
        assert metadata["discord_binding_channel_id"] == "thread-chan-1"
        assert metadata["session_key"] == "discord:guild:guild-main:channel:chan-main"

    asyncio.run(_scenario())


def test_discord_thread_binding_idle_timeout_releases_stale_focus(tmp_path: Path) -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict[str, Any]]] = []
        state_path = tmp_path / "discord-thread-bindings.json"

        async def _on_message(
            session_id: str,
            user_id: str,
            text: str,
            metadata: dict[str, Any],
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = DiscordChannel(
            config={
                "token": "bot-token",
                "thread_binding_state_path": str(state_path),
                "thread_binding_idle_timeout_s": 60,
            },
            on_message=_on_message,
        )
        await channel.bind_thread(
            channel_id="thread-1",
            session_id="discord:guild:guild-main:channel:chan-main",
            actor="discord:u-1",
            guild_id="guild-1",
            source_session_id="discord:guild:guild-1:channel:thread-1",
        )
        channel._thread_bindings["thread-1"]["updated_at"] = "2000-01-01T00:00:00+00:00"

        with patch.object(channel, "_start_typing", AsyncMock()):
            with patch.object(channel, "_stop_typing", AsyncMock()):
                await channel._handle_message_create(
                    {
                        "id": "m-thread-1",
                        "channel_id": "thread-1",
                        "guild_id": "guild-1",
                        "content": "thread hello",
                        "attachments": [],
                        "author": {"id": "u-1", "username": "alice", "bot": False},
                    }
                )

        assert len(emitted) == 1
        session_id, _, _, metadata = emitted[0]
        assert session_id == "discord:guild:guild-1:channel:thread-1"
        assert metadata["session_key"] == "discord:guild:guild-1:channel:thread-1"
        assert metadata["discord_binding_expired"] == "idle_timeout"
        assert metadata.get("discord_binding_active") is None
        assert channel.resolve_bound_session("thread-1") is None

    asyncio.run(_scenario())


def test_discord_thread_binding_max_age_releases_stale_focus(tmp_path: Path) -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict[str, Any]]] = []
        state_path = tmp_path / "discord-thread-bindings.json"

        async def _on_message(
            session_id: str,
            user_id: str,
            text: str,
            metadata: dict[str, Any],
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = DiscordChannel(
            config={
                "token": "bot-token",
                "thread_binding_state_path": str(state_path),
                "thread_binding_max_age_s": 60,
            },
            on_message=_on_message,
        )
        await channel.bind_thread(
            channel_id="thread-1",
            session_id="discord:guild:guild-main:channel:chan-main",
            actor="discord:u-1",
            guild_id="guild-1",
            source_session_id="discord:guild:guild-1:channel:thread-1",
        )
        channel._thread_bindings["thread-1"]["bound_at"] = "2000-01-01T00:00:00+00:00"
        channel._thread_bindings["thread-1"]["updated_at"] = "2000-01-01T00:00:00+00:00"

        with patch.object(channel, "_ack_interaction", AsyncMock()):
            await channel._handle_interaction_create(
                {
                    "id": "interaction-1",
                    "token": "token-1",
                    "type": 2,
                    "channel_id": "thread-1",
                    "guild_id": "guild-1",
                    "data": {"name": "ping", "options": []},
                    "member": {
                        "roles": [],
                        "user": {"id": "u-1", "username": "alice", "bot": False},
                    },
                }
            )

        assert len(emitted) == 1
        session_id, _, _, metadata = emitted[0]
        assert session_id == "discord:guild:guild-1:channel:thread-1:slash:u-1"
        assert metadata["discord_binding_expired"] == "max_age"
        assert channel.resolve_bound_session("thread-1") is None

    asyncio.run(_scenario())
