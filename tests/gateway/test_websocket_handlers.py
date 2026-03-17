from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from starlette.websockets import WebSocketDisconnect

from clawlite.gateway.websocket_handlers import GatewayWebSocketHandlers


class _FakeSocket:
    def __init__(self, inbound: list[object]) -> None:
        self._inbound = list(inbound)
        self.sent: list[object] = []
        self.headers: dict[str, str] = {}
        self.query_params: dict[str, str] = {}
        self.client = SimpleNamespace(host="127.0.0.1")
        self.accepted = False

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, payload: object) -> None:
        self.sent.append(payload)

    async def receive_json(self) -> object:
        if not self._inbound:
            raise WebSocketDisconnect(code=1000)
        return self._inbound.pop(0)


def _build_handler(*, inbound: list[object], run_result: object | None = None) -> tuple[GatewayWebSocketHandlers, _FakeSocket]:
    socket = _FakeSocket(inbound)
    auth_guard = SimpleNamespace(check_ws=AsyncMock(return_value=True))
    ws_telemetry = SimpleNamespace(
        connection_opened=AsyncMock(),
        connection_closed=AsyncMock(),
        frame_inbound=AsyncMock(),
        frame_outbound=AsyncMock(),
    )
    runtime = SimpleNamespace(
        channels=SimpleNamespace(status=lambda: {"telegram": {"running": True}}),
        bus=SimpleNamespace(stats=lambda: {"queued": 0}),
        engine=SimpleNamespace(tools=SimpleNamespace(schema=lambda: [{"name": "exec"}])),
    )
    finalized: list[str] = []
    chat_result = run_result or SimpleNamespace(text="pong", model="fake/test")
    handler = GatewayWebSocketHandlers(
        auth_guard=auth_guard,
        diagnostics_require_auth=False,
        runtime=runtime,
        lifecycle=SimpleNamespace(ready=True, phase="ready"),
        ws_telemetry=ws_telemetry,
        contract_version="2026-03-04",
        run_engine_with_timeout_fn=AsyncMock(return_value=chat_result),
        provider_error_payload_fn=lambda exc: (500, str(exc)),
        finalize_bootstrap_for_user_turn_fn=finalized.append,
        control_plane_payload_fn=lambda: {"contract_version": "2026-03-04", "components": {}, "auth": {}},
        control_plane_to_dict_fn=lambda payload: dict(payload),
        build_tools_catalog_payload_fn=lambda schema, include_schema=False: {
            "aliases": {"bash": "exec"},
            "groups": ["default"],
            "schema_count": len(schema) if include_schema else 0,
            "ws_methods": ["tools.catalog"],
        },
        parse_include_schema_flag_fn=lambda params: bool(params.get("include_schema")),
        utc_now_iso_fn=lambda: "2026-03-17T00:00:00+00:00",
    )
    return handler, socket


def test_websocket_handler_req_connect_ping_and_catalog() -> None:
    handler, socket = _build_handler(
        inbound=[
            {"type": "req", "id": "c1", "method": "connect", "params": {}},
            {"type": "req", "id": "p1", "method": "ping", "params": {}},
            {"type": "req", "id": "tc1", "method": "tools.catalog", "params": {"include_schema": True}},
        ]
    )

    asyncio.run(handler.handle(socket, path_label="/ws"))

    assert socket.accepted is True
    assert socket.sent[0]["type"] == "event"
    assert socket.sent[0]["event"] == "connect.challenge"
    assert socket.sent[1]["result"]["connected"] is True
    assert socket.sent[2]["result"]["server_time"] == "2026-03-17T00:00:00+00:00"
    assert socket.sent[3]["result"]["aliases"]["bash"] == "exec"
    assert socket.sent[3]["result"]["schema_count"] == 1


def test_websocket_handler_rejects_req_before_connect() -> None:
    handler, socket = _build_handler(
        inbound=[
            {"type": "req", "id": "p1", "method": "ping", "params": {}},
        ]
    )

    asyncio.run(handler.handle(socket, path_label="/v1/ws"))

    assert socket.sent[0]["type"] == "event"
    assert socket.sent[1] == {
        "type": "res",
        "id": "p1",
        "ok": False,
        "error": {
            "code": "not_connected",
            "message": "connect handshake required",
            "status_code": 409,
        },
    }
