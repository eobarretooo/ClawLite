from __future__ import annotations

import asyncio
import ipaddress
import html
import json
import re
import socket
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from clawlite.tools.base import Tool, ToolContext
from clawlite.utils.logging import bind_event, setup_logging

setup_logging()


class WebFetchTool(Tool):
    name = "web_fetch"
    description = "Fetch text content from URL."

    def __init__(
        self,
        *,
        proxy: str = "",
        max_redirects: int = 5,
        timeout: float = 15,
        max_chars: int = 12000,
        allowlist: list[str] | None = None,
        denylist: list[str] | None = None,
        block_private_addresses: bool = True,
    ) -> None:
        self.proxy = proxy.strip()
        self.max_redirects = max(0, int(max_redirects))
        self.timeout = max(1.0, float(timeout))
        self.max_chars = max(128, int(max_chars))
        self.allowlist = [str(item).strip().lower() for item in (allowlist or []) if str(item).strip()]
        self.denylist = [str(item).strip().lower() for item in (denylist or []) if str(item).strip()]
        self.block_private_addresses = bool(block_private_addresses)

    def args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "timeout": {"type": "number", "default": 15},
                "mode": {"type": "string", "enum": ["auto", "markdown", "text", "raw", "json"], "default": "auto"},
                "extractMode": {"type": "string", "enum": ["auto", "markdown", "text", "raw", "json"], "default": "auto"},
                "max_chars": {"type": "integer", "default": 12000},
                "maxChars": {"type": "integer", "default": 12000},
            },
            "required": ["url"],
        }

    async def run(self, arguments: dict, ctx: ToolContext) -> str:
        url = str(arguments.get("url", "")).strip()
        log = bind_event("tool.web", session=ctx.session_id, tool=self.name)
        if not url:
            return _error_payload(self.name, "invalid_arguments", "url is required")

        mode = str(arguments.get("mode", arguments.get("extractMode", "auto")) or "auto").strip().lower()
        if mode not in {"auto", "markdown", "text", "raw", "json"}:
            return _error_payload(self.name, "invalid_mode", f"unsupported mode: {mode}")

        timeout = max(1.0, float(arguments.get("timeout", self.timeout) or self.timeout))
        max_chars = max(128, int(arguments.get("max_chars", arguments.get("maxChars", self.max_chars)) or self.max_chars))

        try:
            response, hop_count = await self._request_with_redirects(url=url, timeout=timeout)
        except ValueError as exc:
            log.warning("fetch blocked url={} reason={}", url, str(exc))
            return _error_payload(self.name, "blocked_url", str(exc), url=url)
        except httpx.HTTPStatusError as exc:
            status = int(exc.response.status_code) if exc.response is not None else 0
            log.warning("fetch failed url={} status={}", url, status)
            return _error_payload(self.name, "http_error", str(exc), url=url, status_code=status)
        except httpx.ProxyError as exc:
            log.warning("fetch proxy error url={} error={}", url, str(exc))
            return _error_payload(self.name, "proxy_error", str(exc), url=url)
        except httpx.HTTPError as exc:
            log.warning("fetch network error url={} error={}", url, str(exc))
            return _error_payload(self.name, "network_error", str(exc), url=url)

        mime_type = _mime_type(response.headers.get("content-type", ""))
        extracted, extractor = _extract_content(response=response, mode=mode, mime_type=mime_type)
        if extractor == "mode_error":
            return _error_payload(
                self.name,
                "invalid_mode_for_mime",
                f"mode '{mode}' is not valid for content-type '{mime_type or 'unknown'}'",
                url=url,
                content_type=mime_type,
            )

        text = extracted.strip()
        truncated = len(text) > max_chars
        if truncated:
            text = text[:max_chars]

        payload = {
            "url": url,
            "final_url": str(response.url),
            "status_code": int(response.status_code),
            "redirect_count": hop_count,
            "content_type": mime_type,
            "extractor": extractor,
            "truncated": truncated,
            "length": len(text),
            "text": text,
        }
        log.info("fetched url={} status={} redirects={} mime={}", url, int(response.status_code), hop_count, mime_type or "-")
        return _ok_payload(self.name, payload)

    async def _request_with_redirects(self, *, url: str, timeout: float) -> tuple[httpx.Response, int]:
        hops = 0
        current = url
        headers = {"User-Agent": "ClawLiteWebTool/1.0"}

        _, pre_request_ips, hostname_based_target = await self._validate_target(current)
        async with _build_client(timeout=timeout, proxy=self.proxy) as client:
            while True:
                response = await client.get(current, headers=headers)

                if response.is_redirect:
                    location = str(response.headers.get("location", "") or "").strip()
                    if not location:
                        break
                    if hops >= self.max_redirects:
                        raise ValueError(f"redirect limit exceeded ({self.max_redirects})")
                    current = urljoin(str(response.url), location)
                    _, pre_request_ips, hostname_based_target = await self._validate_target(current)
                    hops += 1
                    continue

                _, post_response_ips, _ = await self._validate_target(current)
                if hostname_based_target and not _has_ip_overlap(pre_request_ips, post_response_ips):
                    raise ValueError("resolution changed unexpectedly")
                if hostname_based_target:
                    peer_ip = _extract_peer_ip(response)
                    if peer_ip is not None and peer_ip not in pre_request_ips:
                        raise ValueError("connected peer IP mismatch detected")
                response.raise_for_status()
                return response, hops

        raise ValueError("empty redirect location")

    async def _validate_target(self, raw_url: str) -> tuple[str, list[ipaddress._BaseAddress], bool]:
        parsed = urlparse(raw_url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("only http/https URLs are supported")
        host = (parsed.hostname or "").strip().lower()
        if not host:
            raise ValueError("missing host")

        ip_literal = _ip_literal(host)
        hostname_based_target = ip_literal is None
        ips = [ip_literal] if ip_literal is not None else await _resolve_ips_async(host)

        if _matches_rules(host=host, ips=ips, rules=self.denylist):
            raise ValueError("target host denied by policy")
        if self.allowlist and not _matches_rules(host=host, ips=ips, rules=self.allowlist):
            raise ValueError("target host is not in allowlist")

        if self.block_private_addresses:
            for ip in ips:
                if ip.is_loopback or ip.is_link_local or ip.is_private or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
                    raise ValueError("target resolves to private or local address")

        return host, ips, hostname_based_target


class WebSearchTool(Tool):
    name = "web_search"
    description = "Search the web and return snippets."

    def __init__(self, *, proxy: str = "", timeout: float = 10) -> None:
        self.proxy = proxy.strip()
        self.timeout = max(1.0, float(timeout))

    def args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 5},
                "timeout": {"type": "number", "default": 10},
            },
            "required": ["query"],
        }

    async def run(self, arguments: dict, ctx: ToolContext) -> str:
        query = str(arguments.get("query", "")).strip()
        log = bind_event("tool.web", session=ctx.session_id, tool=self.name)
        if not query:
            return _error_payload(self.name, "invalid_arguments", "query is required")
        limit = max(1, min(10, int(arguments.get("limit", 5) or 5)))
        timeout = max(1.0, float(arguments.get("timeout", self.timeout) or self.timeout))
        try:
            from duckduckgo_search import DDGS
        except Exception as exc:  # pragma: no cover
            return _error_payload(self.name, "dependency_error", str(exc))

        try:
            rows = await asyncio.to_thread(
                _search_ddgs_sync,
                DDGS,
                query,
                limit,
                self.proxy,
                timeout,
            )
            text_lines = [f"- {item['title']}\n  {item['url']}\n  {item['snippet']}" for item in rows]
            payload = {
                "query": query,
                "count": len(rows),
                "items": rows,
                "text": "\n".join(text_lines),
            }
            log.info("search query={} results={}", query, len(rows))
            return _ok_payload(self.name, payload)
        except httpx.ProxyError as exc:
            return _error_payload(self.name, "proxy_error", str(exc), query=query)
        except Exception as exc:
            return _error_payload(self.name, "search_error", str(exc), query=query)


def _ok_payload(tool: str, result: dict[str, Any]) -> str:
    return json.dumps({"ok": True, "tool": tool, "result": result}, ensure_ascii=False)


def _error_payload(tool: str, code: str, message: str, **extra: Any) -> str:
    payload: dict[str, Any] = {
        "ok": False,
        "tool": tool,
        "error": {"code": code, "message": message},
    }
    if extra:
        payload["error"]["context"] = extra
    return json.dumps(payload, ensure_ascii=False)


def _resolve_ips(host: str) -> list[ipaddress._BaseAddress]:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise ValueError(f"failed to resolve host: {host}") from exc
    rows: list[ipaddress._BaseAddress] = []
    for info in infos:
        value = str(info[4][0])
        ip = _ip_literal(value)
        if ip is not None and ip not in rows:
            rows.append(ip)
    if not rows:
        raise ValueError(f"failed to resolve host: {host}")
    return rows


async def _resolve_ips_async(host: str) -> list[ipaddress._BaseAddress]:
    return await asyncio.to_thread(_resolve_ips, host)


def _ip_literal(value: str) -> ipaddress._BaseAddress | None:
    try:
        return ipaddress.ip_address(value)
    except ValueError:
        return None


def _matches_rules(*, host: str, ips: list[ipaddress._BaseAddress], rules: list[str]) -> bool:
    for raw_rule in rules:
        rule = raw_rule.strip().lower()
        if not rule:
            continue
        if rule.startswith("*."):
            suffix = rule[1:]
            if host.endswith(suffix):
                return True
            continue
        if rule.startswith("."):
            if host.endswith(rule):
                return True
            continue
        if "/" in rule:
            try:
                network = ipaddress.ip_network(rule, strict=False)
            except ValueError:
                network = None
            if network is not None and any(ip in network for ip in ips):
                return True
            continue
        rule_ip = _ip_literal(rule)
        if rule_ip is not None and any(ip == rule_ip for ip in ips):
            return True
        if host == rule:
            return True
    return False


def _has_ip_overlap(
    pre_request_ips: list[ipaddress._BaseAddress],
    post_response_ips: list[ipaddress._BaseAddress],
) -> bool:
    pre_values = set(pre_request_ips)
    return any(ip in pre_values for ip in post_response_ips)


def _mime_type(raw: str) -> str:
    return str(raw or "").split(";", 1)[0].strip().lower()


def _extract_peer_ip(response: httpx.Response) -> ipaddress._BaseAddress | None:
    extensions = getattr(response, "extensions", None)
    if not isinstance(extensions, dict):
        return None

    stream = extensions.get("network_stream")
    if stream is None:
        return None

    for key in ("socket", "ssl_object", "peername"):
        candidate = _extract_ip_from_extra_info(stream, key)
        if candidate is not None:
            return candidate
    return None


def _extract_ip_from_extra_info(stream: Any, key: str) -> ipaddress._BaseAddress | None:
    getter = getattr(stream, "get_extra_info", None)
    if not callable(getter):
        return None
    try:
        value = getter(key)
    except Exception:
        return None
    return _coerce_extra_info_to_ip(value)


def _coerce_extra_info_to_ip(value: Any) -> ipaddress._BaseAddress | None:
    if value is None:
        return None
    if isinstance(value, tuple) and value:
        host = str(value[0])
        return _ip_literal(host)

    family_getter = getattr(value, "family", None)
    if family_getter is not None:
        for getter_name in ("getpeername",):
            getter = getattr(value, getter_name, None)
            if callable(getter):
                try:
                    peer = getter()
                except Exception:
                    peer = None
                if isinstance(peer, tuple) and peer:
                    host = str(peer[0])
                    ip = _ip_literal(host)
                    if ip is not None:
                        return ip

    if isinstance(value, str):
        return _ip_literal(value)
    return None


def _extract_content(*, response: httpx.Response, mode: str, mime_type: str) -> tuple[str, str]:
    is_html = "text/html" in mime_type or response.text[:256].lstrip().lower().startswith("<!doctype") or response.text[:256].lstrip().lower().startswith("<html")
    if mode == "json" and "application/json" not in mime_type:
        return "", "mode_error"

    if "application/json" in mime_type:
        try:
            return json.dumps(response.json(), ensure_ascii=False, indent=2), "json"
        except Exception:
            return response.text, "raw"

    if is_html:
        if mode in {"auto", "markdown"}:
            return _html_to_markdown(response.text), "html_markdown"
        if mode == "text":
            return _html_to_text(response.text), "html_text"
        return response.text, "raw"

    if mode == "raw":
        return response.text, "raw"
    return response.text, "text"


def _html_to_text(raw_html: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", "", raw_html, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", "", text, flags=re.I)
    text = re.sub(r"<noscript[\s\S]*?</noscript>", "", text, flags=re.I)
    text = re.sub(r"<(br|hr)\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</(p|div|section|article|li|h[1-6])>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


def _html_to_markdown(raw_html: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", "", raw_html, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", "", text, flags=re.I)
    text = re.sub(r"<noscript[\s\S]*?</noscript>", "", text, flags=re.I)
    text = re.sub(
        r"<a\s+[^>]*href=[\"']([^\"']+)[\"'][^>]*>([\s\S]*?)</a>",
        lambda m: f"[{_html_to_text(m[2]).strip()}]({m[1]})",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"<h([1-6])[^>]*>([\s\S]*?)</h\1>",
        lambda m: f"\n{'#' * int(m[1])} {_html_to_text(m[2]).strip()}\n",
        text,
        flags=re.I,
    )
    text = re.sub(r"<li[^>]*>([\s\S]*?)</li>", lambda m: f"\n- {_html_to_text(m[1]).strip()}", text, flags=re.I)
    text = re.sub(r"</(p|div|section|article)>", "\n\n", text, flags=re.I)
    text = re.sub(r"<(br|hr)\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _build_client(*, timeout: float, proxy: str) -> httpx.AsyncClient:
    kwargs: dict[str, Any] = {"timeout": timeout, "follow_redirects": False}
    if proxy:
        kwargs["proxy"] = proxy
    try:
        return httpx.AsyncClient(**kwargs)
    except TypeError:
        if "proxy" in kwargs:
            value = kwargs.pop("proxy")
            kwargs["proxies"] = value
        return httpx.AsyncClient(**kwargs)


def _search_ddgs_sync(
    ddgs_cls: Any,
    query: str,
    limit: int,
    proxy: str,
    timeout: float,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with ddgs_cls(proxy=proxy or None, timeout=int(timeout)) as ddgs:
        for item in ddgs.text(query, max_results=limit):
            title = str(item.get("title", "")).strip()
            href = str(item.get("href", "")).strip()
            body = str(item.get("body", "")).strip()
            rows.append({"title": title, "url": href, "snippet": body})
    return rows
