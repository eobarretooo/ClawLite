from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from loguru import logger
from starlette.websockets import WebSocketDisconnect

from clawlite.config.schema import AppConfig, SchedulerConfig
from clawlite.core.memory_monitor import MemorySuggestion
from clawlite.gateway.server import _run_heartbeat, build_runtime, create_app
from clawlite.providers.base import LLMResult
from clawlite.scheduler.heartbeat import HeartbeatDecision
from clawlite.utils import logging as logging_utils


class FakeProvider:
    async def complete(self, *, messages, tools):
        return LLMResult(text="pong", model="fake/test", tool_calls=[], metadata={})


class FailingProvider:
    def __init__(self, message: str) -> None:
        self.message = message

    async def complete(self, *, messages, tools):
        raise RuntimeError(self.message)


class ProviderWithDiagnostics:
    async def complete(self, *, messages, tools):
        return LLMResult(text="pong", model="fake/test", tool_calls=[], metadata={})

    def diagnostics(self) -> dict[str, object]:
        return {
            "provider": "fake_provider",
            "model": "fake/test",
            "counters": {"requests": 12, "successes": 11},
        }


class ProviderWithUnsafeDiagnostics:
    async def complete(self, *, messages, tools):
        return LLMResult(text="pong", model="fake/test", tool_calls=[], metadata={})

    def diagnostics(self) -> dict[str, object]:
        return {
            "provider": "fake_provider",
            "model": "fake/test",
            "api_key": "top-level-secret",
            "token_count": 999,
            "nested": {
                "access_token": "nested-secret",
                "safe": "ok",
                "deep": [
                    {"authorization": "Bearer should-not-leak", "value": "retained"},
                    {"meta": {"credentials": "cred-secret", "message": "still-safe"}},
                ],
            },
            "items": [
                {"auth_header": "dont-leak", "status": "clean"},
                {"credential_type": "token", "note": "keep-note"},
            ],
            "counters": {"requests": 3, "successes": 2},
        }


def test_gateway_chat_endpoint(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)
    app.state.runtime.engine.provider = FakeProvider()

    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        chat = client.post("/v1/chat", json={"session_id": "cli:1", "text": "ping"})
        assert chat.status_code == 200
        assert chat.json()["text"] == "pong"
        alias = client.post("/api/message", json={"session_id": "cli:1", "text": "ping"})
        assert alias.status_code == 200
        assert alias.json()["text"] == "pong"


def test_gateway_telegram_webhook_endpoint_requires_secret_and_dispatches(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={
            "telegram": {
                "enabled": True,
                "token": "x:token",
                "mode": "webhook",
                "webhook_enabled": True,
                "webhook_secret": "secret-1",
                "webhook_url": "https://example.com/hook",
            }
        },
    )
    app = create_app(cfg)

    class FakeBot:
        def __init__(self, token: str) -> None:
            assert token == "x:token"

        async def set_webhook(self, **kwargs):
            return kwargs

        async def delete_webhook(self, **kwargs):
            return kwargs

    fake_module = SimpleNamespace(Bot=FakeBot)
    with patch.dict(sys.modules, {"telegram": fake_module}):
        with TestClient(app) as client:
            unauthorized = client.post("/api/webhooks/telegram", json={"update_id": 1})
            assert unauthorized.status_code == 401
            assert unauthorized.json()["code"] == "telegram_webhook_secret_invalid"

            channel = app.state.runtime.channels.get_channel("telegram")
            assert channel is not None
            webhook_handler = AsyncMock(return_value=True)
            channel.handle_webhook_update = webhook_handler

            authorized = client.post(
                "/api/webhooks/telegram",
                json={"update_id": 2, "message": {"text": "hello"}},
                headers={"X-Telegram-Bot-Api-Secret-Token": "secret-1"},
            )
            assert authorized.status_code == 200
            assert authorized.json() == {"ok": True, "processed": True}
            webhook_handler.assert_awaited_once_with({"update_id": 2, "message": {"text": "hello"}})


def test_gateway_telegram_webhook_timeout_returns_408_contract(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={
            "telegram": {
                "enabled": True,
                "token": "x:token",
                "mode": "webhook",
                "webhook_enabled": True,
                "webhook_secret": "secret-1",
                "webhook_url": "https://example.com/hook",
            }
        },
    )
    app = create_app(cfg)

    class FakeBot:
        def __init__(self, token: str) -> None:
            assert token == "x:token"

        async def set_webhook(self, **kwargs):
            return kwargs

        async def delete_webhook(self, **kwargs):
            return kwargs

    fake_module = SimpleNamespace(Bot=FakeBot)
    with patch.dict(sys.modules, {"telegram": fake_module}):
        with TestClient(app) as client:
            async def _timeout_wait_for(coro, timeout):
                del timeout
                if asyncio.iscoroutine(coro):
                    coro.close()
                raise asyncio.TimeoutError()

            with patch("clawlite.gateway.server.asyncio.wait_for", new=_timeout_wait_for):
                timeout_response = client.post(
                    "/api/webhooks/telegram",
                    json={"update_id": 2, "message": {"text": "hello"}},
                    headers={"X-Telegram-Bot-Api-Secret-Token": "secret-1"},
                )
            assert timeout_response.status_code == 408
            payload = timeout_response.json()
            assert payload["error"] == "telegram_webhook_payload_timeout"
            assert payload["code"] == "telegram_webhook_payload_timeout"


def test_gateway_successful_chat_completes_bootstrap_lifecycle(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)
    app.state.runtime.engine.provider = FakeProvider()
    bootstrap_file = tmp_path / "workspace" / "BOOTSTRAP.md"

    with TestClient(app) as client:
        assert bootstrap_file.exists()
        chat = client.post("/v1/chat", json={"session_id": "cli:bootstrap", "text": "ping"})
        assert chat.status_code == 200
        assert chat.json()["text"] == "pong"

        assert not bootstrap_file.exists()

        status_payload = client.get("/v1/status").json()
        bootstrap_component = status_payload["components"]["bootstrap"]
        assert bootstrap_component["pending"] is False
        assert bootstrap_component["last_status"] == "completed"

        diagnostics_payload = client.get("/v1/diagnostics").json()
        assert diagnostics_payload["bootstrap"]["pending"] is False
        assert diagnostics_payload["bootstrap"]["last_status"] == "completed"


def test_gateway_internal_sessions_do_not_complete_bootstrap(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)
    app.state.runtime.engine.provider = FakeProvider()
    bootstrap_file = tmp_path / "workspace" / "BOOTSTRAP.md"

    with TestClient(app) as client:
        assert bootstrap_file.exists()
        chat = client.post("/v1/chat", json={"session_id": "heartbeat:manual", "text": "ping"})
        assert chat.status_code == 200
        assert bootstrap_file.exists()

        payload = client.get("/v1/diagnostics").json()
        assert payload["bootstrap"]["pending"] is True
        assert payload["bootstrap"]["last_status"] == ""


def test_gateway_runtime_passes_memory_window_to_engine(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        agents={"defaults": {"memory_window": 33}},
        channels={},
    )
    app = create_app(cfg)
    assert app.state.runtime.engine.memory_window == 33


def test_gateway_runtime_passes_emotional_tracking_to_memory_store(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        agents={"defaults": {"memory": {"emotional_tracking": True}}},
        channels={},
    )
    app = create_app(cfg)
    assert app.state.runtime.engine.memory.emotional_tracking is True


def test_gateway_runtime_accepts_sqlite_memory_backend(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        agents={"defaults": {"memory": {"backend": "sqlite"}}},
        channels={},
    )
    runtime = build_runtime(cfg)
    assert runtime.engine.memory is not None


def test_gateway_runtime_rejects_pgvector_backend_without_url(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        agents={"defaults": {"memory": {"backend": "pgvector", "pgvector_url": ""}}},
        channels={},
    )
    with pytest.raises(RuntimeError, match="memory backend 'pgvector'"):
        build_runtime(cfg)


def test_gateway_runtime_rejects_pgvector_backend_with_invalid_url(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        agents={"defaults": {"memory": {"backend": "pgvector", "pgvector_url": "sqlite:///tmp.db"}}},
        channels={},
    )
    with pytest.raises(RuntimeError, match="postgres://"):
        build_runtime(cfg)


def test_gateway_runtime_disables_memory_monitor_when_proactive_false(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        agents={"defaults": {"memory": {"proactive": False}}},
        channels={},
    )
    runtime = build_runtime(cfg)
    assert runtime.memory_monitor is None


def test_run_heartbeat_skips_suggestions_when_memory_monitor_missing() -> None:
    class _Engine:
        async def run(self, *, session_id: str, user_text: str):
            return SimpleNamespace(text="HEARTBEAT_OK")

    async def _scenario() -> None:
        channels = SimpleNamespace(send=AsyncMock(return_value="msg-1"))
        runtime = SimpleNamespace(engine=_Engine(), channels=channels, memory_monitor=None)
        decision = await _run_heartbeat(runtime)

        assert decision.action == "skip"
        assert decision.reason == "heartbeat_ok"
        channels.send.assert_not_awaited()

    asyncio.run(_scenario())


def test_gateway_status_exposes_memory_proactive_enabled_flag(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        agents={"defaults": {"memory": {"proactive": False}}},
        channels={},
    )
    app = create_app(cfg)
    with TestClient(app) as client:
        payload = client.get("/v1/status").json()
        assert payload["memory_proactive_enabled"] is False


def test_gateway_diagnostics_exposes_memory_monitor_telemetry_when_enabled(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        agents={"defaults": {"memory": {"proactive": True}}},
        gateway={"heartbeat": {"enabled": False}, "diagnostics": {"enabled": True, "require_auth": False}},
        channels={},
    )
    app = create_app(cfg)
    with TestClient(app) as client:
        payload = client.get("/v1/diagnostics").json()
        monitor_payload = payload["memory_monitor"]
        assert monitor_payload["enabled"] is True
        assert "scans" in monitor_payload
        assert "generated" in monitor_payload


def test_gateway_root_entrypoint_is_deterministic(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)

    with TestClient(app) as client:
        root = client.get("/")
        assert root.status_code == 200
        body = root.text
        assert "<h1>ClawLite Gateway</h1>" in body
        assert "GET /v1/status, GET /api/status" in body
        assert "POST /v1/chat, POST /api/message" in body
        assert "WS /v1/ws, WS /ws" in body


def test_gateway_chat_provider_error_returns_graceful_message(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)
    app.state.runtime.engine.provider = FailingProvider("provider_http_error:401")

    with TestClient(app) as client:
        chat = client.post("/v1/chat", json={"session_id": "cli:1", "text": "ping"})
        assert chat.status_code == 200
        text = str(chat.json().get("text", "")).lower()
        assert "sorry" in text
        # Avoid provider error leaking from heartbeat lifecycle during client shutdown.
        app.state.runtime.engine.provider = FakeProvider()


def test_gateway_chat_provider_http_400_returns_graceful_message(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)
    app.state.runtime.engine.provider = FailingProvider("provider_http_error:400:invalid model")

    with TestClient(app) as client:
        chat = client.post("/v1/chat", json={"session_id": "cli:1", "text": "ping"})
        assert chat.status_code == 200
        text = str(chat.json().get("text", "")).lower()
        assert "sorry" in text
        app.state.runtime.engine.provider = FakeProvider()


def test_gateway_provider_error_payload_codex_missing_token_guidance(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)

    async def _raise_codex(*, session_id: str, user_text: str):
        raise RuntimeError("codex_auth_error:missing_access_token")

    app.state.runtime.engine.run = _raise_codex

    with TestClient(app) as client:
        chat = client.post("/v1/chat", json={"session_id": "cli:1", "text": "ping"})
        assert chat.status_code == 400
        payload = chat.json()
        assert "provider login openai-codex" in str(payload.get("error", "")).lower()


def test_run_heartbeat_contract_skips_on_heartbeat_ok() -> None:
    class _Engine:
        async def run(self, *, session_id: str, user_text: str):
            return SimpleNamespace(text="HEARTBEAT_OK")

    async def _scenario() -> None:
        runtime = SimpleNamespace(engine=_Engine())
        decision = await _run_heartbeat(runtime)
        assert isinstance(decision, HeartbeatDecision)
        assert decision.action == "skip"
        assert decision.reason == "heartbeat_ok"

    asyncio.run(_scenario())


def test_run_heartbeat_contract_runs_on_actionable_output() -> None:
    class _Engine:
        async def run(self, *, session_id: str, user_text: str):
            return SimpleNamespace(text="Alert: queue backlog is growing")

    async def _scenario() -> None:
        runtime = SimpleNamespace(engine=_Engine())
        decision = await _run_heartbeat(runtime)
        assert decision.action == "run"
        assert decision.reason == "actionable_response"

    asyncio.run(_scenario())


def test_run_heartbeat_sends_high_priority_memory_suggestions() -> None:
    class _Engine:
        async def run(self, *, session_id: str, user_text: str):
            return SimpleNamespace(text="HEARTBEAT_OK")

    class _Monitor:
        def __init__(self) -> None:
            self.delivered: list[str] = []
            self.failed: list[str] = []

        async def scan(self):
            return [
                MemorySuggestion(
                    text="Upcoming birthday in 2 day(s): Ana",
                    priority=0.8,
                    trigger="upcoming_event",
                    channel="telegram",
                    target="chat42",
                    metadata={"days_until": 2},
                ),
                MemorySuggestion(
                    text="Pattern detected: docs appeared 4 times",
                    priority=0.4,
                    trigger="pattern",
                    channel="cli",
                    target="default",
                ),
            ]

        def mark_delivered(self, suggestion_id: str) -> bool:
            if hasattr(suggestion_id, "suggestion_id"):
                self.delivered.append(str(getattr(suggestion_id, "suggestion_id")))
            else:
                self.delivered.append(str(suggestion_id))
            return True

        def mark_failed(self, suggestion_id: str, *, error: str = "") -> bool:
            del error
            if hasattr(suggestion_id, "suggestion_id"):
                self.failed.append(str(getattr(suggestion_id, "suggestion_id")))
            else:
                self.failed.append(str(suggestion_id))
            return True

        def should_deliver(self, suggestion, *, min_priority: float = 0.0) -> bool:
            return float(getattr(suggestion, "priority", 0.0) or 0.0) >= float(min_priority)

    async def _scenario() -> None:
        monitor = _Monitor()
        channels = SimpleNamespace(send=AsyncMock(return_value="msg-1"))
        runtime = SimpleNamespace(engine=_Engine(), channels=channels, memory_monitor=monitor)
        decision = await _run_heartbeat(runtime)

        assert decision.action == "skip"
        channels.send.assert_awaited_once()
        send_kwargs = channels.send.await_args.kwargs
        assert send_kwargs["channel"] == "telegram"
        assert send_kwargs["target"] == "chat42"
        assert send_kwargs["metadata"]["priority"] == 0.8
        assert send_kwargs["metadata"]["trigger"] == "upcoming_event"
        assert len(monitor.delivered) == 1

    asyncio.run(_scenario())


def test_run_heartbeat_skips_low_priority_suggestions() -> None:
    class _Engine:
        async def run(self, *, session_id: str, user_text: str):
            return SimpleNamespace(text="Alert: review now")

    class _Monitor:
        async def scan(self):
            return [
                MemorySuggestion(
                    text="Pattern detected: docs appeared 4 times",
                    priority=0.69,
                    trigger="pattern",
                    channel="cli",
                    target="default",
                )
            ]

        def mark_delivered(self, suggestion_id: str) -> bool:
            return False

        def mark_failed(self, suggestion_id: str, *, error: str = "") -> bool:
            del suggestion_id, error
            return False

        def should_deliver(self, suggestion, *, min_priority: float = 0.0) -> bool:
            return float(getattr(suggestion, "priority", 0.0) or 0.0) >= float(min_priority)

    async def _scenario() -> None:
        channels = SimpleNamespace(send=AsyncMock(return_value="msg-1"))
        runtime = SimpleNamespace(engine=_Engine(), channels=channels, memory_monitor=_Monitor())
        decision = await _run_heartbeat(runtime)

        assert decision.action == "run"
        channels.send.assert_not_awaited()

    asyncio.run(_scenario())


def test_run_heartbeat_monitor_fail_soft_does_not_break_decision() -> None:
    class _Engine:
        async def run(self, *, session_id: str, user_text: str):
            return SimpleNamespace(text="HEARTBEAT_OK")

    class _Monitor:
        async def scan(self):
            raise RuntimeError("monitor failed")

        def mark_delivered(self, suggestion_id: str) -> bool:
            return False

        def mark_failed(self, suggestion_id: str, *, error: str = "") -> bool:
            del suggestion_id, error
            return False

        def should_deliver(self, suggestion, *, min_priority: float = 0.0) -> bool:
            del suggestion
            return min_priority <= 0.0

    async def _scenario() -> None:
        channels = SimpleNamespace(send=AsyncMock(return_value="msg-1"))
        runtime = SimpleNamespace(engine=_Engine(), channels=channels, memory_monitor=_Monitor())
        decision = await _run_heartbeat(runtime)

        assert decision.action == "skip"
        assert decision.reason == "heartbeat_ok"
        channels.send.assert_not_awaited()

    asyncio.run(_scenario())


def test_gateway_auth_required_for_control_plane(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={
            "auth": {
                "mode": "required",
                "token": "secret-token",
                "allow_loopback_without_auth": False,
            },
            "heartbeat": {"enabled": False},
        },
        channels={},
    )
    app = create_app(cfg)
    app.state.runtime.engine.provider = FakeProvider()

    with TestClient(app) as client:
        unauthorized = client.get("/v1/status")
        assert unauthorized.status_code == 401
        assert unauthorized.json()["error"] == "gateway_auth_required"
        assert unauthorized.json()["code"] == "gateway_auth_required"

        unauthorized_alias = client.get("/api/status")
        assert unauthorized_alias.status_code == 401
        assert unauthorized_alias.json()["error"] == "gateway_auth_required"
        assert unauthorized_alias.json()["code"] == "gateway_auth_required"

        unauthorized_token = client.get("/api/token")
        assert unauthorized_token.status_code == 401
        assert unauthorized_token.json()["error"] == "gateway_auth_required"
        assert unauthorized_token.json()["code"] == "gateway_auth_required"

        ok = client.get("/v1/status", headers={"Authorization": "Bearer secret-token"})
        assert ok.status_code == 200
        payload = ok.json()
        assert payload["ready"] is True
        assert payload["auth"]["posture"] == "strict"
        assert payload["contract_version"] == "2026-03-04"
        assert isinstance(payload["server_time"], str) and payload["server_time"]

        ok_alias = client.get("/api/status", headers={"Authorization": "Bearer secret-token"})
        assert ok_alias.status_code == 200
        alias_payload = ok_alias.json()
        assert isinstance(alias_payload["server_time"], str) and alias_payload["server_time"]
        assert {k: v for k, v in alias_payload.items() if k != "server_time"} == {
            k: v for k, v in payload.items() if k != "server_time"
        }

        token = client.get("/api/token", headers={"Authorization": "Bearer secret-token"})
        assert token.status_code == 200
        token_payload = token.json()
        assert token_payload["token_configured"] is True
        assert token_payload["token_masked"] == "********oken"
        assert token_payload["token_masked"] != "secret-token"


def test_gateway_auth_auto_hardens_on_non_loopback_with_token(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={
            "host": "0.0.0.0",
            "auth": {
                "mode": "off",
                "token": "secret-token",
            },
            "heartbeat": {"enabled": False},
        },
        channels={},
    )
    app = create_app(cfg)
    app.state.runtime.engine.provider = FakeProvider()

    with TestClient(app) as client:
        unauthorized = client.get("/v1/status")
        assert unauthorized.status_code == 401
        assert unauthorized.json()["error"] == "gateway_auth_required"

        ok = client.get("/v1/status", headers={"Authorization": "Bearer secret-token"})
        assert ok.status_code == 200
        payload = ok.json()
        assert payload["auth"]["mode"] == "required"
        assert payload["auth"]["posture"] == "strict"


def test_gateway_auth_keeps_loopback_open_with_mode_off(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={
            "host": "127.0.0.1",
            "auth": {
                "mode": "off",
                "token": "secret-token",
            },
            "heartbeat": {"enabled": False},
        },
        channels={},
    )
    app = create_app(cfg)
    app.state.runtime.engine.provider = FakeProvider()

    with TestClient(app) as client:
        response = client.get("/v1/status")
        assert response.status_code == 200
        payload = response.json()
        assert payload["auth"]["mode"] == "off"
        assert payload["auth"]["posture"] == "open"


def test_gateway_auth_auto_hardening_emits_log_event(tmp_path: Path) -> None:
    rows: list[str] = []
    sink_id = logger.add(rows.append, format=logging_utils._text_format)
    try:
        create_app(
            AppConfig(
                workspace_path=str(tmp_path / "workspace"),
                state_path=str(tmp_path / "state"),
                scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
                gateway={
                    "host": "0.0.0.0",
                    "auth": {"mode": "off", "token": "secret-token"},
                    "heartbeat": {"enabled": False},
                },
                channels={},
            )
        )
    finally:
        logger.remove(sink_id)

    joined = "\n".join(rows)
    assert "[gateway.auth]" in joined.lower()
    assert "gateway auth auto-hardened" in joined


def test_gateway_ws_alias_behaves_like_v1_ws(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)
    app.state.runtime.engine.provider = FakeProvider()

    with TestClient(app) as client:
        bootstrap_file = tmp_path / "workspace" / "BOOTSTRAP.md"
        assert bootstrap_file.exists()

        with client.websocket_connect("/v1/ws") as socket:
            socket.send_json({"session_id": "cli:ws", "text": "ping"})
            payload = socket.receive_json()
            assert payload["text"] == "pong"

        assert not bootstrap_file.exists()

        with client.websocket_connect("/ws") as socket_alias:
            socket_alias.send_json({"session_id": "cli:ws", "text": "ping"})
            payload_alias = socket_alias.receive_json()
            assert payload_alias["text"] == "pong"


def test_gateway_ws_alias_respects_auth_guard(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={
            "auth": {
                "mode": "required",
                "token": "secret-token",
                "allow_loopback_without_auth": False,
            },
            "heartbeat": {"enabled": False},
        },
        channels={},
    )
    app = create_app(cfg)
    app.state.runtime.engine.provider = FakeProvider()

    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws"):
                pass

        with client.websocket_connect("/ws?token=secret-token") as socket:
            socket.send_json({"session_id": "cli:ws", "text": "ping"})
            payload = socket.receive_json()
            assert payload["text"] == "pong"


def test_gateway_diagnostics_schema_and_toggle(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={
            "auth": {
                "mode": "required",
                "token": "diag-token",
                "allow_loopback_without_auth": False,
            },
            "heartbeat": {"enabled": False},
            "diagnostics": {"enabled": True, "require_auth": True, "include_config": True},
        },
        channels={},
    )
    app = create_app(cfg)
    app.state.runtime.engine.provider = FakeProvider()
    with TestClient(app) as client:
        unauthorized = client.get("/v1/diagnostics")
        assert unauthorized.status_code == 401
        assert unauthorized.json()["code"] == "gateway_auth_required"

        unauthorized_alias = client.get("/api/diagnostics")
        assert unauthorized_alias.status_code == 401
        assert unauthorized_alias.json()["code"] == "gateway_auth_required"

        response = client.get("/v1/diagnostics", headers={"Authorization": "Bearer diag-token"})
        assert response.status_code == 200
        payload = response.json()
        assert payload["schema_version"] == "2026-03-02"
        assert payload["contract_version"] == "2026-03-04"
        assert isinstance(payload["generated_at"], str) and payload["generated_at"]
        assert isinstance(payload["uptime_s"], int)
        assert payload["uptime_s"] >= 0
        assert "control_plane" in payload
        assert payload["control_plane"]["contract_version"] == "2026-03-04"
        assert "queue" in payload
        assert "dead_letter_recent" in payload["queue"]
        assert isinstance(payload["queue"]["dead_letter_recent"], list)
        assert "channels" in payload
        assert "channels_delivery" in payload
        channels_delivery = payload["channels_delivery"]
        assert set(channels_delivery.keys()) >= {"total", "per_channel", "recent"}
        assert isinstance(channels_delivery["recent"], list)
        assert set(channels_delivery["total"].keys()) >= {
            "attempts",
            "success",
            "failures",
            "dead_lettered",
            "replayed",
            "channel_unavailable",
            "policy_dropped",
            "delivery_confirmed",
            "delivery_failed_final",
            "idempotency_suppressed",
        }
        assert "cron" in payload
        assert "heartbeat" in payload
        assert "bootstrap" in payload
        assert "pending" in payload["bootstrap"]
        assert "memory_monitor" in payload
        assert payload["memory_monitor"]["enabled"] is False
        assert "engine" in payload
        assert "http" in payload
        assert "retrieval_metrics" in payload["engine"]
        assert "turn_metrics" in payload["engine"]
        assert "provider" in payload["engine"]
        retrieval = payload["engine"]["retrieval_metrics"]
        assert set(retrieval.keys()) == {
            "route_counts",
            "retrieval_attempts",
            "retrieval_hits",
            "retrieval_rewrites",
            "latency_buckets",
            "last_route",
            "last_query",
        }
        turn_metrics = payload["engine"]["turn_metrics"]
        assert set(turn_metrics.keys()) == {
            "turns_total",
            "turns_success",
            "turns_provider_errors",
            "turns_cancelled",
            "tool_calls_executed",
            "latency_buckets",
            "last_outcome",
            "last_model",
        }
        assert set(turn_metrics["latency_buckets"].keys()) == {
            "lt_1s",
            "1_3s",
            "3_10s",
            "gte_10s",
        }
        assert payload["environment"]["workspace_path"] == str(tmp_path / "workspace")

        alias = client.get("/api/diagnostics", headers={"Authorization": "Bearer diag-token"})
        assert alias.status_code == 200
        alias_payload = alias.json()
        assert set(alias_payload.keys()) == set(payload.keys())
        assert alias_payload["schema_version"] == payload["schema_version"]
        assert alias_payload["contract_version"] == payload["contract_version"]
        assert alias_payload["environment"] == payload["environment"]
        assert alias_payload["engine"] == payload["engine"]
        assert set(alias_payload["control_plane"].keys()) == set(payload["control_plane"].keys())
        assert alias_payload["control_plane"]["contract_version"] == payload["control_plane"]["contract_version"]

    cfg_disabled = AppConfig(
        workspace_path=str(tmp_path / "workspace2"),
        state_path=str(tmp_path / "state2"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={"diagnostics": {"enabled": False}, "heartbeat": {"enabled": False}},
        channels={},
    )
    app_disabled = create_app(cfg_disabled)
    with TestClient(app_disabled) as client:
        disabled = client.get("/v1/diagnostics")
        assert disabled.status_code == 404
        assert disabled.json()["error"] == "diagnostics_disabled"
        assert disabled.json()["code"] == "diagnostics_disabled"

        disabled_alias = client.get("/api/diagnostics")
        assert disabled_alias.status_code == 404
        assert disabled_alias.json()["error"] == "diagnostics_disabled"
        assert disabled_alias.json()["code"] == "diagnostics_disabled"


def test_gateway_diagnostics_include_provider_telemetry_when_enabled(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={
            "heartbeat": {"enabled": False},
            "diagnostics": {
                "enabled": True,
                "require_auth": False,
                "include_provider_telemetry": True,
            },
        },
        channels={},
    )
    app = create_app(cfg)
    app.state.runtime.engine.provider = ProviderWithDiagnostics()

    with TestClient(app) as client:
        payload = client.get("/v1/diagnostics").json()
        assert "provider" in payload["engine"]
        assert payload["engine"]["provider"]["provider"] == "fake_provider"

        alias_payload = client.get("/api/diagnostics").json()
        assert alias_payload["engine"]["provider"] == payload["engine"]["provider"]


def test_gateway_diagnostics_http_telemetry_tracks_success_and_errors(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={
            "auth": {
                "mode": "required",
                "token": "diag-token",
                "allow_loopback_without_auth": False,
            },
            "heartbeat": {"enabled": False},
            "diagnostics": {"enabled": True, "require_auth": True},
        },
        channels={},
    )
    app = create_app(cfg)

    with TestClient(app) as client:
        unauthorized = client.get("/v1/status")
        assert unauthorized.status_code == 401

        authorized_status = client.get("/v1/status", headers={"Authorization": "Bearer diag-token"})
        assert authorized_status.status_code == 200

        diagnostics = client.get("/v1/diagnostics", headers={"Authorization": "Bearer diag-token"})
        assert diagnostics.status_code == 200
        http_payload = diagnostics.json()["http"]

        assert http_payload["total_requests"] >= 3
        assert http_payload["in_flight"] >= 1
        assert http_payload["by_method"]["GET"] >= 3
        assert http_payload["by_path"]["/v1/status"] >= 2
        assert http_payload["by_path"]["/v1/diagnostics"] >= 1
        assert http_payload["by_status"]["401"] >= 1
        assert http_payload["by_status"]["200"] >= 1

        latency = http_payload["latency_ms"]
        assert latency["count"] >= 2
        assert latency["min"] >= 0
        assert latency["max"] >= latency["min"]
        assert latency["avg"] >= latency["min"]
        assert latency["avg"] <= latency["max"]


def test_gateway_diagnostics_provider_telemetry_sanitizes_nested_secrets(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={
            "heartbeat": {"enabled": False},
            "diagnostics": {
                "enabled": True,
                "require_auth": False,
                "include_provider_telemetry": True,
            },
        },
        channels={},
    )
    app = create_app(cfg)
    app.state.runtime.engine.provider = ProviderWithUnsafeDiagnostics()

    with TestClient(app) as client:
        payload = client.get("/v1/diagnostics").json()
        provider_payload = payload["engine"]["provider"]
        rendered = json.dumps(provider_payload)

        forbidden_keys = [
            "api_key",
            "access_token",
            "token",
            "authorization",
            "auth",
            "credential",
            "credentials",
            "secret",
            "password",
        ]
        for marker in forbidden_keys:
            assert f'"{marker}"' not in rendered

        for secret in [
            "top-level-secret",
            "nested-secret",
            "Bearer should-not-leak",
            "cred-secret",
            "dont-leak",
        ]:
            assert secret not in rendered

        assert provider_payload["provider"] == "fake_provider"
        assert provider_payload["model"] == "fake/test"
        assert provider_payload["diagnostics_available"] is True
        assert provider_payload["nested"]["safe"] == "ok"
        assert provider_payload["nested"]["deep"][0]["value"] == "retained"
        assert provider_payload["nested"]["deep"][1]["meta"]["message"] == "still-safe"
        assert provider_payload["items"][0]["status"] == "clean"
        assert provider_payload["items"][1]["note"] == "keep-note"


def test_gateway_diagnostics_omits_provider_telemetry_when_disabled(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={
            "heartbeat": {"enabled": False},
            "diagnostics": {
                "enabled": True,
                "require_auth": False,
                "include_provider_telemetry": False,
            },
        },
        channels={},
    )
    app = create_app(cfg)
    app.state.runtime.engine.provider = ProviderWithDiagnostics()

    with TestClient(app) as client:
        payload = client.get("/v1/diagnostics").json()
        assert "provider" not in payload["engine"]

        alias_payload = client.get("/api/diagnostics").json()
        assert "provider" not in alias_payload["engine"]
        assert alias_payload["engine"] == payload["engine"]


def test_gateway_startup_rollback_when_subsystem_fails(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={"heartbeat": {"enabled": False}},
        channels={},
    )
    app = create_app(cfg)
    rollback = {"channels_stopped": False}

    async def _channels_start(_config):
        return None

    async def _channels_stop():
        rollback["channels_stopped"] = True

    async def _cron_start(_callback):
        raise RuntimeError("cron_boot_failure")

    app.state.runtime.channels.start = _channels_start
    app.state.runtime.channels.stop = _channels_stop
    app.state.runtime.cron.start = _cron_start

    with pytest.raises(RuntimeError):
        with TestClient(app):
            pass

    assert rollback["channels_stopped"] is True


def test_gateway_shutdown_isolation_continues_after_stop_errors(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={"heartbeat": {"enabled": False}},
        channels={},
    )
    app = create_app(cfg)
    markers = {"cron_stop": False, "channels_stop": False}

    async def _cron_stop():
        markers["cron_stop"] = True
        raise RuntimeError("stop_failed")

    async def _channels_stop():
        markers["channels_stop"] = True

    app.state.runtime.cron.stop = _cron_stop
    app.state.runtime.channels.stop = _channels_stop

    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200

    assert markers["cron_stop"] is True
    assert markers["channels_stop"] is True


def test_gateway_cron_endpoints_roundtrip(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={"heartbeat": {"enabled": False}},
        channels={},
    )
    app = create_app(cfg)

    with TestClient(app) as client:
        created = client.post(
            "/v1/cron/add",
            json={
                "session_id": "cli:cron",
                "expression": "every 60",
                "prompt": "Run cron check",
                "name": "roundtrip-cron",
            },
        )
        assert created.status_code == 200
        created_payload = created.json()
        assert created_payload["ok"] is True
        assert created_payload["status"] == "created"
        job_id = created_payload["id"]
        assert isinstance(job_id, str) and job_id

        listed = client.get("/v1/cron/list", params={"session_id": "cli:cron"})
        assert listed.status_code == 200
        jobs = listed.json()["jobs"]
        assert len(jobs) == 1
        job = jobs[0]
        assert job["id"] == job_id
        assert job["name"] == "roundtrip-cron"
        assert job["session_id"] == "cli:cron"
        assert job["expression"] == "every 60"
        assert job["timezone"] == "UTC"
        assert job["enabled"] is True
        assert isinstance(job["next_run_iso"], str) and job["next_run_iso"]
        assert job["payload"]["prompt"] == "Run cron check"

        deleted = client.delete(f"/v1/cron/{job_id}")
        assert deleted.status_code == 200
        deleted_payload = deleted.json()
        assert deleted_payload["ok"] is True
        assert deleted_payload["status"] == "removed"

        listed_empty = client.get("/v1/cron/list", params={"session_id": "cli:cron"})
        assert listed_empty.status_code == 200
        assert listed_empty.json()["jobs"] == []


def test_gateway_heartbeat_trigger_contract_updates_state(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={"heartbeat": {"enabled": True, "interval_s": 9999}},
        channels={},
    )
    app = create_app(cfg)

    calls: list[tuple[str, str]] = []

    async def _run(*, session_id: str, user_text: str):
        calls.append((session_id, user_text))
        return SimpleNamespace(text="HEARTBEAT_OK", model="fake/test")

    app.state.runtime.engine.run = _run
    state_path = Path(app.state.runtime.heartbeat.state_path)

    with TestClient(app) as client:
        response = client.post("/v1/control/heartbeat/trigger")
        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is True
        assert payload["decision"]["action"] == "skip"
        assert payload["decision"]["reason"] == "heartbeat_ok"

    assert calls
    assert any(session_id == "heartbeat:system" for session_id, _ in calls)
    assert state_path.exists()

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["last_action"] == "skip"
    assert state["last_reason"] == "heartbeat_ok"
    assert state["last_decision"]["action"] == "skip"
    assert state["last_decision"]["reason"] == "heartbeat_ok"
    assert state["skip_count"] >= 1


def test_gateway_heartbeat_trigger_disabled_guard(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={"heartbeat": {"enabled": False}},
        channels={},
    )
    app = create_app(cfg)

    with TestClient(app) as client:
        response = client.post("/v1/control/heartbeat/trigger")
        assert response.status_code == 409
        payload = response.json()
        assert payload["error"] == "heartbeat_disabled"
        assert payload["status"] == 409
        assert payload["code"] == "heartbeat_disabled"
