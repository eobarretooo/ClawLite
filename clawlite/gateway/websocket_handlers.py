from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

from clawlite.utils.logging import bind_event


@dataclass
class GatewayWebSocketHandlers:
    auth_guard: Any
    diagnostics_require_auth: bool
    runtime: Any
    lifecycle: Any
    ws_telemetry: Any
    contract_version: str
    run_engine_with_timeout_fn: Callable[[str, str], Awaitable[Any]]
    provider_error_payload_fn: Callable[[RuntimeError], tuple[int, str]]
    finalize_bootstrap_for_user_turn_fn: Callable[[str], None]
    control_plane_payload_fn: Callable[[], Any]
    control_plane_to_dict_fn: Callable[[Any], dict[str, Any]]
    build_tools_catalog_payload_fn: Callable[..., dict[str, Any]]
    parse_include_schema_flag_fn: Callable[[Any], bool]
    utc_now_iso_fn: Callable[[], str]

    @staticmethod
    def _envelope_error(*, error: str, status_code: int, request_id: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": "error",
            "error": str(error or "invalid_request"),
            "status_code": int(status_code),
        }
        if request_id:
            payload["request_id"] = request_id
        return payload

    @staticmethod
    def _req_error(
        *,
        request_id: str | int | None,
        code: str,
        message: str,
        status_code: int,
    ) -> dict[str, Any]:
        return {
            "type": "res",
            "id": request_id,
            "ok": False,
            "error": {
                "code": str(code or "invalid_request"),
                "message": str(message or "invalid_request"),
                "status_code": int(status_code),
            },
        }

    @staticmethod
    def _coerce_req_id(value: Any) -> str | int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, (str, int)):
            return value
        return None

    @classmethod
    def _coerce_req_payload(cls, payload: dict[str, Any]) -> tuple[str | int | None, str, dict[str, Any] | None]:
        request_id = cls._coerce_req_id(payload.get("id"))
        method = str(payload.get("method", "") or "").strip()
        params = payload.get("params")
        if params is None:
            params = {}
        if not isinstance(params, dict):
            return request_id, method, None
        return request_id, method, params

    async def _run_chat_request(self, *, request_id: str | int | None, params: dict[str, Any]) -> dict[str, Any]:
        session_id = str(params.get("session_id") or params.get("sessionId") or "").strip()
        text = str(params.get("text") or "").strip()
        if not session_id or not text:
            return self._req_error(
                request_id=request_id,
                code="invalid_request",
                message="session_id/sessionId and text are required",
                status_code=400,
            )
        try:
            out = await self.run_engine_with_timeout_fn(session_id, text)
        except RuntimeError as exc:
            status_code, detail = self.provider_error_payload_fn(exc)
            bind_event("gateway.ws", session=session_id, channel="ws").error(
                "websocket request failed status={} detail={}",
                status_code,
                detail,
            )
            return self._req_error(
                request_id=request_id,
                code=detail,
                message=detail,
                status_code=status_code,
            )

        self.finalize_bootstrap_for_user_turn_fn(session_id)
        return {
            "type": "res",
            "id": request_id,
            "ok": True,
            "result": {
                "session_id": session_id,
                "text": out.text,
                "model": out.model,
            },
        }

    async def handle(self, socket: WebSocket, *, path_label: str) -> None:
        if not await self.auth_guard.check_ws(
            socket=socket,
            scope="control",
            diagnostics_auth=self.diagnostics_require_auth,
        ):
            return
        await socket.accept()
        await self.ws_telemetry.connection_opened(path=path_label)

        async def _send_ws(payload: Any) -> None:
            await socket.send_json(payload)
            await self.ws_telemetry.frame_outbound(payload=payload)

        await _send_ws(
            {
                "type": "event",
                "event": "connect.challenge",
                "params": {
                    "nonce": uuid.uuid4().hex,
                    "issued_at": self.utc_now_iso_fn(),
                },
            }
        )
        bind_event("gateway.ws", channel="ws").info("websocket client connected path={}", path_label)
        req_connected = False
        try:
            while True:
                payload = await socket.receive_json()
                await self.ws_telemetry.frame_inbound(path=path_label, payload=payload)
                if not isinstance(payload, dict):
                    await _send_ws({"error": "session_id and text are required"})
                    continue

                message_type = str(payload.get("type", "") or "").strip().lower()
                if message_type:
                    if message_type == "req":
                        request_id, method, params = self._coerce_req_payload(payload)
                        if request_id is None or not method or params is None:
                            await _send_ws(
                                self._req_error(
                                    request_id=request_id,
                                    code="invalid_request",
                                    message="req frames require string|number id, string method, and object params",
                                    status_code=400,
                                )
                            )
                            continue

                        normalized_method = method.lower()
                        if normalized_method == "connect":
                            req_connected = True
                            await _send_ws(
                                {
                                    "type": "res",
                                    "id": request_id,
                                    "ok": True,
                                    "result": {
                                        "connected": req_connected,
                                        "contract_version": self.contract_version,
                                        "server_time": self.utc_now_iso_fn(),
                                    },
                                }
                            )
                            continue
                        if not req_connected:
                            await _send_ws(
                                self._req_error(
                                    request_id=request_id,
                                    code="not_connected",
                                    message="connect handshake required",
                                    status_code=409,
                                )
                            )
                            continue
                        if normalized_method == "ping":
                            await _send_ws(
                                {
                                    "type": "res",
                                    "id": request_id,
                                    "ok": True,
                                    "result": {
                                        "server_time": self.utc_now_iso_fn(),
                                    },
                                }
                            )
                            continue
                        if normalized_method == "health":
                            await _send_ws(
                                {
                                    "type": "res",
                                    "id": request_id,
                                    "ok": True,
                                    "result": {
                                        "ok": True,
                                        "ready": self.lifecycle.ready,
                                        "phase": self.lifecycle.phase,
                                        "channels": self.runtime.channels.status(),
                                        "queue": self.runtime.bus.stats(),
                                    },
                                }
                            )
                            continue
                        if normalized_method == "status":
                            status_payload = self.control_plane_to_dict_fn(self.control_plane_payload_fn())
                            await _send_ws(
                                {
                                    "type": "res",
                                    "id": request_id,
                                    "ok": True,
                                    "result": status_payload,
                                }
                            )
                            continue
                        if normalized_method == "tools.catalog":
                            include_schema = self.parse_include_schema_flag_fn(params)
                            await _send_ws(
                                {
                                    "type": "res",
                                    "id": request_id,
                                    "ok": True,
                                    "result": self.build_tools_catalog_payload_fn(
                                        self.runtime.engine.tools.schema(),
                                        include_schema=include_schema,
                                    ),
                                }
                            )
                            continue
                        if normalized_method in {"chat.send", "message.send"}:
                            await _send_ws(await self._run_chat_request(request_id=request_id, params=params))
                            continue

                        await _send_ws(
                            self._req_error(
                                request_id=request_id,
                                code="unsupported_method",
                                message=f"unsupported req method: {method}",
                                status_code=400,
                            )
                        )
                        continue

                    request_id = str(payload.get("request_id", "") or "").strip() or None
                    if message_type == "hello":
                        await _send_ws(
                            {
                                "type": "ready",
                                "contract_version": self.contract_version,
                                "server_time": self.utc_now_iso_fn(),
                            }
                        )
                        continue
                    if message_type == "ping":
                        await _send_ws({"type": "pong", "server_time": self.utc_now_iso_fn()})
                        continue
                    if message_type != "message":
                        await _send_ws(
                            self._envelope_error(
                                error="unsupported_message_type",
                                status_code=400,
                                request_id=request_id,
                            )
                        )
                        continue

                    session_id = str(payload.get("session_id", "") or "").strip()
                    text = str(payload.get("text", "") or "").strip()
                    if not session_id or not text:
                        await _send_ws(
                            self._envelope_error(
                                error="session_id and text are required",
                                status_code=400,
                                request_id=request_id,
                            )
                        )
                        continue

                    try:
                        out = await self.run_engine_with_timeout_fn(session_id, text)
                    except RuntimeError as exc:
                        status_code, detail = self.provider_error_payload_fn(exc)
                        bind_event("gateway.ws", session=session_id, channel="ws").error(
                            "websocket request failed status={} detail={}",
                            status_code,
                            detail,
                        )
                        await _send_ws(
                            self._envelope_error(error=detail, status_code=status_code, request_id=request_id)
                        )
                        continue

                    self.finalize_bootstrap_for_user_turn_fn(session_id)
                    response_payload: dict[str, Any] = {
                        "type": "message_result",
                        "session_id": session_id,
                        "text": out.text,
                        "model": out.model,
                    }
                    if request_id:
                        response_payload["request_id"] = request_id
                    await _send_ws(response_payload)
                    bind_event("gateway.ws", session=session_id, channel="ws").debug(
                        "websocket response sent model={}",
                        out.model,
                    )
                    continue

                session_id = str(payload.get("session_id", "")).strip()
                text = str(payload.get("text", "")).strip()
                if not session_id or not text:
                    await _send_ws({"error": "session_id and text are required"})
                    continue
                try:
                    out = await self.run_engine_with_timeout_fn(session_id, text)
                except RuntimeError as exc:
                    status_code, detail = self.provider_error_payload_fn(exc)
                    bind_event("gateway.ws", session=session_id, channel="ws").error(
                        "websocket request failed status={} detail={}",
                        status_code,
                        detail,
                    )
                    await _send_ws({"error": detail, "status_code": status_code})
                    continue
                self.finalize_bootstrap_for_user_turn_fn(session_id)
                await _send_ws({"text": out.text, "model": out.model})
                bind_event("gateway.ws", session=session_id, channel="ws").debug(
                    "websocket response sent model={}",
                    out.model,
                )
        except WebSocketDisconnect:
            bind_event("gateway.ws", channel="ws").info("websocket client disconnected path={}", path_label)
        finally:
            await self.ws_telemetry.connection_closed()


__all__ = ["GatewayWebSocketHandlers"]
