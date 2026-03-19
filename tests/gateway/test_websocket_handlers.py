from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from starlette.websockets import WebSocketDisconnect

from clawlite.core.engine import ProviderChunk
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

    async def _stream_result(_session_id: str, _text: str):
        yield ProviderChunk(text="po", accumulated="po", done=False)
        yield ProviderChunk(text="ng", accumulated="pong", done=True)

    handler = GatewayWebSocketHandlers(
        auth_guard=auth_guard,
        diagnostics_require_auth=False,
        runtime=runtime,
        lifecycle=SimpleNamespace(ready=True, phase="ready"),
        ws_telemetry=ws_telemetry,
        contract_version="2026-03-04",
        run_engine_with_timeout_fn=AsyncMock(return_value=chat_result),
        stream_engine_with_timeout_fn=_stream_result,
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


def test_websocket_handler_streams_req_chat_chunks_before_final_result() -> None:
    handler, socket = _build_handler(
        inbound=[
            {"type": "req", "id": "c1", "method": "connect", "params": {}},
            {
                "type": "req",
                "id": "m1",
                "method": "chat.send",
                "params": {
                    "sessionId": "cli:req-stream",
                    "text": "ping",
                    "stream": True,
                    "channel": "telegram",
                    "chatId": 123,
                    "runtimeMetadata": {"reply_to_message_id": "456"},
                },
            },
        ]
    )
    seen: list[tuple[str, str, str | None, str | None, dict[str, object] | None]] = []

    async def _capturing_stream(
        session_id: str,
        text: str,
        *,
        channel: str | None = None,
        chat_id: str | None = None,
        runtime_metadata: dict[str, object] | None = None,
    ):
        seen.append((session_id, text, channel, chat_id, runtime_metadata))
        yield ProviderChunk(text="po", accumulated="po", done=False)
        yield ProviderChunk(text="ng", accumulated="pong", done=True)

    handler.stream_engine_with_timeout_fn = _capturing_stream

    asyncio.run(handler.handle(socket, path_label="/ws"))

    assert seen == [
        (
            "cli:req-stream",
            "ping",
            "telegram",
            "123",
            {"reply_to_message_id": "456"},
        )
    ]
    assert socket.sent[2] == {
        "type": "event",
        "event": "chat.chunk",
        "id": "m1",
        "params": {
            "session_id": "cli:req-stream",
            "text": "pong",
            "accumulated": "pong",
            "done": True,
            "degraded": False,
        },
    }
    assert socket.sent[3] == {
        "type": "res",
        "id": "m1",
        "ok": True,
        "result": {
            "session_id": "cli:req-stream",
            "text": "pong",
            "model": "",
        },
    }


def test_websocket_handler_coalesces_stream_until_sentence_boundary() -> None:
    handler, socket = _build_handler(
        inbound=[
            {"type": "req", "id": "c1", "method": "connect", "params": {}},
            {
                "type": "req",
                "id": "m2",
                "method": "chat.send",
                "params": {
                    "sessionId": "cli:req-stream-boundary",
                    "text": "ping",
                    "stream": True,
                },
            },
        ]
    )

    async def _sentence_stream(
        session_id: str,
        text: str,
        *,
        channel: str | None = None,
        chat_id: str | None = None,
        runtime_metadata: dict[str, object] | None = None,
    ):
        del session_id, text, channel, chat_id, runtime_metadata
        yield ProviderChunk(text="Hello world", accumulated="Hello world", done=False)
        yield ProviderChunk(text=", this is a test.", accumulated="Hello world, this is a test.", done=False)
        yield ProviderChunk(text=" Next chunk", accumulated="Hello world, this is a test. Next chunk", done=False)
        yield ProviderChunk(text=" closes.", accumulated="Hello world, this is a test. Next chunk closes.", done=True)

    handler.stream_engine_with_timeout_fn = _sentence_stream

    asyncio.run(handler.handle(socket, path_label="/ws"))

    assert socket.sent[2] == {
        "type": "event",
        "event": "chat.chunk",
        "id": "m2",
        "params": {
            "session_id": "cli:req-stream-boundary",
            "text": "Hello world, this is a test.",
            "accumulated": "Hello world, this is a test.",
            "done": False,
            "degraded": False,
        },
    }
    assert socket.sent[3] == {
        "type": "event",
        "event": "chat.chunk",
        "id": "m2",
        "params": {
            "session_id": "cli:req-stream-boundary",
            "text": " Next chunk closes.",
            "accumulated": "Hello world, this is a test. Next chunk closes.",
            "done": True,
            "degraded": False,
        },
    }
    assert socket.sent[4] == {
        "type": "res",
        "id": "m2",
        "ok": True,
        "result": {
            "session_id": "cli:req-stream-boundary",
            "text": "Hello world, this is a test. Next chunk closes.",
            "model": "",
        },
    }


def test_websocket_handler_legacy_message_forwards_context_and_ignores_invalid_runtime_metadata() -> None:
    handler, socket = _build_handler(
        inbound=[
            {
                "type": "message",
                "request_id": "legacy-1",
                "session_id": "cli:legacy",
                "text": "ping",
                "channel": "telegram",
                "chat_id": 789,
                "runtime_metadata": ["invalid"],
            },
        ]
    )

    asyncio.run(handler.handle(socket, path_label="/ws"))

    handler.run_engine_with_timeout_fn.assert_awaited_once_with(
        "cli:legacy",
        "ping",
        channel="telegram",
        chat_id="789",
        runtime_metadata=None,
    )
    assert socket.sent[-1] == {
        "type": "message_result",
        "session_id": "cli:legacy",
        "text": "pong",
        "model": "fake/test",
        "request_id": "legacy-1",
    }
