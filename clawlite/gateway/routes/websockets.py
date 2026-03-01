from __future__ import annotations

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from clawlite.gateway.chat import _handle_chat_message, _stream_chat_message
from clawlite.gateway.state import LOG_RING, chat_connections, connections, log_connections
from clawlite.gateway.utils import _filter_logs, _iso_now, _token

router = APIRouter()


@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    token = websocket.query_params.get("token", "")
    if token != _token():
        await websocket.close(code=4403)
        return

    await websocket.accept()
    connections.add(websocket)
    await websocket.send_json({"type": "welcome", "service": "clawlite-gateway"})

    try:
        while True:
            msg = await websocket.receive_json()
            msg_type = msg.get("type")
            if msg_type == "ping":
                await websocket.send_json({"type": "pong", "ts": _iso_now()})
            elif msg_type == "chat":
                session_id = str(msg.get("session_id") or "default")
                text = str(msg.get("text") or "").strip()
                try:
                    async for chunk_payload in _stream_chat_message(session_id=session_id, text=text):
                        if chunk_payload["type"] == "meta":
                            await websocket.send_json({"type": "chat_meta", "meta": chunk_payload["data"]})
                        elif chunk_payload["type"] == "chunk":
                            await websocket.send_json({"type": "chat_chunk", "chunk": chunk_payload["data"]})
                        elif chunk_payload["type"] == "error":
                            await websocket.send_json({"type": "error", "detail": chunk_payload["data"]})
                        elif chunk_payload["type"] == "done":
                            await websocket.send_json(
                                {
                                    "type": "chat",
                                    "message": chunk_payload["assistant_message"],
                                    "meta": chunk_payload["meta"],
                                    "telemetry": chunk_payload["telemetry"],
                                }
                            )
                except Exception as exc:
                    detail = exc.detail if hasattr(exc, "detail") else str(exc)
                    await websocket.send_json({"type": "error", "detail": detail})
                    continue
            else:
                await websocket.send_json({"type": "echo", "payload": msg})
    except WebSocketDisconnect:
        pass
    finally:
        connections.discard(websocket)


@router.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    token = websocket.query_params.get("token", "")
    if token != _token():
        await websocket.close(code=4403)
        return
    await websocket.accept()
    chat_connections.add(websocket)
    await websocket.send_json({"type": "welcome", "channel": "chat"})

    try:
        while True:
            msg = await websocket.receive_json()
            if msg.get("type") != "chat":
                await websocket.send_json({"type": "error", "detail": "Use type=chat"})
                continue
            session_id = str(msg.get("session_id") or "default")
            text = str(msg.get("text") or "").strip()
            try:
                async for chunk_payload in _stream_chat_message(session_id=session_id, text=text):
                    if chunk_payload["type"] == "meta":
                        await websocket.send_json({"type": "chat_meta", "meta": chunk_payload["data"]})
                    elif chunk_payload["type"] == "chunk":
                        await websocket.send_json({"type": "chat_chunk", "chunk": chunk_payload["data"]})
                    elif chunk_payload["type"] == "error":
                        await websocket.send_json({"type": "error", "detail": chunk_payload["data"]})
                    elif chunk_payload["type"] == "done":
                        await websocket.send_json(
                            {
                                "type": "chat",
                                "message": chunk_payload["assistant_message"],
                                "meta": chunk_payload["meta"],
                                "telemetry": chunk_payload["telemetry"],
                            }
                        )
            except Exception as exc:
                detail = exc.detail if hasattr(exc, "detail") else str(exc)
                await websocket.send_json({"type": "error", "detail": detail})
                continue
    except WebSocketDisconnect:
        pass
    finally:
        chat_connections.discard(websocket)


@router.websocket("/ws/logs")
async def ws_logs(websocket: WebSocket):
    token = websocket.query_params.get("token", "")
    if token != _token():
        await websocket.close(code=4403)
        return
    level = str(websocket.query_params.get("level", "")).strip().lower()
    event = str(websocket.query_params.get("event", "")).strip().lower()
    query = str(websocket.query_params.get("q", "")).strip().lower()
    await websocket.accept()
    log_connections[websocket] = {"level": level, "event": event, "q": query}
    try:
        snapshot = _filter_logs(list(LOG_RING), level=level, event=event, query=query)
        await websocket.send_json({"type": "snapshot", "logs": snapshot[-100:]})
        while True:
            raw = await websocket.receive_text()
            if not raw.strip():
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if payload.get("type") != "filters":
                continue
            level = str(payload.get("level", "")).strip().lower()
            event = str(payload.get("event", "")).strip().lower()
            query = str(payload.get("q", "")).strip().lower()
            log_connections[websocket] = {"level": level, "event": event, "q": query}
            snapshot = _filter_logs(list(LOG_RING), level=level, event=event, query=query)
            await websocket.send_json({"type": "snapshot", "logs": snapshot[-100:]})
    except WebSocketDisconnect:
        pass
    finally:
        log_connections.pop(websocket, None)
