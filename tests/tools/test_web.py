from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from clawlite.tools.base import ToolContext
from clawlite.tools.web import WebFetchTool


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        return


def test_web_fetch_tool() -> None:
    async def _scenario() -> None:
        with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=_FakeResponse("ok page"))):
            out = await WebFetchTool().run({"url": "https://example.com"}, ToolContext(session_id="s"))
            assert "ok page" in out

    asyncio.run(_scenario())
