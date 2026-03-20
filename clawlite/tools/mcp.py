from __future__ import annotations

import asyncio
import ipaddress
import socket
import httpx
from urllib.parse import urlparse

from clawlite.config.schema import MCPServerConfig, MCPToolConfig, MCPTransportPolicyConfig

import time
from clawlite.tools.base import Tool, ToolContext, ToolHealthResult
from clawlite.tools.network_safety import is_blocked_network_address, parse_ip_literal
from clawlite.utils.logging import bind_event


class MCPTool(Tool):
    name = "mcp"
    description = "Call configured MCP server tools via registry."
    _TRANSIENT_RETRY_ATTEMPTS = 2
    _TRANSIENT_RETRY_BACKOFF_S = 0.05

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

        await self._validate_transport(url=server.url, policy=self.policy)
        timeout_s = self._resolve_timeout(arguments=arguments, server=server)

        payload = {
            "jsonrpc": "2.0",
            "id": "clawlite-mcp",
            "method": "tools/call",
            "params": {"name": resolved_tool, "arguments": payload_args},
        }

        async with httpx.AsyncClient(timeout=timeout_s, headers=server.headers or None) as client:
            for attempt in range(1, self._TRANSIENT_RETRY_ATTEMPTS + 1):
                try:
                    response = await asyncio.wait_for(client.post(server.url, json=payload), timeout=timeout_s)
                except (asyncio.TimeoutError, httpx.TimeoutException):
                    if attempt < self._TRANSIENT_RETRY_ATTEMPTS:
                        await asyncio.sleep(self._TRANSIENT_RETRY_BACKOFF_S)
                        continue
                    log.warning("mcp timeout server={} tool={} timeout={}s", server_name, resolved_tool, timeout_s)
                    return f"mcp_error:timeout:{server_name}:{resolved_tool}:{timeout_s}s"
                except (httpx.ConnectError, httpx.ReadError, httpx.NetworkError, httpx.TransportError) as exc:
                    if attempt < self._TRANSIENT_RETRY_ATTEMPTS:
                        await asyncio.sleep(self._TRANSIENT_RETRY_BACKOFF_S)
                        continue
                    log.warning("mcp network error server={} tool={} error={}", server_name, resolved_tool, exc)
                    return f"mcp_error:network:{server_name}:{resolved_tool}"
                status = int(getattr(response, "status_code", 0) or 0)
                if status >= 400:
                    log.warning("mcp http status failure server={} tool={} status={}", server_name, resolved_tool, status)
                    return f"mcp_error:http_status:{server_name}:{resolved_tool}:{status}"
                try:
                    data = response.json()
                except Exception:
                    log.warning("mcp invalid json response server={} tool={}", server_name, resolved_tool)
                    return f"mcp_error:invalid_response:{server_name}:{resolved_tool}"

                log.info("mcp call server={} tool={} method=tools/call", server_name, resolved_tool)

                if not isinstance(data, dict):
                    return f"mcp_error:invalid_response:{server_name}:{resolved_tool}"
                if data.get("error"):
                    return f"mcp_error:{data['error']}"
                if "result" not in data:
                    return f"mcp_error:invalid_response:{server_name}:{resolved_tool}"
                return str(data.get("result"))

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

    async def health_check(self) -> ToolHealthResult:
        """Ping each configured MCP server with tools/list."""
        if not self.servers:
            return ToolHealthResult(ok=True, latency_ms=0.0, detail="no_servers_configured")
        results: list[str] = []
        all_ok = True
        for name, server in self.servers.items():
            if not server.url:
                results.append(f"{name}:no_url")
                all_ok = False
                continue
            t0 = time.monotonic()
            try:
                payload = {"jsonrpc": "2.0", "id": "health", "method": "tools/list", "params": {}}
                async with httpx.AsyncClient(timeout=5.0, headers=server.headers or None) as client:
                    resp = await client.post(server.url, json=payload)
                status = resp.status_code
                ok = status < 400
                latency_ms = round((time.monotonic() - t0) * 1000, 1)
                results.append(f"{name}:{'ok' if ok else 'http_' + str(status)}:{latency_ms}ms")
                if not ok:
                    all_ok = False
            except Exception:
                latency_ms = round((time.monotonic() - t0) * 1000, 1)
                results.append(f"{name}:error:{latency_ms}ms")
                all_ok = False
        total_ms = sum(
            float(r.split(":")[-1].rstrip("ms") or 0) for r in results if "ms" in r
        )
        return ToolHealthResult(ok=all_ok, latency_ms=total_ms, detail="; ".join(results))

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
    async def _validate_transport(*, url: str, policy: MCPTransportPolicyConfig) -> None:
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
        ip_literal = _ip_literal(host)
        resolved_ips = [ip_literal] if ip_literal is not None else await _resolve_ips_async(host)

        if allowed_schemes and scheme not in allowed_schemes:
            raise ValueError(f"mcp transport policy rejected scheme '{scheme}'")
        if _match_any(host=host, ips=resolved_ips, rules=denied_hosts):
            raise ValueError(f"mcp transport policy denied host '{host}'")
        explicitly_allowed = _match_any(host=host, ips=resolved_ips, rules=allowed_hosts)
        if allowed_hosts and not explicitly_allowed:
            raise ValueError(f"mcp transport policy blocked host '{host}'")
        if not explicitly_allowed:
            for ip in resolved_ips:
                if _is_private_or_local(ip):
                    raise ValueError(f"mcp transport policy denied resolved address '{ip.compressed}'")


def _host_matches(rule: str, host: str) -> bool:
    value = rule.strip().lower()
    if not value:
        return False
    if value.startswith("*."):
        return host.endswith(value[1:])
    return host == value


def _match_any(*, host: str, ips: list[ipaddress._BaseAddress], rules: list[str]) -> bool:
    return any(_rule_matches(rule=rule, host=host, ips=ips) for rule in rules)


def _rule_matches(*, rule: str, host: str, ips: list[ipaddress._BaseAddress]) -> bool:
    normalized = rule.strip().lower()
    if not normalized:
        return False
    if _host_matches(normalized, host):
        return True
    if "/" in normalized:
        try:
            network = ipaddress.ip_network(normalized, strict=False)
        except ValueError:
            network = None
        if network is not None and any(ip in network for ip in ips):
            return True
    ip_value = _ip_literal(normalized)
    if ip_value is not None and any(ip == ip_value for ip in ips):
        return True
    return False


def _ip_literal(value: str) -> ipaddress._BaseAddress | None:
    return parse_ip_literal(value)


def _resolve_ips(host: str) -> list[ipaddress._BaseAddress]:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise ValueError(f"mcp transport policy failed to resolve host '{host}'") from exc
    rows: list[ipaddress._BaseAddress] = []
    for info in infos:
        value = str(info[4][0])
        ip = _ip_literal(value)
        if ip is not None and ip not in rows:
            rows.append(ip)
    if not rows:
        raise ValueError(f"mcp transport policy failed to resolve host '{host}'")
    return rows


async def _resolve_ips_async(host: str) -> list[ipaddress._BaseAddress]:
    return await asyncio.to_thread(_resolve_ips, host)


def _is_private_or_local(ip: ipaddress._BaseAddress) -> bool:
    return is_blocked_network_address(ip)
