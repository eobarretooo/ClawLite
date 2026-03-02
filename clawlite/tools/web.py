from __future__ import annotations

from urllib.parse import urlparse

import httpx

from clawlite.tools.base import Tool, ToolContext


class WebFetchTool(Tool):
    name = "web_fetch"
    description = "Fetch text content from URL."

    def args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "timeout": {"type": "number", "default": 15},
            },
            "required": ["url"],
        }

    async def run(self, arguments: dict, ctx: ToolContext) -> str:
        url = str(arguments.get("url", "")).strip()
        if not url:
            raise ValueError("url is required")

        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("only http/https URLs are supported")

        timeout = float(arguments.get("timeout", 15) or 15)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
        text = response.text.strip()
        return text[:12000]


class WebSearchTool(Tool):
    name = "web_search"
    description = "Search the web and return snippets."

    def args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        }

    async def run(self, arguments: dict, ctx: ToolContext) -> str:
        query = str(arguments.get("query", "")).strip()
        if not query:
            raise ValueError("query is required")
        limit = int(arguments.get("limit", 5) or 5)
        try:
            from duckduckgo_search import DDGS
        except Exception as exc:  # pragma: no cover
            return f"search_unavailable:{exc}"
        rows: list[str] = []
        with DDGS() as ddgs:
            for item in ddgs.text(query, max_results=limit):
                title = str(item.get("title", "")).strip()
                href = str(item.get("href", "")).strip()
                body = str(item.get("body", "")).strip()
                rows.append(f"- {title}\n  {href}\n  {body}")
        return "\n".join(rows) if rows else "no_results"
