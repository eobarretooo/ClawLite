from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx

from clawlite.channels.slack import SlackChannel


def _response(
    *,
    status: int,
    url: str,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    request = httpx.Request("POST", url)
    if payload is None:
        return httpx.Response(status, request=request, headers=headers)
    return httpx.Response(status, json=payload, request=request, headers=headers)


class _FakeClient:
    def __init__(self, responses: list[httpx.Response]) -> None:
        self._responses = list(responses)
        self.posts: list[tuple[str, dict[str, Any], dict[str, str]]] = []
        self.closed = False

    async def post(
        self,
        url: str,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        self.posts.append((url, dict(json or {}), dict(headers or {})))
        if not self._responses:
            raise AssertionError("unexpected slack post")
        return self._responses.pop(0)

    async def aclose(self) -> None:
        self.closed = True


class _FakeWebSocket:
    def __init__(self, messages: list[dict[str, Any] | str]) -> None:
        self._messages = list(messages)
        self.sent: list[str] = []

    async def __aenter__(self) -> _FakeWebSocket:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb

    def __aiter__(self) -> _FakeWebSocket:
        return self

    async def __anext__(self) -> str:
        if not self._messages:
            raise StopAsyncIteration
        item = self._messages.pop(0)
        if isinstance(item, str):
            return item
        return json.dumps(item)

    async def send(self, payload: str) -> None:
        self.sent.append(payload)


def test_slack_channel_reuses_persistent_client_across_sends(monkeypatch) -> None:
    async def _scenario() -> None:
        client = _FakeClient(
            [
                _response(status=200, url="https://slack.com/api/chat.postMessage", payload={"ok": True, "ts": "1.1"}),
                _response(status=200, url="https://slack.com/api/chat.postMessage", payload={"ok": True, "ts": "1.2"}),
            ]
        )
        created: list[_FakeClient] = []

        def _factory(*args, **kwargs):
            del args, kwargs
            created.append(client)
            return client

        monkeypatch.setattr(httpx, "AsyncClient", _factory)

        channel = SlackChannel(config={"bot_token": "xoxb-1"})
        await channel.start()

        first = await channel.send(target="C123", text="hello")
        second = await channel.send(target="C123", text="again")

        await channel.stop()

        assert first == "slack:sent:C123:1.1"
        assert second == "slack:sent:C123:1.2"
        assert len(created) == 1
        assert len(client.posts) == 2
        assert client.closed is True

    asyncio.run(_scenario())


def test_slack_send_retries_http_429_with_retry_after(monkeypatch) -> None:
    async def _scenario() -> None:
        first = _response(
            status=429,
            url="https://slack.com/api/chat.postMessage",
            payload={"ok": False, "error": "ratelimited"},
            headers={"Retry-After": "2.0"},
        )
        second = _response(
            status=200,
            url="https://slack.com/api/chat.postMessage",
            payload={"ok": True, "ts": "1700.1"},
        )
        client = _FakeClient([first, second])

        def _factory(*args, **kwargs):
            del args, kwargs
            return client

        monkeypatch.setattr(httpx, "AsyncClient", _factory)

        channel = SlackChannel(config={"bot_token": "xoxb-1", "send_retry_attempts": 2})
        await channel.start()

        sleep_mock = AsyncMock()
        with patch("clawlite.channels.slack.asyncio.sleep", new=sleep_mock):
            out = await channel.send(target="C123", text="hello")

        await channel.stop()

        assert out == "slack:sent:C123:1700.1"
        assert len(client.posts) == 2
        assert sleep_mock.await_count == 1
        assert sleep_mock.await_args.args == (2.0,)

    asyncio.run(_scenario())


def test_slack_send_retries_api_ratelimited_error(monkeypatch) -> None:
    async def _scenario() -> None:
        first = _response(
            status=200,
            url="https://slack.com/api/chat.postMessage",
            payload={"ok": False, "error": "ratelimited", "retry_after": 1.5},
        )
        second = _response(
            status=200,
            url="https://slack.com/api/chat.postMessage",
            payload={"ok": True, "ts": "1700.2"},
        )
        client = _FakeClient([first, second])

        def _factory(*args, **kwargs):
            del args, kwargs
            return client

        monkeypatch.setattr(httpx, "AsyncClient", _factory)

        channel = SlackChannel(config={"bot_token": "xoxb-1", "send_retry_attempts": 2})
        await channel.start()

        sleep_mock = AsyncMock()
        with patch("clawlite.channels.slack.asyncio.sleep", new=sleep_mock):
            out = await channel.send(target="C123", text="hello")

        await channel.stop()

        assert out == "slack:sent:C123:1700.2"
        assert len(client.posts) == 2
        assert sleep_mock.await_count == 1
        assert sleep_mock.await_args.args == (1.5,)

    asyncio.run(_scenario())


def test_slack_socket_mode_acknowledges_and_emits_user_message() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict[str, Any]]] = []

        async def _on_message(
            session_id: str,
            user_id: str,
            text: str,
            metadata: dict[str, Any],
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = SlackChannel(config={"bot_token": "xoxb-1"}, on_message=_on_message)
        ws = _FakeWebSocket([])
        processed = await channel._handle_socket_envelope(
            ws,
            {
                "envelope_id": "env-1",
                "type": "events_api",
                "payload": {
                    "event": {
                        "type": "message",
                        "user": "U123",
                        "channel": "C999",
                        "ts": "1700.3",
                        "text": "hello from slack",
                    }
                },
            },
        )

        assert processed is True
        assert ws.sent == ['{"envelope_id": "env-1"}']
        assert emitted == [
            (
                "slack:C999",
                "U123",
                "hello from slack",
                {
                    "channel": "slack",
                    "chat_id": "C999",
                    "channel_id": "C999",
                    "user": "U123",
                    "sender_id": "U123",
                    "message_id": "1700.3",
                    "thread_ts": "",
                    "slack_event": {
                        "type": "message",
                        "user": "U123",
                        "channel": "C999",
                        "ts": "1700.3",
                        "text": "hello from slack",
                    },
                },
            )
        ]

    asyncio.run(_scenario())


def test_slack_socket_mode_ignores_bot_and_acl_blocked_messages() -> None:
    async def _scenario() -> None:
        emitted: list[str] = []

        async def _on_message(
            session_id: str,
            user_id: str,
            text: str,
            metadata: dict[str, Any],
        ) -> None:
            del session_id, user_id, metadata
            emitted.append(text)

        channel = SlackChannel(
            config={"bot_token": "xoxb-1", "allow_from": ["U-allowed"]},
            on_message=_on_message,
        )

        bot_message = await channel._handle_slack_event(
            {
                "event": {
                    "type": "message",
                    "bot_id": "B123",
                    "user": "U-bot",
                    "channel": "C1",
                    "ts": "1.0",
                    "text": "ignore bot",
                }
            }
        )
        blocked = await channel._handle_slack_event(
            {
                "event": {
                    "type": "message",
                    "user": "U-blocked",
                    "channel": "C1",
                    "ts": "1.1",
                    "text": "ignore acl",
                }
            }
        )
        allowed = await channel._handle_slack_event(
            {
                "event": {
                    "type": "app_mention",
                    "user": "U-allowed",
                    "channel": "C1",
                    "ts": "1.2",
                    "text": "<@bot> hi",
                }
            }
        )

        assert bot_message is False
        assert blocked is False
        assert allowed is True
        assert emitted == ["<@bot> hi"]

    asyncio.run(_scenario())


def test_slack_typing_keepalive_adds_and_removes_working_indicator(monkeypatch) -> None:
    async def _scenario() -> None:
        client = _FakeClient(
            [
                _response(status=200, url="https://slack.com/api/reactions.add", payload={"ok": True}),
                _response(status=200, url="https://slack.com/api/reactions.remove", payload={"ok": True}),
            ]
        )

        def _factory(*args, **kwargs):
            del args, kwargs
            return client

        monkeypatch.setattr(httpx, "AsyncClient", _factory)

        channel = SlackChannel(config={"bot_token": "xoxb-1", "typing_enabled": True})
        await channel.start()
        channel._latest_inbound_ts["C123"] = "1700.4"

        channel._start_typing_keepalive(chat_id="C123")
        await asyncio.sleep(0)
        await channel._stop_typing_keepalive(chat_id="C123")
        await channel.stop()

        assert [row[0] for row in client.posts] == [
            "https://slack.com/api/reactions.add",
            "https://slack.com/api/reactions.remove",
        ]
        assert client.posts[0][1]["timestamp"] == "1700.4"
        assert client.posts[1][1]["name"] == "hourglass_flowing_sand"

    asyncio.run(_scenario())
