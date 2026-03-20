from __future__ import annotations

import asyncio
import ipaddress
from unittest.mock import AsyncMock, patch

import httpx

from clawlite.config.schema import MCPServerConfig, MCPToolConfig, MCPTransportPolicyConfig
from clawlite.tools.base import ToolContext
from clawlite.tools.mcp import MCPTool


def _tool() -> MCPTool:
    return MCPTool(
        MCPToolConfig(
            default_timeout_s=2,
            policy=MCPTransportPolicyConfig(allowed_schemes=["https"], allowed_hosts=["example.com"]),
            servers={
                "local": MCPServerConfig(
                    url="https://example.com/call",
                    headers={"Authorization": "Bearer x"},
                    timeout_s=0.2,
                )
            },
        )
    )


def test_mcp_tool_namespaced_server_lookup() -> None:
    async def _scenario() -> None:
        fake_response = AsyncMock()
        fake_response.status_code = 200
        fake_response.json = lambda: {"result": {"ok": True}}
        with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake_response)):
            out = await _tool().run({"tool": "local::skill.test", "arguments": {"x": 1}}, ToolContext(session_id="s"))
        assert "ok" in out

    asyncio.run(_scenario())


def test_mcp_tool_legacy_url_must_match_registry() -> None:
    async def _scenario() -> None:
        fake_response = AsyncMock()
        fake_response.status_code = 200
        fake_response.json = lambda: {"result": {"ok": True}}
        tool = _tool()
        with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake_response)):
            out = await tool.run(
                {"url": "https://example.com/call", "tool": "skill.test", "arguments": {}},
                ToolContext(session_id="s"),
            )
            assert "ok" in out

        try:
            await tool.run(
                {"url": "https://evil.local/call", "tool": "skill.test", "arguments": {}},
                ToolContext(session_id="s"),
            )
            raise AssertionError("expected registry mismatch")
        except ValueError as exc:
            assert "configured mcp server" in str(exc)

    asyncio.run(_scenario())


def test_mcp_tool_timeout_enforced() -> None:
    async def _scenario() -> None:
        async def _slow_post(*args, **kwargs):
            await asyncio.sleep(0.5)
            return AsyncMock()

        with patch("httpx.AsyncClient.post", new=_slow_post):
            out = await _tool().run(
                {"tool": "local::skill.test", "arguments": {}, "timeout_s": 2},
                ToolContext(session_id="s"),
            )

        assert out.startswith("mcp_error:timeout:local:skill.test")

    asyncio.run(_scenario())


def test_mcp_tool_transport_policy_blocks_disallowed_host() -> None:
    async def _scenario() -> None:
        tool = MCPTool(
            MCPToolConfig(
                policy=MCPTransportPolicyConfig(allowed_schemes=["https"], allowed_hosts=["safe.example.com"]),
                servers={"unsafe": MCPServerConfig(url="https://example.com/call", timeout_s=1)},
            )
        )
        try:
            await tool.run({"tool": "unsafe::skill.test", "arguments": {}}, ToolContext(session_id="s"))
            raise AssertionError("expected policy block")
        except ValueError as exc:
            assert "blocked host" in str(exc)

    asyncio.run(_scenario())


def test_mcp_tool_http_status_error_is_deterministic() -> None:
    async def _scenario() -> None:
        fake_response = AsyncMock()
        fake_response.status_code = 503
        fake_response.json = lambda: {"error": "unavailable"}

        with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake_response)):
            out = await _tool().run(
                {"tool": "local::skill.test", "arguments": {}},
                ToolContext(session_id="s"),
            )

        assert out == "mcp_error:http_status:local:skill.test:503"

    asyncio.run(_scenario())


def test_mcp_tool_invalid_json_response_is_deterministic() -> None:
    async def _scenario() -> None:
        fake_response = AsyncMock()
        fake_response.status_code = 200

        def _invalid_json():
            raise ValueError("invalid json")

        fake_response.json = _invalid_json
        with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake_response)):
            out = await _tool().run(
                {"tool": "local::skill.test", "arguments": {}},
                ToolContext(session_id="s"),
            )

        assert out == "mcp_error:invalid_response:local:skill.test"

    asyncio.run(_scenario())


def test_mcp_tool_retries_transient_timeout_then_succeeds() -> None:
    async def _scenario() -> None:
        fake_response = AsyncMock()
        fake_response.status_code = 200
        fake_response.json = lambda: {"result": {"ok": True, "retry": 1}}

        post = AsyncMock(side_effect=[httpx.ReadTimeout("transient timeout"), fake_response])
        with patch("httpx.AsyncClient.post", new=post):
            out = await _tool().run(
                {"tool": "local::skill.test", "arguments": {}},
                ToolContext(session_id="s"),
            )

        assert "ok" in out
        assert post.await_count == 2

    asyncio.run(_scenario())


def test_mcp_tool_blocks_private_resolved_ip() -> None:
    async def _scenario() -> None:
        tool = MCPTool(
            MCPToolConfig(
                policy=MCPTransportPolicyConfig(allowed_schemes=["https"]),
                servers={"local": MCPServerConfig(url="https://service.internal/call", timeout_s=1)},
            )
        )
        with patch("clawlite.tools.mcp._resolve_ips_async", new=AsyncMock(return_value=[ipaddress.ip_address("127.0.0.1")])):
            try:
                await tool.run({"tool": "local::skill.test", "arguments": {}}, ToolContext(session_id="s"))
                raise AssertionError("expected private IP block")
            except ValueError as exc:
                assert "denied resolved address" in str(exc)

    asyncio.run(_scenario())


def test_mcp_tool_blocks_metadata_service_ip_outside_builtin_private_sets() -> None:
    async def _scenario() -> None:
        tool = MCPTool(
            MCPToolConfig(
                policy=MCPTransportPolicyConfig(allowed_schemes=["https"]),
                servers={"local": MCPServerConfig(url="https://100.100.100.200/call", timeout_s=1)},
            )
        )
        try:
            await tool.run({"tool": "local::skill.test", "arguments": {}}, ToolContext(session_id="s"))
            raise AssertionError("expected metadata IP block")
        except ValueError as exc:
            assert "denied resolved address" in str(exc)

    asyncio.run(_scenario())


def test_mcp_tool_retries_with_single_client_instance() -> None:
    async def _scenario() -> None:
        fake_response = AsyncMock()
        fake_response.status_code = 200
        fake_response.json = lambda: {"result": {"ok": True}}

        state = {"instances": 0, "post_calls": 0}

        class FakeClient:
            def __init__(self, *args, **kwargs) -> None:
                state["instances"] += 1

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb) -> None:
                return None

            async def post(self, *args, **kwargs):
                state["post_calls"] += 1
                if state["post_calls"] == 1:
                    raise httpx.ReadTimeout("transient timeout")
                return fake_response

        with patch("httpx.AsyncClient", new=FakeClient):
            out = await _tool().run(
                {"tool": "local::skill.test", "arguments": {}},
                ToolContext(session_id="s"),
            )

        assert "ok" in out
        assert state["instances"] == 1
        assert state["post_calls"] == 2

    asyncio.run(_scenario())
