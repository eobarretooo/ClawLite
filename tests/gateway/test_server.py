from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from clawlite.bus.events import OutboundEvent
from clawlite.config.schema import AppConfig, SchedulerConfig
from clawlite.gateway.server import _run_heartbeat, create_app
from clawlite.providers.base import LLMResult
from clawlite.scheduler.heartbeat import HeartbeatDecision


class FakeProvider:
    async def complete(self, *, messages, tools):
        return LLMResult(text="pong", model="fake/test", tool_calls=[], metadata={})

    def diagnostics(self):
        return {"requests": 1, "successes": 1}


class FailingProvider:
    def __init__(self, message: str) -> None:
        self.message = message

    async def complete(self, *, messages, tools):
        raise RuntimeError(self.message)


class ActionProvider:
    async def complete(self, *, messages, tools):
        return LLMResult(text='{"action":"validate_provider","args":{}}', model="fake/action", tool_calls=[], metadata={})

    def diagnostics(self):
        return {"requests": 1, "successes": 1}


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

        ok = client.get("/v1/status", headers={"Authorization": "Bearer secret-token"})
        assert ok.status_code == 200
        payload = ok.json()
        assert payload["ready"] is True
        assert payload["auth"]["posture"] == "strict"


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

        response = client.get("/v1/diagnostics", headers={"Authorization": "Bearer diag-token"})
        assert response.status_code == 200
        payload = response.json()
        assert payload["schema_version"] == "2026-03-02"
        assert "control_plane" in payload
        assert "queue" in payload
        assert "dead_letter_replayed" in payload["queue"]
        assert "dead_letter_replay_attempts" in payload["queue"]
        assert "channels" in payload
        assert "channels_delivery" in payload
        assert "total" in payload["channels_delivery"]
        assert "per_channel" in payload["channels_delivery"]
        assert "cron" in payload
        assert "heartbeat" in payload
        assert "supervisor" in payload
        assert "autonomy" in payload
        assert "autonomy_actions" in payload
        assert "ticks" in payload["supervisor"]
        assert "incident_count" in payload["supervisor"]
        assert "recovery_attempts" in payload["supervisor"]
        assert payload["supervisor"]["ticks"] >= 0
        assert "enabled" in payload["autonomy"]
        assert "run_attempts" in payload["autonomy"]
        assert "skipped_disabled" in payload["autonomy"]
        assert "totals" in payload["autonomy_actions"]
        assert "quality_blocked" in payload["autonomy_actions"]["totals"]
        assert "degraded_blocked" in payload["autonomy_actions"]["totals"]
        assert payload["environment"]["workspace_path"] == str(tmp_path / "workspace")
        assert "engine" in payload["environment"]
        assert "persistence" in payload["environment"]["engine"]
        assert "session_store" in payload["environment"]["engine"]
        assert "memory_store" in payload["environment"]["engine"]
        assert "session_recovery" in payload["environment"]["engine"]
        assert payload["environment"]["engine"]["provider"]["requests"] == 1

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


def test_gateway_dead_letter_replay_endpoint_auth_and_summary(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={
            "auth": {
                "mode": "required",
                "token": "replay-token",
                "allow_loopback_without_auth": False,
            },
            "heartbeat": {"enabled": False},
        },
        channels={},
    )
    app = create_app(cfg)
    asyncio.run(
        app.state.runtime.bus.publish_dead_letter(
            OutboundEvent(
                channel="fake",
                session_id="s1",
                target="u1",
                text="dead",
                dead_lettered=True,
                dead_letter_reason="send_failed",
            )
        )
    )

    with TestClient(app) as client:
        unauthorized = client.post("/v1/control/dead-letter/replay", json={"dry_run": True})
        assert unauthorized.status_code == 401

        replay = client.post(
            "/v1/control/dead-letter/replay",
            headers={"Authorization": "Bearer replay-token"},
            json={
                "limit": 10,
                "channel": "fake",
                "reason": "send_failed",
                "session_id": "s1",
                "dry_run": True,
            },
        )
        assert replay.status_code == 200
        payload = replay.json()
        assert payload["scanned"] == 1
        assert payload["matched"] == 1
        assert payload["replayed"] == 0
        assert payload["kept"] == 1
        assert payload["dropped"] == 0


def test_gateway_autonomy_trigger_endpoint_auth_and_forced_run(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={
            "auth": {
                "mode": "required",
                "token": "autonomy-token",
                "allow_loopback_without_auth": False,
            },
            "heartbeat": {"enabled": False},
            "autonomy": {"enabled": False},
        },
        channels={},
    )
    app = create_app(cfg)
    app.state.runtime.engine.provider = FakeProvider()

    with TestClient(app) as client:
        unauthorized = client.post("/v1/control/autonomy/trigger")
        assert unauthorized.status_code == 401

        forced = client.post(
            "/v1/control/autonomy/trigger",
            headers={"Authorization": "Bearer autonomy-token"},
            json={"force": True},
        )
        assert forced.status_code == 200
        payload = forced.json()
        assert payload["ok"] is True
        assert payload["forced"] is True
        assert payload["autonomy"]["enabled"] is False
        assert payload["autonomy"]["run_attempts"] >= 1
        assert "autonomy_actions" in payload
        assert "totals" in payload["autonomy_actions"]


def test_gateway_autonomy_trigger_executes_allowlisted_action_from_provider_text(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={
            "auth": {
                "mode": "required",
                "token": "autonomy-action-token",
                "allow_loopback_without_auth": False,
            },
            "heartbeat": {"enabled": False},
            "autonomy": {"enabled": False},
        },
        channels={},
    )
    app = create_app(cfg)
    app.state.runtime.engine.provider = ActionProvider()

    with TestClient(app) as client:
        response = client.post(
            "/v1/control/autonomy/trigger",
            headers={"Authorization": "Bearer autonomy-action-token"},
            json={"force": True},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is True
        assert payload["autonomy_actions"]["totals"]["executed"] >= 1

        audit = client.get(
            "/v1/control/autonomy/audit?limit=50",
            headers={"Authorization": "Bearer autonomy-action-token"},
        )
        assert audit.status_code == 200
        audit_payload = audit.json()
        assert audit_payload["ok"] is True
        assert audit_payload["count"] >= 1


def test_gateway_autonomy_audit_endpoint_auth_and_success_payload(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={
            "auth": {
                "mode": "required",
                "token": "autonomy-audit-token",
                "allow_loopback_without_auth": False,
            },
            "heartbeat": {"enabled": False},
            "autonomy": {"enabled": False},
        },
        channels={},
    )
    app = create_app(cfg)
    app.state.runtime.engine.provider = FakeProvider()

    with TestClient(app) as client:
        unauthorized = client.get("/v1/control/autonomy/audit")
        assert unauthorized.status_code == 401

        response = client.get(
            "/v1/control/autonomy/audit?limit=20",
            headers={"Authorization": "Bearer autonomy-audit-token"},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is True
        assert "path" in payload
        assert "count" in payload
        assert "entries" in payload
        assert isinstance(payload["entries"], list)


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
