from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from clawlite.channels.discord import DiscordChannel
from clawlite.channels.slack import SlackChannel
from clawlite.channels.whatsapp import WhatsAppChannel


def _response(*, status: int, url: str, payload: dict[str, Any] | None = None, text: str = "") -> httpx.Response:
    request = httpx.Request("POST", url)
    if payload is not None:
        return httpx.Response(status, json=payload, request=request)
    return httpx.Response(status, text=text, request=request)


class _ClientFactory:
    def __init__(self, outcome: Any) -> None:
        self.outcome = outcome
        self.calls: list[dict[str, Any]] = []

    def __call__(self, *args, **kwargs):
        timeout = kwargs.get("timeout")
        headers = kwargs.get("headers")
        parent = self

        class _Client:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def post(self, url: str, json: dict[str, Any] | None = None):
                parent.calls.append({"url": url, "json": dict(json or {}), "headers": dict(headers or {}), "timeout": timeout})
                if isinstance(parent.outcome, Exception):
                    raise parent.outcome
                return parent.outcome

        return _Client()


@pytest.mark.parametrize(
    ("channel", "target", "text", "error"),
    [
        (DiscordChannel(config={"token": "x"}), "123", "hello", "discord_not_running"),
        (SlackChannel(config={"bot_token": "x"}), "C123", "hello", "slack_not_running"),
        (WhatsAppChannel(config={"bridge_url": "http://bridge"}), "551199999", "hello", "whatsapp_not_running"),
    ],
)
def test_outbound_channels_raise_when_not_running(channel, target: str, text: str, error: str) -> None:
    async def _scenario() -> None:
        with pytest.raises(RuntimeError, match=error):
            await channel.send(target=target, text=text)

    asyncio.run(_scenario())


def test_discord_send_success_and_http_failure(monkeypatch) -> None:
    async def _scenario() -> None:
        ok_factory = _ClientFactory(
            _response(
                status=200,
                url="https://discord.com/api/v10/channels/123/messages",
                payload={"id": "m-1"},
            )
        )
        monkeypatch.setattr(httpx, "AsyncClient", ok_factory)
        channel = DiscordChannel(config={"token": "bot-token", "timeout_s": 3})
        await channel.start()

        result = await channel.send(target="123", text="ping")

        assert result == "discord:sent:m-1"
        assert ok_factory.calls[0]["url"].endswith("/channels/123/messages")
        assert ok_factory.calls[0]["json"] == {"content": "ping"}
        assert ok_factory.calls[0]["headers"]["Authorization"] == "Bot bot-token"

        fail_factory = _ClientFactory(_response(status=400, url="https://discord.com/api/v10/channels/123/messages", text="bad"))
        monkeypatch.setattr(httpx, "AsyncClient", fail_factory)
        with pytest.raises(RuntimeError, match="discord_send_http_400"):
            await channel.send(target="123", text="ping")

        await channel.stop()

    asyncio.run(_scenario())


def test_slack_send_success_and_api_failure(monkeypatch) -> None:
    async def _scenario() -> None:
        ok_factory = _ClientFactory(
            _response(
                status=200,
                url="https://slack.com/api/chat.postMessage",
                payload={"ok": True, "ts": "1700000000.001"},
            )
        )
        monkeypatch.setattr(httpx, "AsyncClient", ok_factory)
        channel = SlackChannel(config={"bot_token": "xoxb-123"})
        await channel.start()

        result = await channel.send(target="C123", text="hello")

        assert result == "slack:sent:C123:1700000000.001"
        assert ok_factory.calls[0]["url"].endswith("/chat.postMessage")
        assert ok_factory.calls[0]["json"] == {"channel": "C123", "text": "hello"}
        assert ok_factory.calls[0]["headers"]["Authorization"] == "Bearer xoxb-123"

        fail_factory = _ClientFactory(
            _response(
                status=200,
                url="https://slack.com/api/chat.postMessage",
                payload={"ok": False, "error": "channel_not_found"},
            )
        )
        monkeypatch.setattr(httpx, "AsyncClient", fail_factory)
        with pytest.raises(RuntimeError, match="slack_send_api_error:channel_not_found"):
            await channel.send(target="C123", text="hello")

        await channel.stop()

    asyncio.run(_scenario())


def test_whatsapp_send_success_and_request_failure(monkeypatch) -> None:
    async def _scenario() -> None:
        ok_factory = _ClientFactory(
            _response(
                status=200,
                url="http://localhost:3001/send",
                payload={"id": "wa-1"},
            )
        )
        monkeypatch.setattr(httpx, "AsyncClient", ok_factory)
        channel = WhatsAppChannel(config={"bridge_url": "ws://localhost:3001", "bridge_token": "bridge-abc"})
        await channel.start()

        result = await channel.send(target="551199999", text="hello")

        assert result == "whatsapp:sent:wa-1"
        assert ok_factory.calls[0]["url"] == "http://localhost:3001/send"
        assert ok_factory.calls[0]["json"]["target"] == "551199999"
        assert ok_factory.calls[0]["headers"]["Authorization"] == "Bearer bridge-abc"

        request = httpx.Request("POST", "http://localhost:3001/send")
        fail_factory = _ClientFactory(httpx.ConnectError("boom", request=request))
        monkeypatch.setattr(httpx, "AsyncClient", fail_factory)
        with pytest.raises(RuntimeError, match="whatsapp_send_request_error"):
            await channel.send(target="551199999", text="hello")

        await channel.stop()

    asyncio.run(_scenario())
