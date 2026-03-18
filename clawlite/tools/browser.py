from __future__ import annotations

import base64
import os
import time
from typing import Any
from urllib.parse import urlparse

from clawlite.tools.base import Tool, ToolContext, ToolHealthResult
from clawlite.tools.web import _ip_literal
from clawlite.tools.web import _matches_rules
from clawlite.tools.web import _resolve_ips_async


class BrowserTool(Tool):
    name = "browser"
    description = (
        "Control a headless browser. Actions: navigate (go to URL, returns page text), "
        "click (CSS selector), fill (CSS selector + value), screenshot (base64 PNG), "
        "evaluate (run JavaScript), close."
    )

    def __init__(
        self,
        *,
        headless: bool = True,
        timeout_ms: int = 20_000,
        screenshot_dir: str | None = None,
        allowlist: list[str] | None = None,
        denylist: list[str] | None = None,
        block_private_addresses: bool = True,
    ) -> None:
        self.headless = bool(headless)
        self.timeout_ms = max(1000, int(timeout_ms or 20_000))
        self.screenshot_dir = screenshot_dir
        self.allowlist = [str(item).strip().lower() for item in (allowlist or []) if str(item).strip()]
        self.denylist = [str(item).strip().lower() for item in (denylist or []) if str(item).strip()]
        self.block_private_addresses = bool(block_private_addresses)
        self._playwright: Any = None
        self._browser: Any = None
        self._page: Any = None

    def args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["navigate", "click", "fill", "screenshot", "evaluate", "close"]},
                "url": {"type": "string"},
                "selector": {"type": "string"},
                "value": {"type": "string"},
                "script": {"type": "string"},
                "wait_for": {"type": "string", "enum": ["load", "networkidle", "domcontentloaded"], "default": "load"},
            },
            "required": ["action"],
        }

    @staticmethod
    def _playwright_setup_hint(exc: Exception) -> str:
        message = str(exc or "").strip()
        lowered = message.lower()
        if "executable doesn't exist" in lowered or "playwright install" in lowered:
            return f"{message} (hint: run `playwright install chromium`)"
        if "no module named 'playwright'" in lowered or 'no module named "playwright"' in lowered:
            return (
                f"{message} "
                "(hint: install the browser extra with `pip install \"clawlite[browser]\"` "
                "and then run `playwright install chromium`)"
            )
        return message or exc.__class__.__name__.lower()

    async def _ensure_browser(self) -> Any:
        from playwright.async_api import async_playwright

        if self._browser is not None:
            return self._browser

        playwright = await async_playwright().start()
        try:
            browser = await playwright.chromium.launch(headless=self.headless)
        except Exception:
            try:
                await playwright.stop()
            finally:
                self._playwright = None
            raise

        self._playwright = playwright
        self._browser = browser
        return browser

    async def _ensure_page(self) -> Any:
        browser = await self._ensure_browser()
        if self._page is None or self._page.is_closed():
            self._page = await browser.new_page()
            self._page.set_default_timeout(self.timeout_ms)
        return self._page

    async def _validate_target(self, raw_url: str) -> None:
        parsed = urlparse(str(raw_url or "").strip())
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("only http/https URLs are supported")
        host = (parsed.hostname or "").strip().lower()
        if not host:
            raise ValueError("missing host")

        ip_literal = _ip_literal(host)
        ips = [ip_literal] if ip_literal is not None else await _resolve_ips_async(host)

        if _matches_rules(host=host, ips=ips, rules=self.denylist):
            raise ValueError("target host denied by policy")
        if self.allowlist and not _matches_rules(host=host, ips=ips, rules=self.allowlist):
            raise ValueError("target host is not in allowlist")

        if self.block_private_addresses:
            for ip in ips:
                if ip.is_loopback or ip.is_link_local or ip.is_private or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
                    raise ValueError("target resolves to private or local address")

    async def _close_runtime(self) -> None:
        page = self._page
        browser = self._browser
        playwright = self._playwright
        self._page = None
        self._browser = None
        self._playwright = None

        if page is not None and not page.is_closed():
            await page.close()
        if browser is not None:
            await browser.close()
        if playwright is not None:
            await playwright.stop()

    async def run(self, arguments: dict, ctx: ToolContext) -> str:
        del ctx
        action = str(arguments.get("action", "") or "").strip().lower()
        try:
            if action == "navigate":
                url = str(arguments.get("url", "") or "").strip()
                if not url:
                    return "error: url is required"
                await self._validate_target(url)
                page = await self._ensure_page()
                response = await page.goto(
                    url,
                    wait_until=str(arguments.get("wait_for", "load") or "load"),
                    timeout=self.timeout_ms,
                )
                status = response.status if response else 0
                title = await page.title()
                text = (await page.inner_text("body"))[:8000]
                return f"[{status}] {title}\n\n{text}"
            if action == "click":
                selector = str(arguments.get("selector", "") or "").strip()
                if not selector:
                    return "error: selector required"
                await (await self._ensure_page()).click(selector, timeout=self.timeout_ms)
                return f"clicked: {selector}"
            if action == "fill":
                selector = str(arguments.get("selector", "") or "").strip()
                if not selector:
                    return "error: selector required"
                await (await self._ensure_page()).fill(selector, str(arguments.get("value", "") or ""), timeout=self.timeout_ms)
                return f"filled: {selector}"
            if action == "screenshot":
                page = await self._ensure_page()
                if self.screenshot_dir:
                    os.makedirs(self.screenshot_dir, exist_ok=True)
                    path = f"{self.screenshot_dir}/screenshot-{int(time.time())}.png"
                    await page.screenshot(path=path)
                    return f"screenshot saved: {path}"
                return f"data:image/png;base64,{base64.b64encode(await page.screenshot()).decode()}"
            if action == "evaluate":
                script = str(arguments.get("script", "") or "").strip()
                if not script:
                    return "error: script required"
                return str(await (await self._ensure_page()).evaluate(script))
            if action == "close":
                await self._close_runtime()
                return "browser closed"
            return f"error: unknown action '{action}'"
        except Exception as exc:
            return f"browser_error: {self._playwright_setup_hint(exc)}"

    async def health_check(self) -> ToolHealthResult:
        t0 = time.monotonic()
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.goto("about:blank")
                await browser.close()
            latency_ms = (time.monotonic() - t0) * 1000
            if latency_ms > 5000:
                return ToolHealthResult(ok=False, latency_ms=latency_ms, detail="browser_too_slow")
            return ToolHealthResult(ok=True, latency_ms=latency_ms, detail="chromium_ok")
        except Exception as exc:
            detail = self._playwright_setup_hint(exc)
            return ToolHealthResult(ok=False, latency_ms=(time.monotonic() - t0) * 1000, detail=detail)
