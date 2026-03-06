from __future__ import annotations

import asyncio
import json
from types import ModuleType
from typing import Any
from unittest.mock import patch

from clawlite.tools.base import ToolContext
from clawlite.tools.web import WebFetchTool, WebSearchTool, _html_to_markdown, _html_to_text


class _FakeResponse:
    def __init__(
        self,
        text: str,
        *,
        url: str = "https://example.com",
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.text = text
        self.url = url
        self.status_code = status_code
        self.headers = headers or {"content-type": "text/plain"}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"status={self.status_code}")

    @property
    def is_redirect(self) -> bool:
        return 300 <= self.status_code < 400

    def json(self) -> Any:
        return json.loads(self.text)


class _FakeClient:
    def __init__(self, responses: list[_FakeResponse], **_: Any) -> None:
        self._responses = list(responses)

    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def get(self, url: str, headers: dict[str, str] | None = None) -> _FakeResponse:
        if not self._responses:
            raise RuntimeError("no fake response")
        response = self._responses.pop(0)
        response.url = url
        return response


def _public_dns(*_: Any) -> list[tuple[Any, Any, Any, Any, tuple[str, int]]]:
    return [(0, 0, 0, "", ("93.184.216.34", 0))]


def test_web_fetch_tool() -> None:
    async def _scenario() -> None:
        responses = [_FakeResponse("ok page", headers={"content-type": "text/plain"})]
        with patch("clawlite.tools.web.socket.getaddrinfo", side_effect=_public_dns), patch(
            "httpx.AsyncClient",
            side_effect=lambda **kwargs: _FakeClient(responses, **kwargs),
        ):
            out = await WebFetchTool().run({"url": "https://example.com"}, ToolContext(session_id="s"))
            payload = json.loads(out)
            assert payload["ok"] is True
            assert payload["result"]["text"] == "ok page"

    asyncio.run(_scenario())


def test_web_fetch_blocks_private_target() -> None:
    async def _scenario() -> None:
        out = await WebFetchTool().run({"url": "http://127.0.0.1"}, ToolContext(session_id="s"))
        payload = json.loads(out)
        assert payload["ok"] is False
        assert payload["error"]["code"] == "blocked_url"

    asyncio.run(_scenario())


def test_web_fetch_redirect_limit() -> None:
    async def _scenario() -> None:
        responses = [
            _FakeResponse("", status_code=302, headers={"location": "https://example.com/r1"}),
            _FakeResponse("", status_code=302, headers={"location": "https://example.com/r2"}),
            _FakeResponse("final", headers={"content-type": "text/plain"}),
        ]
        tool = WebFetchTool(max_redirects=1)
        with patch("clawlite.tools.web.socket.getaddrinfo", side_effect=_public_dns), patch(
            "httpx.AsyncClient",
            side_effect=lambda **kwargs: _FakeClient(responses, **kwargs),
        ):
            out = await tool.run({"url": "https://example.com"}, ToolContext(session_id="s"))
            payload = json.loads(out)
            assert payload["ok"] is False
            assert payload["error"]["code"] == "blocked_url"

    asyncio.run(_scenario())


def test_web_fetch_mode_json_requires_json_mime() -> None:
    async def _scenario() -> None:
        responses = [_FakeResponse("plain text", headers={"content-type": "text/plain"})]
        with patch("clawlite.tools.web.socket.getaddrinfo", side_effect=_public_dns), patch(
            "httpx.AsyncClient",
            side_effect=lambda **kwargs: _FakeClient(responses, **kwargs),
        ):
            out = await WebFetchTool().run({"url": "https://example.com", "mode": "json"}, ToolContext(session_id="s"))
            payload = json.loads(out)
            assert payload["ok"] is False
            assert payload["error"]["code"] == "invalid_mode_for_mime"

    asyncio.run(_scenario())


def test_web_search_tool_returns_structured_payload() -> None:
    class _DDGS:
        def __init__(self, **_: Any) -> None:
            return

        def __enter__(self) -> _DDGS:
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def text(self, query: str, max_results: int):
            assert query == "clawlite"
            assert max_results == 2
            return [
                {"title": "A", "href": "https://a.test", "body": "aa"},
                {"title": "B", "href": "https://b.test", "body": "bb"},
            ]

    async def _scenario() -> None:
        module = ModuleType("duckduckgo_search")
        module.DDGS = _DDGS
        with patch.dict("sys.modules", {"duckduckgo_search": module}):
            out = await WebSearchTool(proxy="http://127.0.0.1:8080").run(
                {"query": "clawlite", "limit": 2},
                ToolContext(session_id="s"),
            )
            payload = json.loads(out)
            assert payload["ok"] is True
            assert payload["result"]["count"] == 2
            assert payload["result"]["items"][0]["url"] == "https://a.test"

    asyncio.run(_scenario())


def test_html_extractors_strip_multiline_blocks() -> None:
    source = """
    <html>
      <head>
        <style>
          .hidden {
            display: none;
          }
        </style>
        <script>
          const x = "should not appear";
          console.log(x);
        </script>
      </head>
      <body>
        <noscript>
          this should also be removed
        </noscript>
        <h2>Title</h2>
        <p>Hello <a href="https://example.com">world</a></p>
      </body>
    </html>
    """

    text = _html_to_text(source)
    markdown = _html_to_markdown(source)

    assert "should not appear" not in text
    assert "this should also be removed" not in text
    assert "display: none" not in text
    assert "Hello world" in text

    assert "should not appear" not in markdown
    assert "this should also be removed" not in markdown
    assert "display: none" not in markdown
    assert "## Title" in markdown
    assert "[world](https://example.com)" in markdown
