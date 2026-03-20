from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, ClassVar

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

from clawlite.utils.logging import bind_event


@dataclass
class GatewayWebSocketHandlers:
    _STREAM_COALESCE_DEFAULT_MIN_CHARS: ClassVar[int] = 24
    _STREAM_COALESCE_DEFAULT_MAX_CHARS: ClassVar[int] = 120
    _STREAM_SENTENCE_TRAILERS: ClassVar[str] = "\"')]}»”’"

    auth_guard: Any
    diagnostics_require_auth: bool
    runtime: Any
    lifecycle: Any
    ws_telemetry: Any
    contract_version: str
    run_engine_with_timeout_fn: Callable[..., Awaitable[Any]]
    stream_engine_with_timeout_fn: Callable[..., Any] | None
    provider_error_payload_fn: Callable[[RuntimeError], tuple[int, str]]
    finalize_bootstrap_for_user_turn_fn: Callable[[str], None]
    control_plane_payload_fn: Callable[[], Any]
    control_plane_to_dict_fn: Callable[[Any], dict[str, Any]]
    build_tools_catalog_payload_fn: Callable[..., dict[str, Any]]
    parse_include_schema_flag_fn: Callable[[Any], bool]
    utc_now_iso_fn: Callable[[], str]
    rate_limiter: Any | None = None
    coalesce_enabled: bool = True
    coalesce_min_chars: int = _STREAM_COALESCE_DEFAULT_MIN_CHARS
    coalesce_max_chars: int = _STREAM_COALESCE_DEFAULT_MAX_CHARS
    coalesce_profile: str = "compact"

    @staticmethod
    def _envelope_error(
        *,
        error: str,
        status_code: int,
        request_id: str | None = None,
        retry_after_s: float = 0.0,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": "error",
            "error": str(error or "invalid_request"),
            "status_code": int(status_code),
        }
        if request_id:
            payload["request_id"] = request_id
        if retry_after_s > 0:
            payload["retry_after_s"] = round(float(retry_after_s), 3)
        return payload

    @staticmethod
    def _req_error(
        *,
        request_id: str | int | None,
        code: str,
        message: str,
        status_code: int,
        retry_after_s: float = 0.0,
    ) -> dict[str, Any]:
        payload = {
            "type": "res",
            "id": request_id,
            "ok": False,
            "error": {
                "code": str(code or "invalid_request"),
                "message": str(message or "invalid_request"),
                "status_code": int(status_code),
            },
        }
        if retry_after_s > 0:
            payload["error"]["retry_after_s"] = round(float(retry_after_s), 3)
        return payload

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

    @staticmethod
    def _coerce_stream_flag(payload: dict[str, Any]) -> bool:
        raw = payload.get("stream")
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            return raw.strip().lower() in {"1", "true", "yes", "on"}
        return False

    @staticmethod
    def _coerce_chat_context(payload: dict[str, Any]) -> tuple[str | None, str | None, dict[str, Any] | None]:
        channel = str(payload.get("channel", "") or "").strip() or None
        raw_chat_id = payload.get("chat_id")
        if raw_chat_id is None:
            raw_chat_id = payload.get("chatId")
        chat_id: str | None = None
        if isinstance(raw_chat_id, (str, int)) and not isinstance(raw_chat_id, bool):
            chat_id = str(raw_chat_id).strip() or None
        raw_runtime_metadata = payload.get("runtime_metadata")
        if raw_runtime_metadata is None:
            raw_runtime_metadata = payload.get("runtimeMetadata")
        runtime_metadata = None
        if isinstance(raw_runtime_metadata, dict) and raw_runtime_metadata:
            runtime_metadata = dict(raw_runtime_metadata)
        return channel, chat_id, runtime_metadata

    def _socket_credential(self, *, socket: WebSocket, allow_dashboard_session: bool) -> str:
        header_name = getattr(self.auth_guard, "header_name", "Authorization")
        query_param = getattr(self.auth_guard, "query_param", "token")
        extract_token = getattr(self.auth_guard, "_extract_token", None)
        if callable(extract_token):
            raw_token = extract_token(
                header_value=str(socket.headers.get(header_name, "") or ""),
                query_value=str(socket.query_params.get(query_param, "") or ""),
            )
            if raw_token:
                return str(raw_token)
        if allow_dashboard_session:
            dashboard_header_name = getattr(self.auth_guard, "dashboard_session_header_name", "")
            dashboard_query_param = getattr(self.auth_guard, "dashboard_session_query_param", "")
            extract_dashboard_session = getattr(self.auth_guard, "_extract_dashboard_session", None)
            if callable(extract_dashboard_session):
                dashboard_session = extract_dashboard_session(
                    header_value=str(socket.headers.get(dashboard_header_name, "") or ""),
                    query_value=str(socket.query_params.get(dashboard_query_param, "") or ""),
                )
                if dashboard_session:
                    return str(dashboard_session)
        return ""

    def _ws_chat_rate_limit_error(
        self,
        *,
        socket: WebSocket,
        request_id: str | int | None,
        legacy_envelope: bool,
        allow_dashboard_session: bool,
    ) -> dict[str, Any] | None:
        if self.rate_limiter is None:
            return None
        decision = self.rate_limiter.consume_ws_chat(
            client_ip=socket.client.host if socket.client is not None else None,
            credential=self._socket_credential(socket=socket, allow_dashboard_session=allow_dashboard_session),
        )
        if decision.allowed:
            return None
        if legacy_envelope:
            return self._envelope_error(
                error="gateway_rate_limited",
                status_code=429,
                request_id=str(request_id or "").strip() or None,
                retry_after_s=decision.retry_after_s,
            )
        return self._req_error(
            request_id=request_id,
            code="gateway_rate_limited",
            message="gateway chat rate limit exceeded; retry shortly",
            status_code=429,
            retry_after_s=decision.retry_after_s,
        )

    def _should_flush_stream_buffer(self, text: str, *, done: bool) -> bool:
        content = str(text or "")
        if not content:
            return bool(done)
        profile = str(self.coalesce_profile or "compact").strip().lower()
        if not self.coalesce_enabled or profile == "raw":
            return True
        if done or len(content) >= self.coalesce_max_chars:
            return True
        if len(content) < self.coalesce_min_chars:
            return False
        if profile == "paragraph":
            return content.endswith("\n\n")
        if profile == "newline":
            return content.endswith("\n")
        if content.endswith("\n\n") or content.endswith("\n"):
            return True
        stripped = content.rstrip()
        while stripped and stripped[-1] in self._STREAM_SENTENCE_TRAILERS:
            stripped = stripped[:-1].rstrip()
        return bool(stripped) and stripped[-1] in ".!?"

    @staticmethod
    def _stream_event_payload(
        *,
        session_id: str,
        text: str,
        accumulated: str,
        done: bool,
        degraded: bool,
        model: str,
        error: str,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "session_id": session_id,
            "text": text,
            "accumulated": accumulated,
            "done": done,
            "degraded": degraded,
        }
        if error:
            payload["error"] = error
        if model:
            payload["model"] = model
        return payload

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
        channel, chat_id, runtime_metadata = self._coerce_chat_context(params)
        try:
            out = await self.run_engine_with_timeout_fn(
                session_id,
                text,
                channel=channel,
                chat_id=chat_id,
                runtime_metadata=runtime_metadata,
            )
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

    async def _run_chat_stream_request(
        self,
        *,
        socket: WebSocket,
        request_id: str | int | None,
        params: dict[str, Any],
        send_ws_fn: Callable[[Any], Awaitable[None]],
        legacy_envelope: bool = False,
        allow_dashboard_session: bool = False,
    ) -> bool:
        session_id = str(params.get("session_id") or params.get("sessionId") or "").strip()
        text = str(params.get("text") or "").strip()
        if not session_id or not text:
            if legacy_envelope:
                await send_ws_fn(
                    self._envelope_error(
                        error="session_id and text are required",
                        status_code=400,
                        request_id=str(request_id or "").strip() or None,
                    )
                )
            else:
                await send_ws_fn(
                    self._req_error(
                        request_id=request_id,
                        code="invalid_request",
                        message="session_id/sessionId and text are required",
                        status_code=400,
                    )
                )
            return False
        rate_limit_error = self._ws_chat_rate_limit_error(
            socket=socket,
            request_id=request_id,
            legacy_envelope=legacy_envelope,
            allow_dashboard_session=allow_dashboard_session,
        )
        if rate_limit_error is not None:
            await send_ws_fn(rate_limit_error)
            return True
        if self.stream_engine_with_timeout_fn is None:
            return False

        last_accumulated = ""
        last_model = ""
        channel, chat_id, runtime_metadata = self._coerce_chat_context(params)
        try:
            buffered_text = ""
            buffered_accumulated = ""
            buffered_done = False
            buffered_degraded = False
            buffered_error = ""

            async for chunk in self.stream_engine_with_timeout_fn(
                session_id,
                text,
                channel=channel,
                chat_id=chat_id,
                runtime_metadata=runtime_metadata,
            ):
                last_accumulated = str(getattr(chunk, "accumulated", "") or last_accumulated)
                last_model = str(getattr(chunk, "model", "") or last_model)
                error_text = str(getattr(chunk, "error", "") or "").strip()
                buffered_text += str(getattr(chunk, "text", "") or "")
                buffered_accumulated = last_accumulated or buffered_accumulated
                buffered_done = bool(getattr(chunk, "done", False))
                buffered_degraded = buffered_degraded or bool(getattr(chunk, "degraded", False))
                if error_text:
                    buffered_error = error_text
                if not self._should_flush_stream_buffer(buffered_text, done=buffered_done):
                    continue
                event_payload = self._stream_event_payload(
                    session_id=session_id,
                    text=buffered_text,
                    accumulated=buffered_accumulated or buffered_text,
                    done=buffered_done,
                    degraded=buffered_degraded,
                    model=last_model,
                    error=buffered_error,
                )
                if legacy_envelope:
                    outbound = {
                        "type": "message_chunk",
                        **event_payload,
                    }
                    if request_id is not None:
                        outbound["request_id"] = request_id
                else:
                    outbound = {
                        "type": "event",
                        "event": "chat.chunk",
                        "id": request_id,
                        "params": event_payload,
                    }
                await send_ws_fn(outbound)
                buffered_text = ""
                buffered_accumulated = ""
                buffered_done = False
                buffered_degraded = False
                buffered_error = ""

            if buffered_text:
                final_accumulated = buffered_accumulated or last_accumulated or buffered_text
                event_payload = self._stream_event_payload(
                    session_id=session_id,
                    text=buffered_text,
                    accumulated=final_accumulated,
                    done=True,
                    degraded=buffered_degraded,
                    model=last_model,
                    error=buffered_error,
                )
                if legacy_envelope:
                    outbound = {
                        "type": "message_chunk",
                        **event_payload,
                    }
                    if request_id is not None:
                        outbound["request_id"] = request_id
                else:
                    outbound = {
                        "type": "event",
                        "event": "chat.chunk",
                        "id": request_id,
                        "params": event_payload,
                    }
                await send_ws_fn(outbound)
                if not last_accumulated:
                    last_accumulated = final_accumulated
        except RuntimeError as exc:
            status_code, detail = self.provider_error_payload_fn(exc)
            bind_event("gateway.ws", session=session_id, channel="ws").error(
                "websocket request failed status={} detail={}",
                status_code,
                detail,
            )
            if legacy_envelope:
                await send_ws_fn(self._envelope_error(error=detail, status_code=status_code, request_id=str(request_id or "").strip() or None))
            else:
                await send_ws_fn(
                    self._req_error(
                        request_id=request_id,
                        code=detail,
                        message=detail,
                        status_code=status_code,
                    )
                )
            return True

        self.finalize_bootstrap_for_user_turn_fn(session_id)
        if legacy_envelope:
            response_payload: dict[str, Any] = {
                "type": "message_result",
                "session_id": session_id,
                "text": last_accumulated,
                "model": last_model,
            }
            if request_id is not None:
                response_payload["request_id"] = request_id
            await send_ws_fn(response_payload)
        else:
            await send_ws_fn(
                {
                    "type": "res",
                    "id": request_id,
                    "ok": True,
                    "result": {
                        "session_id": session_id,
                        "text": last_accumulated,
                        "model": last_model,
                    },
                }
            )
        bind_event("gateway.ws", session=session_id, channel="ws").debug(
            "websocket streaming response sent model={}",
            last_model or "-",
        )
        return True

    async def handle(self, socket: WebSocket, *, path_label: str, allow_dashboard_session: bool = False) -> None:
        if not await self.auth_guard.check_ws(
            socket=socket,
            scope="control",
            diagnostics_auth=self.diagnostics_require_auth,
            allow_dashboard_session=allow_dashboard_session,
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
                            if self._coerce_stream_flag(params):
                                handled = await self._run_chat_stream_request(
                                    socket=socket,
                                    request_id=request_id,
                                    params=params,
                                    send_ws_fn=_send_ws,
                                    allow_dashboard_session=allow_dashboard_session,
                                )
                                if handled:
                                    continue
                            rate_limit_error = self._ws_chat_rate_limit_error(
                                socket=socket,
                                request_id=request_id,
                                legacy_envelope=False,
                                allow_dashboard_session=allow_dashboard_session,
                            )
                            if rate_limit_error is not None:
                                await _send_ws(rate_limit_error)
                                continue
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

                    if self._coerce_stream_flag(payload):
                        handled = await self._run_chat_stream_request(
                            socket=socket,
                            request_id=request_id,
                            params=payload,
                            send_ws_fn=_send_ws,
                            legacy_envelope=True,
                            allow_dashboard_session=allow_dashboard_session,
                        )
                        if handled:
                            continue
                    rate_limit_error = self._ws_chat_rate_limit_error(
                        socket=socket,
                        request_id=request_id,
                        legacy_envelope=True,
                        allow_dashboard_session=allow_dashboard_session,
                    )
                    if rate_limit_error is not None:
                        await _send_ws(rate_limit_error)
                        continue

                    channel, chat_id, runtime_metadata = self._coerce_chat_context(payload)
                    try:
                        out = await self.run_engine_with_timeout_fn(
                            session_id,
                            text,
                            channel=channel,
                            chat_id=chat_id,
                            runtime_metadata=runtime_metadata,
                        )
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
                rate_limit_error = self._ws_chat_rate_limit_error(
                    socket=socket,
                    request_id=None,
                    legacy_envelope=True,
                    allow_dashboard_session=allow_dashboard_session,
                )
                if rate_limit_error is not None:
                    await _send_ws(rate_limit_error)
                    continue
                channel, chat_id, runtime_metadata = self._coerce_chat_context(payload)
                try:
                    out = await self.run_engine_with_timeout_fn(
                        session_id,
                        text,
                        channel=channel,
                        chat_id=chat_id,
                        runtime_metadata=runtime_metadata,
                    )
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
