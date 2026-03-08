from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from clawlite.tools.base import ToolContext
from clawlite.tools.discord_admin import DiscordAdminTool


def _response(
    *,
    method: str,
    url: str,
    status: int,
    payload: dict[str, Any] | list[dict[str, Any]] | None = None,
    text: str = "",
) -> httpx.Response:
    request = httpx.Request(method, url)
    if payload is not None:
        return httpx.Response(status, json=payload, request=request)
    return httpx.Response(status, text=text, request=request)


class _AsyncClientFactory:
    def __init__(self, outcomes: list[httpx.Response]) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, Any]] = []

    def __call__(self, *args, **kwargs):
        timeout = kwargs.get("timeout")
        headers = dict(kwargs.get("headers", {}) or {})
        parent = self

        class _Client:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def request(self, method: str, url: str, json: dict[str, Any] | None = None):
                parent.calls.append(
                    {
                        "method": method,
                        "url": url,
                        "json": dict(json or {}),
                        "headers": dict(headers),
                        "timeout": timeout,
                    }
                )
                if not parent.outcomes:
                    raise AssertionError("unexpected discord admin request")
                return parent.outcomes.pop(0)

        return _Client()


def test_discord_admin_tool_lists_guilds(monkeypatch) -> None:
    async def _scenario() -> None:
        factory = _AsyncClientFactory(
            [
                _response(
                    method="GET",
                    url="https://discord.com/api/v10/users/@me/guilds",
                    status=200,
                    payload=[
                        {
                            "id": "g1",
                            "name": "Alpha",
                            "owner": True,
                            "permissions": "8",
                        }
                    ],
                )
            ]
        )
        monkeypatch.setattr(httpx, "AsyncClient", factory)

        tool = DiscordAdminTool(token="bot-token")
        out = json.loads(await tool.run({"action": "list_guilds"}, ToolContext(session_id="telegram:1")))

        assert out["ok"] is True
        assert out["guilds"][0]["id"] == "g1"
        assert out["guilds"][0]["name"] == "Alpha"
        assert factory.calls[0]["url"].endswith("/users/@me/guilds")
        assert factory.calls[0]["headers"]["Authorization"] == "Bot bot-token"

    asyncio.run(_scenario())


def test_discord_admin_tool_creates_channel(monkeypatch) -> None:
    async def _scenario() -> None:
        factory = _AsyncClientFactory(
            [
                _response(
                    method="GET",
                    url="https://discord.com/api/v10/guilds/g1/channels",
                    status=200,
                    payload=[],
                ),
                _response(
                    method="POST",
                    url="https://discord.com/api/v10/guilds/g1/channels",
                    status=200,
                    payload={"id": "c1", "name": "ops", "type": 0, "parent_id": "cat-1", "topic": "alerts"},
                ),
            ]
        )
        monkeypatch.setattr(httpx, "AsyncClient", factory)

        tool = DiscordAdminTool(token="bot-token")
        out = json.loads(
            await tool.run(
                {
                    "action": "create_channel",
                    "guild_id": "g1",
                    "name": "ops",
                    "kind": "text",
                    "parent_id": "cat-1",
                    "topic": "alerts",
                    "ensure": True,
                },
                ToolContext(session_id="telegram:1"),
            )
        )

        assert out["ok"] is True
        assert out["created"] is True
        assert out["channel"]["name"] == "ops"
        assert factory.calls[1]["json"] == {
            "name": "ops",
            "type": 0,
            "parent_id": "cat-1",
            "topic": "alerts",
        }

    asyncio.run(_scenario())


def test_discord_admin_tool_apply_layout_reuses_existing_rows(monkeypatch) -> None:
    async def _scenario() -> None:
        factory = _AsyncClientFactory(
            [
                _response(
                    method="GET",
                    url="https://discord.com/api/v10/guilds/g1/roles",
                    status=200,
                    payload=[{"id": "r1", "name": "Admin", "permissions": "8", "position": 10}],
                ),
                _response(
                    method="GET",
                    url="https://discord.com/api/v10/guilds/g1/channels",
                    status=200,
                    payload=[
                        {"id": "cat1", "name": "Info", "type": 4, "position": 1},
                        {"id": "c1", "name": "rules", "type": 0, "parent_id": "cat1", "position": 1},
                    ],
                ),
                _response(
                    method="POST",
                    url="https://discord.com/api/v10/guilds/g1/channels",
                    status=200,
                    payload={"id": "c2", "name": "announcements", "type": 0, "parent_id": "cat1", "position": 2},
                ),
            ]
        )
        monkeypatch.setattr(httpx, "AsyncClient", factory)

        tool = DiscordAdminTool(token="bot-token")
        out = json.loads(
            await tool.run(
                {
                    "action": "apply_layout",
                    "guild_id": "g1",
                    "template": {
                        "roles": [{"name": "Admin", "permissions": "8"}],
                        "categories": [
                            {
                                "name": "Info",
                                "channels": [
                                    {"name": "rules", "kind": "text"},
                                    {"name": "announcements", "kind": "text"},
                                ],
                            }
                        ],
                    },
                },
                ToolContext(session_id="telegram:1"),
            )
        )

        assert out["ok"] is True
        assert out["roles"][0]["name"] == "Admin"
        assert out["roles"][0]["created"] is False
        assert out["categories"][0]["name"] == "Info"
        assert out["categories"][0]["created"] is False
        assert out["categories"][0]["channels"][0]["name"] == "rules"
        assert out["categories"][0]["channels"][0]["created"] is False
        assert out["categories"][0]["channels"][1]["name"] == "announcements"
        assert out["categories"][0]["channels"][1]["created"] is True

    asyncio.run(_scenario())


def test_discord_admin_tool_returns_http_error_payload(monkeypatch) -> None:
    async def _scenario() -> None:
        factory = _AsyncClientFactory(
            [
                _response(
                    method="GET",
                    url="https://discord.com/api/v10/guilds/g1/channels",
                    status=403,
                    payload={"message": "Missing Permissions"},
                )
            ]
        )
        monkeypatch.setattr(httpx, "AsyncClient", factory)

        tool = DiscordAdminTool(token="bot-token")
        out = json.loads(await tool.run({"action": "list_channels", "guild_id": "g1"}, ToolContext(session_id="telegram:1")))

        assert out["ok"] is False
        assert out["error"] == "discord_admin_http_403:Missing Permissions"

    asyncio.run(_scenario())
