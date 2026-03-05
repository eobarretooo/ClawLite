from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from loguru import logger
from starlette.websockets import WebSocketDisconnect

from clawlite.config.schema import AppConfig, SchedulerConfig
from clawlite.core.memory_monitor import MemorySuggestion
from clawlite.gateway.server import _run_heartbeat, _run_proactive_monitor, build_runtime, create_app
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


class _FakeTuningMemory:
    def __init__(self, *, degrade: bool = True, fail_update: bool = False, fail_tuning_update: bool = False) -> None:
        self.degrade = degrade
        self.fail_update = fail_update
        self.fail_tuning_update = fail_tuning_update
        self.snapshot_calls = 0
        self.tuning = {
            "degrading_streak": 0,
            "last_action": "",
            "last_action_at": "",
            "last_action_status": "",
            "last_reason": "",
            "next_run_at": "",
            "last_run_at": "",
            "last_error": "",
            "recent_actions": [],
        }

    def diagnostics(self) -> dict[str, object]:
        return {
            "available": True,
            "backend_name": "fake",
            "backend_supported": True,
            "backend_initialized": True,
            "backend_init_error": "",
        }

    def analyze(self) -> dict[str, object]:
        return {
            "semantic": {
                "enabled": True,
                "coverage_ratio": 0.1,
                "missing_records": 200,
                "total_records": 220,
            }
        }

    def update_quality_state(self, *, retrieval_metrics, turn_stability_metrics, semantic_metrics, sampled_at):
        del retrieval_metrics, turn_stability_metrics, semantic_metrics
        if self.fail_update:
            raise RuntimeError("tuning-update-failed")
        return {
            "sampled_at": sampled_at,
            "score": 20 if self.degrade else 88,
            "retrieval": {"attempts": 10, "hits": 1, "rewrites": 0, "hit_rate": 0.1},
            "turn_stability": {"successes": 1, "errors": 3, "success_rate": 0.25, "error_rate": 0.75},
            "drift": {
                "assessment": "degrading" if self.degrade else "stable",
                "score_delta_previous": -10,
                "score_delta_baseline": -10,
                "hit_rate_delta_previous": -0.2,
                "hit_rate_delta_baseline": -0.2,
            },
            "semantic": {"enabled": True, "coverage_ratio": 0.1},
            "recommendations": ["x"],
        }

    def quality_state_snapshot(self) -> dict[str, object]:
        return {
            "version": 1,
            "updated_at": "",
            "baseline": {},
            "current": {},
            "history": [],
            "tuning": dict(self.tuning),
        }

    def update_quality_tuning_state(self, tuning_patch: dict[str, object] | None = None) -> dict[str, object]:
        if self.fail_tuning_update:
            raise RuntimeError("tuning-state-write-failed")
        patch_payload = dict(tuning_patch or {})
        for key, value in patch_payload.items():
            if key == "recent_actions":
                rows = value if isinstance(value, list) else [value]
                self.tuning["recent_actions"] = list(self.tuning.get("recent_actions", [])) + [dict(row) for row in rows]
                self.tuning["recent_actions"] = self.tuning["recent_actions"][-20:]
            else:
                self.tuning[key] = value
        return dict(self.tuning)

    def snapshot(self, tag: str = "") -> str:
        del tag
        self.snapshot_calls += 1
        return f"v{self.snapshot_calls}"


def _assert_connect_challenge(socket) -> dict[str, object]:
    payload = socket.receive_json()
    assert payload["type"] == "event"
    assert payload["event"] == "connect.challenge"
    assert isinstance(payload["params"]["nonce"], str) and payload["params"]["nonce"]
    assert isinstance(payload["params"]["issued_at"], str) and payload["params"]["issued_at"]
    return payload


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


def test_gateway_telegram_webhook_processing_failure_returns_200_by_default(tmp_path: Path) -> None:
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
            channel = app.state.runtime.channels.get_channel("telegram")
            assert channel is not None
            channel.handle_webhook_update = AsyncMock(return_value=False)

            response = client.post(
                "/api/webhooks/telegram",
                json={"update_id": 2, "message": {"text": "hello"}},
                headers={"X-Telegram-Bot-Api-Secret-Token": "secret-1"},
            )

            assert response.status_code == 200
            assert response.json() == {"ok": True, "processed": False}


def test_gateway_telegram_webhook_processing_failure_returns_503_in_fail_fast_mode(tmp_path: Path) -> None:
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
                "webhook_fail_fast_on_error": True,
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
            channel = app.state.runtime.channels.get_channel("telegram")
            assert channel is not None
            channel.handle_webhook_update = AsyncMock(return_value=False)

            response = client.post(
                "/api/webhooks/telegram",
                json={"update_id": 2, "message": {"text": "hello"}},
                headers={"X-Telegram-Bot-Api-Secret-Token": "secret-1"},
            )

            assert response.status_code == 503
            payload = response.json()
            assert payload["error"] == "telegram_webhook_processing_failed"
            assert payload["code"] == "telegram_webhook_processing_failed"


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


def test_build_runtime_heartbeat_state_path_uses_workspace_memory_dir(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    runtime = build_runtime(cfg)

    assert Path(runtime.heartbeat.state_path) == (tmp_path / "workspace" / "memory" / "heartbeat-state.json")


def test_build_runtime_heartbeat_interval_accepts_120_from_scheduler(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=120),
        channels={},
    )
    runtime = build_runtime(cfg)

    assert runtime.heartbeat.interval_seconds == 120


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


def test_run_heartbeat_does_not_run_memory_monitor_when_present() -> None:
    class _Engine:
        async def run(self, *, session_id: str, user_text: str):
            del session_id, user_text
            return SimpleNamespace(text="HEARTBEAT_OK")

    class _Monitor:
        async def scan(self):
            return [
                MemorySuggestion(
                    text="Should not send from heartbeat",
                    priority=0.9,
                    trigger="upcoming_event",
                    channel="telegram",
                    target="chat42",
                )
            ]

    async def _scenario() -> None:
        channels = SimpleNamespace(send=AsyncMock(return_value="msg-1"))
        runtime = SimpleNamespace(engine=_Engine(), channels=channels, memory_monitor=_Monitor())
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
    app.state.runtime.autonomy_wake.submit = AsyncMock(
        return_value={
            "status": "ok",
            "scanned": 0,
            "delivered": 0,
            "failed": 0,
            "next_step_sent": False,
            "error": "",
        }
    )
    with TestClient(app) as client:
        payload = client.get("/v1/diagnostics").json()
        monitor_payload = payload["memory_monitor"]
        assert monitor_payload["enabled"] is True
        assert "scans" in monitor_payload
        assert "generated" in monitor_payload
        assert "runner" in monitor_payload
        assert monitor_payload["runner"]["enabled"] is True
        assert monitor_payload["runner"]["running"] is True

        status_payload = client.get("/v1/status").json()
        proactive_component = status_payload["components"]["proactive_monitor"]
        assert proactive_component["enabled"] is True
        assert proactive_component["running"] is True

    app.state.runtime.autonomy_wake.submit.assert_awaited()


def test_gateway_diagnostics_includes_autonomy_wake_and_alias_parity(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={"heartbeat": {"enabled": False}, "diagnostics": {"enabled": True, "require_auth": False}},
        channels={},
    )
    app = create_app(cfg)

    with TestClient(app) as client:
        payload = client.get("/v1/diagnostics").json()
        alias_payload = client.get("/api/diagnostics").json()

        assert "autonomy_wake" in payload
        assert set(payload["autonomy_wake"].keys()) >= {
            "running",
            "max_pending",
            "enqueued",
            "coalesced",
            "dropped_backpressure",
            "executed_ok",
            "executed_error",
            "queue_depth",
            "inflight",
            "max_queue_depth_seen",
            "by_kind",
        }
        assert alias_payload["autonomy_wake"] == payload["autonomy_wake"]


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
    class _Memory:
        def all(self):
            return [SimpleNamespace(source="session:telegram:chat42", created_at="2026-03-05T00:00:00+00:00")]

    class _Engine:
        def __init__(self) -> None:
            self.memory = _Memory()

        async def run(self, *, session_id: str, user_text: str):
            return SimpleNamespace(text="Alert: queue backlog is growing")

    async def _scenario() -> None:
        channels = SimpleNamespace(send=AsyncMock(return_value="msg-1"))
        runtime = SimpleNamespace(engine=_Engine(), channels=channels)
        decision = await _run_heartbeat(runtime)
        assert decision.action == "run"
        assert decision.reason == "actionable_dispatched"
        channels.send.assert_awaited_once()
        kwargs = channels.send.await_args.kwargs
        assert kwargs["channel"] == "telegram"
        assert kwargs["target"] == "chat42"
        assert kwargs["text"] == "Alert: queue backlog is growing"
        assert kwargs["metadata"]["source"] == "heartbeat"
        assert kwargs["metadata"]["trigger"] == "heartbeat_loop"

    asyncio.run(_scenario())


def test_run_heartbeat_injects_workspace_content_when_available() -> None:
    class _Engine:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        async def run(self, *, session_id: str, user_text: str):
            self.calls.append((session_id, user_text))
            return SimpleNamespace(text="HEARTBEAT_OK")

    async def _scenario() -> None:
        engine = _Engine()
        runtime = SimpleNamespace(
            engine=engine,
            workspace=SimpleNamespace(heartbeat_prompt=lambda: "- check inbox\n- prune stale tasks"),
        )

        decision = await _run_heartbeat(runtime)

        assert decision.action == "skip"
        assert engine.calls
        session_id, user_text = engine.calls[0]
        assert session_id == "heartbeat:system"
        assert "HEARTBEAT.md content:" in user_text
        assert "check inbox" in user_text
        assert "prune stale tasks" in user_text

    asyncio.run(_scenario())


def test_run_heartbeat_actionable_dispatch_failure_marks_reason() -> None:
    class _Engine:
        async def run(self, *, session_id: str, user_text: str):
            del session_id, user_text
            return SimpleNamespace(text="Alert: dispatch this")

    async def _scenario() -> None:
        channels = SimpleNamespace(send=AsyncMock(side_effect=RuntimeError("channel down")))
        runtime = SimpleNamespace(engine=_Engine(), channels=channels)

        decision = await _run_heartbeat(runtime)

        assert decision.action == "run"
        assert decision.reason == "actionable_dispatch_failed"
        channels.send.assert_awaited_once()

    asyncio.run(_scenario())


def test_run_proactive_monitor_sends_high_priority_memory_suggestions() -> None:
    class _Engine:
        def __init__(self) -> None:
            self.memory = None

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
        result = await _run_proactive_monitor(runtime)

        assert result["status"] == "ok"
        assert result["delivered"] == 1
        channels.send.assert_awaited_once()
        send_kwargs = channels.send.await_args.kwargs
        assert send_kwargs["channel"] == "telegram"
        assert send_kwargs["target"] == "chat42"
        assert send_kwargs["metadata"]["priority"] == 0.8
        assert send_kwargs["metadata"]["trigger"] == "upcoming_event"
        assert len(monitor.delivered) == 1

    asyncio.run(_scenario())


def test_run_proactive_monitor_sends_next_step_query_proactive_suggestion() -> None:
    class _Memory:
        async def retrieve(self, query: str, *, method: str = "rag", limit: int = 5):
            assert query
            assert method == "llm"
            assert limit == 5
            return {
                "status": "ok",
                "method": "llm",
                "next_step_query": "Should we confirm the deployment owner?",
            }

        def all(self):
            return [SimpleNamespace(source="session:telegram:chat42", created_at="2026-03-05T00:00:00+00:00")]

    class _Engine:
        def __init__(self) -> None:
            self.memory = _Memory()

    class _Monitor:
        def __init__(self) -> None:
            self.delivered = 0
            self.failed = 0

        async def scan(self):
            return []

        def should_deliver(self, suggestion, *, min_priority: float = 0.0) -> bool:
            return float(getattr(suggestion, "priority", 0.0) or 0.0) >= float(min_priority)

        def mark_delivered(self, suggestion) -> bool:
            del suggestion
            self.delivered += 1
            return True

        def mark_failed(self, suggestion, *, error: str = "") -> bool:
            del suggestion, error
            self.failed += 1
            return True

    async def _scenario() -> None:
        monitor = _Monitor()
        channels = SimpleNamespace(send=AsyncMock(return_value="msg-1"))
        runtime = SimpleNamespace(engine=_Engine(), channels=channels, memory_monitor=monitor)

        result = await _run_proactive_monitor(runtime)

        assert result["status"] == "ok"
        channels.send.assert_awaited_once()
        kwargs = channels.send.await_args.kwargs
        assert kwargs["channel"] == "telegram"
        assert kwargs["target"] == "chat42"
        assert kwargs["text"] == "Should we confirm the deployment owner?"
        assert kwargs["metadata"]["trigger"] == "next_step_query"
        assert monitor.delivered == 1
        assert monitor.failed == 0

    asyncio.run(_scenario())


def test_run_proactive_monitor_next_step_retrieve_fail_soft() -> None:
    class _Memory:
        async def retrieve(self, query: str, *, method: str = "rag", limit: int = 5):
            del query, method, limit
            raise RuntimeError("retrieve failed")

        def all(self):
            return [SimpleNamespace(source="session:cli:profile", created_at="2026-03-05T00:00:00+00:00")]

    class _Engine:
        def __init__(self) -> None:
            self.memory = _Memory()

    class _Monitor:
        async def scan(self):
            return []

        def should_deliver(self, suggestion, *, min_priority: float = 0.0) -> bool:
            del suggestion
            return min_priority <= 0.0

        def mark_delivered(self, suggestion) -> bool:
            del suggestion
            return False

        def mark_failed(self, suggestion, *, error: str = "") -> bool:
            del suggestion, error
            return False

    async def _scenario() -> None:
        channels = SimpleNamespace(send=AsyncMock(return_value="msg-1"))
        runtime = SimpleNamespace(engine=_Engine(), channels=channels, memory_monitor=_Monitor())
        result = await _run_proactive_monitor(runtime)

        assert result["status"] == "next_step_error"
        channels.send.assert_not_awaited()

    asyncio.run(_scenario())


def test_run_heartbeat_ignores_memory_monitor_suggestions() -> None:
    class _Engine:
        def __init__(self) -> None:
            self.memory = None

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
        assert decision.reason == "actionable_dispatched"
        channels.send.assert_awaited_once()
        kwargs = channels.send.await_args.kwargs
        assert kwargs["channel"] == "cli"
        assert kwargs["target"] == "profile"

    asyncio.run(_scenario())


def test_run_proactive_monitor_scan_fail_soft_does_not_raise() -> None:
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
        runtime = SimpleNamespace(engine=SimpleNamespace(memory=None), channels=channels, memory_monitor=_Monitor())
        result = await _run_proactive_monitor(runtime)

        assert result["status"] == "scan_error"
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
            _assert_connect_challenge(socket)
            socket.send_json({"session_id": "cli:ws", "text": "ping"})
            payload = socket.receive_json()
            assert payload["text"] == "pong"

        assert not bootstrap_file.exists()

        with client.websocket_connect("/ws") as socket_alias:
            _assert_connect_challenge(socket_alias)
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
            _assert_connect_challenge(socket)
            socket.send_json({"session_id": "cli:ws", "text": "ping"})
            payload = socket.receive_json()
            assert payload["text"] == "pong"


def test_gateway_ws_envelope_hello_and_ping_contract(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)
    app.state.runtime.engine.provider = FakeProvider()

    with TestClient(app) as client:
        with client.websocket_connect("/v1/ws") as socket:
            _assert_connect_challenge(socket)
            socket.send_json({"type": "hello"})
            ready_payload = socket.receive_json()
            assert ready_payload["type"] == "ready"
            assert ready_payload["contract_version"] == "2026-03-04"
            assert isinstance(ready_payload["server_time"], str) and ready_payload["server_time"]

            socket.send_json({"type": "ping"})
            pong_payload = socket.receive_json()
            assert pong_payload["type"] == "pong"
            assert isinstance(pong_payload["server_time"], str) and pong_payload["server_time"]


def test_gateway_ws_envelope_message_result_and_request_id(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)
    app.state.runtime.engine.provider = FakeProvider()

    with TestClient(app) as client:
        with client.websocket_connect("/ws") as socket:
            _assert_connect_challenge(socket)
            socket.send_json(
                {
                    "type": "message",
                    "session_id": "cli:ws-envelope",
                    "text": "ping",
                    "request_id": "req-123",
                }
            )
            payload = socket.receive_json()
            assert payload == {
                "type": "message_result",
                "session_id": "cli:ws-envelope",
                "text": "pong",
                "model": "fake/test",
                "request_id": "req-123",
            }


def test_gateway_ws_envelope_error_path_returns_structured_error(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)
    app.state.runtime.engine.provider = FakeProvider()

    with TestClient(app) as client:
        with client.websocket_connect("/v1/ws") as socket:
            _assert_connect_challenge(socket)
            socket.send_json({"type": "message", "session_id": "cli:ws-envelope", "request_id": "req-err"})
            payload = socket.receive_json()
            assert payload == {
                "type": "error",
                "error": "session_id and text are required",
                "status_code": 400,
                "request_id": "req-err",
            }


def test_gateway_ws_legacy_payload_without_type_keeps_legacy_contract(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)
    app.state.runtime.engine.provider = FakeProvider()

    with TestClient(app) as client:
        with client.websocket_connect("/v1/ws") as socket:
            _assert_connect_challenge(socket)
            socket.send_json({"session_id": "cli:ws-legacy", "text": "ping"})
            payload = socket.receive_json()
            assert payload == {"text": "pong", "model": "fake/test"}


def test_gateway_ws_req_res_openclaw_compatibility_methods(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)
    app.state.runtime.engine.provider = FakeProvider()

    with TestClient(app) as client:
        with client.websocket_connect("/ws") as socket:
            _assert_connect_challenge(socket)

            socket.send_json({"type": "req", "id": "pre1", "method": "ping", "params": {}})
            preconnect_ping = socket.receive_json()
            assert preconnect_ping == {
                "type": "res",
                "id": "pre1",
                "ok": False,
                "error": {
                    "code": "not_connected",
                    "message": "connect handshake required",
                    "status_code": 409,
                },
            }

            socket.send_json({"type": "req", "id": "c1", "method": "connect", "params": {}})
            connect_payload = socket.receive_json()
            assert connect_payload["type"] == "res"
            assert connect_payload["id"] == "c1"
            assert connect_payload["ok"] is True
            assert connect_payload["result"]["contract_version"] == "2026-03-04"
            assert connect_payload["result"]["connected"] is True
            assert isinstance(connect_payload["result"]["server_time"], str)

            socket.send_json({"type": "req", "id": 2, "method": "ping", "params": {}})
            ping_payload = socket.receive_json()
            assert ping_payload == {
                "type": "res",
                "id": 2,
                "ok": True,
                "result": {
                    "server_time": ping_payload["result"]["server_time"],
                },
            }
            assert isinstance(ping_payload["result"]["server_time"], str) and ping_payload["result"]["server_time"]

            socket.send_json({"type": "req", "id": "s1", "method": "status", "params": {}})
            status_payload = socket.receive_json()
            assert status_payload["type"] == "res"
            assert status_payload["id"] == "s1"
            assert status_payload["ok"] is True
            assert status_payload["result"]["contract_version"] == "2026-03-04"
            assert "components" in status_payload["result"]
            assert "auth" in status_payload["result"]

            socket.send_json(
                {
                    "type": "req",
                    "id": "m1",
                    "method": "chat.send",
                    "params": {"sessionId": "cli:req-path", "text": "ping"},
                }
            )
            message_payload = socket.receive_json()
            assert message_payload == {
                "type": "res",
                "id": "m1",
                "ok": True,
                "result": {
                    "session_id": "cli:req-path",
                    "text": "pong",
                    "model": "fake/test",
                },
            }

            socket.send_json({"type": "req", "id": "u1", "method": "nope.method", "params": {}})
            unsupported = socket.receive_json()
            assert unsupported == {
                "type": "res",
                "id": "u1",
                "ok": False,
                "error": {
                    "code": "unsupported_method",
                    "message": "unsupported req method: nope.method",
                    "status_code": 400,
                },
            }


def test_gateway_diagnostics_ws_telemetry_tracks_frames_and_errors(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={
            "heartbeat": {"enabled": False},
            "diagnostics": {"enabled": True, "require_auth": False},
        },
        channels={},
    )
    app = create_app(cfg)
    app.state.runtime.engine.provider = FakeProvider()

    with TestClient(app) as client:
        with client.websocket_connect("/ws") as socket:
            _assert_connect_challenge(socket)

            socket.send_json({"type": "req", "id": "c1", "method": "connect", "params": {}})
            connect_payload = socket.receive_json()
            assert connect_payload["ok"] is True

            socket.send_json({"type": "req", "id": "p1", "method": "ping", "params": {}})
            ping_payload = socket.receive_json()
            assert ping_payload["ok"] is True

            socket.send_json({"type": "req", "id": "u1", "method": "unsupported.method", "params": {}})
            unsupported = socket.receive_json()
            assert unsupported["ok"] is False
            assert unsupported["error"]["code"] == "unsupported_method"

        ws_payload = client.get("/v1/diagnostics").json()["ws"]
        ws_alias_payload = client.get("/api/diagnostics").json()["ws"]
        assert ws_alias_payload == ws_payload

        assert ws_payload["connections_opened"] >= 1
        assert ws_payload["connections_closed"] >= 1
        assert ws_payload["active_connections"] == 0
        assert ws_payload["frames_in"] >= 3
        assert ws_payload["frames_out"] >= 4
        assert ws_payload["by_path"]["/ws"] >= 1
        assert ws_payload["by_message_type_in"]["req"] >= 3
        assert ws_payload["by_message_type_out"]["event"] >= 1
        assert ws_payload["by_message_type_out"]["res"] >= 3
        assert ws_payload["req_methods"]["connect"] >= 1
        assert ws_payload["req_methods"]["ping"] >= 1
        assert ws_payload["req_methods"]["unsupported.method"] >= 1
        assert ws_payload["error_codes"]["unsupported_method"] >= 1


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
        assert "ws" in payload
        assert set(payload["ws"].keys()) >= {
            "connections_opened",
            "connections_closed",
            "active_connections",
            "frames_in",
            "frames_out",
            "by_path",
            "by_message_type_in",
            "by_message_type_out",
            "req_methods",
            "error_codes",
        }
        assert "retrieval_metrics" in payload["engine"]
        assert "turn_metrics" in payload["engine"]
        assert "memory" in payload["engine"]
        assert "memory_analysis" in payload["engine"]
        assert "memory_integration" in payload["engine"]
        assert "memory_quality" in payload["engine"]
        assert "provider" in payload["engine"]
        memory_diag = payload["engine"]["memory"]
        assert memory_diag["available"] is True
        assert memory_diag["backend_name"] == "sqlite"
        assert memory_diag["backend_supported"] is True
        assert memory_diag["backend_initialized"] is True
        assert memory_diag["backend_init_error"] == ""
        memory_analysis = payload["engine"]["memory_analysis"]
        assert memory_analysis["available"] is True
        assert isinstance(memory_analysis.get("reasoning_layers"), dict)
        assert isinstance(memory_analysis.get("confidence"), dict)
        memory_integration = payload["engine"]["memory_integration"]
        assert memory_integration["available"] is True
        assert set(memory_integration.keys()) >= {"mode", "policies", "quality", "session_id", "available"}
        assert isinstance(memory_integration["policies"], dict)
        assert set(memory_integration["policies"].keys()) >= {"system", "agent", "subagent", "tool"}
        memory_quality = payload["engine"]["memory_quality"]
        assert memory_quality["available"] is True
        assert memory_quality["updated"] is True
        assert isinstance(memory_quality["report"], dict)
        assert isinstance(memory_quality["state"], dict)
        assert memory_quality["error"] is None
        assert set(memory_quality["report"].keys()) >= {
            "sampled_at",
            "score",
            "retrieval",
            "turn_stability",
            "drift",
            "semantic",
            "recommendations",
        }
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
            "diagnostic_switches",
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


def test_gateway_diagnostics_memory_quality_fail_soft_when_update_errors(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={
            "heartbeat": {"enabled": False},
            "diagnostics": {"enabled": True, "require_auth": False},
        },
        channels={},
    )
    app = create_app(cfg)

    def _boom(*, retrieval_metrics, turn_stability_metrics, semantic_metrics, sampled_at):
        del retrieval_metrics, turn_stability_metrics, semantic_metrics, sampled_at
        raise RuntimeError("quality update failed")

    app.state.runtime.engine.memory.update_quality_state = _boom

    with TestClient(app) as client:
        response = client.get("/v1/diagnostics")
        assert response.status_code == 200
        payload = response.json()
        quality = payload["engine"]["memory_quality"]

        assert quality["available"] is True
        assert quality["updated"] is False
        assert quality["report"] == {}
        assert isinstance(quality["state"], dict)
        assert quality["error"]["type"] == "RuntimeError"
        assert quality["error"]["message"] == "quality update failed"


def test_gateway_diagnostics_memory_quality_prefers_analysis_stats(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={
            "heartbeat": {"enabled": False},
            "diagnostics": {"enabled": True, "require_auth": False},
        },
        channels={},
    )
    app = create_app(cfg)
    memory = app.state.runtime.engine.memory
    calls = {"analysis_stats": 0, "analyze": 0}
    captured_semantic: dict[str, object] = {}

    def _analysis_stats() -> dict[str, object]:
        calls["analysis_stats"] += 1
        return {
            "semantic": {
                "enabled": True,
                "coverage_ratio": 0.73,
                "missing_records": 27,
                "total_records": 100,
            }
        }

    def _analyze() -> dict[str, object]:
        calls["analyze"] += 1
        return {
            "semantic": {
                "enabled": True,
                "coverage_ratio": 0.0,
                "missing_records": 100,
                "total_records": 100,
            }
        }

    def _quality_update(*, retrieval_metrics, turn_stability_metrics, semantic_metrics, sampled_at):
        del retrieval_metrics, turn_stability_metrics, sampled_at
        captured_semantic.clear()
        captured_semantic.update(dict(semantic_metrics or {}))
        return {
            "semantic": dict(semantic_metrics or {}),
            "drift": {"assessment": "stable"},
            "score": 85,
            "recommendations": [],
        }

    def _quality_snapshot() -> dict[str, object]:
        return {"tuning": {}}

    memory.analysis_stats = _analysis_stats
    memory.analyze = _analyze
    memory.update_quality_state = _quality_update
    memory.quality_state_snapshot = _quality_snapshot

    with TestClient(app) as client:
        response = client.get("/v1/diagnostics")
        assert response.status_code == 200
        payload = response.json()
        semantic_report = payload["engine"]["memory_quality"]["report"]["semantic"]

        assert calls["analysis_stats"] >= 1
        assert calls["analyze"] == 0
        assert semantic_report["enabled"] is True
        assert semantic_report["coverage_ratio"] == pytest.approx(0.73)
        assert captured_semantic["coverage_ratio"] == pytest.approx(0.73)
        analysis_payload = payload["engine"]["memory_analysis"]
        assert analysis_payload["available"] is True
        assert analysis_payload["semantic"]["coverage_ratio"] == pytest.approx(0.73)


def test_gateway_diagnostics_memory_analysis_fail_soft_when_unavailable(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={
            "heartbeat": {"enabled": False},
            "diagnostics": {"enabled": True, "require_auth": False},
        },
        channels={},
    )
    app = create_app(cfg)
    app.state.runtime.engine.memory.analysis_stats = None

    with TestClient(app) as client:
        payload = client.get("/v1/diagnostics").json()
        assert payload["engine"]["memory_analysis"] == {"available": False}


def test_gateway_diagnostics_memory_analysis_fail_soft_when_errors(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={
            "heartbeat": {"enabled": False},
            "diagnostics": {"enabled": True, "require_auth": False},
        },
        channels={},
    )
    app = create_app(cfg)

    def _analysis_error() -> dict[str, object]:
        raise RuntimeError("analysis_stats_failed")

    app.state.runtime.engine.memory.analysis_stats = _analysis_error

    with TestClient(app) as client:
        payload = client.get("/v1/diagnostics").json()
        analysis_payload = payload["engine"]["memory_analysis"]
        assert analysis_payload["available"] is True
        assert analysis_payload["error"] == "analysis_stats_failed"


def test_gateway_tuning_loop_runs_when_heartbeat_disabled(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={
            "heartbeat": {"enabled": False},
            "diagnostics": {"enabled": True, "require_auth": False},
            "autonomy": {"tuning_loop_enabled": True},
        },
        channels={},
    )
    cfg.gateway.autonomy.tuning_loop_interval_s = 1
    app = create_app(cfg)

    with TestClient(app) as client:
        for _ in range(20):
            payload = client.get("/v1/diagnostics").json()
            if int(payload["memory_quality_tuning"]["ticks"]) >= 1:
                break
            time.sleep(0.05)

        status_payload = client.get("/v1/status").json()
        assert status_payload["components"]["heartbeat"]["enabled"] is False
        tuning_component = status_payload["components"]["memory_quality_tuning"]
        assert tuning_component["enabled"] is True
        assert tuning_component["running"] is True
        assert int(payload["memory_quality_tuning"]["ticks"]) >= 1


def test_gateway_diagnostics_include_tuning_runner_and_quality_tuning_state(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={
            "heartbeat": {"enabled": False},
            "diagnostics": {"enabled": True, "require_auth": False},
            "autonomy": {"tuning_loop_enabled": True},
        },
        channels={},
    )
    cfg.gateway.autonomy.tuning_loop_interval_s = 1
    app = create_app(cfg)

    with TestClient(app) as client:
        time.sleep(0.1)
        payload = client.get("/v1/diagnostics").json()

        assert "memory_quality_tuning" in payload
        assert set(payload["memory_quality_tuning"].keys()) >= {
            "enabled",
            "running",
            "ticks",
            "success_count",
            "error_count",
            "last_result",
            "last_error",
            "last_run_iso",
            "next_run_iso",
        }
        memory_quality = payload["engine"]["memory_quality"]
        assert isinstance(memory_quality["state"], dict)
        assert isinstance(memory_quality["tuning"], dict)
        assert isinstance(memory_quality["state"].get("tuning", {}), dict)


def test_gateway_tuning_loop_guardrails_prevent_action_spam(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={
            "heartbeat": {"enabled": False},
            "diagnostics": {"enabled": True, "require_auth": False},
            "autonomy": {
                "tuning_loop_enabled": True,
                "tuning_degrading_streak_threshold": 1,
                "action_rate_limit_per_hour": 1,
                "tuning_loop_cooldown_s": 0,
            },
        },
        channels={},
    )
    cfg.gateway.autonomy.tuning_loop_interval_s = 1
    app = create_app(cfg)
    fake_memory = _FakeTuningMemory(degrade=True)
    app.state.runtime.engine.memory = fake_memory
    app.state.runtime.channels.send = AsyncMock(return_value="ok")

    with TestClient(app) as client:
        time.sleep(2.4)
        payload = client.get("/v1/diagnostics").json()

        assert int(payload["memory_quality_tuning"]["ticks"]) >= 2
        assert fake_memory.snapshot_calls == 1
        assert payload["memory_quality_tuning"]["last_action_status"] in {"ok", "rate_limited", "cooldown_skipped"}
        assert fake_memory.tuning["recent_actions"]


def test_gateway_tuning_loop_cooldown_skip_does_not_advance_last_action_at(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={
            "heartbeat": {"enabled": False},
            "diagnostics": {"enabled": True, "require_auth": False},
            "autonomy": {
                "tuning_loop_enabled": True,
                "tuning_degrading_streak_threshold": 1,
                "action_rate_limit_per_hour": 10,
                "tuning_loop_cooldown_s": 3600,
            },
        },
        channels={},
    )
    cfg.gateway.autonomy.tuning_loop_interval_s = 1
    app = create_app(cfg)
    fake_memory = _FakeTuningMemory(degrade=True)
    app.state.runtime.engine.memory = fake_memory
    app.state.runtime.channels.send = AsyncMock(return_value="ok")

    with TestClient(app) as client:
        first_last_action_at = ""
        for _ in range(40):
            payload = client.get("/v1/diagnostics").json()
            first_last_action_at = str(fake_memory.tuning.get("last_action_at", "") or "")
            if int(payload["memory_quality_tuning"]["ticks"]) >= 1 and first_last_action_at:
                break
            time.sleep(0.05)

        assert first_last_action_at

        final_payload = payload
        for _ in range(50):
            final_payload = client.get("/v1/diagnostics").json()
            if int(final_payload["memory_quality_tuning"]["ticks"]) >= 2:
                break
            time.sleep(0.05)

        assert int(final_payload["memory_quality_tuning"]["ticks"]) >= 2
        skipped_entries = [
            entry
            for entry in fake_memory.tuning.get("recent_actions", [])
            if isinstance(entry, dict) and str(entry.get("status", "")) == "cooldown_skipped"
        ]
        assert skipped_entries
        assert str(fake_memory.tuning.get("last_action_at", "") or "") == first_last_action_at


def test_gateway_diagnostics_memory_quality_cache_hit_refreshes_tuning_from_state(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={
            "heartbeat": {"enabled": False},
            "diagnostics": {"enabled": True, "require_auth": False},
            "autonomy": {"tuning_loop_enabled": False},
        },
        channels={},
    )
    app = create_app(cfg)
    memory = app.state.runtime.engine.memory
    calls = {"quality_update": 0}
    tuning_state = {
        "degrading_streak": 1,
        "last_action": "notify_operator",
        "last_action_at": "2026-03-05T10:00:00+00:00",
        "last_action_status": "ok",
    }

    def _analysis_stats() -> dict[str, object]:
        return {
            "semantic": {
                "enabled": True,
                "coverage_ratio": 0.5,
                "missing_records": 50,
                "total_records": 100,
            }
        }

    def _quality_update(*, retrieval_metrics, turn_stability_metrics, semantic_metrics, sampled_at):
        del retrieval_metrics, turn_stability_metrics, sampled_at
        calls["quality_update"] += 1
        return {
            "semantic": dict(semantic_metrics or {}),
            "drift": {"assessment": "stable"},
            "score": 90,
            "recommendations": [],
        }

    def _quality_snapshot() -> dict[str, object]:
        return {
            "version": 1,
            "updated_at": "",
            "baseline": {},
            "current": {},
            "history": [],
            "tuning": dict(tuning_state),
        }

    memory.analysis_stats = _analysis_stats
    memory.update_quality_state = _quality_update
    memory.quality_state_snapshot = _quality_snapshot

    with TestClient(app) as client:
        first_payload = client.get("/v1/diagnostics").json()
        first_tuning = first_payload["engine"]["memory_quality"]["tuning"]
        assert first_tuning["last_action_at"] == "2026-03-05T10:00:00+00:00"

        tuning_state["last_action"] = "memory_snapshot"
        tuning_state["last_action_at"] = "2026-03-05T10:30:00+00:00"
        tuning_state["last_action_status"] = "unsupported"

        second_payload = client.get("/v1/diagnostics").json()
        second_quality = second_payload["engine"]["memory_quality"]

        assert calls["quality_update"] == 1
        assert second_quality["tuning"]["last_action"] == "memory_snapshot"
        assert second_quality["tuning"]["last_action_at"] == "2026-03-05T10:30:00+00:00"
        assert second_quality["state"]["tuning"]["last_action"] == "memory_snapshot"
        assert second_quality["report"]["tuning"]["last_action"] == "memory_snapshot"


def test_gateway_tuning_loop_fail_soft_on_action_and_state_update_exceptions(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={
            "heartbeat": {"enabled": False},
            "diagnostics": {"enabled": True, "require_auth": False},
            "autonomy": {"tuning_loop_enabled": True},
        },
        channels={},
    )
    cfg.gateway.autonomy.tuning_loop_interval_s = 1
    app = create_app(cfg)
    app.state.runtime.engine.memory = _FakeTuningMemory(degrade=True, fail_update=True, fail_tuning_update=True)

    with TestClient(app) as client:
        time.sleep(0.2)
        payload = client.get("/v1/diagnostics").json()

        assert payload["memory_quality_tuning"]["enabled"] is True
        assert int(payload["memory_quality_tuning"]["error_count"]) >= 1
        assert isinstance(payload["memory_quality_tuning"]["last_error"], str)
        assert payload["memory_quality_tuning"]["last_error"]


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


def test_gateway_heartbeat_trigger_surfaces_wake_backpressure_from_coordinator(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={"heartbeat": {"enabled": True, "interval_s": 9999}},
        channels={},
    )
    app = create_app(cfg)
    submit_mock = AsyncMock(return_value=HeartbeatDecision(action="skip", reason="wake_backpressure"))
    app.state.runtime.autonomy_wake.submit = submit_mock

    with TestClient(app) as client:
        response = client.post("/v1/control/heartbeat/trigger")
        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is True
        assert payload["decision"]["action"] == "skip"
        assert payload["decision"]["reason"] == "wake_backpressure"

    submit_mock.assert_awaited()
