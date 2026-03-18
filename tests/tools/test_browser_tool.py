from __future__ import annotations

import sys
import types

import pytest

from clawlite.tools.base import ToolContext
from clawlite.tools.browser import BrowserTool


class FakeResponse:
    def __init__(self, status: int) -> None:
        self.status = status


class FakePage:
    def __init__(self) -> None:
        self.closed = False
        self.default_timeout_ms: int | None = None
        self.goto_calls: list[dict[str, object]] = []

    def is_closed(self) -> bool:
        return self.closed

    def set_default_timeout(self, timeout_ms: int) -> None:
        self.default_timeout_ms = timeout_ms

    async def goto(self, url: str, *, wait_until: str, timeout: int) -> FakeResponse:
        self.goto_calls.append({"url": url, "wait_until": wait_until, "timeout": timeout})
        return FakeResponse(200)

    async def title(self) -> str:
        return "Example"

    async def inner_text(self, selector: str) -> str:
        assert selector == "body"
        return "Body text"

    async def close(self) -> None:
        self.closed = True


class FakeBrowser:
    def __init__(self) -> None:
        self.closed = False
        self.pages: list[FakePage] = []

    async def new_page(self) -> FakePage:
        page = FakePage()
        self.pages.append(page)
        return page

    async def close(self) -> None:
        self.closed = True


class FakeChromium:
    def __init__(self, browser: FakeBrowser | None = None, *, launch_error: Exception | None = None) -> None:
        self.browser = browser or FakeBrowser()
        self.launch_error = launch_error
        self.launch_calls = 0

    async def launch(self, *, headless: bool) -> FakeBrowser:
        self.launch_calls += 1
        assert isinstance(headless, bool)
        if self.launch_error is not None:
            raise self.launch_error
        return self.browser


class FakePlaywrightRuntime:
    def __init__(self, chromium: FakeChromium) -> None:
        self.chromium = chromium
        self.stopped = False

    async def stop(self) -> None:
        self.stopped = True


class FakePlaywrightManager:
    def __init__(self, runtimes: list[FakePlaywrightRuntime]) -> None:
        self.runtimes = runtimes

    async def start(self) -> FakePlaywrightRuntime:
        if not self.runtimes:
            raise AssertionError("unexpected async_playwright().start()")
        return self.runtimes.pop(0)

    async def __aenter__(self) -> FakePlaywrightRuntime:
        return await self.start()

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


def _install_fake_playwright(monkeypatch: pytest.MonkeyPatch, runtimes: list[FakePlaywrightRuntime]) -> None:
    module = types.ModuleType("playwright.async_api")
    module.async_playwright = lambda: FakePlaywrightManager(runtimes)
    package = types.ModuleType("playwright")
    package.async_api = module
    monkeypatch.setitem(sys.modules, "playwright", package)
    monkeypatch.setitem(sys.modules, "playwright.async_api", module)


@pytest.mark.asyncio
async def test_browser_tool_closes_page_browser_and_playwright(monkeypatch: pytest.MonkeyPatch) -> None:
    first_runtime = FakePlaywrightRuntime(FakeChromium())
    second_runtime = FakePlaywrightRuntime(FakeChromium())
    _install_fake_playwright(monkeypatch, [first_runtime, second_runtime])

    tool = BrowserTool(timeout_ms=1234)
    ctx = ToolContext(session_id="browser:test")

    first = await tool.run({"action": "navigate", "url": "https://example.com"}, ctx)
    assert first == "[200] Example\n\nBody text"
    assert tool._playwright is first_runtime
    assert tool._browser is first_runtime.chromium.browser
    assert tool._page is first_runtime.chromium.browser.pages[0]
    assert tool._page.default_timeout_ms == 1234

    closed = await tool.run({"action": "close"}, ctx)
    assert closed == "browser closed"
    assert first_runtime.chromium.browser.pages[0].closed is True
    assert first_runtime.chromium.browser.closed is True
    assert first_runtime.stopped is True
    assert tool._page is None
    assert tool._browser is None
    assert tool._playwright is None

    second = await tool.run({"action": "navigate", "url": "https://example.org", "wait_for": "domcontentloaded"}, ctx)
    assert second == "[200] Example\n\nBody text"
    assert tool._playwright is second_runtime
    assert second_runtime.chromium.browser.pages[0].goto_calls == [
        {"url": "https://example.org", "wait_until": "domcontentloaded", "timeout": 1234}
    ]

    await tool.run({"action": "close"}, ctx)
    assert second_runtime.stopped is True


@pytest.mark.asyncio
async def test_browser_tool_returns_setup_hint_and_cleans_playwright_on_launch_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launch_error = RuntimeError("Executable doesn't exist at /tmp/chromium/chrome")
    runtime = FakePlaywrightRuntime(FakeChromium(launch_error=launch_error))
    _install_fake_playwright(monkeypatch, [runtime])

    tool = BrowserTool()
    result = await tool.run({"action": "navigate", "url": "https://example.com"}, ToolContext(session_id="browser:test"))

    assert result.startswith("browser_error: Executable doesn't exist at /tmp/chromium/chrome")
    assert "playwright install chromium" in result
    assert runtime.stopped is True
    assert tool._playwright is None
    assert tool._browser is None
    assert tool._page is None


@pytest.mark.asyncio
async def test_browser_tool_blocks_private_or_local_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_runtime = FakePlaywrightRuntime(FakeChromium())
    _install_fake_playwright(monkeypatch, [first_runtime])

    tool = BrowserTool()
    result = await tool.run({"action": "navigate", "url": "http://127.0.0.1:8080"}, ToolContext(session_id="browser:test"))

    assert result == "browser_error: target resolves to private or local address"
    assert tool._playwright is None
    assert tool._browser is None
    assert tool._page is None


@pytest.mark.asyncio
async def test_browser_tool_respects_allowlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakePlaywrightRuntime(FakeChromium())
    _install_fake_playwright(monkeypatch, [runtime])

    async def _fake_resolve(host: str):
        if host == "example.com":
            return []
        return []

    monkeypatch.setattr("clawlite.tools.browser._resolve_ips_async", _fake_resolve)

    tool = BrowserTool(allowlist=["example.com"])
    blocked = await tool.run({"action": "navigate", "url": "https://other.example.org"}, ToolContext(session_id="browser:test"))
    assert blocked == "browser_error: target host is not in allowlist"

    allowed = await tool.run({"action": "navigate", "url": "https://example.com"}, ToolContext(session_id="browser:test"))
    assert allowed == "[200] Example\n\nBody text"
