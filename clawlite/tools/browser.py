from __future__ import annotations
import base64, time
from typing import Any
from clawlite.tools.base import Tool, ToolContext, ToolHealthResult

class BrowserTool(Tool):
    name = "browser"
    description = (
        "Control a headless browser. Actions: navigate (go to URL, returns page text), "
        "click (CSS selector), fill (CSS selector + value), screenshot (base64 PNG), "
        "evaluate (run JavaScript), close."
    )
    def __init__(self, *, headless: bool = True, timeout_ms: int = 20_000, screenshot_dir: str | None = None) -> None:
        self.headless = bool(headless)
        self.timeout_ms = max(1000, int(timeout_ms or 20_000))
        self.screenshot_dir = screenshot_dir
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

    async def _ensure_page(self) -> Any:
        from playwright.async_api import async_playwright
        if self._browser is None:
            pw = await async_playwright().start()
            self._browser = await pw.chromium.launch(headless=self.headless)
        if self._page is None or self._page.is_closed():
            self._page = await self._browser.new_page()
            self._page.set_default_timeout(self.timeout_ms)
        return self._page

    async def run(self, arguments: dict, ctx: ToolContext) -> str:
        action = str(arguments.get("action", "") or "").strip().lower()
        try:
            if action == "navigate":
                url = str(arguments.get("url", "") or "").strip()
                if not url:
                    return "error: url is required"
                page = await self._ensure_page()
                resp = await page.goto(url, wait_until=str(arguments.get("wait_for", "load") or "load"), timeout=self.timeout_ms)
                status = resp.status if resp else 0
                title = await page.title()
                text = (await page.inner_text("body"))[:8000]
                return f"[{status}] {title}\n\n{text}"
            elif action == "click":
                sel = str(arguments.get("selector", "") or "").strip()
                if not sel: return "error: selector required"
                await (await self._ensure_page()).click(sel, timeout=self.timeout_ms)
                return f"clicked: {sel}"
            elif action == "fill":
                sel = str(arguments.get("selector", "") or "").strip()
                if not sel: return "error: selector required"
                await (await self._ensure_page()).fill(sel, str(arguments.get("value", "") or ""), timeout=self.timeout_ms)
                return f"filled: {sel}"
            elif action == "screenshot":
                page = await self._ensure_page()
                if self.screenshot_dir:
                    import os; os.makedirs(self.screenshot_dir, exist_ok=True)
                    path = f"{self.screenshot_dir}/screenshot-{int(time.time())}.png"
                    await page.screenshot(path=path)
                    return f"screenshot saved: {path}"
                return f"data:image/png;base64,{base64.b64encode(await page.screenshot()).decode()}"
            elif action == "evaluate":
                script = str(arguments.get("script", "") or "").strip()
                if not script: return "error: script required"
                return str(await (await self._ensure_page()).evaluate(script))
            elif action == "close":
                if self._page and not self._page.is_closed():
                    await self._page.close(); self._page = None
                if self._browser:
                    await self._browser.close(); self._browser = None
                return "browser closed"
            return f"error: unknown action '{action}'"
        except Exception as exc:
            return f"browser_error: {exc}"

    async def health_check(self) -> ToolHealthResult:
        t0 = time.monotonic()
        try:
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.goto("about:blank")
                await browser.close()
            latency_ms = (time.monotonic() - t0) * 1000
            if latency_ms > 5000:
                return ToolHealthResult(ok=False, latency_ms=latency_ms, detail="browser_too_slow")
            return ToolHealthResult(ok=True, latency_ms=latency_ms, detail="chromium_ok")
        except Exception as exc:
            return ToolHealthResult(ok=False, latency_ms=(time.monotonic() - t0) * 1000, detail=str(exc))
