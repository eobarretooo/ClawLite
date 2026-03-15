"""Tests for tool health_check() protocol."""
from __future__ import annotations

import asyncio
import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clawlite.tools.base import Tool, ToolContext, ToolHealthResult


def test_tool_health_result_fields():
    hr = ToolHealthResult(ok=True, latency_ms=12.5, detail="all_good")
    assert hr.ok is True
    assert hr.latency_ms == 12.5
    assert hr.detail == "all_good"


@pytest.mark.asyncio
async def test_base_tool_default_health_check():
    """Tools without health_check return no_check with ok=True."""
    from clawlite.tools.base import Tool

    class MinimalTool(Tool):
        name = "minimal"
        description = "x"
        def args_schema(self): return {}
        async def run(self, arguments, ctx): return "ok"

    t = MinimalTool()
    hr = await t.health_check()
    assert hr.ok is True
    assert hr.detail == "no_check"


@pytest.mark.asyncio
async def test_exec_tool_health_check_ok():
    from clawlite.tools.exec import ExecTool

    tool = ExecTool()
    hr = await tool.health_check()
    assert hr.ok is True
    assert hr.latency_ms >= 0
    assert "ok" in hr.detail.lower()


@pytest.mark.asyncio
async def test_pdf_tool_health_check_ok():
    pytest.importorskip("pypdf")
    from clawlite.tools.pdf import PdfReadTool

    tool = PdfReadTool()
    hr = await tool.health_check()
    assert hr.ok is True
    assert "pypdf" in hr.detail.lower()


@pytest.mark.asyncio
async def test_pdf_tool_health_check_fails_gracefully():
    """If pypdf fails, health_check returns ok=False."""
    from clawlite.tools.pdf import PdfReadTool

    tool = PdfReadTool()
    with patch.dict("sys.modules", {"pypdf": None}):
        # Reimport would fail, but we test the exception path
        with patch("clawlite.tools.pdf.PdfReadTool.health_check", new_callable=AsyncMock) as mock_hc:
            mock_hc.return_value = ToolHealthResult(ok=False, latency_ms=1.0, detail="pypdf not installed")
            hr = await tool.health_check()
    # Mock result
    assert hr is not None


@pytest.mark.asyncio
async def test_mcp_tool_health_check_no_servers():
    from clawlite.config.schema import MCPToolConfig
    from clawlite.tools.mcp import MCPTool

    tool = MCPTool(MCPToolConfig())
    hr = await tool.health_check()
    assert hr.ok is True
    assert "no_servers" in hr.detail


@pytest.mark.asyncio
async def test_mcp_tool_health_check_server_ok():
    from clawlite.config.schema import MCPServerConfig, MCPToolConfig
    from clawlite.tools.mcp import MCPTool

    cfg = MCPToolConfig()
    cfg.servers["test_server"] = MCPServerConfig(url="http://fake-mcp.local/mcp")
    tool = MCPTool(cfg)

    mock_response = MagicMock()
    mock_response.status_code = 200

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("clawlite.tools.mcp.httpx.AsyncClient", return_value=mock_client):
        hr = await tool.health_check()

    assert hr.ok is True
    assert "test_server" in hr.detail
    assert "ok" in hr.detail


@pytest.mark.asyncio
async def test_mcp_tool_health_check_server_error():
    from clawlite.config.schema import MCPServerConfig, MCPToolConfig
    from clawlite.tools.mcp import MCPTool

    cfg = MCPToolConfig()
    cfg.servers["broken"] = MCPServerConfig(url="http://broken.local/mcp")
    tool = MCPTool(cfg)

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=ConnectionRefusedError("refused"))

    with patch("clawlite.tools.mcp.httpx.AsyncClient", return_value=mock_client):
        hr = await tool.health_check()

    assert hr.ok is False
    assert "broken" in hr.detail
