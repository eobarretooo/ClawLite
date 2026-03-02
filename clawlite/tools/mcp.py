from __future__ import annotations

import asyncio
import httpx
from urllib.parse import urlparse

from clawlite.config.schema import MCPServerConfig, MCPToolConfig, MCPTransportPolicyConfig

from clawlite.tools.base import Tool, ToolContext
from clawlite.utils.logging import bind_event, setup_logging

setup_logging()


class MCPTool(Tool):
    name = "mcp"
    description = "Call configured MCP server tools via registry."

    def __init__(self, config: MCPToolConfig | None = None) -> None:
        cfg = config or MCPToolConfig()
        self.default_timeout_s = max(0.1, float(cfg.default_timeout_s))
        self.policy = cfg.policy
        self.servers = dict(cfg.servers)

    def args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "server": {"type": "string"},
                "url": {"type": "string"},
                "tool": {"type": "string"},
                "arguments": {"type": "object"},
                "timeout_s": {"type": "number"},
                "timeoutS": {"type": "number"},
            },
            "required": ["tool"],
        }

    async def run(self, arguments: dict, ctx: ToolContext) -> str:
        log = bind_event("tool.mcp", session=ctx.session_id, tool=self.name)
        tool = str(arguments.get("tool", "")).strip()
        payload_args = arguments.get("arguments", {})
        if not isinstance(payload_args, dict):
            raise ValueError("arguments must be an object")
        if not tool:
            raise ValueError("tool is required")

        server_name, resolved_tool = self._resolve_target(arguments=arguments, tool=tool)
        server = self.servers.get(server_name)
        if server is None:
            raise ValueError(f"mcp server not configured: {server_name}")
        if not server.url:
            raise ValueError(f"mcp server has no url configured: {server_name}")

        self._validate_transport(url=server.url, policy=self.policy)
        timeout_s = self._resolve_timeout(arguments=arguments, server=server)

        payload = {
            "jsonrpc": "2.0",
            "id": "clawlite-mcp",
            "method": "tools/call",
            "params": {"name": resolved_tool, "arguments": payload_args},
        }

        try:
            async with httpx.AsyncClient(timeout=timeout_s, headers=server.headers or None) as client:
                response = await asyncio.wait_for(client.post(server.url, json=payload), timeout=timeout_s)
                response.raise_for_status()
                data = response.json()
        except asyncio.TimeoutError:
            log.warning("mcp timeout server={} tool={} timeout={}s", server_name, resolved_tool, timeout_s)
            return f"mcp_error:timeout:{server_name}:{resolved_tool}:{timeout_s}s"
        except httpx.TimeoutException:
            log.warning("mcp timeout server={} tool={} timeout={}s", server_name, resolved_tool, timeout_s)
            return f"mcp_error:timeout:{server_name}:{resolved_tool}:{timeout_s}s"

        log.info("mcp call server={} tool={} method=tools/call", server_name, resolved_tool)

        if isinstance(data, dict) and data.get("error"):
            return f"mcp_error:{data['error']}"
        return str(data.get("result", data))

    def _resolve_target(self, *, arguments: dict, tool: str) -> tuple[str, str]:
        if not self.servers:
            raise ValueError("mcp server registry is empty")

        server_name = str(arguments.get("server", "")).strip()
        if server_name:
            normalized_tool = self._strip_server_prefix(server_name=server_name, tool=tool)
            return server_name, normalized_tool

        namespaced = self._parse_namespaced_tool(tool)
        if namespaced is not None:
            return namespaced

        legacy_url = str(arguments.get("url", "")).strip()
        if legacy_url:
            matched = self._server_name_from_url(legacy_url)
            if matched is None:
                raise ValueError("url must match a configured mcp server")
            return matched, tool

        if len(self.servers) == 1:
            only = next(iter(self.servers.keys()))
            return only, tool

        raise ValueError("server is required (or use namespaced tool like 'server::tool')")

    def _resolve_timeout(self, *, arguments: dict, server: MCPServerConfig) -> float:
        configured = max(0.1, float(server.timeout_s or self.default_timeout_s))
        requested_raw = arguments.get("timeout_s", arguments.get("timeoutS"))
        if requested_raw is None:
            return configured
        try:
            requested = max(0.1, float(requested_raw))
        except (TypeError, ValueError):
            return configured
        return min(configured, requested)

    def _parse_namespaced_tool(self, tool: str) -> tuple[str, str] | None:
        for separator in ("::", "/"):
            if separator not in tool:
                continue
            server_name, nested_tool = tool.split(separator, 1)
            server_name = server_name.strip()
            nested_tool = nested_tool.strip()
            if server_name and nested_tool and server_name in self.servers:
                return server_name, nested_tool
        return None

    def _strip_server_prefix(self, *, server_name: str, tool: str) -> str:
        normalized = tool.strip()
        for separator in ("::", "/"):
            prefix = f"{server_name}{separator}"
            if normalized.startswith(prefix):
                return normalized[len(prefix) :].strip()
        return normalized

    def _server_name_from_url(self, url: str) -> str | None:
        candidate = self._normalize_url(url)
        for name, server in self.servers.items():
            if self._normalize_url(server.url) == candidate:
                return name
        return None

    @staticmethod
    def _normalize_url(url: str) -> str:
        return str(url or "").strip().rstrip("/")

    @staticmethod
    def _validate_transport(*, url: str, policy: MCPTransportPolicyConfig) -> None:
        parsed = urlparse(url)
        scheme = str(parsed.scheme or "").strip().lower()
        if not scheme:
            raise ValueError("mcp server url missing scheme")
        host = str(parsed.hostname or "").strip().lower()
        if not host:
            raise ValueError("mcp server url missing host")

        allowed_schemes = [str(item).strip().lower() for item in policy.allowed_schemes if str(item).strip()]
        allowed_hosts = [str(item).strip().lower() for item in policy.allowed_hosts if str(item).strip()]
        denied_hosts = [str(item).strip().lower() for item in policy.denied_hosts if str(item).strip()]

        if allowed_schemes and scheme not in allowed_schemes:
            raise ValueError(f"mcp transport policy rejected scheme '{scheme}'")
        if _match_any(host=host, rules=denied_hosts):
            raise ValueError(f"mcp transport policy denied host '{host}'")
        if allowed_hosts and not _match_any(host=host, rules=allowed_hosts):
            raise ValueError(f"mcp transport policy blocked host '{host}'")


def _host_matches(rule: str, host: str) -> bool:
    value = rule.strip().lower()
    if not value:
        return False
    if value.startswith("*."):
        return host.endswith(value[1:])
    return host == value


def _match_any(*, host: str, rules: list[str]) -> bool:
    return any(_host_matches(rule, host) for rule in rules)
