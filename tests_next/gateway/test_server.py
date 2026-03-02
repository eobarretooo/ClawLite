from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from clawlite.config.schema import AppConfig, SchedulerConfig
from clawlite.gateway.server import create_app
from clawlite.providers.base import LLMResult


class FakeProvider:
    async def complete(self, *, messages, tools):
        return LLMResult(text="pong", model="fake/test", tool_calls=[], metadata={})


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
