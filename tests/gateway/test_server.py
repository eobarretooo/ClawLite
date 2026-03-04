from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from loguru import logger
from starlette.websockets import WebSocketDisconnect

from clawlite.config.schema import AppConfig, SchedulerConfig
from clawlite.gateway.server import _run_heartbeat, create_app
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
        assert ok_alias.json() == payload

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
    assert "gateway.auth" in joined
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
        with client.websocket_connect("/v1/ws") as socket:
            socket.send_json({"session_id": "cli:ws", "text": "ping"})
            payload = socket.receive_json()
            assert payload["text"] == "pong"

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
        assert "channels" in payload
        assert "cron" in payload
        assert "heartbeat" in payload
        assert "engine" in payload
        assert "retrieval_metrics" in payload["engine"]
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
