from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from clawlite.config.schema import AppConfig, SchedulerConfig
from clawlite.gateway.server import create_app
from clawlite.providers.base import LLMResult


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
