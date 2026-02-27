from __future__ import annotations

from typing import Any

from clawlite.mcp import dispatch_skill_tool, mcp_tools_from_skills


MCP_PROTOCOL_VERSION = "2024-11-05"


def _ok(result: dict[str, Any], id_value: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id_value, "result": result}


def _err(code: int, message: str, id_value: Any = None) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id_value, "error": {"code": code, "message": message}}


def handle_mcp_jsonrpc(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return _err(-32600, "Payload MCP deve ser objeto JSON", None)

    method = str(payload.get("method", "")).strip()
    rpc = str(payload.get("jsonrpc", "2.0"))
    req_id = payload.get("id")

    if rpc != "2.0":
        return _err(-32600, "JSON-RPC inválido", req_id)
    if not method:
        return _err(-32600, "Método MCP ausente", req_id)

    try:
        if method == "initialize":
            return _ok(
                {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "serverInfo": {"name": "clawlite-mcp", "version": "0.1.0"},
                    "capabilities": {"tools": {"listChanged": False}},
                },
                req_id,
            )

        if method == "notifications/initialized":
            return _ok({}, req_id)

        if method == "ping":
            return _ok({"pong": True}, req_id)

        if method == "tools/list":
            return _ok({"tools": mcp_tools_from_skills()}, req_id)

        if method == "tools/call":
            params = payload.get("params", {}) or {}
            tool_name = str(params.get("name", "")).strip()
            arguments = params.get("arguments", {})
            if not tool_name:
                return _err(-32602, "tools/call requer params.name", req_id)
            if arguments is not None and not isinstance(arguments, dict):
                return _err(-32602, "params.arguments deve ser objeto", req_id)
            result = dispatch_skill_tool(tool_name, arguments if isinstance(arguments, dict) else {})
            return _ok(result, req_id)

        return _err(-32601, f"Método MCP não suportado: {method}", req_id)
    except ValueError as exc:
        return _err(-32000, str(exc), req_id)
    except RuntimeError as exc:
        return _err(-32001, str(exc), req_id)
    except Exception as exc:  # noqa: BLE001
        return _err(-32603, f"Erro interno MCP: {exc}", req_id)
