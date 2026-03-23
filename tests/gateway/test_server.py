from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import threading
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from loguru import logger
from starlette.websockets import WebSocketDisconnect

import clawlite.gateway.runtime_builder as gateway_runtime_builder
import clawlite.gateway.server as gateway_server
from clawlite.bus.events import OutboundEvent
from clawlite.channels.base import BaseChannel, ChannelCapabilities
from clawlite.config.schema import AppConfig, SchedulerConfig
from clawlite.core.engine import ProviderChunk
from clawlite.core.memory import MemoryStore
from clawlite.core.memory_monitor import MemoryMonitor, MemorySuggestion
from clawlite.core.skills import SkillsLoader
from clawlite.core.subagent import SubagentManager, SubagentRun
from clawlite.gateway.dashboard_sessions import issue_dashboard_handoff
from clawlite.gateway.server import (
    _LATEST_MEMORY_ROUTE_CACHE,
    _latest_memory_route,
    _normalize_background_task,
    _route_cron_job,
    _run_heartbeat,
    _run_proactive_monitor,
    build_runtime,
    create_app,
)
from clawlite.providers.base import LLMResult
from clawlite.scheduler.heartbeat import HeartbeatDecision
from clawlite.utils import logging as logging_utils
from clawlite.workspace.loader import WorkspaceLoader


class FakeProvider:
    def get_default_model(self) -> str:
        return "fake/test"

    async def complete(self, *, messages, tools):
        return LLMResult(text="pong", model="fake/test", tool_calls=[], metadata={})


class SelfEvolutionProposalProvider:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def get_default_model(self) -> str:
        return "fake/self-evolution"

    async def complete(self, **kwargs):
        self.calls.append(dict(kwargs))
        return LLMResult(
            text="DESCRIPTION: implement target\n```python\ndef target():\n    return 42\n```\n",
            model="fake/self-evolution",
            tool_calls=[],
            metadata={},
        )


class AutonomyIdleProvider:
    def get_default_model(self) -> str:
        return "fake/autonomy"

    async def complete(self, *, messages, tools):
        del messages, tools
        return LLMResult(text="AUTONOMY_IDLE", model="fake/autonomy", tool_calls=[], metadata={})


class ReplayProvider:
    def __init__(self) -> None:
        self.calls = 0
        self.snapshots: list[list[dict[str, object]]] = []

    def get_default_model(self) -> str:
        return "fake/replay"

    async def complete(self, *, messages, tools):
        del tools
        self.calls += 1
        self.snapshots.append(messages)
        return LLMResult(text="replayed", model="fake/replay", tool_calls=[], metadata={})


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


class ProviderWithFailoverDiagnostics:
    async def complete(self, *, messages, tools):
        return LLMResult(text="pong", model="openai/gpt-4o-mini", tool_calls=[], metadata={})

    def diagnostics(self) -> dict[str, object]:
        return {
            "provider": "failover",
            "provider_name": "failover",
            "model": "openai/gpt-4o-mini",
            "transport": "openai_compatible",
            "counters": {
                "fallback_attempts": 2,
                "last_error_class": "rate_limit",
            },
            "candidates": [
                {
                    "role": "primary",
                    "model": "openai/gpt-4o-mini",
                    "in_cooldown": True,
                    "cooldown_remaining_s": 17.25,
                    "suppression_reason": "auth",
                },
                {
                    "role": "fallback",
                    "model": "groq/llama-3.1-8b-instant",
                    "in_cooldown": False,
                    "cooldown_remaining_s": 0.0,
                    "suppression_reason": "",
                },
            ],
        }

    def operator_clear_suppression(self, *, role: str = "", model: str = "") -> dict[str, object]:
        return {"ok": True, "cleared": 1, "role": role, "model": model}


def _normalized_diagnostics_engine_payload(engine_payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(engine_payload)

    skills_diag = dict(normalized.get("skills", {}) or {})
    watcher = dict(skills_diag.get("watcher", {}) or {})
    for key in (
        "ticks",
        "last_result",
        "last_tick_monotonic",
        "last_refresh_monotonic",
        "pending",
        "debounced",
    ):
        watcher.pop(key, None)
    skills_diag["watcher"] = watcher
    normalized["skills"] = skills_diag

    memory_analysis = dict(normalized.get("memory_analysis", {}) or {})
    if memory_analysis:
        confidence = dict(memory_analysis.get("confidence", {}) or {})
        counts = dict(memory_analysis.get("counts", {}) or {})
        recent = dict(memory_analysis.get("recent", {}) or {})
        semantic = dict(memory_analysis.get("semantic", {}) or {})
        normalized["memory_analysis"] = {
            "available": bool(memory_analysis.get("available", False)),
            "keys": sorted(memory_analysis.keys()),
            "confidence_keys": sorted(confidence.keys()),
            "counts_keys": sorted(counts.keys()),
            "recent_keys": sorted(recent.keys()),
            "semantic_keys": sorted(semantic.keys()),
            "reasoning_layers_type": type(memory_analysis.get("reasoning_layers", {})).__name__,
            "categories_type": type(memory_analysis.get("categories", {})).__name__,
            "top_sources_type": type(memory_analysis.get("top_sources", [])).__name__,
        }

    memory_integration = dict(normalized.get("memory_integration", {}) or {})
    if memory_integration:
        policies = dict(memory_integration.get("policies", {}) or {})
        quality = dict(memory_integration.get("quality", {}) or {})
        normalized["memory_integration"] = {
            "available": bool(memory_integration.get("available", False)),
            "mode": str(memory_integration.get("mode", "")),
            "keys": sorted(memory_integration.keys()),
            "policy_keys": sorted(policies.keys()),
            "quality_keys": sorted(quality.keys()),
        }

    memory_quality = dict(normalized.get("memory_quality", {}) or {})
    if memory_quality:
        report = dict(memory_quality.get("report", {}) or {})
        reasoning_layers = dict(report.get("reasoning_layers", {}) or {})
        state = dict(memory_quality.get("state", {}) or {})
        tuning = dict(memory_quality.get("tuning", {}) or {})
        normalized["memory_quality"] = {
            "available": bool(memory_quality.get("available", False)),
            "updated": bool(memory_quality.get("updated", False)),
            "error_type": type(memory_quality.get("error")).__name__,
            "keys": sorted(memory_quality.keys()),
            "report_keys": sorted(report.keys()),
            "report_reasoning_layer_keys": sorted(reasoning_layers.keys()),
            "state_keys": sorted(state.keys()),
            "tuning_keys": sorted(tuning.keys()),
        }

    return normalized


class RecoveringGatewayChannel(BaseChannel):
    starts = 0

    def __init__(self, *, config: dict[str, object], on_message=None) -> None:
        super().__init__(name="fake", config=config, on_message=on_message)
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        type(self).starts += 1
        self._running = True
        if type(self).starts == 1:
            async def _crash() -> None:
                raise RuntimeError("gateway channel worker crashed")

            self._task = asyncio.create_task(_crash())
            await asyncio.sleep(0)
            return
        self._task = asyncio.create_task(asyncio.sleep(3600))

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
        self._task = None

    async def send(self, *, target: str, text: str, metadata=None) -> str:
        del target, text, metadata
        return "ok"


class FakeSelfEvolutionEngine:
    def __init__(
        self,
        *,
        enabled: bool = True,
        cooldown_s: float = 9999.0,
        background_enabled: bool | None = None,
        enabled_for_sessions: list[str] | None = None,
        autonomy_session_id: str = "autonomy:system",
    ) -> None:
        self.enabled = enabled
        self.cooldown_s = float(cooldown_s)
        self._background_enabled = bool(enabled if background_enabled is None else background_enabled)
        self.enabled_for_sessions = list(enabled_for_sessions or [])
        self.autonomy_session_id = str(autonomy_session_id or "autonomy:system")
        self._run_count = 0
        self._committed_count = 0
        self._dry_run_count = 0
        self._last_outcome = ""
        self._last_error = ""
        self.log = SimpleNamespace(recent=lambda _n=10: [{"outcome": self._last_outcome}] if self._run_count else [])

    def background_enabled(self) -> bool:
        return self._background_enabled

    async def run_once(self, *, force: bool = False, dry_run: bool = False) -> dict[str, object]:
        self._run_count += 1
        if dry_run:
            self._dry_run_count += 1
            self._last_outcome = "dry_run"
        else:
            self._last_outcome = "forced" if force else "no_gaps"
        self._last_error = ""
        return self.status()

    def status(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "background_enabled": self._background_enabled,
            "activation_mode": "global" if self.enabled and self._background_enabled else "session_canary",
            "activation_reason": "" if self._background_enabled else "autonomy_session_not_allowlisted",
            "enabled_for_sessions": list(self.enabled_for_sessions),
            "autonomy_session_id": self.autonomy_session_id,
            "run_count": self._run_count,
            "committed_count": self._committed_count,
            "dry_run_count": self._dry_run_count,
            "last_outcome": self._last_outcome,
            "last_error": self._last_error,
            "cooldown_remaining_s": 0.0,
            "locked": False,
        }


class _FakeTuningMemory:
    def __init__(
        self,
        *,
        degrade: bool = True,
        fail_update: bool = False,
        fail_tuning_update: bool = False,
        weakest_layer: str = "",
        degrade_score: int = 20,
    ) -> None:
        self.degrade = degrade
        self.fail_update = fail_update
        self.fail_tuning_update = fail_tuning_update
        self.weakest_layer = str(weakest_layer or "").strip()
        self.degrade_score = int(degrade_score)
        self.snapshot_calls = 0
        self.last_snapshot_tag = ""
        self.compact_calls = 0
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
        payload = {
            "sampled_at": sampled_at,
            "score": self.degrade_score if self.degrade else 88,
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
        if self.weakest_layer:
            payload["reasoning_layers"] = {
                "weakest_layer": self.weakest_layer,
                "distribution": {self.weakest_layer: 1},
                "confidence": {"average": 0.5},
            }
        return payload

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
        self.last_snapshot_tag = str(tag or "")
        self.snapshot_calls += 1
        return f"v{self.snapshot_calls}"

    async def compact(self) -> dict[str, object]:
        self.compact_calls += 1
        return {
            "expired_records": 2,
            "decayed_records": 3,
            "consolidated_records": 4,
            "consolidated_categories": {"context": 4},
        }


def _assert_connect_challenge(socket) -> dict[str, object]:
    payload = socket.receive_json()
    assert payload["type"] == "event"
    assert payload["event"] == "connect.challenge"
    assert isinstance(payload["params"]["nonce"], str) and payload["params"]["nonce"]
    assert isinstance(payload["params"]["issued_at"], str) and payload["params"]["issued_at"]
    assert isinstance(payload["params"]["connection_id"], str) and payload["params"]["connection_id"].startswith("ws-")
    return payload


def test_gateway_server_import_has_no_runtime_side_effects() -> None:
    server_path = Path(__file__).resolve().parents[2] / "clawlite" / "gateway" / "server.py"
    module_name = f"_test_gateway_server_{uuid.uuid4().hex}"

    with patch("clawlite.config.loader.load_config", side_effect=RuntimeError("load_config_called")):
        with patch("clawlite.utils.logging.setup_logging", side_effect=RuntimeError("setup_logging_called")):
            spec = importlib.util.spec_from_file_location(module_name, server_path)
            assert spec is not None and spec.loader is not None
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

    assert hasattr(module, "create_app")
    assert hasattr(module, "app")
    sys.modules.pop(module_name, None)


def test_latest_memory_route_prefers_history_tail_and_skips_full_scan(tmp_path: Path) -> None:
    _LATEST_MEMORY_ROUTE_CACHE.clear()
    history_path = tmp_path / "memory.jsonl"
    history_path.write_text(
        "\n".join(
            [
                json.dumps({"source": "session:cli:profile", "created_at": "2026-03-01T00:00:00+00:00"}),
                json.dumps({"source": "session:telegram:chat42", "created_at": "2026-03-02T00:00:00+00:00"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    class _Memory:
        def __init__(self, path: Path) -> None:
            self.history_path = path

        def all(self):
            raise AssertionError("full_scan_should_not_run")

    route = asyncio.run(_latest_memory_route(_Memory(history_path)))
    assert route == ("telegram", "chat42")


def test_latest_memory_route_caches_default_route_without_full_scan(tmp_path: Path) -> None:
    del tmp_path
    _LATEST_MEMORY_ROUTE_CACHE.clear()

    class _Memory:
        def __init__(self) -> None:
            self.calls = 0

        def all(self):
            self.calls += 1
            raise AssertionError("full_scan_should_not_run")

    memory = _Memory()
    first = asyncio.run(_latest_memory_route(memory))
    second = asyncio.run(_latest_memory_route(memory))

    assert first == ("cli", "profile")
    assert second == ("cli", "profile")
    assert memory.calls == 0


def test_latest_memory_route_prefers_telegram_when_requested(tmp_path: Path) -> None:
    _LATEST_MEMORY_ROUTE_CACHE.clear()
    history_path = tmp_path / "memory.jsonl"
    history_path.write_text(
        "\n".join(
            [
                json.dumps({"source": "session:telegram:chat42", "created_at": "2026-03-01T00:00:00+00:00"}),
                json.dumps({"source": "session:cli:profile", "created_at": "2026-03-02T00:00:00+00:00"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    class _Memory:
        def __init__(self, path: Path) -> None:
            self.history_path = path

    default_route = asyncio.run(_latest_memory_route(_Memory(history_path)))
    preferred_route = asyncio.run(_latest_memory_route(_Memory(history_path), preferred_channel="telegram"))

    assert default_route == ("cli", "profile")
    assert preferred_route == ("telegram", "chat42")


def test_normalize_background_task_treats_done_and_running_tasks_correctly() -> None:
    async def _scenario() -> None:
        done_task = asyncio.create_task(asyncio.sleep(0))
        await done_task

        normalized_done, state_done = await _normalize_background_task(done_task)
        assert normalized_done is None
        assert state_done == "done"

        running_task = asyncio.create_task(asyncio.sleep(10))
        normalized_running, state_running = await _normalize_background_task(running_task)
        assert normalized_running is running_task
        assert state_running == "running"
        running_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await running_task

    asyncio.run(_scenario())


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
        assert isinstance(health.headers.get("X-Request-ID", ""), str) and health.headers["X-Request-ID"]
        chat = client.post("/v1/chat", json={"session_id": "cli:1", "text": "ping"})
        assert chat.status_code == 200
        assert isinstance(chat.headers.get("X-Request-ID", ""), str) and chat.headers["X-Request-ID"]
        assert chat.json()["text"] == "pong"
        alias = client.post("/api/message", json={"session_id": "cli:1", "text": "ping"})
        assert alias.status_code == 200
        assert isinstance(alias.headers.get("X-Request-ID", ""), str) and alias.headers["X-Request-ID"]
        assert alias.json()["text"] == "pong"


def test_gateway_http_request_id_preserves_safe_header(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)

    with TestClient(app) as client:
        response = client.get("/health", headers={"X-Request-ID": "req-health-123"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "req-health-123"


def test_gateway_http_request_id_replaces_invalid_header(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)

    with TestClient(app) as client:
        response = client.get("/health", headers={"X-Request-ID": "bad request id"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] != "bad request id"
    assert response.headers["X-Request-ID"].startswith("req-")


def test_gateway_http_unhandled_error_includes_request_id(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)

    @app.get("/boom")
    async def _boom() -> dict[str, object]:
        raise RuntimeError("boom")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom", headers={"X-Request-ID": "req-boom-1"})

    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == "req-boom-1"
    assert response.json() == {
        "error": "internal_server_error",
        "status": 500,
        "code": "internal_server_error",
        "request_id": "req-boom-1",
    }


def test_gateway_chat_endpoint_forwards_optional_context(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)
    seen: list[dict[str, Any]] = []

    async def _capture_run(
        *,
        session_id: str,
        user_text: str,
        channel: str | None = None,
        chat_id: str | None = None,
        runtime_metadata: dict[str, Any] | None = None,
    ):
        seen.append(
            {
                "session_id": session_id,
                "user_text": user_text,
                "channel": channel,
                "chat_id": chat_id,
                "runtime_metadata": runtime_metadata,
            }
        )
        return SimpleNamespace(text="pong", model="fake/test")

    app.state.runtime.engine.run = _capture_run

    with TestClient(app) as client:
        chat = client.post(
            "/v1/chat",
            json={
                "session_id": "cli:1",
                "text": "ping",
                "channel": "telegram",
                "chat_id": "42",
                "runtime_metadata": {"reply_to_message_id": "7"},
            },
        )
        assert chat.status_code == 200
        assert chat.json()["text"] == "pong"

    forwarded = [row for row in seen if row["session_id"] == "cli:1"]
    assert forwarded == [
        {
            "session_id": "cli:1",
            "user_text": "ping",
            "channel": "telegram",
            "chat_id": "42",
            "runtime_metadata": {"reply_to_message_id": "7"},
        }
    ]


def test_gateway_chat_rate_limit_blocks_repeated_http_chat_requests(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={
            "rate_limit": {
                "window_s": 60,
                "chat_requests_per_window": 1,
                "ws_chat_requests_per_window": 0,
            }
        },
        channels={},
    )
    app = create_app(cfg)
    app.state.runtime.engine.provider = FakeProvider()

    with TestClient(app) as client:
        first = client.post("/v1/chat", json={"session_id": "cli:1", "text": "ping"})
        assert first.status_code == 200

        second = client.post("/v1/chat", json={"session_id": "cli:1", "text": "ping again"})
        assert second.status_code == 429
        payload = second.json()
        assert payload["error"] == "gateway_rate_limited"
        assert payload["code"] == "gateway_rate_limited"
        assert payload["retry_after_s"] > 0
        assert second.headers["Retry-After"] == "60"

        diagnostics = client.get("/v1/diagnostics")
        assert diagnostics.status_code == 200
        http_payload = diagnostics.json()["http"]
        assert http_payload["last_error_request_id"] == second.headers["X-Request-ID"]
        assert http_payload["last_error_method"] == "POST"
        assert http_payload["last_error_path"] == "/v1/chat"
        assert http_payload["last_error_status"] == 429
        assert http_payload["last_error_code"] == "gateway_rate_limited"
        assert http_payload["last_error_message"] == "gateway chat rate limit exceeded; retry shortly"


def test_gateway_chat_rate_limit_shares_bucket_with_api_message_alias(tmp_path: Path) -> None:
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
            "rate_limit": {
                "window_s": 60,
                "chat_requests_per_window": 1,
                "ws_chat_requests_per_window": 0,
            },
            "heartbeat": {"enabled": False},
        },
        channels={},
    )
    app = create_app(cfg)
    app.state.runtime.engine.provider = FakeProvider()

    with TestClient(app) as client:
        headers = {"Authorization": "Bearer secret-token"}
        first = client.post("/v1/chat", headers=headers, json={"session_id": "cli:1", "text": "ping"})
        assert first.status_code == 200

        second = client.post("/api/message", headers=headers, json={"session_id": "cli:1", "text": "ping again"})
        assert second.status_code == 429
        assert second.json()["error"] == "gateway_rate_limited"


def test_gateway_chat_endpoint_timeout_returns_provider_style_code(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={"heartbeat": {"enabled": False}},
        channels={},
    )
    app = create_app(cfg)

    async def _slow_run(*, session_id: str, user_text: str):
        del session_id, user_text
        await asyncio.sleep(0.05)
        return SimpleNamespace(text="late", model="fake/test")

    app.state.runtime.engine.run = _slow_run

    with patch.object(gateway_server, "GATEWAY_CHAT_WS_ENGINE_TIMEOUT_S", new=0.01):
        with TestClient(app) as client:
            chat = client.post("/v1/chat", json={"session_id": "cli:1", "text": "ping"})

    assert chat.status_code == 504
    payload = chat.json()
    assert payload["error"] == "engine_run_timeout"
    assert payload["code"] == "engine_run_timeout"


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

            with patch.object(gateway_server.asyncio, "wait_for", new=_timeout_wait_for):
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


def test_gateway_whatsapp_webhook_requires_secret_and_dispatches(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={
            "whatsapp": {
                "enabled": True,
                "bridge_url": "http://localhost:3001",
                "webhook_secret": "secret-wa-1",
            }
        },
    )
    app = create_app(cfg)

    with TestClient(app) as client:
        unauthorized = client.post("/api/webhooks/whatsapp", json={"messageId": "wa-1"})
        assert unauthorized.status_code == 401
        assert unauthorized.json()["code"] == "whatsapp_webhook_secret_invalid"

        channel = app.state.runtime.channels.get_channel("whatsapp")
        assert channel is not None
        webhook_handler = AsyncMock(return_value=True)
        channel.receive_hook = webhook_handler

        authorized = client.post(
            "/api/webhooks/whatsapp",
            json={"from": "5511999999999@c.us", "body": "hello", "messageId": "wa-2"},
            headers={"Authorization": "Bearer secret-wa-1"},
        )
        assert authorized.status_code == 200
        assert authorized.json() == {"ok": True, "processed": True}
        webhook_handler.assert_awaited_once_with(
            {"from": "5511999999999@c.us", "body": "hello", "messageId": "wa-2"}
        )


def test_gateway_whatsapp_webhook_rejects_non_dict_payload(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={
            "whatsapp": {
                "enabled": True,
                "bridge_url": "http://localhost:3001",
                "webhook_secret": "secret-wa-1",
            }
        },
    )
    app = create_app(cfg)

    with TestClient(app) as client:
        response = client.post(
            "/api/webhooks/whatsapp",
            json=["not", "a", "dict"],
            headers={"X-Webhook-Secret": "secret-wa-1"},
        )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"] == "whatsapp_webhook_payload_invalid"
    assert payload["code"] == "whatsapp_webhook_payload_invalid"


def test_gateway_startup_completes_bootstrap_lifecycle_without_user_turn(tmp_path: Path) -> None:
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
        assert not bootstrap_file.exists()

        status_payload = client.get("/v1/status").json()
        bootstrap_component = status_payload["components"]["bootstrap"]
        assert bootstrap_component["pending"] is False
        assert bootstrap_component["last_status"] == "completed"
        assert bootstrap_component["last_session_id"] == "bootstrap:system"

        diagnostics_payload = client.get("/v1/diagnostics").json()
        assert diagnostics_payload["bootstrap"]["pending"] is False
        assert diagnostics_payload["bootstrap"]["last_status"] == "completed"
        assert diagnostics_payload["bootstrap"]["last_session_id"] == "bootstrap:system"


def test_gateway_hatch_session_completes_bootstrap_after_startup_failure(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)
    app.state.runtime.engine.provider = FailingProvider("bootstrap_boom")
    bootstrap_file = tmp_path / "workspace" / "BOOTSTRAP.md"

    with TestClient(app) as client:
        assert bootstrap_file.exists()

        diagnostics_payload = client.get("/v1/diagnostics").json()
        assert diagnostics_payload["bootstrap"]["pending"] is True
        assert diagnostics_payload["bootstrap"]["last_status"] == "error"
        assert diagnostics_payload["bootstrap"]["last_error"] == "bootstrap_run_unsatisfied:engine/fallback"

        app.state.runtime.engine.provider = FakeProvider()
        chat = client.post("/v1/chat", json={"session_id": "hatch:operator", "text": "Wake up, my friend!"})
        assert chat.status_code == 200
        assert chat.json()["text"] == "pong"

        assert not bootstrap_file.exists()

        diagnostics_payload = client.get("/v1/diagnostics").json()
        assert diagnostics_payload["bootstrap"]["pending"] is False
        assert diagnostics_payload["bootstrap"]["last_status"] == "completed"
        assert diagnostics_payload["bootstrap"]["last_session_id"] == "hatch:operator"


def test_gateway_non_hatch_session_does_not_complete_bootstrap_after_startup_failure(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)
    app.state.runtime.engine.provider = FailingProvider("bootstrap_boom")
    bootstrap_file = tmp_path / "workspace" / "BOOTSTRAP.md"

    with TestClient(app) as client:
        assert bootstrap_file.exists()

        diagnostics_payload = client.get("/v1/diagnostics").json()
        assert diagnostics_payload["bootstrap"]["pending"] is True

        app.state.runtime.engine.provider = FakeProvider()
        chat = client.post("/v1/chat", json={"session_id": "cli:bootstrap", "text": "ping"})
        assert chat.status_code == 200
        assert chat.json()["text"] == "pong"
        assert bootstrap_file.exists()

        diagnostics_payload = client.get("/v1/diagnostics").json()
        assert diagnostics_payload["bootstrap"]["pending"] is True
        assert diagnostics_payload["bootstrap"]["last_status"] == "error"


def test_gateway_internal_sessions_do_not_complete_bootstrap(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)
    app.state.runtime.engine.provider = FailingProvider("bootstrap_boom")
    bootstrap_file = tmp_path / "workspace" / "BOOTSTRAP.md"

    with TestClient(app) as client:
        assert bootstrap_file.exists()
        app.state.runtime.engine.provider = FakeProvider()
        chat = client.post("/v1/chat", json={"session_id": "heartbeat:manual", "text": "ping"})
        assert chat.status_code == 200
        assert bootstrap_file.exists()

        payload = client.get("/v1/diagnostics").json()
        assert payload["bootstrap"]["pending"] is True
        assert payload["bootstrap"]["last_status"] == "error"


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


def test_build_runtime_passes_config_path_to_skills_loader(tmp_path: Path, monkeypatch) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    config_path = tmp_path / "custom-config.json"
    config_path.write_text("{}", encoding="utf-8")
    builtin_root = tmp_path / "builtin"
    builtin_root.mkdir(parents=True, exist_ok=True)
    captured: dict[str, object] = {}

    def _loader_factory(*, state_path=None, config_path=None, config_profile=None):
        captured["state_path"] = state_path
        captured["config_path"] = config_path
        captured["config_profile"] = config_profile
        return SkillsLoader(
            builtin_root=builtin_root,
            state_path=state_path,
            config_path=config_path,
            config_profile=config_profile,
        )

    monkeypatch.setattr(gateway_runtime_builder, "SkillsLoader", _loader_factory)

    runtime = build_runtime(cfg, config_path=str(config_path), config_profile="prod")

    assert runtime.skills_loader is not None
    assert captured["config_path"] == str(config_path)
    assert captured["config_profile"] == "prod"
    assert Path(str(captured["state_path"])) == (tmp_path / "state" / "skills-state.json")


def test_create_app_prefers_explicit_config_profile_over_passed_config(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace-file"),
                "state_path": str(tmp_path / "state-file"),
                "gateway": {"port": 1111},
                "channels": {},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "config.prod.json").write_text(
        json.dumps(
            {
                "gateway": {"port": 2222},
            }
        ),
        encoding="utf-8",
    )
    base_cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace-base"),
        state_path=str(tmp_path / "state-base"),
        gateway={"port": 1111},
        channels={},
    )

    app = create_app(base_cfg, config_path=str(config_path), config_profile="prod")

    assert int(app.state.runtime.config.gateway.port) == 2222
    assert app.state.runtime.config.workspace_path == str(tmp_path / "workspace-file")


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


def test_gateway_runtime_rejects_pgvector_backend_with_probe_details(tmp_path: Path, monkeypatch) -> None:
    class _Backend:
        name = "pgvector"

        def is_supported(self) -> bool:
            return False

        def diagnostics(self) -> dict[str, object]:
            return {"last_error": "pgvector extension 'vector' is unavailable"}

    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        agents={"defaults": {"memory": {"backend": "pgvector", "pgvector_url": "postgresql://memory-db"}}},
        channels={},
    )
    monkeypatch.setattr("clawlite.gateway.runtime_builder.resolve_memory_backend", lambda **kwargs: _Backend())

    with pytest.raises(RuntimeError, match="vector' is unavailable"):
        build_runtime(cfg)


def test_gateway_runtime_rejects_local_provider_when_startup_probe_fails(tmp_path: Path, monkeypatch) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        provider={"model": "openai/llama3.2", "litellm_base_url": "http://127.0.0.1:11434"},
        providers={"openai": {"api_base": "http://127.0.0.1:11434"}},
        channels={},
    )
    monkeypatch.setattr(
        "clawlite.gateway.runtime_builder.probe_local_provider_runtime",
        lambda *, model, base_url, timeout_s=2.0: {
            "checked": True,
            "ok": False,
            "runtime": "ollama",
            "model": "llama3.2",
            "base_url": base_url,
            "error": "provider_config_error:ollama_unreachable:http://127.0.0.1:11434",
            "detail": "connection_refused",
            "available_models": [],
        },
    )

    with pytest.raises(RuntimeError, match="provider_config_error:ollama_unreachable"):
        build_runtime(cfg)


def test_provider_config_forwards_failover_and_reliability_settings() -> None:
    cfg = AppConfig(
        provider={
            "model": "openai/llama3.2",
            "fallback_model": "anthropic/claude-3-5-haiku-latest",
            "retry_max_attempts": 5,
            "retry_initial_backoff_s": 1.25,
            "retry_max_backoff_s": 9.0,
            "retry_jitter_s": 0.0,
            "circuit_failure_threshold": 7,
            "circuit_cooldown_s": 0.0,
        },
        providers={
            "openai": {"api_base": "http://127.0.0.1:11434"},
            "anthropic": {"api_key": "sk-ant-test"},
        },
        channels={},
    )

    payload = gateway_server._provider_config(cfg)

    assert payload["fallback_model"] == "anthropic/claude-3-5-haiku-latest"
    assert payload["retry_max_attempts"] == 5
    assert payload["retry_initial_backoff_s"] == 1.25
    assert payload["retry_max_backoff_s"] == 9.0
    assert payload["retry_jitter_s"] == 0.0
    assert payload["circuit_failure_threshold"] == 7
    assert payload["circuit_cooldown_s"] == 0.0


def test_gateway_runtime_allows_remote_fallback_when_local_primary_probe_fails(tmp_path: Path, monkeypatch) -> None:
    class _CandidateProvider:
        def __init__(self, *, model: str, base_url: str = "") -> None:
            self._model = model
            self.base_url = base_url

        def get_default_model(self) -> str:
            return self._model

        async def complete(self, *, messages, tools):
            del messages, tools
            return LLMResult(text="ok", model=self._model, tool_calls=[], metadata={})

    class _FailoverProvider:
        def __init__(self) -> None:
            local = _CandidateProvider(model="openai/llama3.2", base_url="http://127.0.0.1:11434/v1")
            remote = _CandidateProvider(model="anthropic/claude-3-5-haiku-latest", base_url="https://api.anthropic.com")
            self._candidates = [
                SimpleNamespace(provider=local, model=local.get_default_model()),
                SimpleNamespace(provider=remote, model=remote.get_default_model()),
            ]

        def get_default_model(self) -> str:
            return str(self._candidates[0].model)

        async def complete(self, *, messages, tools):
            del messages, tools
            return LLMResult(text="ok", model=self.get_default_model(), tool_calls=[], metadata={})

    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        provider={"model": "openai/llama3.2", "fallback_model": "anthropic/claude-3-5-haiku-latest"},
        providers={
            "openai": {"api_base": "http://127.0.0.1:11434/v1"},
            "anthropic": {"api_key": "sk-ant-test"},
        },
        channels={},
    )
    failover_provider = _FailoverProvider()
    probe_calls: list[tuple[str, str]] = []

    monkeypatch.setattr(gateway_runtime_builder, "build_provider", lambda config: failover_provider)
    monkeypatch.setattr(
        gateway_runtime_builder,
        "probe_local_provider_runtime",
        lambda *, model, base_url, timeout_s=2.0: (
            probe_calls.append((model, base_url))
            or {
                "checked": True,
                "ok": False,
                "runtime": "ollama",
                "model": model,
                "base_url": base_url,
                "error": f"provider_config_error:ollama_unreachable:{base_url}",
                "detail": "connection_refused",
                "available_models": [],
            }
        ),
    )

    runtime = build_runtime(cfg)

    assert runtime.engine.provider is failover_provider
    assert probe_calls == [("openai/llama3.2", "http://127.0.0.1:11434/v1")]


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


def test_build_runtime_passes_session_retention_ttl(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=120),
        agents={"defaults": {"session_retention_ttl_s": 7200}},
        channels={},
    )
    runtime = build_runtime(cfg)

    assert getattr(runtime.engine.sessions, "session_retention_ttl_s", None) == 7200


def test_build_runtime_uses_redis_bus_when_configured(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=120),
        bus={"backend": "redis", "redis_url": "redis://localhost:6379/9", "redis_prefix": "clawlite:test"},
        channels={},
    )
    runtime = build_runtime(cfg)

    assert runtime.bus.__class__.__name__ == "RedisMessageQueue"
    stats = runtime.bus.stats()
    assert stats["backend"] == "redis"
    assert stats["redis_url"] == "redis://localhost:6379/9"
    assert stats["redis_prefix"] == "clawlite:test"


def test_build_runtime_exposes_observability_status(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        gateway_runtime_builder,
        "configure_observability",
        lambda **kwargs: {
            "enabled": bool(kwargs.get("enabled")),
            "configured": False,
            "endpoint": str(kwargs.get("endpoint", "")),
            "service_name": str(kwargs.get("service_name", "")),
            "service_namespace": str(kwargs.get("service_namespace", "")),
            "last_error": "otel-missing",
        },
    )
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=120),
        observability={
            "enabled": True,
            "otlp_endpoint": "http://otel:4317",
            "service_name": "clawlite-dev",
            "service_namespace": "local",
        },
        channels={},
    )
    runtime = build_runtime(cfg)

    assert runtime.telemetry == {
        "enabled": True,
        "configured": False,
        "endpoint": "http://otel:4317",
        "service_name": "clawlite-dev",
        "service_namespace": "local",
        "last_error": "otel-missing",
    }


def test_gateway_lifespan_connects_and_closes_redis_bus(tmp_path: Path, monkeypatch) -> None:
    connect_calls: list[str] = []
    close_calls: list[str] = []

    async def _connect(self) -> None:
        connect_calls.append(str(getattr(self, "_redis_url", "")))

    async def _close(self) -> None:
        close_calls.append(str(getattr(self, "_redis_url", "")))

    monkeypatch.setattr(gateway_runtime_builder.RedisMessageQueue, "connect", _connect)
    monkeypatch.setattr(gateway_runtime_builder.RedisMessageQueue, "close", _close)

    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        bus={"backend": "redis", "redis_url": "redis://localhost:6379/7"},
        gateway={"heartbeat": {"enabled": False}},
        channels={},
    )
    app = create_app(cfg)

    with TestClient(app):
        assert app.state.runtime.bus.__class__.__name__ == "RedisMessageQueue"

    assert connect_calls == ["redis://localhost:6379/7"]
    assert close_calls == ["redis://localhost:6379/7"]


def test_build_runtime_passes_cron_concurrency_limit(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999, cron_max_concurrent_jobs=5),
        channels={},
    )
    runtime = build_runtime(cfg)

    assert runtime.cron.status()["concurrency_limit"] == 5


def test_build_runtime_passes_cron_completed_job_retention(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999, cron_completed_job_retention_seconds=123),
        channels={},
    )
    runtime = build_runtime(cfg)

    assert runtime.cron.status()["completed_job_retention_seconds"] == 123


def test_build_runtime_self_evolution_uses_provider_direct_completion(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    provider = SelfEvolutionProposalProvider()
    with patch.object(gateway_runtime_builder, "build_provider", return_value=provider):
        with patch.object(
            gateway_runtime_builder,
            "probe_local_provider_runtime",
            return_value={"checked": False, "ok": True},
        ):
            runtime = build_runtime(cfg)

    runtime.engine.run = AsyncMock(side_effect=AssertionError("engine.run_should_not_be_used"))
    result = asyncio.run(runtime.self_evolution._run_llm("patch this gap"))

    assert result.startswith("DESCRIPTION: implement target")
    assert len(provider.calls) == 1
    kwargs = provider.calls[0]
    assert kwargs["tools"] == []
    assert kwargs["temperature"] == 0.0
    assert kwargs["reasoning_effort"] == "low"
    assert kwargs["max_tokens"] == min(int(runtime.engine.max_tokens), 1200)
    messages = kwargs["messages"]
    assert isinstance(messages, list) and len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1] == {"role": "user", "content": "patch this gap"}


def test_build_runtime_self_evolution_notify_routes_operator_notice(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    provider = SelfEvolutionProposalProvider()
    with patch.object(gateway_runtime_builder, "build_provider", return_value=provider):
        with patch.object(
            gateway_runtime_builder,
            "probe_local_provider_runtime",
            return_value={"checked": False, "ok": True},
        ):
            runtime = build_runtime(cfg)

    history_path = Path(runtime.engine.memory.history_path)
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(
        json.dumps({"source": "session:telegram:chat42", "created_at": "2026-03-17T00:00:00+00:00"}) + "\n",
        encoding="utf-8",
    )
    runtime.channels.send = AsyncMock(return_value="msg-1")

    asyncio.run(
        runtime.self_evolution._notify_operator(
            "self-evolution finished a safe validation pass",
            status="committed",
            summary="self-evolution operator notice",
        )
    )

    runtime.channels.send.assert_awaited_once()
    send_kwargs = runtime.channels.send.await_args.kwargs
    assert send_kwargs["channel"] == "telegram"
    assert send_kwargs["target"] == "chat42"
    assert send_kwargs["text"] == "self-evolution finished a safe validation pass"
    assert send_kwargs["metadata"]["source"] == "self_evolution"
    assert send_kwargs["metadata"]["autonomy_notice"] is True
    assert send_kwargs["metadata"]["autonomy_action"] == "self_evolution"
    assert send_kwargs["metadata"]["autonomy_status"] == "committed"
    recent = runtime.autonomy_log.snapshot(limit=5)["recent"]
    assert any(
        str(row.get("action", "")) == "self_evolution_notice"
        and str(row.get("status", "")) == "sent"
        for row in recent
    )


def test_build_runtime_registers_openclaw_compatibility_alias_tools(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    runtime = build_runtime(cfg)

    schema_names = {row["name"] for row in runtime.engine.tools.schema()}
    assert {
        "agents_list",
        "read",
        "write",
        "edit",
        "memory_search",
        "memory_get",
        "apply_patch",
        "process",
        "sessions_list",
        "sessions_history",
        "sessions_send",
        "sessions_spawn",
        "subagents",
        "session_status",
    }.issubset(schema_names)


def test_gateway_startup_replays_resumable_subagents_after_restart(tmp_path: Path) -> None:
    state_root = tmp_path / "state" / "subagents"
    manager = SubagentManager(state_path=state_root)
    run = SubagentRun(
        run_id="run-replay-1",
        session_id="cli:owner",
        task="retry task",
        status="running",
        started_at="2026-03-06T10:00:00+00:00",
        updated_at="2026-03-06T10:00:00+00:00",
        metadata={
            "target_session_id": "cli:owner:subagent",
            "run_version": 1,
            "resume_attempts": 0,
            "resume_attempts_max": 2,
            "retry_budget_remaining": 2,
            "resume_token": "tok-1",
            "resumable": False,
            "last_status_reason": "spawned",
            "last_status_at": "2026-03-06T10:00:00+00:00",
            "continuation_context_applied": True,
            "continuation_digest_summary": "current:cli:owner:subagent -> blocker triaged",
            "continuation_digest_session_id": "cli:owner:subagent",
            "continuation_digest_count": 1,
        },
    )
    manager._runs[run.run_id] = run
    manager._save_state()

    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    provider = ReplayProvider()
    with patch.object(gateway_runtime_builder, "build_provider", return_value=provider):
        with patch.object(
            gateway_runtime_builder,
            "probe_local_provider_runtime",
            return_value={"checked": False, "ok": True},
        ):
            app = create_app(cfg)
            app.state.runtime.channels.send = AsyncMock(return_value="ok")
            with TestClient(app) as client:
                deadline = time.time() + 1.0
                rows = client.app.state.runtime.engine.subagents.list_runs(session_id="cli:owner")
                payload: dict[str, object] = {}
                while time.time() < deadline:
                    rows = client.app.state.runtime.engine.subagents.list_runs(session_id="cli:owner")
                    payload = client.get("/v1/diagnostics").json()
                    if rows and rows[0].status == "done" and app.state.runtime.channels.send.await_count >= 1:
                        break
                    time.sleep(0.01)

                assert rows
                assert rows[0].run_id == "run-replay-1"
                assert rows[0].status == "done"
                assert rows[0].result == "replayed"
                assert rows[0].metadata["last_status_reason"] == "done"
                assert rows[0].metadata["resume_attempts"] == 1
                assert rows[0].metadata["retry_budget_remaining"] == 1
                replay_component = client.app.state.lifecycle.components["subagent_replay"]
                assert replay_component["replayed"] == 1
                assert replay_component["replayed_groups"] == 1
                assert replay_component["failed"] == 0
                assert replay_component["failed_groups"] == 0
                assert replay_component["last_group_ids"] == ["run-replay-1"]
                assert provider.calls >= 1
                send_kwargs = next(
                    call.kwargs
                    for call in app.state.runtime.channels.send.await_args_list
                    if dict(call.kwargs.get("metadata", {})).get("autonomy_action") == "startup_replay"
                )
                assert send_kwargs["metadata"]["source"] == "subagents"
                assert send_kwargs["metadata"]["autonomy_notice"] is True
                assert send_kwargs["metadata"]["autonomy_action"] == "startup_replay"
                assert "startup subagent replay replayed=1 failed=0 groups=1" in str(send_kwargs["text"])
                autonomy_recent = payload["autonomy_log"]["recent"]
                assert any(
                    str(row.get("action", "")) == "startup_replay_notice"
                    and str(row.get("status", "")) == "sent"
                    for row in autonomy_recent
                )


def test_gateway_startup_replays_parallel_subagent_group_after_restart(tmp_path: Path) -> None:
    state_root = tmp_path / "state" / "subagents"
    manager = SubagentManager(state_path=state_root)
    group_id = "grp-replay-1"
    manager._runs["run-replay-a"] = SubagentRun(
        run_id="run-replay-a",
        session_id="cli:owner",
        task="retry task a",
        status="running",
        started_at="2026-03-06T10:00:00+00:00",
        updated_at="2026-03-06T10:00:00+00:00",
        metadata={
            "target_session_id": "cli:owner:subagent:1",
            "parallel_group_id": group_id,
            "parallel_group_index": 1,
            "parallel_group_size": 2,
            "run_version": 1,
            "resume_attempts": 0,
            "resume_attempts_max": 2,
            "retry_budget_remaining": 2,
            "resume_token": "tok-a",
            "resumable": False,
            "last_status_reason": "spawned",
            "last_status_at": "2026-03-06T10:00:00+00:00",
        },
    )
    manager._runs["run-replay-b"] = SubagentRun(
        run_id="run-replay-b",
        session_id="cli:owner",
        task="retry task b",
        status="running",
        started_at="2026-03-06T10:00:00+00:00",
        updated_at="2026-03-06T10:00:00+00:00",
        metadata={
            "target_session_id": "cli:owner:subagent:2",
            "parallel_group_id": group_id,
            "parallel_group_index": 2,
            "parallel_group_size": 2,
            "run_version": 1,
            "resume_attempts": 0,
            "resume_attempts_max": 2,
            "retry_budget_remaining": 2,
            "resume_token": "tok-b",
            "resumable": False,
            "last_status_reason": "spawned",
            "last_status_at": "2026-03-06T10:00:00+00:00",
        },
    )
    manager._save_state()

    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    provider = ReplayProvider()
    with patch.object(gateway_runtime_builder, "build_provider", return_value=provider):
        with patch.object(
            gateway_runtime_builder,
            "probe_local_provider_runtime",
            return_value={"checked": False, "ok": True},
        ):
            app = create_app(cfg)
            with TestClient(app) as client:
                deadline = time.time() + 1.0
                rows = client.app.state.runtime.engine.subagents.list_runs(session_id="cli:owner")
                while time.time() < deadline:
                    rows = client.app.state.runtime.engine.subagents.list_runs(session_id="cli:owner")
                    if rows and all(row.status == "done" for row in rows):
                        break
                    time.sleep(0.01)

                assert len(rows) == 2
                assert {row.status for row in rows} == {"done"}
                replay_component = client.app.state.lifecycle.components["subagent_replay"]
                assert replay_component["replayed"] == 2
                assert replay_component["replayed_groups"] == 1
                assert replay_component["failed"] == 0
                assert replay_component["failed_groups"] == 0
                assert replay_component["last_group_ids"] == [group_id]
                assert provider.calls >= 2


def test_gateway_startup_replays_orphaned_resumable_subagent_after_restart(tmp_path: Path) -> None:
    state_root = tmp_path / "state" / "subagents"
    manager = SubagentManager(state_path=state_root)
    run = SubagentRun(
        run_id="run-orphaned-1",
        session_id="cli:owner",
        task="retry orphaned task",
        status="interrupted",
        started_at="2026-03-06T10:00:00+00:00",
        updated_at="2026-03-06T10:00:30+00:00",
        metadata={
            "target_session_id": "cli:owner:subagent",
            "run_version": 1,
            "resume_attempts": 0,
            "resume_attempts_max": 2,
            "retry_budget_remaining": 2,
            "resume_token": "resume_orphaned_one",
            "resumable": True,
            "last_status_reason": "orphaned_queue_entry",
            "last_status_at": "2026-03-06T10:00:30+00:00",
        },
    )
    manager._runs[run.run_id] = run
    manager._save_state()

    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    provider = ReplayProvider()
    with patch.object(gateway_runtime_builder, "build_provider", return_value=provider):
        with patch.object(
            gateway_runtime_builder,
            "probe_local_provider_runtime",
            return_value={"checked": False, "ok": True},
        ):
            app = create_app(cfg)
            app.state.runtime.channels.send = AsyncMock(return_value="ok")
            with TestClient(app) as client:
                deadline = time.time() + 1.0
                rows = client.app.state.runtime.engine.subagents.list_runs(session_id="cli:owner")
                while time.time() < deadline:
                    rows = client.app.state.runtime.engine.subagents.list_runs(session_id="cli:owner")
                    if rows and rows[0].status == "done":
                        break
                    time.sleep(0.01)

                assert rows
                assert rows[0].run_id == "run-orphaned-1"
                assert rows[0].status == "done"
                assert rows[0].result == "replayed"
                assert rows[0].metadata["resume_attempts"] == 1
                assert rows[0].metadata["retry_budget_remaining"] == 1
                replay_component = client.app.state.lifecycle.components["subagent_replay"]
                assert replay_component["replayed"] == 1
                assert replay_component["failed"] == 0
                assert replay_component["last_group_ids"] == ["run-orphaned-1"]
                assert provider.calls >= 1


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


def test_gateway_skills_watcher_tracks_hot_reload_and_diagnostics(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    workspace_skill_dir = tmp_path / ".clawlite" / "workspace" / "skills" / "dynamic"
    workspace_skill_dir.mkdir(parents=True, exist_ok=True)
    skill_path = workspace_skill_dir / "SKILL.md"
    skill_path.write_text(
        "---\nname: dynamic\ndescription: first\nscript: web_search\n---\n",
        encoding="utf-8",
    )

    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={"heartbeat": {"enabled": False}, "diagnostics": {"enabled": True, "require_auth": False}},
        channels={},
    )
    app = create_app(cfg)
    app.state.runtime.skills_loader.watch_interval_s = 0.01
    app.state.runtime.skills_loader.watch_debounce_ms = 20

    with TestClient(app) as client:
        first = client.get("/v1/diagnostics").json()
        first_version = next(
            item["version"]
            for item in first["engine"]["skills"]["skills"]
            if item["name"] == "dynamic"
        )
        first_watcher_refresh = float(
            first["engine"]["skills"]["watcher"].get("last_refresh_monotonic", 0.0) or 0.0
        )
        assert first["control_plane"]["components"]["skills_watcher"]["running"] is True

        skill_path.write_text(
            "---\nname: dynamic\ndescription: second\nscript: web_search\n---\n",
            encoding="utf-8",
        )

        refreshed_version = first_version
        for _ in range(40):
            time.sleep(0.02)
            payload = client.get("/v1/diagnostics").json()
            refreshed_version = next(
                item["version"]
                for item in payload["engine"]["skills"]["skills"]
                if item["name"] == "dynamic"
            )
            if refreshed_version != first_version:
                assert payload["engine"]["skills"]["watcher"]["running"] is True
                assert payload["engine"]["skills"]["watcher"]["task_state"] == "running"
                refreshed_monotonic = float(
                    payload["engine"]["skills"]["watcher"].get(
                        "last_refresh_monotonic", 0.0
                    )
                    or 0.0
                )
                assert refreshed_monotonic >= first_watcher_refresh
                break
        else:
            raise AssertionError("skills watcher did not reload updated skill")

        assert refreshed_version != first_version


def test_gateway_diagnostics_includes_autonomy_wake_and_alias_parity(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={
            "heartbeat": {"enabled": False},
            "autonomy": {"enabled": True, "interval_s": 9999, "cooldown_s": 30, "timeout_s": 5},
            "diagnostics": {"enabled": True, "require_auth": False},
        },
        channels={},
    )
    app = create_app(cfg)
    app.state.runtime.engine.provider = AutonomyIdleProvider()

    with TestClient(app) as client:
        payload = client.get("/v1/diagnostics").json()
        alias_payload = client.get("/api/diagnostics").json()

        assert "autonomy" in payload
        assert "autonomy_wake" in payload
        assert "autonomy_log" in payload
        assert "supervisor" in payload
        assert payload["control_plane"]["components"]["autonomy"]["running"] is True
        assert set(payload["autonomy"].keys()) >= {
            "running",
            "worker_state",
            "enabled",
            "session_id",
            "ticks",
            "run_attempts",
            "run_success",
            "run_failures",
            "skipped_backlog",
            "skipped_cooldown",
            "skipped_provider_backoff",
            "skipped_no_progress",
            "skipped_disabled",
            "last_run_at",
            "last_result_excerpt",
            "last_error",
            "last_error_kind",
            "provider_backoff_reason",
            "provider_backoff_provider",
            "no_progress_reason",
            "no_progress_streak",
            "consecutive_error_count",
            "last_snapshot",
            "cooldown_remaining_s",
            "provider_backoff_remaining_s",
            "no_progress_backoff_remaining_s",
        }
        assert payload["autonomy"]["enabled"] is True
        assert payload["autonomy"]["running"] is True
        assert payload["autonomy"]["run_attempts"] >= 1
        assert payload["autonomy"]["run_success"] >= 1
        assert payload["autonomy"]["last_result_excerpt"] == "AUTONOMY_IDLE"
        assert payload["autonomy"]["last_snapshot"]["provider"]["state"] == "healthy"
        assert payload["autonomy"]["last_snapshot"]["provider"]["suppression_reason"] == ""
        assert set(payload["autonomy_wake"].keys()) >= {
            "running",
            "worker_state",
            "max_pending",
            "enqueued",
            "coalesced",
            "coalesced_priority_upgrades",
            "coalesced_payload_updates",
            "dropped_backpressure",
            "dropped_quota",
            "dropped_global_backpressure",
            "executed_ok",
            "executed_error",
            "queue_depth",
            "inflight",
            "max_queue_depth_seen",
            "restored",
            "journal_path",
            "journal_entries",
            "kind_limits",
            "kind_policies",
            "pending_by_kind",
            "last_error",
            "by_kind",
        }
        assert payload["autonomy_wake"]["journal_path"].endswith("autonomy-wake.json")
        assert payload["autonomy_wake"]["kind_policies"]["heartbeat"]["coalesce_mode"] == "replace_latest"
        assert payload["autonomy_wake"]["kind_limits"]["cron"] >= 1
        assert "channels_dispatcher" in payload
        assert payload["channels_dispatcher"]["enabled"] is True
        assert payload["channels_dispatcher"]["running"] is True
        assert payload["control_plane"]["components"]["channels_dispatcher"]["running"] is True
        assert "channels_recovery" in payload
        assert payload["channels_recovery"]["enabled"] is True
        assert payload["channels_recovery"]["running"] is True
        assert payload["control_plane"]["components"]["channels_recovery"]["running"] is True
        assert set(payload["autonomy_log"].keys()) >= {
            "enabled",
            "path",
            "max_entries",
            "total",
            "last_event_at",
            "counts",
            "recent",
        }
        assert set(payload["autonomy_log"]["counts"].keys()) >= {
            "by_source",
            "by_action",
            "by_status",
        }
        assert isinstance(payload["autonomy_log"]["recent"], list)
        assert set(payload["supervisor"].keys()) >= {
            "running",
            "worker_state",
            "interval_s",
            "cooldown_s",
            "ticks",
            "incident_count",
            "recovery_attempts",
            "recovery_success",
            "recovery_failures",
            "recovery_skipped_cooldown",
            "recovery_skipped_budget",
            "component_incidents",
            "component_recovery",
            "last_incident",
            "last_recovery_at",
            "last_error",
            "consecutive_error_count",
            "cooldown_active",
        }
        assert payload["supervisor"]["component_recovery"]["autonomy"]["max_recoveries"] >= 1
        assert payload["supervisor"]["component_recovery"]["autonomy"]["budget_window_s"] == 3600.0
        alias_autonomy = dict(alias_payload["autonomy"])
        payload_autonomy = dict(payload["autonomy"])
        alias_cooldown = float(alias_autonomy.pop("cooldown_remaining_s", 0.0) or 0.0)
        payload_cooldown = float(payload_autonomy.pop("cooldown_remaining_s", 0.0) or 0.0)
        assert alias_autonomy == payload_autonomy
        assert abs(alias_cooldown - payload_cooldown) <= 1.0
        assert alias_payload["autonomy_wake"] == payload["autonomy_wake"]
        assert alias_payload["channels_dispatcher"] == payload["channels_dispatcher"]
        assert alias_payload["channels_recovery"] == payload["channels_recovery"]
        assert alias_payload["autonomy_log"] == payload["autonomy_log"]
        assert alias_payload["supervisor"] == payload["supervisor"]


def test_gateway_supervisor_recovers_crashed_heartbeat_task(tmp_path: Path) -> None:
    async def _scenario() -> None:
        cfg = AppConfig(
            workspace_path=str(tmp_path / "workspace"),
            state_path=str(tmp_path / "state"),
            scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
            gateway={
                "heartbeat": {"enabled": True, "interval_s": 9999},
                "supervisor": {"enabled": False, "interval_s": 60, "cooldown_s": 0},
            },
            channels={},
        )
        app = create_app(cfg)

        async with app.router.lifespan_context(app):
            runtime = app.state.runtime
            assert runtime.supervisor is not None
            runtime.channels.send = AsyncMock(return_value="ok")

            heartbeat_task = runtime.heartbeat._task
            assert heartbeat_task is not None
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

            assert runtime.heartbeat.status()["worker_state"] == "cancelled"

            await runtime.supervisor.run_once()

            replacement_task = runtime.heartbeat._task
            assert replacement_task is not None
            assert replacement_task is not heartbeat_task
            assert runtime.heartbeat.status()["running"] is True

            supervisor_status = runtime.supervisor.status()
            assert supervisor_status["recovery_attempts"] >= 1
            assert supervisor_status["recovery_success"] >= 1
            assert supervisor_status["component_incidents"]["heartbeat"] >= 1
            send_kwargs = next(
                call.kwargs
                for call in runtime.channels.send.await_args_list
                if dict(call.kwargs.get("metadata", {})).get("autonomy_action") == "component_recovery"
            )
            assert send_kwargs["metadata"]["source"] == "supervisor"
            assert send_kwargs["metadata"]["autonomy_notice"] is True
            assert send_kwargs["metadata"]["autonomy_action"] == "component_recovery"
            assert send_kwargs["metadata"]["component"] == "heartbeat"
            assert "supervisor recovered component=heartbeat" in str(send_kwargs["text"])

    asyncio.run(_scenario())


def test_gateway_supervisor_recovers_crashed_autonomy_task(tmp_path: Path) -> None:
    async def _scenario() -> None:
        cfg = AppConfig(
            workspace_path=str(tmp_path / "workspace"),
            state_path=str(tmp_path / "state"),
            scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
            gateway={
                "heartbeat": {"enabled": False},
                "autonomy": {"enabled": True, "interval_s": 9999, "cooldown_s": 0, "timeout_s": 5},
                "supervisor": {"enabled": False, "interval_s": 60, "cooldown_s": 0},
            },
            channels={},
        )
        app = create_app(cfg)
        app.state.runtime.engine.provider = AutonomyIdleProvider()

        async with app.router.lifespan_context(app):
            runtime = app.state.runtime
            assert runtime.supervisor is not None
            assert runtime.autonomy is not None
            runtime.channels.send = AsyncMock(return_value="ok")

            autonomy_task = runtime.autonomy._task
            assert autonomy_task is not None
            autonomy_task.cancel()
            try:
                await autonomy_task
            except asyncio.CancelledError:
                pass

            assert runtime.autonomy.status()["worker_state"] == "cancelled"

            await runtime.supervisor.run_once()

            replacement_task = runtime.autonomy._task
            assert replacement_task is not None
            assert replacement_task is not autonomy_task
            assert runtime.autonomy.status()["running"] is True

            supervisor_status = runtime.supervisor.status()
            assert supervisor_status["recovery_attempts"] >= 1
            assert supervisor_status["recovery_success"] >= 1
            assert supervisor_status["component_incidents"]["autonomy"] >= 1
            send_kwargs = next(
                call.kwargs
                for call in runtime.channels.send.await_args_list
                if dict(call.kwargs.get("metadata", {})).get("autonomy_action") == "component_recovery"
                and dict(call.kwargs.get("metadata", {})).get("component") == "autonomy"
            )
            assert send_kwargs["metadata"]["source"] == "supervisor"
            assert send_kwargs["metadata"]["autonomy_notice"] is True
            assert send_kwargs["metadata"]["autonomy_action"] == "component_recovery"
            assert send_kwargs["metadata"]["component"] == "autonomy"
            assert "supervisor recovered component=autonomy" in str(send_kwargs["text"])

    asyncio.run(_scenario())


def test_gateway_supervisor_reports_provider_circuit_open_once_per_cooldown(tmp_path: Path) -> None:
    async def _scenario() -> None:
        cfg = AppConfig(
            workspace_path=str(tmp_path / "workspace"),
            state_path=str(tmp_path / "state"),
            scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
            gateway={
                "heartbeat": {"enabled": False},
                "supervisor": {"enabled": False, "interval_s": 60, "cooldown_s": 0},
            },
            channels={},
        )
        app = create_app(cfg)

        async with app.router.lifespan_context(app):
            runtime = app.state.runtime
            assert runtime.supervisor is not None
            runtime.channels.send = AsyncMock(return_value="ok")
            runtime.engine.provider = SimpleNamespace(
                provider_name="failover",
                model="openai/gpt-4.1-mini",
                diagnostics=lambda: {
                    "provider": "failover",
                    "model": "openai/gpt-4.1-mini",
                    "candidate_count": 2,
                    "candidates": [],
                    "counters": {"fallback_attempts": 1},
                    "circuit_open": True,
                },
            )

            await runtime.supervisor.run_once()
            await runtime.supervisor.run_once()

            supervisor_status = runtime.supervisor.status()
            assert supervisor_status["incident_count"] >= 2
            assert supervisor_status["recovery_attempts"] == 0
            assert supervisor_status["component_incidents"]["provider"] >= 2
            assert supervisor_status["last_incident"]["component"] == "provider"
            assert "provider_circuit_open:failover" in str(supervisor_status["last_incident"]["reason"])

            incident_calls = [
                call.kwargs
                for call in runtime.channels.send.await_args_list
                if dict(call.kwargs.get("metadata", {})).get("autonomy_action") == "component_incident"
            ]
            assert len(incident_calls) == 1
            metadata = dict(incident_calls[0]["metadata"])
            assert metadata["source"] == "supervisor"
            assert metadata["component"] == "provider"
            assert metadata["incident_reason"] == "provider_circuit_open:failover"
            assert metadata["autonomy_notice"] is True

    asyncio.run(_scenario())


def test_gateway_autonomy_respects_provider_backoff_without_calling_model(tmp_path: Path) -> None:
    async def _scenario() -> None:
        cfg = AppConfig(
            workspace_path=str(tmp_path / "workspace"),
            state_path=str(tmp_path / "state"),
            scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
            gateway={
                "heartbeat": {"enabled": False},
                "autonomy": {"enabled": True, "interval_s": 9999, "cooldown_s": 0, "timeout_s": 5},
            },
            channels={},
        )
        app = create_app(cfg)
        provider_complete = AsyncMock(side_effect=AssertionError("provider should not be called while cooling down"))
        app.state.runtime.workspace.should_run_bootstrap = lambda: False
        app.state.runtime.engine.provider = SimpleNamespace(
            provider_name="failover",
            model="openai/gpt-4.1-mini",
            complete=provider_complete,
            diagnostics=lambda: {
                "provider": "failover",
                "model": "openai/gpt-4.1-mini",
                "candidate_count": 2,
                "candidates": [
                    {
                        "role": "primary",
                        "model": "openai/gpt-4.1-mini",
                        "in_cooldown": True,
                        "cooldown_remaining_s": 30.0,
                    }
                ],
                "counters": {"fallback_attempts": 1, "last_error_class": "rate_limit"},
            },
        )

        async with app.router.lifespan_context(app):
            runtime = app.state.runtime
            assert runtime.autonomy is not None
            baseline_calls = provider_complete.await_count
            runtime.autonomy.cooldown_s = 0.0
            runtime.autonomy._cooldown_until = 0.0
            runtime.autonomy._provider_backoff_until = 0.0

            first = await runtime.autonomy.run_once(force=True)
            second = await runtime.autonomy.run_once(force=False)

            assert first["run_attempts"] >= 1
            assert first["run_failures"] >= 1
            assert first["last_error_kind"] == "provider_backoff"
            assert first["provider_backoff_reason"] == "cooldown"
            assert first["provider_backoff_provider"] == "failover"
            assert first["provider_backoff_remaining_s"] >= 29.0
            assert first["last_snapshot"]["provider"]["state"] == "cooldown"
            assert first["last_snapshot"]["provider"]["provider"] == "failover"
            assert first["last_snapshot"]["provider"]["suppression_reason"] == "cooldown"
            assert second["skipped_provider_backoff"] >= 1
            assert provider_complete.await_count == baseline_calls

    asyncio.run(_scenario())


def test_gateway_autonomy_suppresses_provider_quota_without_calling_model(tmp_path: Path) -> None:
    async def _scenario() -> None:
        cfg = AppConfig(
            workspace_path=str(tmp_path / "workspace"),
            state_path=str(tmp_path / "state"),
            scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
            gateway={
                "heartbeat": {"enabled": False},
                "autonomy": {"enabled": True, "interval_s": 9999, "cooldown_s": 0, "timeout_s": 5},
            },
            channels={},
        )
        app = create_app(cfg)
        provider_complete = AsyncMock(side_effect=AssertionError("provider should not be called while quota is exhausted"))
        app.state.runtime.workspace.should_run_bootstrap = lambda: False
        app.state.runtime.engine.provider = SimpleNamespace(
            provider_name="openai",
            model="openai/gpt-4.1-mini",
            complete=provider_complete,
            diagnostics=lambda: {
                "provider": "openai",
                "model": "openai/gpt-4.1-mini",
                "counters": {"last_error_class": "quota"},
            },
        )

        async with app.router.lifespan_context(app):
            runtime = app.state.runtime
            assert runtime.autonomy is not None
            baseline_calls = provider_complete.await_count
            runtime.autonomy.cooldown_s = 0.0
            runtime.autonomy._cooldown_until = 0.0
            runtime.autonomy._provider_backoff_until = 0.0

            first = await runtime.autonomy.run_once(force=True)
            second = await runtime.autonomy.run_once(force=False)

            assert first["run_attempts"] >= 1
            assert first["run_failures"] >= 1
            assert first["last_error_kind"] == "provider_backoff"
            assert first["provider_backoff_reason"] == "quota"
            assert first["provider_backoff_provider"] == "openai"
            assert first["provider_backoff_remaining_s"] >= 1799.0
            assert first["last_snapshot"]["provider"]["state"] == "degraded"
            assert first["last_snapshot"]["provider"]["suppression_reason"] == "quota"
            assert first["last_snapshot"]["provider"]["suppression_backoff_s"] == 1800.0
            assert "quota" in str(first["last_snapshot"]["provider"]["suppression_hint"]).lower()
            assert second["skipped_provider_backoff"] >= 1
            assert provider_complete.await_count == baseline_calls

    asyncio.run(_scenario())


def test_gateway_diagnostics_exposes_subagent_status_and_runner(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={
            "heartbeat": {"enabled": False},
            "supervisor": {"enabled": False},
            "diagnostics": {"enabled": True, "require_auth": False},
        },
        channels={},
    )
    app = create_app(cfg)

    with TestClient(app) as client:
        payload = client.get("/v1/diagnostics").json()
        alias_payload = client.get("/api/diagnostics").json()

        assert "subagents" in payload
        assert payload["subagents"]["maintenance_interval_s"] >= 1.0
        assert payload["subagents"]["runner"]["enabled"] is True
        assert payload["subagents"]["runner"]["running"] is True
        assert payload["subagents"]["runner"]["success_count"] >= 1
        assert payload["control_plane"]["components"]["subagent_maintenance"]["running"] is True
        assert alias_payload["subagents"] == payload["subagents"]


def test_gateway_diagnostics_exposes_self_evolution_runner_when_enabled(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={
            "heartbeat": {"enabled": False},
            "supervisor": {"enabled": False},
            "autonomy": {"self_evolution_enabled": True, "self_evolution_cooldown_s": 3600},
            "diagnostics": {"enabled": True, "require_auth": False},
        },
        channels={},
    )
    app = create_app(cfg)
    app.state.runtime.self_evolution = FakeSelfEvolutionEngine(enabled=True, cooldown_s=9999.0)
    app.state.runtime.workspace.should_run = lambda: False

    with TestClient(app) as client:
        payload = client.get("/v1/diagnostics").json()
        status_payload = client.get("/v1/self-evolution/status").json()

        assert payload["self_evolution"]["enabled"] is True
        assert payload["self_evolution"]["run_count"] >= 1
        assert payload["self_evolution"]["runner"]["enabled"] is True
        assert payload["self_evolution"]["runner"]["running"] is True
        assert payload["self_evolution"]["runner"]["success_count"] >= 1
        assert payload["control_plane"]["components"]["self_evolution"]["running"] is True
        assert status_payload["enabled"] is True
        assert status_payload["status"]["run_count"] >= 1
        assert status_payload["runner"]["running"] is True


def test_gateway_self_evolution_trigger_accepts_dry_run_payload(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={
            "heartbeat": {"enabled": False},
            "supervisor": {"enabled": False},
            "autonomy": {"self_evolution_enabled": True},
            "diagnostics": {"enabled": True, "require_auth": False},
        },
        channels={},
    )
    app = create_app(cfg)
    app.state.runtime.self_evolution = FakeSelfEvolutionEngine(enabled=True, cooldown_s=9999.0)
    app.state.runtime.workspace.should_run = lambda: False

    with TestClient(app) as client:
        payload = client.post("/v1/self-evolution/trigger", json={"dry_run": True}).json()

    assert payload["ok"] is True
    assert payload["status"]["last_outcome"] == "dry_run"
    assert payload["status"]["dry_run_count"] == 1


def test_gateway_self_evolution_status_reports_session_canary_when_background_disabled(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={
            "heartbeat": {"enabled": False},
            "supervisor": {"enabled": False},
            "autonomy": {
                "self_evolution_enabled": True,
                "self_evolution_enabled_for_sessions": ["autonomy:canary"],
            },
            "diagnostics": {"enabled": True, "require_auth": False},
        },
        channels={},
    )
    app = create_app(cfg)
    app.state.runtime.self_evolution = FakeSelfEvolutionEngine(
        enabled=True,
        background_enabled=False,
        enabled_for_sessions=["autonomy:canary"],
        autonomy_session_id="autonomy:system",
    )
    app.state.runtime.workspace.should_run = lambda: False

    with TestClient(app) as client:
        status_payload = client.get("/v1/self-evolution/status").json()
        diagnostics_payload = client.get("/v1/diagnostics").json()

    assert status_payload["enabled"] is True
    assert status_payload["status"]["background_enabled"] is False
    assert status_payload["status"]["activation_mode"] == "session_canary"
    assert status_payload["status"]["activation_reason"] == "autonomy_session_not_allowlisted"
    assert status_payload["status"]["enabled_for_sessions"] == ["autonomy:canary"]
    assert diagnostics_payload["self_evolution"]["background_enabled"] is False
    assert diagnostics_payload["self_evolution"]["runner"]["enabled"] is False
    assert diagnostics_payload["control_plane"]["components"]["self_evolution"]["last_error"] == "autonomy_session_not_allowlisted"


def test_gateway_supervisor_recovers_crashed_subagent_maintenance_task(tmp_path: Path) -> None:
    async def _scenario() -> None:
        cfg = AppConfig(
            workspace_path=str(tmp_path / "workspace"),
            state_path=str(tmp_path / "state"),
            scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
            gateway={
                "heartbeat": {"enabled": False},
                "supervisor": {"enabled": False, "interval_s": 60, "cooldown_s": 0},
            },
            channels={},
        )
        app = create_app(cfg)

        async with app.router.lifespan_context(app):
            runtime = app.state.runtime
            assert runtime.supervisor is not None
            runtime.channels.send = AsyncMock(return_value="ok")

            maintenance_task = next(
                task
                for task in asyncio.all_tasks()
                if task is not asyncio.current_task()
                and getattr(task.get_coro(), "cr_code", None) is not None
                and task.get_coro().cr_code.co_name == "_maintenance_loop"
            )
            maintenance_task.cancel()
            try:
                await maintenance_task
            except asyncio.CancelledError:
                pass

            diagnostics_before = app.state.runtime.engine.subagents.status()
            assert diagnostics_before["maintenance"]["sweep_runs"] >= 1

            await runtime.supervisor.run_once()

            diagnostics_after = runtime.engine.subagents.status()
            assert diagnostics_after["maintenance"]["sweep_runs"] >= diagnostics_before["maintenance"]["sweep_runs"]

            supervisor_status = runtime.supervisor.status()
            assert supervisor_status["recovery_attempts"] >= 1
            assert supervisor_status["recovery_success"] >= 1
            assert supervisor_status["component_incidents"]["subagent_maintenance"] >= 1
            send_kwargs = next(
                call.kwargs
                for call in runtime.channels.send.await_args_list
                if dict(call.kwargs.get("metadata", {})).get("autonomy_action") == "component_recovery"
                and dict(call.kwargs.get("metadata", {})).get("component") == "subagent_maintenance"
            )
            assert send_kwargs["metadata"]["source"] == "supervisor"
            assert send_kwargs["metadata"]["autonomy_notice"] is True
            assert send_kwargs["metadata"]["autonomy_action"] == "component_recovery"
            assert send_kwargs["metadata"]["component"] == "subagent_maintenance"
            assert "supervisor recovered component=subagent_maintenance" in str(send_kwargs["text"])

    asyncio.run(_scenario())


def test_gateway_supervisor_recovers_crashed_self_evolution_task(tmp_path: Path) -> None:
    async def _scenario() -> None:
        cfg = AppConfig(
            workspace_path=str(tmp_path / "workspace"),
            state_path=str(tmp_path / "state"),
            scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
            gateway={
                "heartbeat": {"enabled": False},
                "autonomy": {"self_evolution_enabled": True, "self_evolution_cooldown_s": 3600},
                "supervisor": {"enabled": False, "interval_s": 60, "cooldown_s": 0},
            },
            channels={},
        )
        app = create_app(cfg)
        app.state.runtime.self_evolution = FakeSelfEvolutionEngine(enabled=True, cooldown_s=9999.0)
        app.state.runtime.workspace.should_run = lambda: False

        async with app.router.lifespan_context(app):
            runtime = app.state.runtime
            assert runtime.supervisor is not None
            runtime.channels.send = AsyncMock(return_value="ok")

            evolution_task = next(
                task
                for task in asyncio.all_tasks()
                if task is not asyncio.current_task()
                and getattr(task.get_coro(), "cr_code", None) is not None
                and task.get_coro().cr_code.co_name == "_evo_loop"
            )
            evolution_task.cancel()
            try:
                await evolution_task
            except asyncio.CancelledError:
                pass

            await runtime.supervisor.run_once()

            replacement_task = next(
                task
                for task in asyncio.all_tasks()
                if task is not asyncio.current_task()
                and getattr(task.get_coro(), "cr_code", None) is not None
                and task.get_coro().cr_code.co_name == "_evo_loop"
            )
            assert replacement_task is not evolution_task

            supervisor_status = runtime.supervisor.status()
            assert supervisor_status["recovery_attempts"] >= 1
            assert supervisor_status["recovery_success"] >= 1
            assert supervisor_status["component_incidents"]["self_evolution"] >= 1
            send_kwargs = next(
                call.kwargs
                for call in runtime.channels.send.await_args_list
                if dict(call.kwargs.get("metadata", {})).get("autonomy_action") == "component_recovery"
                and dict(call.kwargs.get("metadata", {})).get("component") == "self_evolution"
            )
            assert send_kwargs["metadata"]["source"] == "supervisor"
            assert send_kwargs["metadata"]["autonomy_notice"] is True
            assert send_kwargs["metadata"]["autonomy_action"] == "component_recovery"
            assert send_kwargs["metadata"]["component"] == "self_evolution"
            assert "supervisor recovered component=self_evolution" in str(send_kwargs["text"])

    asyncio.run(_scenario())


def test_gateway_supervisor_recovers_crashed_channels_recovery_task(tmp_path: Path) -> None:
    async def _scenario() -> None:
        cfg = AppConfig(
            workspace_path=str(tmp_path / "workspace"),
            state_path=str(tmp_path / "state"),
            scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
            gateway={
                "heartbeat": {"enabled": False},
                "supervisor": {"enabled": False, "interval_s": 60, "cooldown_s": 0},
            },
            channels={},
        )
        app = create_app(cfg)

        async with app.router.lifespan_context(app):
            runtime = app.state.runtime
            assert runtime.supervisor is not None
            runtime.channels.send = AsyncMock(return_value="ok")

            recovery_task = runtime.channels._recovery_task
            assert recovery_task is not None
            recovery_task.cancel()
            try:
                await recovery_task
            except asyncio.CancelledError:
                pass

            assert runtime.channels.recovery_diagnostics()["task_state"] == "cancelled"

            await runtime.supervisor.run_once()

            replacement_task = runtime.channels._recovery_task
            assert replacement_task is not None
            assert replacement_task is not recovery_task
            assert runtime.channels.recovery_diagnostics()["running"] is True

            supervisor_status = runtime.supervisor.status()
            assert supervisor_status["recovery_attempts"] >= 1
            assert supervisor_status["recovery_success"] >= 1
            assert supervisor_status["component_incidents"]["channels_recovery"] >= 1
            send_kwargs = next(
                call.kwargs
                for call in runtime.channels.send.await_args_list
                if dict(call.kwargs.get("metadata", {})).get("autonomy_action") == "component_recovery"
                and dict(call.kwargs.get("metadata", {})).get("component") == "channels_recovery"
            )
            assert send_kwargs["metadata"]["source"] == "supervisor"
            assert send_kwargs["metadata"]["autonomy_notice"] is True
            assert send_kwargs["metadata"]["autonomy_action"] == "component_recovery"
            assert send_kwargs["metadata"]["component"] == "channels_recovery"
            assert "supervisor recovered component=channels_recovery" in str(send_kwargs["text"])

    asyncio.run(_scenario())


def test_gateway_supervisor_recovers_crashed_channels_dispatcher_task(tmp_path: Path) -> None:
    async def _scenario() -> None:
        cfg = AppConfig(
            workspace_path=str(tmp_path / "workspace"),
            state_path=str(tmp_path / "state"),
            scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
            gateway={
                "heartbeat": {"enabled": False},
                "supervisor": {"enabled": False, "interval_s": 60, "cooldown_s": 0},
            },
            channels={},
        )
        app = create_app(cfg)

        async with app.router.lifespan_context(app):
            runtime = app.state.runtime
            assert runtime.supervisor is not None
            runtime.channels.send = AsyncMock(return_value="ok")

            dispatcher_task = runtime.channels._dispatcher_task
            assert dispatcher_task is not None
            dispatcher_task.cancel()
            try:
                await dispatcher_task
            except asyncio.CancelledError:
                pass

            assert runtime.channels.dispatcher_diagnostics()["task_state"] == "cancelled"

            await runtime.supervisor.run_once()

            replacement_task = runtime.channels._dispatcher_task
            assert replacement_task is not None
            assert replacement_task is not dispatcher_task
            assert runtime.channels.dispatcher_diagnostics()["running"] is True

            supervisor_status = runtime.supervisor.status()
            assert supervisor_status["recovery_attempts"] >= 1
            assert supervisor_status["recovery_success"] >= 1
            assert supervisor_status["component_incidents"]["channels_dispatcher"] >= 1
            send_kwargs = next(
                call.kwargs
                for call in runtime.channels.send.await_args_list
                if dict(call.kwargs.get("metadata", {})).get("autonomy_action") == "component_recovery"
                and dict(call.kwargs.get("metadata", {})).get("component") == "channels_dispatcher"
            )
            assert send_kwargs["metadata"]["source"] == "supervisor"
            assert send_kwargs["metadata"]["autonomy_notice"] is True
            assert send_kwargs["metadata"]["autonomy_action"] == "component_recovery"
            assert send_kwargs["metadata"]["component"] == "channels_dispatcher"
            assert "supervisor recovered component=channels_dispatcher" in str(send_kwargs["text"])

    asyncio.run(_scenario())


def test_gateway_startup_delivery_replay_sends_autonomy_notice(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={
            "heartbeat": {"enabled": False},
            "supervisor": {"enabled": False},
            "diagnostics": {"enabled": True, "require_auth": False},
        },
        channels={},
    )
    app = create_app(cfg)
    app.state.runtime.channels.start = AsyncMock(return_value=None)
    app.state.runtime.channels.stop = AsyncMock(return_value=None)
    app.state.runtime.channels.send = AsyncMock(return_value="ok")
    app.state.runtime.channels.startup_replay_status = lambda: {
        "enabled": True,
        "running": False,
        "last_error": "",
        "restored": 2,
        "replayed": 2,
        "failed": 1,
        "skipped": 0,
    }

    with TestClient(app) as client:
        deadline = time.monotonic() + 2.0
        payload: dict[str, object] = {}
        while time.monotonic() < deadline:
            payload = client.get("/v1/diagnostics").json()
            if app.state.runtime.channels.send.await_count >= 1:
                break
            time.sleep(0.05)

        send_kwargs = app.state.runtime.channels.send.await_args.kwargs
        metadata = dict(send_kwargs["metadata"])
        assert metadata["source"] == "delivery_replay"
        assert metadata["autonomy_notice"] is True
        assert metadata["autonomy_action"] == "startup_delivery_replay"
        assert metadata["replayed"] == 2
        assert metadata["failed"] == 1
        assert "startup delivery replay replayed=2 failed=1 skipped=0" in str(send_kwargs["text"])
        autonomy_recent = payload["autonomy_log"]["recent"]
        assert any(
            str(row.get("action", "")) == "startup_delivery_replay_notice"
            and str(row.get("status", "")) == "sent"
            for row in autonomy_recent
        )


def test_gateway_startup_inbound_replay_sends_autonomy_notice(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={
            "heartbeat": {"enabled": False},
            "supervisor": {"enabled": False},
            "diagnostics": {"enabled": True, "require_auth": False},
        },
        channels={},
    )
    app = create_app(cfg)
    app.state.runtime.channels.start = AsyncMock(return_value=None)
    app.state.runtime.channels.stop = AsyncMock(return_value=None)
    app.state.runtime.channels.send = AsyncMock(return_value="ok")
    app.state.runtime.channels.startup_replay_status = lambda: {
        "enabled": True,
        "running": False,
        "last_error": "",
        "restored": 0,
        "replayed": 0,
        "failed": 0,
        "skipped": 0,
    }
    app.state.runtime.channels.startup_inbound_replay_status = lambda: {
        "enabled": True,
        "running": False,
        "last_error": "",
        "restored": 1,
        "replayed": 1,
        "remaining": 0,
        "replayed_by_channel": {"telegram": 1},
    }

    with TestClient(app) as client:
        deadline = time.monotonic() + 2.0
        payload: dict[str, object] = {}
        while time.monotonic() < deadline:
            payload = client.get("/v1/diagnostics").json()
            if app.state.runtime.channels.send.await_count >= 1:
                break
            time.sleep(0.05)

        send_kwargs = app.state.runtime.channels.send.await_args.kwargs
        metadata = dict(send_kwargs["metadata"])
        assert metadata["source"] == "inbound_replay"
        assert metadata["autonomy_notice"] is True
        assert metadata["autonomy_action"] == "startup_inbound_replay"
        assert metadata["replayed"] == 1
        assert metadata["remaining"] == 0
        assert "startup inbound replay replayed=1 remaining=0" in str(send_kwargs["text"])
        autonomy_recent = payload["autonomy_log"]["recent"]
        assert any(
            str(row.get("action", "")) == "startup_inbound_replay_notice"
            and str(row.get("status", "")) == "sent"
            for row in autonomy_recent
        )


def test_gateway_startup_wake_replay_sends_autonomy_notice(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={
            "heartbeat": {"enabled": False},
            "supervisor": {"enabled": False},
            "diagnostics": {"enabled": True, "require_auth": False},
        },
        channels={},
    )
    journal_path = Path(cfg.state_path) / "autonomy-wake.json"
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    journal_path.write_text(
        json.dumps(
            [
                {
                    "kind": "noop",
                    "key": "noop:restore",
                    "priority": 5,
                    "sequence": 0,
                    "payload": {"source": "journal"},
                }
            ]
        ),
        encoding="utf-8",
    )
    app = create_app(cfg)
    app.state.runtime.channels.start = AsyncMock(return_value=None)
    app.state.runtime.channels.stop = AsyncMock(return_value=None)
    app.state.runtime.channels.send = AsyncMock(return_value="ok")

    with TestClient(app) as client:
        deadline = time.monotonic() + 2.0
        payload: dict[str, object] = {}
        while time.monotonic() < deadline:
            payload = client.get("/v1/diagnostics").json()
            if app.state.runtime.channels.send.await_count >= 1:
                break
            time.sleep(0.05)

        send_kwargs = app.state.runtime.channels.send.await_args.kwargs
        metadata = dict(send_kwargs["metadata"])
        assert metadata["source"] == "wake_replay"
        assert metadata["autonomy_notice"] is True
        assert metadata["autonomy_action"] == "startup_wake_replay"
        assert metadata["restored"] == 1
        assert "startup wake replay restored=1" in str(send_kwargs["text"])
        autonomy_recent = payload["autonomy_log"]["recent"]
        assert any(
            str(row.get("action", "")) == "startup_wake_replay_notice"
            and str(row.get("status", "")) == "sent"
            for row in autonomy_recent
        )
        components = payload["control_plane"]["components"]
        assert components["wake_replay"]["restored"] == 1


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
        assert "<h1>ClawLite Dashboard</h1>" in body
        assert "Gateway Control Plane" in body
        assert "Operator view for health, chat, diagnostics, tools, and WebSocket connectivity." in body
        assert "Trigger heartbeat" in body
        assert "Hatch agent" in body
        assert "Next Steps" in body
        assert "Control-Plane Correlation" in body
        assert 'id="skills-grid"' in body
        assert 'id="refresh-skills-inventory"' in body
        assert 'id="doctor-skills-inventory"' in body
        assert 'id="provider-grid"' in body
        assert 'id="delivery-grid"' in body
        assert 'id="supervisor-grid"' in body
        assert 'id="replay-dead-letters"' in body
        assert "Signal Feed" in body
        assert "HTTP Correlation" in body
        assert "Workspace Runtime Files" in body
        assert "Recent Sessions" in body
        assert 'window.__CLAWLITE_DASHBOARD_BOOTSTRAP__ = {' in body
        assert "/_clawlite/dashboard.css" in body
        assert "/_clawlite/dashboard.js" in body
        assert '"dashboard_state": "/api/dashboard/state"' in body
        assert '"status": "/api/status"' in body
        assert '"diagnostics": "/api/diagnostics"' in body
        assert '"dashboard_session": "/api/dashboard/session"' in body
        assert '"message": "/api/message"' in body
        assert '"channels_replay": "/v1/control/channels/replay"' in body
        assert '"channels_recover": "/v1/control/channels/recover"' in body
        assert '"channels_inbound_replay": "/v1/control/channels/inbound-replay"' in body
        assert '"telegram_refresh": "/v1/control/channels/telegram/refresh"' in body
        assert '"telegram_pairing_approve": "/v1/control/channels/telegram/pairing/approve"' in body
        assert '"telegram_pairing_reject": "/v1/control/channels/telegram/pairing/reject"' in body
        assert '"telegram_pairing_revoke": "/v1/control/channels/telegram/pairing/revoke"' in body
        assert '"telegram_offset_commit": "/v1/control/channels/telegram/offset/commit"' in body
        assert '"telegram_offset_sync": "/v1/control/channels/telegram/offset/sync"' in body
        assert '"telegram_offset_reset": "/v1/control/channels/telegram/offset/reset"' in body
        assert '"discord_refresh": "/v1/control/channels/discord/refresh"' in body
        assert '"skills_refresh": "/v1/control/skills/refresh"' in body
        assert '"skills_doctor": "/v1/control/skills/doctor"' in body
        assert '"memory_suggest_refresh": "/v1/control/memory/suggest/refresh"' in body
        assert '"memory_snapshot_create": "/v1/control/memory/snapshot/create"' in body
        assert '"memory_snapshot_rollback": "/v1/control/memory/snapshot/rollback"' in body
        assert '"provider_recover": "/v1/control/provider/recover"' in body
        assert '"autonomy_wake": "/v1/control/autonomy/wake"' in body
        assert '"supervisor_recover": "/v1/control/supervisor/recover"' in body
        assert '"heartbeat_trigger": "/v1/control/heartbeat/trigger"' in body
        assert '"tools": "/api/tools/catalog"' in body
        assert '"ws": "/ws"' in body
        assert 'value="dashboard:operator"' not in body


def test_gateway_dashboard_assets_are_served(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)

    with TestClient(app) as client:
        css = client.get("/_clawlite/dashboard.css")
        js = client.get("/_clawlite/dashboard.js")

    assert css.status_code == 200
    assert "--accent" in css.text
    assert css.headers["content-type"].startswith("text/css")

    assert js.status_code == 200
    assert "const bootstrap = window.__CLAWLITE_DASHBOARD_BOOTSTRAP__ || {}" in js.text
    assert "connectWs" in js.text
    assert "triggerHeartbeat" in js.text
    assert "triggerHatch" in js.text
    assert "Wake up, my friend!" in js.text
    assert "handoff-grid" in js.text
    assert "renderDeliveryBoard" in js.text
    assert "renderSupervisorBoard" in js.text
    assert "renderProviderRecoveryBoard" in js.text
    assert "triggerDeadLetterReplay" in js.text
    assert "triggerChannelRecovery" in js.text
    assert "triggerInboundReplay" in js.text
    assert "triggerTelegramRefresh" in js.text
    assert "renderControlPlaneCorrelationBoard" in js.text
    assert "renderHttpCorrelationBoard" in js.text
    assert "renderSkillsBoard" in js.text
    assert "triggerSkillsRefresh" in js.text
    assert "triggerSkillsDoctor" in js.text
    assert 'paths.skills_refresh || "/v1/control/skills/refresh"' in js.text
    assert 'paths.skills_doctor || "/v1/control/skills/doctor"' in js.text
    assert "missingRequirements.os" in js.text
    assert "Skills doctor finished" in js.text
    assert "Skills refresh finished" in js.text
    assert "syncGatewayWsEvents" in js.text
    assert "syncGatewayHttpEvents" in js.text
    assert "Gateway WebSocket error observed" in js.text
    assert "Gateway WebSocket observed" in js.text
    assert "Gateway HTTP error observed" in js.text
    assert 'lastObservedGatewayHttpErrorAt' in js.text
    assert 'response.headers.get("X-Request-ID")' in js.text
    assert "appendRequestIdMeta" in js.text
    assert "requestIdFromValue" in js.text
    assert "triggerTelegramPairingApprove" in js.text
    assert "triggerTelegramPairingReject" in js.text
    assert "triggerTelegramPairingRevoke" in js.text
    assert "triggerTelegramOffsetCommit" in js.text
    assert "triggerTelegramOffsetSync" in js.text
    assert "triggerTelegramOffsetReset" in js.text
    assert "triggerDiscordRefresh" in js.text
    assert "triggerMemorySuggestRefresh" in js.text
    assert "triggerMemorySnapshotCreate" in js.text
    assert "triggerMemorySnapshotRollback" in js.text
    assert "triggerProviderRecovery" in js.text
    assert "triggerAutonomyWake" in js.text
    assert "triggerSupervisorRecovery" in js.text
    assert "hatch:operator" in js.text
    assert 'const operatorStorageKey = "clawlite.dashboard.operatorId"' in js.text
    assert 'const chatSessionStorageKey = "clawlite.dashboard.chatSessionId"' in js.text
    assert "window.sessionStorage" in js.text
    assert "window.localStorage.setItem(tokenStorageKey" not in js.text
    assert "storageRemove(window.localStorage, tokenStorageKey);" in js.text
    assert 'const dashboardSessionStorageKey = "clawlite.dashboard.sessionToken"' in js.text
    assert 'const dashboardClientStorageKey = "clawlite.dashboard.clientId"' in js.text
    assert "exchangeDashboardSession" in js.text
    assert '"/api/dashboard/session"' in js.text
    assert 'exchangeDashboardSession({ rawToken: byId("token-input").value, source: "auth" })' in js.text
    assert 'exchangeDashboardSession(byId("token-input").value, { source: "auth" })' not in js.text
    assert "X-ClawLite-Dashboard-Handoff" in js.text
    assert "X-ClawLite-Dashboard-Session" in js.text
    assert "X-ClawLite-Dashboard-Client" in js.text
    assert "dashboard:operator:" in js.text
    assert "scheduleAutoRefresh" in js.text
    assert "window.location.hash" in js.text
    assert "history.replaceState" in js.text
    assert js.headers["content-type"].startswith("application/javascript")


def test_gateway_dashboard_state_endpoint_returns_operational_summary(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)
    app.state.runtime.engine.sessions.append("dashboard:test", "user", "hello dashboard")

    with TestClient(app) as client:
        response = client.get("/api/dashboard/state")

    assert response.status_code == 200
    payload = response.json()
    assert payload["contract_version"]
    assert payload["control_plane"]["contract_version"]
    assert payload["sessions"]["count"] >= 1
    assert any(item["session_id"] == "dashboard:test" for item in payload["sessions"]["items"])
    assert payload["handoff"]["hatch_session_id"] == "hatch:operator"
    assert any(item["id"] == "dashboard" for item in payload["handoff"]["guidance"])
    assert "queue" in payload
    assert "channels_delivery" in payload
    assert "channels_recovery" in payload
    assert "supervisor" in payload
    assert "manual_replay" in payload["channels_delivery"]["persistence"]
    assert "operator" in payload["channels_recovery"]
    assert "manual_replay" in payload["channels_inbound"]["persistence"]
    assert payload["telegram"]["available"] is False
    assert payload["discord"]["available"] is False
    assert "profile" in payload["memory"]
    assert "suggestions" in payload["memory"]
    assert "quality" in payload["memory"]
    assert "versions" in payload["memory"]
    assert "status" in payload["cron"]
    assert "jobs" in payload["cron"]
    assert "ws" in payload
    assert "workspace" in payload
    assert "onboarding" in payload
    assert "bootstrap" in payload
    assert "memory" in payload
    assert "telemetry" in payload["provider"]
    assert "autonomy" in payload["provider"]
    assert "items" in payload["channels"]
    assert "enabled" in payload["self_evolution"]


def test_gateway_dashboard_state_includes_ws_correlation_summary(tmp_path: Path) -> None:
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
            challenge = _assert_connect_challenge(socket)
            connection_id = str(challenge["params"]["connection_id"])
            socket.send_json({"type": "req", "id": "c1", "method": "connect", "params": {}})
            assert socket.receive_json()["ok"] is True
            socket.send_json({"type": "req", "id": "req-ws-1", "method": "unsupported.method", "params": {}})
            assert socket.receive_json()["ok"] is False

        payload = client.get("/api/dashboard/state").json()
        ws_payload = payload["ws"]
        assert ws_payload["last_connection_id"] == connection_id
        assert ws_payload["last_connection_path"] == "/ws"
        assert ws_payload["last_connection_opened_at"]
        assert ws_payload["last_connection_closed_id"] == connection_id
        assert ws_payload["last_connection_closed_at"]
        assert ws_payload["last_request_id"] == "req-ws-1"
        assert ws_payload["last_error_connection_id"] == connection_id
        assert ws_payload["last_error_request_id"] == "req-ws-1"
        assert ws_payload["last_error_code"] == "unsupported_method"
        assert ws_payload["last_error_message"]
        assert ws_payload["last_error_status"] == 400


def test_gateway_dashboard_state_redacts_sensitive_handoff_token_fields(tmp_path: Path) -> None:
    token = "secret" + "-token"
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
        gateway={
            "auth": {
                "mode": "required",
                "token": token,
            }
        },
    )
    app = create_app(cfg)

    with TestClient(app) as client:
        response = client.get("/api/dashboard/state", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    payload = response.json()
    handoff = payload["handoff"]
    assert handoff["gateway_url"] == "http://127.0.0.1:8787"
    assert handoff["gateway_token_masked"] == "****et-token"
    assert "gateway_token" not in handoff
    assert "dashboard_url_with_token" not in handoff
    dashboard_row = next(item for item in handoff["guidance"] if item["id"] == "dashboard")
    assert "#token=" not in dashboard_row["body"]
    assert token not in json.dumps(handoff)


class _ReplayChannel(BaseChannel):
    def __init__(self) -> None:
        super().__init__(name="fake", config={}, capabilities=ChannelCapabilities())
        self._running = True
        self.sent: list[tuple[str, str, dict[str, object]]] = []

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def send(self, *, target: str, text: str, metadata: dict[str, object] | None = None) -> str:
        self.sent.append((target, text, dict(metadata or {})))
        return "ok"


class _RecoveringGatewayChannel(BaseChannel):
    starts = 0

    def __init__(self, *, config: dict[str, object], on_message=None) -> None:
        super().__init__(name="fake", config=config, on_message=on_message, capabilities=ChannelCapabilities())
        self._task = None

    async def start(self) -> None:
        type(self).starts += 1
        self._running = True
        if type(self).starts == 1:
            async def _crash() -> None:
                raise RuntimeError("channel worker crashed")

            self._task = asyncio.create_task(_crash())
            await asyncio.sleep(0)
            return
        self._task = asyncio.create_task(asyncio.sleep(3600))

    async def stop(self) -> None:
        self._running = False
        task = self._task
        if isinstance(task, asyncio.Task):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
        self._task = None

    async def send(self, *, target: str, text: str, metadata: dict[str, object] | None = None) -> str:
        del target, text, metadata
        return "ok"


def test_gateway_channels_replay_endpoint_replays_dead_letters(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)
    replay_channel = _ReplayChannel()
    app.state.runtime.channels._channels["fake"] = replay_channel

    with TestClient(app) as client:
        asyncio.run(
            app.state.runtime.bus.publish_dead_letter(
                OutboundEvent(
                    channel="fake",
                    session_id="fake:session",
                    target="dest",
                    text="replay-me",
                    metadata={"_delivery_idempotency_key": "gateway-replay-test-key"},
                    dead_lettered=True,
                    dead_letter_reason="send_failed",
                )
            )
        )
        response = client.post(
            "/v1/control/channels/replay",
            json={"limit": 5, "channel": "fake", "reason": "send_failed", "session_id": "fake:session"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["summary"]["replayed"] == 1
    assert payload["summary"]["remaining"] == 0
    assert replay_channel.sent[0][0] == "dest"
    assert replay_channel.sent[0][1] == "replay-me"
    assert replay_channel.sent[0][2]["_replayed_from_dead_letter"] is True


def test_gateway_channels_recover_endpoint_recovers_failed_worker(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)
    _RecoveringGatewayChannel.starts = 0
    app.state.runtime.channels.register("fake", _RecoveringGatewayChannel)

    with TestClient(app) as client:
        asyncio.run(app.state.runtime.channels.start({"channels": {"recovery_enabled": False, "fake": {"enabled": True}}}))
        response = client.post("/v1/control/channels/recover", json={"force": True})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["summary"]["attempted"] >= 1
    assert payload["summary"]["recovered"] >= 1
    diagnostics = app.state.runtime.channels.recovery_diagnostics()
    assert diagnostics["operator"]["recovered"] >= 1


def test_gateway_channels_inbound_replay_endpoint_calls_manager(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)
    app.state.runtime.channels.operator_replay_inbound = AsyncMock(
        return_value={"replayed": 2, "remaining": 1, "skipped_busy": 0}
    )

    with TestClient(app) as client:
        response = client.post(
            "/v1/control/channels/inbound-replay",
            json={"limit": 7, "channel": "telegram", "session_id": "tg:1", "force": True},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["summary"]["replayed"] == 2
    app.state.runtime.channels.operator_replay_inbound.assert_awaited_once_with(
        limit=7,
        channel="telegram",
        session_id="tg:1",
        force=True,
    )


def test_gateway_telegram_refresh_endpoint_calls_channel_operator_hook(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)
    fake_channel = SimpleNamespace(operator_refresh_transport=AsyncMock(return_value={"connected": True}))
    app.state.runtime.channels._channels["telegram"] = fake_channel

    with TestClient(app) as client:
        response = client.post("/v1/control/channels/telegram/refresh", json={})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["summary"]["connected"] is True
    fake_channel.operator_refresh_transport.assert_awaited_once_with()


def test_gateway_telegram_pairing_approve_endpoint_calls_channel_operator_hook(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)
    fake_channel = SimpleNamespace(operator_approve_pairing=AsyncMock(return_value={"ok": True, "request": {"chat_id": "1"}}))
    app.state.runtime.channels._channels["telegram"] = fake_channel

    with TestClient(app) as client:
        response = client.post("/v1/control/channels/telegram/pairing/approve", json={"code": "ABCD1234"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["summary"]["request"]["chat_id"] == "1"
    fake_channel.operator_approve_pairing.assert_awaited_once_with("ABCD1234")


def test_gateway_telegram_offset_commit_endpoint_calls_channel_operator_hook(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)
    fake_channel = SimpleNamespace(operator_force_commit_offset=AsyncMock(return_value={"ok": True, "update_id": 99}))
    app.state.runtime.channels._channels["telegram"] = fake_channel

    with TestClient(app) as client:
        response = client.post("/v1/control/channels/telegram/offset/commit", json={"update_id": 99})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["summary"]["update_id"] == 99
    fake_channel.operator_force_commit_offset.assert_awaited_once_with(99)


def test_gateway_telegram_offset_sync_endpoint_calls_channel_operator_hook(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)
    fake_channel = SimpleNamespace(operator_sync_next_offset=AsyncMock(return_value={"ok": True, "next_offset": 145}))
    app.state.runtime.channels._channels["telegram"] = fake_channel

    with TestClient(app) as client:
        response = client.post("/v1/control/channels/telegram/offset/sync", json={"next_offset": 145, "allow_reset": False})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["summary"]["next_offset"] == 145
    fake_channel.operator_sync_next_offset.assert_awaited_once_with(145, allow_reset=False)


def test_gateway_telegram_offset_reset_endpoint_calls_channel_operator_hook(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)
    fake_channel = SimpleNamespace(operator_sync_next_offset=AsyncMock(return_value={"ok": True, "next_offset": 0}))
    app.state.runtime.channels._channels["telegram"] = fake_channel

    with TestClient(app) as client:
        response = client.post("/v1/control/channels/telegram/offset/reset", json={"confirm": True})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["summary"]["next_offset"] == 0
    fake_channel.operator_sync_next_offset.assert_awaited_once_with(0, allow_reset=True)


def test_gateway_telegram_pairing_reject_endpoint_calls_channel_operator_hook(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)
    fake_channel = SimpleNamespace(operator_reject_pairing=AsyncMock(return_value={"ok": True, "request": {"chat_id": "1"}}))
    app.state.runtime.channels._channels["telegram"] = fake_channel

    with TestClient(app) as client:
        response = client.post("/v1/control/channels/telegram/pairing/reject", json={"code": "WXYZ9999"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["summary"]["request"]["chat_id"] == "1"
    fake_channel.operator_reject_pairing.assert_awaited_once_with("WXYZ9999")


def test_gateway_telegram_pairing_revoke_endpoint_calls_channel_operator_hook(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)
    fake_channel = SimpleNamespace(operator_revoke_pairing=AsyncMock(return_value={"ok": True, "removed_entry": "@alice"}))
    app.state.runtime.channels._channels["telegram"] = fake_channel

    with TestClient(app) as client:
        response = client.post("/v1/control/channels/telegram/pairing/revoke", json={"entry": "@alice"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["summary"]["removed_entry"] == "@alice"
    fake_channel.operator_revoke_pairing.assert_awaited_once_with("@alice")


def test_gateway_supervisor_recover_endpoint_calls_runtime_supervisor(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)
    app.state.runtime.supervisor = SimpleNamespace(
        start=AsyncMock(),
        stop=AsyncMock(),
        operator_recover_components=AsyncMock(return_value={"attempted": 1, "recovered": 1, "failed": 0}),
    )

    with TestClient(app) as client:
        response = client.post("/v1/control/supervisor/recover", json={"component": "heartbeat", "force": True})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["summary"]["recovered"] == 1
    app.state.runtime.supervisor.operator_recover_components.assert_awaited_once_with(
        component="heartbeat",
        force=True,
        reason="operator_recover",
    )


def test_gateway_tools_catalog_http_endpoints_return_expected_shape(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)

    with TestClient(app) as client:
        v1_payload = client.get("/v1/tools/catalog").json()
        api_payload = client.get("/api/tools/catalog").json()

    for payload in (v1_payload, api_payload):
        assert isinstance(payload["contract_version"], str) and payload["contract_version"]
        assert isinstance(payload["tool_count"], int) and payload["tool_count"] > 0
        assert isinstance(payload["aliases"], dict)
        assert isinstance(payload["groups"], list) and payload["groups"]
        assert isinstance(payload["ws_methods"], list)
        assert "tools.catalog" in payload["ws_methods"]

        aliases = payload["aliases"]
        assert aliases["bash"] == "exec"
        assert aliases["apply-patch"] == "apply_patch"
        assert aliases["read_file"] == "read"
        assert aliases["write_file"] == "write"
        assert aliases["edit_file"] == "edit"
        assert aliases["memory_recall"] == "memory_search"
        agents_group = [group for group in payload["groups"] if group["id"] == "agents"][0]
        assert {"agents_list", "spawn", "run_skill"}.issubset({tool["id"] for tool in agents_group["tools"]})

        total_tools = 0
        for group in payload["groups"]:
            assert isinstance(group["id"], str) and group["id"]
            assert isinstance(group["label"], str) and group["label"]
            assert isinstance(group["tools"], list) and group["tools"]
            tool_ids = [tool["id"] for tool in group["tools"]]
            assert tool_ids == sorted(tool_ids)
            for tool in group["tools"]:
                assert isinstance(tool["id"], str) and tool["id"]
                assert isinstance(tool["label"], str) and tool["label"]
                assert isinstance(tool["description"], str)
            total_tools += len(group["tools"])

        assert total_tools == payload["tool_count"]

    assert {k: v for k, v in api_payload.items() if k != "schema"} == {
        k: v for k, v in v1_payload.items() if k != "schema"
    }


def test_gateway_tools_catalog_include_schema_matches_tool_count(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)

    with TestClient(app) as client:
        snake_payload = client.get("/v1/tools/catalog?include_schema=true").json()
        camel_payload = client.get("/api/tools/catalog?includeSchema=true").json()

    for payload in (snake_payload, camel_payload):
        assert isinstance(payload["schema"], list)
        assert len(payload["schema"]) == payload["tool_count"]
        schema_names = [str(row.get("name", "")) for row in payload["schema"]]
        assert schema_names == sorted(schema_names)


def test_gateway_tools_approvals_endpoints_return_requests_and_grants(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)
    registry = app.state.runtime.engine.tools
    registry._approval_requests["req-1"] = {
        "request_id": "req-1",
        "tool": "browser",
        "session_id": "telegram:1",
        "channel": "telegram",
        "matched_approval_specifiers": ["browser:evaluate"],
        "status": "pending",
        "created_at_monotonic": time.monotonic() - 1.0,
        "expires_at_monotonic": time.monotonic() + 300.0,
        "arguments_preview": '{"action":"evaluate"}',
        "approval_context": {"tool": "browser", "action": "evaluate"},
        "notified_count": 1,
    }
    registry._approval_request_order.append("req-1")
    registry._approval_requests["req-2"] = {
        "request_id": "req-2",
        "tool": "exec",
        "session_id": "telegram:1",
        "channel": "telegram",
        "matched_approval_specifiers": ["exec:env-key:git-ssh-command"],
        "status": "pending",
        "created_at_monotonic": time.monotonic() - 1.0,
        "expires_at_monotonic": time.monotonic() + 300.0,
        "arguments_preview": '{"command":"git status"}',
        "approval_context": {"tool": "exec", "command_binary": "git"},
        "notified_count": 0,
    }
    registry._approval_request_order.append("req-2")
    registry._approval_grants["telegram:1::telegram::browser:evaluate"] = time.monotonic() + 120.0

    with TestClient(app) as client:
        v1_response = client.get(
            "/v1/tools/approvals?session_id=telegram:1&channel=telegram&tool=browser&rule=browser:evaluate&include_grants=true"
        )
        api_response = client.get(
            "/api/tools/approvals?session_id=telegram:1&channel=telegram&tool=browser&rule=browser:evaluate&include_grants=true"
        )

    for response in (v1_response, api_response):
        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is True
        assert payload["count"] == 1
        assert payload["tool"] == "browser"
        assert payload["rule"] == "browser:evaluate"
        assert payload["requests"][0]["request_id"] == "req-1"
        assert payload["requests"][0]["expires_in_s"] > 0.0
        assert payload["grant_count"] == 1
        assert payload["grants"][0]["rule"] == "browser:evaluate"


def test_gateway_tools_approval_review_endpoint_updates_request(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)
    registry = app.state.runtime.engine.tools
    registry._approval_requests["req-1"] = {
        "request_id": "req-1",
        "tool": "browser",
        "session_id": "telegram:1",
        "channel": "telegram",
        "matched_approval_specifiers": ["browser:evaluate"],
        "status": "pending",
        "created_at_monotonic": time.monotonic() - 1.0,
        "expires_at_monotonic": time.monotonic() + 300.0,
        "arguments_preview": '{"action":"evaluate"}',
        "approval_context": {"tool": "browser", "action": "evaluate"},
        "notified_count": 1,
    }
    registry._approval_request_order.append("req-1")

    with TestClient(app) as client:
        response = client.post("/v1/tools/approvals/req-1/approve", json={"actor": "cli", "note": "ok"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["summary"]["status"] == "approved"
    assert payload["summary"]["request_id"] == "req-1"
    assert payload["summary"]["approval_context"] == {"tool": "browser", "action": "evaluate"}
    reviewed = registry._approval_requests["req-1"]
    assert reviewed["status"] == "approved"
    assert reviewed["actor"] == "control-plane"
    grant_keys = list(registry._approval_grants.keys())
    assert len(grant_keys) == 1
    assert grant_keys[0].startswith("exact::req-1::telegram:1::telegram::browser:evaluate")


def test_gateway_tools_approval_review_endpoint_rejects_actor_bound_requests_from_generic_control_plane(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)
    registry = app.state.runtime.engine.tools
    registry._approval_requests["req-actor"] = {
        "request_id": "req-actor",
        "tool": "browser",
        "session_id": "telegram:1",
        "channel": "telegram",
        "requester_actor": "telegram:42",
        "matched_approval_specifiers": ["browser:evaluate"],
        "status": "pending",
        "created_at_monotonic": time.monotonic() - 1.0,
        "expires_at_monotonic": time.monotonic() + 300.0,
        "arguments_preview": '{"action":"evaluate"}',
        "approval_context": {"tool": "browser", "action": "evaluate"},
        "notified_count": 1,
    }
    registry._approval_request_order.append("req-actor")

    with TestClient(app) as client:
        response = client.post(
            "/v1/tools/approvals/req-actor/approve",
            json={"actor": "telegram:42", "note": "ok"},
        )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"] == "approval_channel_bound:telegram:42"
    reviewed = registry._approval_requests["req-actor"]
    assert reviewed["status"] == "pending"


def test_gateway_tools_grants_revoke_endpoint_removes_matching_grants(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)
    registry = app.state.runtime.engine.tools
    registry._approval_grants["telegram:1::telegram::browser:evaluate"] = time.monotonic() + 120.0
    registry._approval_grants["telegram:2::telegram::browser:evaluate"] = time.monotonic() + 120.0

    with TestClient(app) as client:
        response = client.post(
            "/v1/tools/grants/revoke",
            json={"session_id": "telegram:1", "channel": "telegram", "rule": "browser:evaluate"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["summary"]["removed_count"] == 1
    assert "telegram:1::telegram::browser:evaluate" not in registry._approval_grants
    assert "telegram:2::telegram::browser:evaluate" in registry._approval_grants


def test_gateway_tools_approval_endpoints_require_token_when_configured_even_on_loopback(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={
            "auth": {
                "mode": "off",
                "token": "secret-token",
            },
            "heartbeat": {"enabled": False},
        },
        channels={},
    )
    app = create_app(cfg)
    registry = app.state.runtime.engine.tools
    registry._approval_requests["req-1"] = {
        "request_id": "req-1",
        "tool": "browser",
        "session_id": "telegram:1",
        "channel": "telegram",
        "matched_approval_specifiers": ["browser:evaluate"],
        "status": "pending",
        "created_at_monotonic": time.monotonic() - 1.0,
        "expires_at_monotonic": time.monotonic() + 300.0,
        "arguments_preview": '{"action":"evaluate"}',
        "approval_context": {"tool": "browser", "action": "evaluate"},
        "notified_count": 1,
    }
    registry._approval_request_order.append("req-1")
    registry._approval_grants["telegram:1::telegram::browser:evaluate"] = time.monotonic() + 120.0

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/v1/status").status_code == 401

        unauthorized_list = client.get("/v1/tools/approvals")
        assert unauthorized_list.status_code == 401
        assert unauthorized_list.json()["error"] == "gateway_auth_required"

        unauthorized_review = client.post("/v1/tools/approvals/req-1/approve", json={"actor": "ops"})
        assert unauthorized_review.status_code == 401
        assert unauthorized_review.json()["error"] == "gateway_auth_required"

        unauthorized_revoke = client.post(
            "/v1/tools/grants/revoke",
            json={"session_id": "telegram:1", "channel": "telegram", "rule": "browser:evaluate"},
        )
        assert unauthorized_revoke.status_code == 401
        assert unauthorized_revoke.json()["error"] == "gateway_auth_required"

        invalid_list = client.get("/v1/tools/approvals", headers={"Authorization": "Bearer wrong-token"})
        assert invalid_list.status_code == 401
        assert invalid_list.json()["error"] == "gateway_auth_invalid"

        headers = {"Authorization": "Bearer secret-token"}
        listed = client.get("/v1/tools/approvals", headers=headers)
        assert listed.status_code == 200
        assert listed.json()["count"] == 1

        reviewed = client.post(
            "/v1/tools/approvals/req-1/approve",
            headers=headers,
            json={"actor": "ops", "note": "reviewed"},
        )
        assert reviewed.status_code == 200
        assert registry._approval_requests["req-1"]["actor"] == "control-plane"

        revoked = client.post(
            "/v1/tools/grants/revoke",
            headers=headers,
            json={"session_id": "telegram:1", "channel": "telegram", "rule": "browser:evaluate"},
        )
        assert revoked.status_code == 200
        assert revoked.json()["summary"]["removed_count"] >= 1


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


def test_gateway_provider_error_payload_failover_cooldown_lists_candidates(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)

    async def _raise_provider(*, session_id: str, user_text: str):
        raise RuntimeError(
            "provider_failover_cooldown:all_candidates_cooling_down:openai/gpt-4o-mini:30.000,groq/llama-3.1-8b-instant:12.500"
        )

    app.state.runtime.engine.run = _raise_provider

    with TestClient(app) as client:
        chat = client.post("/v1/chat", json={"session_id": "cli:1", "text": "ping"})
        assert chat.status_code == 503
        payload = chat.json()
        text = str(payload.get("error", "")).lower()
        assert "cooldown" in text
        assert "openai/gpt-4o-mini" in text
        assert "groq/llama-3.1-8b-instant" in text


def test_gateway_provider_error_payload_circuit_open_includes_provider_and_cooldown(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)

    async def _raise_provider(*, session_id: str, user_text: str):
        raise RuntimeError("provider_circuit_open:openai:30.0")

    app.state.runtime.engine.run = _raise_provider

    with TestClient(app) as client:
        chat = client.post("/v1/chat", json={"session_id": "cli:1", "text": "ping"})
        assert chat.status_code == 503
        payload = chat.json()
        text = str(payload.get("error", "")).lower()
        assert "openai" in text
        assert "30.0s" in text
    assert "protection mode" in text


def test_gateway_provider_error_payload_quota_429_is_specific(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)

    async def _raise_provider(*, session_id: str, user_text: str):
        raise RuntimeError("provider_http_error:429:insufficient_quota: billing exhausted")

    app.state.runtime.engine.run = _raise_provider

    with TestClient(app) as client:
        chat = client.post("/v1/chat", json={"session_id": "cli:1", "text": "ping"})
        assert chat.status_code == 429
        payload = chat.json()
        text = str(payload.get("error", "")).lower()
        assert "quota" in text
        assert "billing" in text


def test_gateway_provider_error_payload_http_401_includes_provider_guidance(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        provider={"model": "openai/gpt-4.1-mini"},
        channels={},
    )
    app = create_app(cfg)
    app.state.runtime.engine.provider = SimpleNamespace(provider_name="openai", model="openai/gpt-4.1-mini")

    async def _raise_provider(*, session_id: str, user_text: str):
        raise RuntimeError("provider_http_error:401")

    app.state.runtime.engine.run = _raise_provider

    with TestClient(app) as client:
        chat = client.post("/v1/chat", json={"session_id": "cli:1", "text": "ping"})
        assert chat.status_code == 502
        payload = chat.json()
        text = str(payload.get("error", "")).lower()
        assert "openai" in text
        assert "gpt-4o-mini" in text
        assert "billing" in text


def test_gateway_provider_error_payload_ollama_model_missing_is_actionable(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        provider={"model": "openai/llama3.2"},
        channels={},
    )
    app = create_app(cfg)
    app.state.runtime.engine.provider = SimpleNamespace(provider_name="ollama", model="openai/llama3.2")

    async def _raise_provider(*, session_id: str, user_text: str):
        raise RuntimeError("provider_config_error:ollama_model_missing:llama3.2")

    app.state.runtime.engine.run = _raise_provider

    with TestClient(app) as client:
        chat = client.post("/v1/chat", json={"session_id": "cli:1", "text": "ping"})
        assert chat.status_code == 400
        payload = chat.json()
        text = str(payload.get("error", "")).lower()
        assert "ollama" in text
        assert "ollama pull llama3.2" in text


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


def test_run_heartbeat_prunes_expired_sessions_before_provider_call() -> None:
    calls: list[tuple[str, int]] = []

    class _Sessions:
        def prune_expired(self) -> int:
            calls.append(("prune", len(calls)))
            return 2

    class _Engine:
        def __init__(self) -> None:
            self.sessions = _Sessions()

        async def run(self, *, session_id: str, user_text: str):
            calls.append((session_id, len(user_text)))
            return SimpleNamespace(text="HEARTBEAT_OK")

    async def _scenario() -> None:
        runtime = SimpleNamespace(engine=_Engine())
        decision = await _run_heartbeat(runtime)
        assert decision.reason == "heartbeat_ok"
        assert calls[0] == ("prune", 0)
        assert calls[1][0] == "heartbeat:system"

    asyncio.run(_scenario())


def test_run_heartbeat_contract_runs_on_actionable_output(tmp_path: Path) -> None:
    history_path = tmp_path / "memory.jsonl"
    history_path.write_text(
        json.dumps({"source": "session:telegram:chat42", "created_at": "2026-03-05T00:00:00+00:00"}) + "\n",
        encoding="utf-8",
    )

    class _Memory:
        def __init__(self, path: Path) -> None:
            self.history_path = path

    class _Engine:
        def __init__(self) -> None:
            self.memory = _Memory(history_path)

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


def test_run_heartbeat_prefers_telegram_route_over_newer_cli_history(tmp_path: Path) -> None:
    _LATEST_MEMORY_ROUTE_CACHE.clear()
    history_path = tmp_path / "memory.jsonl"
    history_path.write_text(
        "\n".join(
            [
                json.dumps({"source": "session:telegram:chat42", "created_at": "2026-03-05T00:00:00+00:00"}),
                json.dumps({"source": "session:cli:profile", "created_at": "2026-03-06T00:00:00+00:00"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    class _Memory:
        def __init__(self, path: Path) -> None:
            self.history_path = path

    class _Engine:
        def __init__(self) -> None:
            self.memory = _Memory(history_path)

        async def run(self, *, session_id: str, user_text: str):
            del session_id, user_text
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
        assert "Current time:" in user_text

    asyncio.run(_scenario())


def test_run_heartbeat_skips_effectively_empty_workspace_heartbeat(tmp_path: Path) -> None:
    loader = WorkspaceLoader(workspace_path=tmp_path / "ws")
    loader.bootstrap()
    (tmp_path / "ws" / "HEARTBEAT.md").write_text("# Heartbeat\n\n- [ ]\n", encoding="utf-8")

    class _Engine:
        def __init__(self) -> None:
            self.calls = 0

        async def run(self, *, session_id: str, user_text: str):
            del session_id, user_text
            self.calls += 1
            return SimpleNamespace(text="HEARTBEAT_OK")

    async def _scenario() -> None:
        engine = _Engine()
        runtime = SimpleNamespace(engine=engine, workspace=loader)

        decision = await _run_heartbeat(runtime)

        assert decision.action == "skip"
        assert decision.reason == "heartbeat_empty"
        assert engine.calls == 0

    asyncio.run(_scenario())


def test_run_heartbeat_appends_current_time_line_with_workspace_timezone(tmp_path: Path) -> None:
    loader = WorkspaceLoader(workspace_path=tmp_path / "ws")
    loader.bootstrap(variables={"user_timezone": "America/Sao_Paulo"})

    class _Engine:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def run(self, *, session_id: str, user_text: str):
            del session_id
            self.calls.append(user_text)
            return SimpleNamespace(text="HEARTBEAT_OK")

    async def _scenario() -> None:
        engine = _Engine()
        runtime = SimpleNamespace(engine=engine, workspace=loader)

        decision = await _run_heartbeat(runtime)

        assert decision.reason == "heartbeat_ok"
        assert engine.calls
        assert "Current time:" in engine.calls[0]
        assert "America/Sao_Paulo" in engine.calls[0]

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


def test_run_proactive_monitor_sends_next_step_query_proactive_suggestion(tmp_path: Path) -> None:
    history_path = tmp_path / "memory.jsonl"
    history_path.write_text(
        json.dumps({"source": "session:telegram:chat42", "created_at": "2026-03-05T00:00:00+00:00"}) + "\n",
        encoding="utf-8",
    )

    class _Memory:
        def __init__(self, path: Path) -> None:
            self.history_path = path

        async def retrieve(self, query: str, *, method: str = "rag", limit: int = 5):
            assert query
            assert method == "llm"
            assert limit == 5
            return {
                "status": "ok",
                "method": "llm",
                "next_step_query": "Should we confirm the deployment owner?",
            }

    class _Engine:
        def __init__(self) -> None:
            self.memory = _Memory(history_path)

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


def test_run_proactive_monitor_next_step_prefers_telegram_route_over_newer_cli_history(tmp_path: Path) -> None:
    _LATEST_MEMORY_ROUTE_CACHE.clear()
    history_path = tmp_path / "memory.jsonl"
    history_path.write_text(
        "\n".join(
            [
                json.dumps({"source": "session:telegram:chat42", "created_at": "2026-03-05T00:00:00+00:00"}),
                json.dumps({"source": "session:cli:profile", "created_at": "2026-03-06T00:00:00+00:00"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    class _Memory:
        def __init__(self, path: Path) -> None:
            self.history_path = path

        async def retrieve(self, query: str, *, method: str = "rag", limit: int = 5):
            assert query
            assert method == "llm"
            assert limit == 5
            return {
                "status": "ok",
                "method": "llm",
                "next_step_query": "Should we confirm the deployment owner?",
            }

    class _Engine:
        def __init__(self) -> None:
            self.memory = _Memory(history_path)

    class _Monitor:
        async def scan(self):
            return []

        def should_deliver(self, suggestion, *, min_priority: float = 0.0) -> bool:
            return float(getattr(suggestion, "priority", 0.0) or 0.0) >= float(min_priority)

        def mark_delivered(self, suggestion) -> bool:
            del suggestion
            return True

        def mark_failed(self, suggestion, *, error: str = "") -> bool:
            del suggestion, error
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


def test_run_proactive_monitor_replays_retryable_failed_suggestions(tmp_path: Path) -> None:
    async def _scenario() -> None:
        store = MemoryStore(tmp_path / "memory.jsonl")
        monitor = MemoryMonitor(store, retry_backoff_seconds=0.0, max_retry_attempts=3)
        suggestion = MemorySuggestion(
            text="Pending task with no updates for 2 day(s): revisar rollout",
            priority=0.85,
            trigger="pending_task",
            channel="telegram",
            target="chat42",
        )
        row = suggestion.to_payload()
        row["status"] = "failed"
        row["failure_count"] = 1
        row["failed_at"] = "2026-03-06T00:00:00+00:00"
        row["retry_after_at"] = "2026-03-06T00:00:00+00:00"
        monitor._write_pending_payload(
            [row]
        )
        channels = SimpleNamespace(send=AsyncMock(return_value="msg-1"))
        runtime = SimpleNamespace(engine=SimpleNamespace(memory=None), channels=channels, memory_monitor=monitor)

        result = await _run_proactive_monitor(runtime)

        assert result["status"] == "ok"
        assert result["delivered"] == 1
        assert result["replayed"] == 1
        channels.send.assert_awaited_once()
        assert json.loads(monitor.suggestions_path.read_text(encoding="utf-8"))[0]["status"] == "delivered"

    asyncio.run(_scenario())


def test_gateway_startup_replays_failed_memory_suggestions(tmp_path: Path) -> None:
    memory_home = tmp_path / "memory"
    memory_home.mkdir(parents=True, exist_ok=True)
    suggestions_path = memory_home / "suggestions_pending.json"
    suggestion = MemorySuggestion(
        text="Upcoming birthday in 1 day(s): Ana",
        priority=0.9,
        trigger="upcoming_event",
        channel="telegram",
        target="chat42",
        metadata={"days_until": 1},
    )
    row = suggestion.to_payload()
    row["status"] = "failed"
    row["failure_count"] = 1
    row["failed_at"] = "2026-03-06T00:00:00+00:00"
    row["retry_after_at"] = "2026-03-06T00:00:00+00:00"
    suggestions_path.write_text(
        json.dumps([row]) + "\n",
        encoding="utf-8",
    )

    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        agents={"defaults": {"memory": {"proactive": True, "proactive_retry_backoff_s": 0, "proactive_max_retry_attempts": 3}}},
        gateway={"heartbeat": {"enabled": False}, "diagnostics": {"enabled": True, "require_auth": False}},
        channels={},
    )
    app = create_app(cfg)
    app.state.runtime.channels.send = AsyncMock(return_value="ok")

    with TestClient(app) as client:
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            payload = client.get("/v1/diagnostics").json()
            runner = payload["memory_monitor"]["runner"]
            if app.state.runtime.channels.send.await_count >= 1 and int(runner.get("replayed_count", 0) or 0) >= 1:
                break
            time.sleep(0.05)

        send_kwargs = app.state.runtime.channels.send.await_args.kwargs
        assert send_kwargs["channel"] == "telegram"
        assert send_kwargs["target"] == "chat42"
        assert "Upcoming birthday in 1 day(s): Ana" in str(send_kwargs["text"])
        payload = json.loads(suggestions_path.read_text(encoding="utf-8"))
        assert payload[0]["status"] == "delivered"


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

        unauthorized_tools_catalog = client.get("/v1/tools/catalog")
        assert unauthorized_tools_catalog.status_code == 401
        assert unauthorized_tools_catalog.json()["error"] == "gateway_auth_required"
        assert unauthorized_tools_catalog.json()["code"] == "gateway_auth_required"

        unauthorized_tools_catalog_alias = client.get("/api/tools/catalog")
        assert unauthorized_tools_catalog_alias.status_code == 401
        assert unauthorized_tools_catalog_alias.json()["error"] == "gateway_auth_required"
        assert unauthorized_tools_catalog_alias.json()["code"] == "gateway_auth_required"

        unauthorized_dashboard_state = client.get("/api/dashboard/state")
        assert unauthorized_dashboard_state.status_code == 401
        assert unauthorized_dashboard_state.json()["error"] == "gateway_auth_required"
        assert unauthorized_dashboard_state.json()["code"] == "gateway_auth_required"

        unauthorized_chat = client.post("/v1/chat", json={"session_id": "cli:1", "text": "ping"})
        assert unauthorized_chat.status_code == 401
        assert unauthorized_chat.json()["error"] == "gateway_auth_required"
        assert unauthorized_chat.json()["code"] == "gateway_auth_required"

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

        tools_catalog = client.get("/v1/tools/catalog", headers={"Authorization": "Bearer secret-token"})
        assert tools_catalog.status_code == 200
        tools_catalog_alias = client.get("/api/tools/catalog", headers={"Authorization": "Bearer secret-token"})
        assert tools_catalog_alias.status_code == 200
        assert tools_catalog_alias.json() == tools_catalog.json()

        dashboard_state = client.get("/api/dashboard/state", headers={"Authorization": "Bearer secret-token"})
        assert dashboard_state.status_code == 200

        chat = client.post(
            "/v1/chat",
            headers={"Authorization": "Bearer secret-token"},
            json={"session_id": "cli:1", "text": "ping"},
        )
        assert chat.status_code == 200
        assert chat.json()["text"] == "pong"


def test_gateway_dashboard_session_scopes_to_dashboard_surfaces(tmp_path: Path) -> None:
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
        missing_client = client.post("/api/dashboard/session", headers={"Authorization": "Bearer secret-token"})
        assert missing_client.status_code == 400
        assert missing_client.json()["error"] == "dashboard_client_required"

        missing = client.post("/api/dashboard/session")
        assert missing.status_code == 401
        assert missing.json()["error"] == "gateway_auth_required"

        query_denied = client.post("/api/dashboard/session?token=secret-token")
        assert query_denied.status_code == 401
        assert query_denied.json()["error"] == "gateway_auth_required"

        client_id = "dshc1.alpha-client"
        handoff = issue_dashboard_handoff(gateway_token="secret-token")
        minted = client.post(
            "/api/dashboard/session",
            headers={
                "X-ClawLite-Dashboard-Handoff": handoff.token,
                "X-ClawLite-Dashboard-Client": client_id,
            },
        )
        assert minted.status_code == 200
        payload = minted.json()
        assert payload["ok"] is True
        assert payload["token_type"] == "dashboard_session"
        assert payload["bootstrap_kind"] == "dashboard_handoff"
        assert payload["session_token"].startswith("dshs1.")
        assert payload["handoff_header_name"] == "X-ClawLite-Dashboard-Handoff"
        assert payload["handoff_query_param"] == "dashboard_handoff"
        assert payload["client_header_name"] == "X-ClawLite-Dashboard-Client"
        assert payload["client_query_param"] == "dashboard_client"
        session_headers = {
            payload["header_name"]: payload["session_token"],
            payload["client_header_name"]: client_id,
        }

        api_status = client.get("/api/status", headers=session_headers)
        assert api_status.status_code == 200
        assert api_status.json()["auth"]["dashboard_session_enabled"] is True
        assert api_status.json()["auth"]["dashboard_handoff_enabled"] is True
        assert api_status.json()["auth"]["dashboard_handoff_header_name"] == "X-ClawLite-Dashboard-Handoff"
        assert api_status.json()["auth"]["dashboard_client_header_name"] == "X-ClawLite-Dashboard-Client"

        dashboard_state = client.get("/api/dashboard/state", headers=session_headers)
        assert dashboard_state.status_code == 200

        api_token = client.get("/api/token", headers=session_headers)
        assert api_token.status_code == 200
        assert api_token.json()["dashboard_handoff_enabled"] is True
        assert api_token.json()["dashboard_handoff_header_name"] == "X-ClawLite-Dashboard-Handoff"
        assert api_token.json()["dashboard_handoff_query_param"] == "dashboard_handoff"
        assert api_token.json()["dashboard_session_enabled"] is True
        assert api_token.json()["dashboard_client_header_name"] == "X-ClawLite-Dashboard-Client"
        assert api_token.json()["dashboard_client_query_param"] == "dashboard_client"

        api_tools = client.get("/api/tools/catalog", headers=session_headers)
        assert api_tools.status_code == 200

        api_message = client.post(
            "/api/message",
            headers=session_headers,
            json={"session_id": "dashboard:test", "text": "ping"},
        )
        assert api_message.status_code == 200
        assert api_message.json()["text"] == "pong"

        v1_status = client.get("/v1/status", headers=session_headers)
        assert v1_status.status_code == 401
        assert v1_status.json()["error"] == "gateway_auth_required"

        v1_tools = client.get("/v1/tools/catalog", headers=session_headers)
        assert v1_tools.status_code == 401
        assert v1_tools.json()["error"] == "gateway_auth_required"

        v1_chat = client.post(
            "/v1/chat",
            headers=session_headers,
            json={"session_id": "dashboard:test", "text": "ping"},
        )
        assert v1_chat.status_code == 401
        assert v1_chat.json()["error"] == "gateway_auth_required"


def test_gateway_dashboard_handoff_is_single_use(tmp_path: Path) -> None:
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
        handoff = issue_dashboard_handoff(gateway_token="secret-token")

        first = client.post(
            "/api/dashboard/session",
            headers={
                "X-ClawLite-Dashboard-Handoff": handoff.token,
                "X-ClawLite-Dashboard-Client": "dshc1.alpha-client",
            },
        )
        assert first.status_code == 200
        assert first.json()["bootstrap_kind"] == "dashboard_handoff"

        replay_same_client = client.post(
            "/api/dashboard/session",
            headers={
                "X-ClawLite-Dashboard-Handoff": handoff.token,
                "X-ClawLite-Dashboard-Client": "dshc1.alpha-client",
            },
        )
        assert replay_same_client.status_code == 401
        assert replay_same_client.json()["error"] == "gateway_auth_invalid"

        replay_other_client = client.post(
            "/api/dashboard/session",
            headers={
                "X-ClawLite-Dashboard-Handoff": handoff.token,
                "X-ClawLite-Dashboard-Client": "dshc1.beta-client",
            },
        )
        assert replay_other_client.status_code == 401
        assert replay_other_client.json()["error"] == "gateway_auth_invalid"


def test_gateway_dashboard_session_alias_ws_only_and_not_chainable(tmp_path: Path) -> None:
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
        client_id = "dshc1.alpha-client"
        handoff = issue_dashboard_handoff(gateway_token="secret-token")
        minted = client.post(
            "/api/dashboard/session",
            headers={
                "X-ClawLite-Dashboard-Handoff": handoff.token,
                "X-ClawLite-Dashboard-Client": client_id,
            },
        )
        assert minted.status_code == 200
        payload = minted.json()
        session_headers = {
            payload["header_name"]: payload["session_token"],
            payload["client_header_name"]: client_id,
        }

        nested = client.post("/api/dashboard/session", headers=session_headers)
        assert nested.status_code == 401
        assert nested.json()["error"] == "gateway_auth_required"

        invalid = client.get(
            "/api/status",
            headers={
                payload["header_name"]: "dshs1.invalid",
                payload["client_header_name"]: client_id,
            },
        )
        assert invalid.status_code == 401
        assert invalid.json()["error"] == "gateway_auth_invalid"

        mismatched_client = client.get(
            "/api/status",
            headers={
                payload["header_name"]: payload["session_token"],
                payload["client_header_name"]: "dshc1.other-client",
            },
        )
        assert mismatched_client.status_code == 401
        assert mismatched_client.json()["error"] == "gateway_auth_invalid"

        with client.websocket_connect(
            f"/ws?{payload['query_param']}={payload['session_token']}&{payload['client_query_param']}={client_id}"
        ) as socket:
            _assert_connect_challenge(socket)
            socket.send_json({"session_id": "dashboard:ws", "text": "ping"})
            response = socket.receive_json()
            assert response["text"] == "pong"

        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(
                f"/v1/ws?{payload['query_param']}={payload['session_token']}&{payload['client_query_param']}={client_id}"
            ):
                pass

        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(
                f"/ws?{payload['query_param']}={payload['session_token']}&{payload['client_query_param']}=dshc1.other-client"
            ):
                pass


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


def test_gateway_auth_keeps_loopback_health_and_assets_open_with_mode_off(tmp_path: Path) -> None:
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
        health = client.get("/health")
        assert health.status_code == 200

        root = client.get("/")
        assert root.status_code == 200

        asset = client.get("/_clawlite/dashboard.js")
        assert asset.status_code == 200

        status = client.get("/v1/status")
        assert status.status_code == 401
        assert status.json()["error"] == "gateway_auth_required"

        dashboard_state = client.get("/api/dashboard/state")
        assert dashboard_state.status_code == 401
        assert dashboard_state.json()["error"] == "gateway_auth_required"

        chat = client.post("/v1/chat", json={"session_id": "cli:1", "text": "ping"})
        assert chat.status_code == 401
        assert chat.json()["error"] == "gateway_auth_required"

        authorized_status = client.get("/v1/status", headers={"Authorization": "Bearer secret-token"})
        assert authorized_status.status_code == 200
        payload = authorized_status.json()
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
        assert not bootstrap_file.exists()

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


def test_gateway_ws_chat_rate_limit_blocks_second_legacy_message(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={
            "rate_limit": {
                "window_s": 60,
                "chat_requests_per_window": 0,
                "ws_chat_requests_per_window": 1,
            }
        },
        channels={},
    )
    app = create_app(cfg)
    app.state.runtime.engine.provider = FakeProvider()

    with TestClient(app) as client:
        with client.websocket_connect("/v1/ws") as socket:
            _assert_connect_challenge(socket)
            socket.send_json({"session_id": "cli:ws", "text": "ping"})
            first = socket.receive_json()
            assert first["text"] == "pong"

            socket.send_json({"session_id": "cli:ws", "text": "ping again"})
            blocked = socket.receive_json()
            assert blocked["type"] == "error"
            assert blocked["error"] == "gateway_rate_limited"
            assert blocked["status_code"] == 429
            assert blocked["retry_after_s"] > 0


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


def test_gateway_ws_requires_token_when_configured_even_on_loopback(tmp_path: Path) -> None:
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
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/v1/ws"):
                pass

        with client.websocket_connect("/v1/ws?token=secret-token") as socket:
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


def test_gateway_ws_message_timeout_returns_provider_style_error(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={"heartbeat": {"enabled": False}},
        channels={},
    )
    app = create_app(cfg)

    async def _slow_run(*, session_id: str, user_text: str):
        del session_id, user_text
        await asyncio.sleep(0.05)
        return SimpleNamespace(text="late", model="fake/test")

    app.state.runtime.engine.run = _slow_run

    with patch.object(gateway_server, "GATEWAY_CHAT_WS_ENGINE_TIMEOUT_S", new=0.01):
        with TestClient(app) as client:
            with client.websocket_connect("/ws") as socket:
                _assert_connect_challenge(socket)
                socket.send_json(
                    {
                        "type": "message",
                        "session_id": "cli:ws-timeout",
                        "text": "ping",
                        "request_id": "req-timeout",
                    }
                )
                payload = socket.receive_json()

    assert payload == {
        "type": "error",
        "error": "engine_run_timeout",
        "status_code": 504,
        "request_id": "req-timeout",
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

            socket.send_json({"type": "req", "id": "tc1", "method": "tools.catalog", "params": {}})
            tools_catalog_payload = socket.receive_json()
            assert tools_catalog_payload["type"] == "res"
            assert tools_catalog_payload["id"] == "tc1"
            assert tools_catalog_payload["ok"] is True
            assert "groups" in tools_catalog_payload["result"]
            assert tools_catalog_payload["result"]["aliases"]["bash"] == "exec"
            assert "tools.catalog" in tools_catalog_payload["result"]["ws_methods"]

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


def test_gateway_ws_req_streams_chunks_before_final_response(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)

    seen: list[dict[str, Any]] = []

    async def _fake_stream_run(
        *,
        session_id: str,
        user_text: str,
        channel: str | None = None,
        chat_id: str | None = None,
        runtime_metadata: dict[str, Any] | None = None,
    ):
        assert session_id == "cli:req-stream"
        assert user_text == "ping"
        seen.append(
            {
                "channel": channel,
                "chat_id": chat_id,
                "runtime_metadata": runtime_metadata,
            }
        )
        yield ProviderChunk(text="po", accumulated="po", done=False)
        yield ProviderChunk(text="ng", accumulated="pong", done=True)

    app.state.runtime.engine.stream_run = _fake_stream_run

    with TestClient(app) as client:
        with client.websocket_connect("/ws") as socket:
            _assert_connect_challenge(socket)
            socket.send_json({"type": "req", "id": "c1", "method": "connect", "params": {}})
            connect_payload = socket.receive_json()
            assert connect_payload["ok"] is True

            socket.send_json(
                {
                    "type": "req",
                    "id": "m-stream",
                    "method": "chat.send",
                    "params": {
                        "sessionId": "cli:req-stream",
                        "text": "ping",
                        "stream": True,
                        "channel": "telegram",
                        "chatId": 123,
                        "runtimeMetadata": {"reply_to_message_id": "456"},
                    },
                }
            )
            chunk_one = socket.receive_json()
            final_payload = socket.receive_json()

    assert seen == [
        {
            "channel": "telegram",
            "chat_id": "123",
            "runtime_metadata": {"reply_to_message_id": "456"},
        }
    ]
    assert chunk_one == {
        "type": "event",
        "event": "chat.chunk",
        "id": "m-stream",
        "params": {
            "session_id": "cli:req-stream",
            "text": "pong",
            "accumulated": "pong",
            "done": True,
            "degraded": False,
        },
    }
    assert final_payload == {
        "type": "res",
        "id": "m-stream",
        "ok": True,
        "result": {
            "session_id": "cli:req-stream",
            "text": "pong",
            "model": "",
        },
    }


def test_gateway_ws_req_respects_websocket_coalescing_config(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
        gateway={"websocket": {"coalesce_enabled": False}},
    )
    app = create_app(cfg)

    async def _fake_stream_run(
        *,
        session_id: str,
        user_text: str,
        channel: str | None = None,
        chat_id: str | None = None,
        runtime_metadata: dict[str, Any] | None = None,
    ):
        del session_id, user_text, channel, chat_id, runtime_metadata
        yield ProviderChunk(text="po", accumulated="po", done=False)
        yield ProviderChunk(text="ng", accumulated="pong", done=True)

    app.state.runtime.engine.stream_run = _fake_stream_run

    with TestClient(app) as client:
        with client.websocket_connect("/ws") as socket:
            _assert_connect_challenge(socket)
            socket.send_json({"type": "req", "id": "c1", "method": "connect", "params": {}})
            connect_payload = socket.receive_json()
            assert connect_payload["ok"] is True

            socket.send_json(
                {
                    "type": "req",
                    "id": "m-stream-raw",
                    "method": "chat.send",
                    "params": {
                        "sessionId": "cli:req-stream-raw",
                        "text": "ping",
                        "stream": True,
                    },
                }
            )
            chunk_one = socket.receive_json()
            chunk_two = socket.receive_json()
            final_payload = socket.receive_json()

    assert chunk_one == {
        "type": "event",
        "event": "chat.chunk",
        "id": "m-stream-raw",
        "params": {
            "session_id": "cli:req-stream-raw",
            "text": "po",
            "accumulated": "po",
            "done": False,
            "degraded": False,
        },
    }
    assert chunk_two == {
        "type": "event",
        "event": "chat.chunk",
        "id": "m-stream-raw",
        "params": {
            "session_id": "cli:req-stream-raw",
            "text": "ng",
            "accumulated": "pong",
            "done": True,
            "degraded": False,
        },
    }
    assert final_payload == {
        "type": "res",
        "id": "m-stream-raw",
        "ok": True,
        "result": {
            "session_id": "cli:req-stream-raw",
            "text": "pong",
            "model": "",
        },
    }


def test_gateway_ws_req_respects_websocket_coalescing_profile(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
        gateway={"websocket": {"coalesce_profile": "newline", "coalesce_min_chars": 8}},
    )
    app = create_app(cfg)

    async def _fake_stream_run(
        *,
        session_id: str,
        user_text: str,
        channel: str | None = None,
        chat_id: str | None = None,
        runtime_metadata: dict[str, Any] | None = None,
    ):
        del session_id, user_text, channel, chat_id, runtime_metadata
        yield ProviderChunk(text="Hello world.", accumulated="Hello world.", done=False)
        yield ProviderChunk(text="\n", accumulated="Hello world.\n", done=False)
        yield ProviderChunk(text="Next line done", accumulated="Hello world.\nNext line done", done=True)

    app.state.runtime.engine.stream_run = _fake_stream_run

    with TestClient(app) as client:
        with client.websocket_connect("/ws") as socket:
            _assert_connect_challenge(socket)
            socket.send_json({"type": "req", "id": "c1", "method": "connect", "params": {}})
            connect_payload = socket.receive_json()
            assert connect_payload["ok"] is True

            socket.send_json(
                {
                    "type": "req",
                    "id": "m-stream-newline",
                    "method": "chat.send",
                    "params": {
                        "sessionId": "cli:req-stream-newline",
                        "text": "ping",
                        "stream": True,
                    },
                }
            )
            chunk_one = socket.receive_json()
            chunk_two = socket.receive_json()
            final_payload = socket.receive_json()

    assert chunk_one == {
        "type": "event",
        "event": "chat.chunk",
        "id": "m-stream-newline",
        "params": {
            "session_id": "cli:req-stream-newline",
            "text": "Hello world.\n",
            "accumulated": "Hello world.\n",
            "done": False,
            "degraded": False,
        },
    }
    assert chunk_two == {
        "type": "event",
        "event": "chat.chunk",
        "id": "m-stream-newline",
        "params": {
            "session_id": "cli:req-stream-newline",
            "text": "Next line done",
            "accumulated": "Hello world.\nNext line done",
            "done": True,
            "degraded": False,
        },
    }
    assert final_payload == {
        "type": "res",
        "id": "m-stream-newline",
        "ok": True,
        "result": {
            "session_id": "cli:req-stream-newline",
            "text": "Hello world.\nNext line done",
            "model": "",
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
            challenge = _assert_connect_challenge(socket)
            connection_id = str(challenge["params"]["connection_id"])

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
        assert ws_payload["last_connection_id"] == connection_id
        assert ws_payload["last_connection_path"] == "/ws"
        assert ws_payload["last_connection_opened_at"]
        assert ws_payload["last_connection_closed_id"] == connection_id
        assert ws_payload["last_connection_closed_at"]
        assert ws_payload["last_request_id"] == "u1"
        assert ws_payload["last_error_connection_id"] == connection_id
        assert ws_payload["last_error_request_id"] == "u1"
        assert ws_payload["last_error_at"]
        assert ws_payload["last_error_code"] == "unsupported_method"
        assert "unsupported req method" in ws_payload["last_error_message"]
        assert ws_payload["last_error_status"] == 400
        assert ws_payload["by_path"]["/ws"] >= 1
        assert ws_payload["by_message_type_in"]["req"] >= 3
        assert ws_payload["by_message_type_out"]["event"] >= 1
        assert ws_payload["by_message_type_out"]["res"] >= 3
        assert ws_payload["req_methods"]["connect"] >= 1
        assert ws_payload["req_methods"]["ping"] >= 1
        assert ws_payload["req_methods"]["unsupported.method"] >= 1
        assert ws_payload["error_codes"]["unsupported_method"] >= 1


def test_gateway_ws_error_logs_include_connection_and_request_ids(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)

    async def _boom(*, session_id: str, user_text: str, channel=None, chat_id=None, runtime_metadata=None):
        del session_id, user_text, channel, chat_id, runtime_metadata
        raise RuntimeError("ws_boom")

    app.state.runtime.engine.run = _boom

    rows: list[str] = []
    sink_id = logger.add(rows.append, format=logging_utils._text_format)
    try:
        with TestClient(app) as client:
            with client.websocket_connect("/v1/ws") as socket:
                challenge = _assert_connect_challenge(socket)
                connection_id = str(challenge["params"]["connection_id"])
                socket.send_json(
                    {
                        "type": "message",
                        "session_id": "cli:ws-log",
                        "text": "ping",
                        "request_id": "req-log-1",
                    }
                )
                payload = socket.receive_json()
                assert payload["error"] == "Internal failure while processing the request."
                assert payload["request_id"] == "req-log-1"
    finally:
        logger.remove(sink_id)

    joined = "\n".join(rows)
    assert "[gateway.ws]" in joined.lower()
    assert f"connection_id={connection_id}" in joined
    assert "request_id=req-log-1" in joined
    assert "status=500" in joined


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
        assert "delivery_replay" in payload["control_plane"]["components"]
        assert "inbound_replay" in payload["control_plane"]["components"]
        assert "wake_replay" in payload["control_plane"]["components"]
        assert "wake_pressure" in payload["control_plane"]["components"]
        assert "queue" in payload
        assert "dead_letter_recent" in payload["queue"]
        assert isinstance(payload["queue"]["dead_letter_recent"], list)
        assert "channels" in payload
        assert "channels_delivery" in payload
        assert "channels_inbound" in payload
        channels_delivery = payload["channels_delivery"]
        channels_inbound = payload["channels_inbound"]
        assert set(channels_delivery.keys()) >= {"total", "per_channel", "recent"}
        assert "persistence" in channels_delivery
        assert set(channels_inbound.keys()) >= {"persistence"}
        assert "startup_replay" in channels_inbound["persistence"]
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
        assert "wake_policy" in payload["cron"]
        assert set(payload["cron"].keys()) >= {
            "last_job_status",
            "last_job_trigger",
            "last_job_lag_s",
            "overdue_run_count",
        }
        assert "heartbeat" in payload
        assert set(payload["heartbeat"].keys()) >= {
            "wake_backpressure_count",
            "wake_pressure_by_reason",
            "last_pressure_reason",
            "last_pressure_at",
        }
        assert "bootstrap" in payload
        assert "pending" in payload["bootstrap"]
        assert "workspace" in payload
        assert "critical_files" in payload["workspace"]
        assert set(payload["workspace"]["critical_files"].keys()) >= {"IDENTITY.md", "SOUL.md", "USER.md"}
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
            "reasoning_layers",
            "recommendations",
        }
        assert set(memory_quality["report"]["reasoning_layers"].keys()) >= {
            "distribution",
            "weakest_layer",
            "confidence",
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
        expected_engine = _normalized_diagnostics_engine_payload(dict(payload["engine"]))
        actual_engine = _normalized_diagnostics_engine_payload(dict(alias_payload["engine"]))
        assert actual_engine == expected_engine
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


def test_gateway_runtime_repairs_workspace_core_docs_and_surfaces_health(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "SOUL.md").write_bytes(b"\x00bad-soul")
    (workspace / "USER.md").write_text("", encoding="utf-8")

    cfg = AppConfig(
        workspace_path=str(workspace),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={
            "heartbeat": {"enabled": False},
            "diagnostics": {"enabled": True, "require_auth": False},
        },
        channels={},
    )
    app = create_app(cfg)

    with TestClient(app) as client:
        payload = client.get("/v1/diagnostics").json()

    workspace_payload = payload["workspace"]
    assert workspace_payload["repaired_count"] >= 2
    assert workspace_payload["critical_files"]["SOUL.md"]["repaired"] is True
    assert workspace_payload["critical_files"]["SOUL.md"]["issue"] == "corrupt"
    assert workspace_payload["critical_files"]["SOUL.md"]["backup_path"]
    assert workspace_payload["critical_files"]["USER.md"]["repaired"] is True
    assert workspace_payload["critical_files"]["USER.md"]["issue"] == "empty"
    assert "## Core Values" in (workspace / "SOUL.md").read_text(encoding="utf-8")
    assert "Preferences:" in (workspace / "USER.md").read_text(encoding="utf-8")


def test_gateway_channel_recovery_notice_uses_runtime_send(tmp_path: Path) -> None:
    RecoveringGatewayChannel.starts = 0
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={
            "heartbeat": {"enabled": False},
            "diagnostics": {"enabled": True, "require_auth": False},
        },
        channels={
            "recovery_interval_s": 0.01,
            "recovery_cooldown_s": 0.0,
            "fake": {"enabled": True},
        },
    )
    app = create_app(cfg)
    app.state.runtime.channels.register("fake", RecoveringGatewayChannel)
    app.state.runtime.channels.send = AsyncMock(return_value="ok")

    with TestClient(app) as client:
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            payload = client.get("/v1/diagnostics").json()
            fake_status = payload["channels"].get("fake", {})
            recovery = fake_status.get("recovery", {}) if isinstance(fake_status, dict) else {}
            if app.state.runtime.channels.send.await_count >= 1 and int(recovery.get("success", 0) or 0) >= 1:
                break
            time.sleep(0.05)

        send_kwargs = app.state.runtime.channels.send.await_args.kwargs
        metadata = dict(send_kwargs["metadata"])
        assert metadata["source"] == "channel_recovery"
        assert metadata["autonomy_notice"] is True
        assert metadata["recovery_channel"] == "fake"
        assert metadata["recovery_status"] == "recovered"
        assert "Autonomy notice: channel fake recovered." in str(send_kwargs["text"])
        autonomy_recent = payload["autonomy_log"]["recent"]
        assert any(
            str(row.get("action", "")) == "channel_recovery"
            and str(row.get("status", "")) == "recovered"
            and str((row.get("metadata", {}) or {}).get("channel", "")) == "fake"
            for row in autonomy_recent
        )
        assert any(
            str(row.get("action", "")) == "channel_recovery_notice"
            and str(row.get("status", "")) == "sent"
            for row in autonomy_recent
        )


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
        deadline = time.monotonic() + 5.0
        payload: dict[str, object] = {}
        while time.monotonic() < deadline:
            payload = client.get("/v1/diagnostics").json()
            first_last_action_at = str(fake_memory.tuning.get("last_action_at", "") or "")
            if int(payload["memory_quality_tuning"]["ticks"]) >= 1 and first_last_action_at:
                break
            time.sleep(0.05)

        assert first_last_action_at

        final_payload = payload
        cooldown_seen = False
        deadline = time.monotonic() + 6.0
        while time.monotonic() < deadline:
            final_payload = client.get("/v1/diagnostics").json()
            ticks = int(final_payload["memory_quality_tuning"]["ticks"])
            skipped_entries = [
                entry
                for entry in fake_memory.tuning.get("recent_actions", [])
                if isinstance(entry, dict) and str(entry.get("status", "")) == "cooldown_skipped"
            ]
            if ticks >= 2 and skipped_entries:
                cooldown_seen = True
                break
            time.sleep(0.05)

        assert cooldown_seen is True
        assert int(final_payload["memory_quality_tuning"]["ticks"]) >= 2
        skipped_entries = [
            entry
            for entry in fake_memory.tuning.get("recent_actions", [])
            if isinstance(entry, dict) and str(entry.get("status", "")) == "cooldown_skipped"
        ]
        assert skipped_entries
        assert str(fake_memory.tuning.get("last_action_at", "") or "") == first_last_action_at


def test_gateway_tuning_loop_stage18_fact_layer_backfill_uses_layer_specific_limit_metadata(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={
            "heartbeat": {"enabled": False},
            "diagnostics": {"enabled": True, "require_auth": False},
            "autonomy": {
                "tuning_loop_enabled": True,
                "tuning_degrading_streak_threshold": 2,
                "tuning_loop_cooldown_s": 0,
            },
        },
        channels={},
    )
    cfg.gateway.autonomy.tuning_loop_interval_s = 1
    app = create_app(cfg)
    fake_memory = _FakeTuningMemory(degrade=True, weakest_layer="fact", degrade_score=70)
    backfill_calls: list[int] = []

    def _backfill_embeddings(*, limit: int) -> int:
        backfill_calls.append(int(limit))
        return int(limit)

    fake_memory.backfill_embeddings = _backfill_embeddings
    app.state.runtime.engine.memory = fake_memory
    app.state.runtime.channels.send = AsyncMock(return_value="ok")

    with TestClient(app) as client:
        deadline = time.monotonic() + 6.0
        payload: dict[str, object] = {}
        while time.monotonic() < deadline:
            payload = client.get("/v1/diagnostics").json()
            ticks = int(payload["memory_quality_tuning"]["ticks"])
            if ticks >= 1 and str(fake_memory.tuning.get("last_action", "") or ""):
                break
            time.sleep(0.05)

        assert str(fake_memory.tuning.get("last_action", "") or "") == "semantic_backfill"
        assert backfill_calls
        assert backfill_calls[-1] == 24
        recent_actions = fake_memory.tuning.get("recent_actions", [])
        assert recent_actions
        last_entry = recent_actions[-1]
        assert last_entry["metadata"]["backfill_limit"] == 24
        assert int(payload["memory_quality_tuning"]["last_action_metadata"]["backfill_limit"]) == 24
        app.state.runtime.channels.send.assert_not_awaited()


def test_gateway_tuning_loop_stage18_notify_includes_template_and_layer_variant_marker(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={
            "heartbeat": {"enabled": False},
            "diagnostics": {"enabled": True, "require_auth": False},
            "autonomy": {
                "tuning_loop_enabled": True,
                "tuning_degrading_streak_threshold": 2,
                "tuning_loop_cooldown_s": 0,
            },
        },
        channels={},
    )
    cfg.gateway.autonomy.tuning_loop_interval_s = 1
    app = create_app(cfg)
    fake_memory = _FakeTuningMemory(degrade=True, weakest_layer="decision", degrade_score=70)
    app.state.runtime.engine.memory = fake_memory
    app.state.runtime.channels.send = AsyncMock(return_value="ok")

    with TestClient(app) as client:
        deadline = time.monotonic() + 6.0
        while time.monotonic() < deadline:
            payload = client.get("/v1/diagnostics").json()
            ticks = int(payload["memory_quality_tuning"]["ticks"])
            if ticks >= 1 and app.state.runtime.channels.send.await_count >= 1:
                break
            time.sleep(0.05)

        send_kwargs = app.state.runtime.channels.send.await_args.kwargs
        metadata = dict(send_kwargs["metadata"])
        assert metadata["weakest_layer"] == "decision"
        assert metadata["severity"] == "low"
        assert metadata["playbook_id"] == "layer_decision_low_v1"
        assert metadata["template_id"] == "notify.decision.low.v1"
        assert metadata["action_variant"] == "layer_decision_low_v1:notify_operator:v2"
        assert "variant=decision-low" in str(send_kwargs["text"])
        assert "playbook_id=layer_decision_low_v1" in str(fake_memory.tuning.get("last_reason", "") or "")
        assert "weakest_layer=decision" in str(fake_memory.tuning.get("last_reason", "") or "")

        recent_actions = fake_memory.tuning.get("recent_actions", [])
        assert recent_actions
        last_entry = recent_actions[-1]
        assert last_entry["metadata"]["weakest_layer"] == "decision"
        assert last_entry["metadata"]["severity"] == "low"
        assert last_entry["metadata"]["playbook_id"] == "layer_decision_low_v1"
        assert last_entry["metadata"]["template_id"] == "notify.decision.low.v1"
        assert last_entry["metadata"]["action_variant"] == "layer_decision_low_v1:notify_operator:v2"


def test_gateway_tuning_loop_stage18_decision_snapshot_uses_layer_specific_tag_metadata(tmp_path: Path) -> None:
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
                "tuning_loop_cooldown_s": 0,
            },
        },
        channels={},
    )
    cfg.gateway.autonomy.tuning_loop_interval_s = 1
    app = create_app(cfg)
    fake_memory = _FakeTuningMemory(degrade=True, weakest_layer="decision", degrade_score=70)
    app.state.runtime.engine.memory = fake_memory
    app.state.runtime.channels.send = AsyncMock(return_value="ok")

    with TestClient(app) as client:
        deadline = time.monotonic() + 6.0
        while time.monotonic() < deadline:
            payload = client.get("/v1/diagnostics").json()
            ticks = int(payload["memory_quality_tuning"]["ticks"])
            if ticks >= 1 and fake_memory.snapshot_calls >= 1:
                break
            time.sleep(0.05)

        assert str(fake_memory.tuning.get("last_action", "") or "") == "memory_snapshot"
        assert fake_memory.snapshot_calls >= 1
        assert fake_memory.last_snapshot_tag == "quality-drift-decision-medium"
        recent_actions = fake_memory.tuning.get("recent_actions", [])
        assert recent_actions
        last_entry = recent_actions[-1]
        assert last_entry["metadata"]["snapshot_tag"] == "quality-drift-decision-medium"
        assert last_entry["metadata"]["action_variant"] == "layer_decision_medium_v1:memory_snapshot:v2"


def test_gateway_tuning_loop_stage18_outcome_compact_persists_compaction_metadata(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={
            "heartbeat": {"enabled": False},
            "diagnostics": {"enabled": True, "require_auth": False},
            "autonomy": {
                "tuning_loop_enabled": True,
                "tuning_degrading_streak_threshold": 2,
                "tuning_loop_cooldown_s": 0,
            },
        },
        channels={},
    )
    cfg.gateway.autonomy.tuning_loop_interval_s = 1
    app = create_app(cfg)
    fake_memory = _FakeTuningMemory(degrade=True, weakest_layer="episodic", degrade_score=35)
    app.state.runtime.engine.memory = fake_memory
    app.state.runtime.channels.send = AsyncMock(return_value="ok")

    with TestClient(app) as client:
        deadline = time.monotonic() + 6.0
        payload: dict[str, object] = {}
        while time.monotonic() < deadline:
            payload = client.get("/v1/diagnostics").json()
            ticks = int(payload["memory_quality_tuning"]["ticks"])
            if ticks >= 1 and fake_memory.compact_calls >= 1:
                break
            time.sleep(0.05)

        assert str(fake_memory.tuning.get("last_action", "") or "") == "memory_compact"
        assert fake_memory.compact_calls >= 1
        recent_actions = fake_memory.tuning.get("recent_actions", [])
        assert recent_actions
        last_entry = recent_actions[-1]
        assert last_entry["metadata"]["expired_records"] == 2
        assert last_entry["metadata"]["decayed_records"] == 3
        assert last_entry["metadata"]["consolidated_records"] == 4
        assert last_entry["metadata"]["consolidated_categories"] == {"context": 4}
        assert last_entry["metadata"]["action_variant"] == "layer_outcome_high_v1:memory_compact:v2"
        assert int(payload["memory_quality_tuning"]["last_action_metadata"]["consolidated_records"]) == 4
        app.state.runtime.channels.send.assert_not_awaited()


def test_gateway_tuning_loop_stage18_diagnostics_include_action_telemetry_maps(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={
            "heartbeat": {"enabled": False},
            "diagnostics": {"enabled": True, "require_auth": False},
            "autonomy": {
                "tuning_loop_enabled": True,
                "tuning_degrading_streak_threshold": 2,
                "tuning_loop_cooldown_s": 0,
            },
        },
        channels={},
    )
    cfg.gateway.autonomy.tuning_loop_interval_s = 1
    app = create_app(cfg)
    fake_memory = _FakeTuningMemory(degrade=True, weakest_layer="decision", degrade_score=70)
    app.state.runtime.engine.memory = fake_memory
    app.state.runtime.channels.send = AsyncMock(return_value="ok")

    with TestClient(app) as client:
        deadline = time.monotonic() + 6.0
        payload: dict[str, object] = {}
        while time.monotonic() < deadline:
            payload = client.get("/v1/diagnostics").json()
            ticks = int(payload["memory_quality_tuning"]["ticks"])
            if ticks >= 1 and app.state.runtime.channels.send.await_count >= 1:
                break
            time.sleep(0.05)

        tuning = payload["memory_quality_tuning"]
        assert isinstance(tuning["actions_by_layer"], dict)
        assert int(tuning["actions_by_layer"]["decision"]) >= 1
        assert isinstance(tuning["actions_by_playbook"], dict)
        assert int(tuning["actions_by_playbook"]["layer_decision_low_v1"]) >= 1
        assert isinstance(tuning["actions_by_action"], dict)
        assert int(tuning["actions_by_action"]["notify_operator"]) >= 1
        assert isinstance(tuning["action_status_by_layer"], dict)
        assert int(tuning["action_status_by_layer"]["decision"]["ok"]) >= 1
        assert isinstance(tuning["last_action_metadata"], dict)
        assert tuning["last_action_metadata"]["template_id"] == "notify.decision.low.v1"


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


def test_gateway_diagnostics_memory_quality_cache_fingerprint_includes_reasoning_layers(tmp_path: Path) -> None:
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
    calls = {"quality_update": 0, "analysis_stats": 0}

    def _analysis_stats() -> dict[str, object]:
        calls["analysis_stats"] += 1
        if calls["analysis_stats"] <= 2:
            reasoning_layers = {"fact": 5, "decision": 5}
        else:
            reasoning_layers = {"fact": 9, "decision": 1}
        return {
            "semantic": {
                "enabled": True,
                "coverage_ratio": 0.5,
                "missing_records": 50,
                "total_records": 100,
            },
            "reasoning_layers": reasoning_layers,
            "confidence": {"average": 0.66},
        }

    def _quality_update(*, retrieval_metrics, turn_stability_metrics, semantic_metrics, sampled_at, reasoning_layer_metrics=None):
        del retrieval_metrics, turn_stability_metrics, semantic_metrics, sampled_at
        calls["quality_update"] += 1
        reasoning_payload = dict(reasoning_layer_metrics or {})
        reasoning_layers = reasoning_payload.get("reasoning_layers", {})
        weakest_layer = ""
        if isinstance(reasoning_layers, dict):
            weakest_layer = min(reasoning_layers.keys(), key=lambda key: int(reasoning_layers.get(key, 0) or 0))
        return {
            "semantic": {"enabled": True, "coverage_ratio": 0.5},
            "drift": {"assessment": "stable"},
            "score": 90,
            "reasoning_layers": {
                "distribution": dict(reasoning_layers),
                "weakest_layer": weakest_layer,
                "confidence": dict(reasoning_payload.get("confidence", {})),
            },
            "recommendations": [],
        }

    def _quality_snapshot() -> dict[str, object]:
        return {"tuning": {}}

    memory.analysis_stats = _analysis_stats
    memory.update_quality_state = _quality_update
    memory.quality_state_snapshot = _quality_snapshot

    with TestClient(app) as client:
        first = client.get("/v1/diagnostics").json()
        second = client.get("/v1/diagnostics").json()

    assert calls["quality_update"] == 2
    assert (
        first["engine"]["memory_quality"]["report"]["reasoning_layers"]["weakest_layer"]
        != second["engine"]["memory_quality"]["report"]["reasoning_layers"]["weakest_layer"]
    )


def test_gateway_tuning_loop_annotates_action_reason_and_metadata_with_weakest_layer(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={
            "heartbeat": {"enabled": False},
            "diagnostics": {"enabled": True, "require_auth": False},
            "autonomy": {
                "tuning_loop_enabled": True,
                "tuning_degrading_streak_threshold": 2,
                "tuning_loop_cooldown_s": 0,
            },
        },
        channels={},
    )
    cfg.gateway.autonomy.tuning_loop_interval_s = 1
    app = create_app(cfg)
    fake_memory = _FakeTuningMemory(degrade=True, weakest_layer="decision", degrade_score=70)
    app.state.runtime.engine.memory = fake_memory
    app.state.runtime.channels.send = AsyncMock(return_value="ok")

    with TestClient(app) as client:
        payload = {}
        for _ in range(40):
            payload = client.get("/v1/diagnostics").json()
            if int(payload["memory_quality_tuning"]["ticks"]) >= 1 and app.state.runtime.channels.send.await_count >= 1:
                break
            time.sleep(0.05)

        assert int(payload["memory_quality_tuning"]["ticks"]) >= 1
        send_kwargs = app.state.runtime.channels.send.await_args.kwargs
        assert send_kwargs["metadata"]["weakest_layer"] == "decision"
        assert "weakest_layer=decision" in str(fake_memory.tuning.get("last_reason", "") or "")
        recent_actions = fake_memory.tuning.get("recent_actions", [])
        assert recent_actions
        last_entry = recent_actions[-1]
        assert last_entry["metadata"]["weakest_layer"] == "decision"


def test_gateway_tuning_loop_stage17_normalizes_legacy_reasoning_layer_aliases(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={
            "heartbeat": {"enabled": False},
            "diagnostics": {"enabled": True, "require_auth": False},
            "autonomy": {
                "tuning_loop_enabled": True,
                "tuning_degrading_streak_threshold": 2,
                "tuning_loop_cooldown_s": 0,
            },
        },
        channels={},
    )
    cfg.gateway.autonomy.tuning_loop_interval_s = 1
    app = create_app(cfg)
    fake_memory = _FakeTuningMemory(degrade=True, weakest_layer="procedural", degrade_score=70)
    app.state.runtime.engine.memory = fake_memory
    app.state.runtime.channels.send = AsyncMock(return_value="ok")

    with TestClient(app) as client:
        deadline = time.monotonic() + 6.0
        while time.monotonic() < deadline:
            payload = client.get("/v1/diagnostics").json()
            ticks = int(payload["memory_quality_tuning"]["ticks"])
            if ticks >= 1 and app.state.runtime.channels.send.await_count >= 1:
                break
            time.sleep(0.05)

        send_kwargs = app.state.runtime.channels.send.await_args.kwargs
        metadata = dict(send_kwargs["metadata"])
        assert metadata["weakest_layer"] == "decision"
        assert metadata["playbook_id"] == "layer_decision_low_v1"


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
        unauthorized_request_id = unauthorized.headers["X-Request-ID"]
        assert unauthorized.json()["request_id"] == unauthorized_request_id

        authorized_status = client.get("/v1/status", headers={"Authorization": "Bearer diag-token"})
        assert authorized_status.status_code == 200
        assert isinstance(authorized_status.headers.get("X-Request-ID", ""), str) and authorized_status.headers["X-Request-ID"]

        diagnostics = client.get("/v1/diagnostics", headers={"Authorization": "Bearer diag-token"})
        assert diagnostics.status_code == 200
        assert isinstance(diagnostics.headers.get("X-Request-ID", ""), str) and diagnostics.headers["X-Request-ID"]
        http_payload = diagnostics.json()["http"]

        assert http_payload["total_requests"] >= 3
        assert http_payload["in_flight"] >= 1
        assert http_payload["by_method"]["GET"] >= 3
        assert http_payload["by_path"]["/v1/status"] >= 2
        assert http_payload["by_path"]["/v1/diagnostics"] >= 1
        assert http_payload["by_status"]["401"] >= 1
        assert http_payload["by_status"]["200"] >= 1
        assert http_payload["last_request_id"] == diagnostics.headers["X-Request-ID"]
        assert http_payload["last_request_method"] == "GET"
        assert http_payload["last_request_path"] == "/v1/diagnostics"
        assert http_payload["last_request_started_at"]
        assert http_payload["last_error_request_id"] == unauthorized_request_id
        assert http_payload["last_error_method"] == "GET"
        assert http_payload["last_error_path"] == "/v1/status"
        assert http_payload["last_error_at"]
        assert http_payload["last_error_status"] == 401
        assert http_payload["last_error_code"] == unauthorized.json()["code"]
        assert http_payload["last_error_message"] == unauthorized.json()["error"]

        latency = http_payload["latency_ms"]
        assert latency["count"] >= 2
        assert latency["min"] >= 0
        assert latency["max"] >= latency["min"]
        assert latency["avg"] >= latency["min"]
        assert latency["avg"] <= latency["max"]


def test_gateway_http_error_logs_include_request_id(tmp_path: Path) -> None:
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
        },
        channels={},
    )
    app = create_app(cfg)

    rows: list[str] = []
    sink_id = logger.add(rows.append, format=logging_utils._text_format)
    try:
        with TestClient(app) as client:
            response = client.get("/v1/status", headers={"X-Request-ID": "req-http-log-1"})
            assert response.status_code == 401
            assert response.headers["X-Request-ID"] == "req-http-log-1"
    finally:
        logger.remove(sink_id)

    joined = "\n".join(rows)
    assert "[gateway.http]" in joined.lower()
    assert "method=GET" in joined
    assert "path=/v1/status" in joined
    assert "status=401" in joined
    assert "request_id=req-http-log-1" in joined


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
        expected_engine = _normalized_diagnostics_engine_payload(dict(payload["engine"]))
        actual_engine = _normalized_diagnostics_engine_payload(dict(alias_payload["engine"]))
        assert actual_engine == expected_engine


def test_gateway_diagnostics_provider_summary_surfaces_failover_state(tmp_path: Path) -> None:
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
    app.state.runtime.engine.provider = ProviderWithFailoverDiagnostics()

    with TestClient(app) as client:
        payload = client.get("/v1/diagnostics").json()
        provider_payload = payload["engine"]["provider"]
        summary = provider_payload["summary"]

        assert summary["state"] == "cooldown"
        assert summary["transport"] == "openai_compatible"
        assert summary["family"] == "openai_compatible"
        assert summary["recommended_model"] == "openai/gpt-4o-mini"
        assert "openai/gpt-4o-mini" in summary["recommended_models"]
        assert "billing" in summary["onboarding_hint"].lower()
        assert summary["suppression_reason"] == "auth"
        assert summary["suppressed_candidates"][0]["model"] == "openai/gpt-4o-mini"
        assert summary["cooling_candidates"][0]["model"] == "openai/gpt-4o-mini"
        assert any("cooldown" in row.lower() for row in summary["hints"])
        assert any("authentication" in row.lower() for row in summary["hints"])


def test_gateway_provider_recover_endpoint_calls_provider_operator_hook(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)
    app.state.runtime.engine.provider = ProviderWithFailoverDiagnostics()

    with TestClient(app) as client:
        response = client.post("/v1/control/provider/recover", json={"role": "primary", "model": ""})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["summary"]["cleared"] == 1
    assert payload["summary"]["role"] == "primary"


def test_gateway_memory_suggest_refresh_endpoint_returns_snapshot(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)

    with TestClient(app) as client:
        response = client.post("/v1/control/memory/suggest/refresh", json={})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["summary"]["ok"] is True
    assert "count" in payload["summary"]


def test_gateway_skills_refresh_endpoint_returns_summary(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)

    with TestClient(app) as client:
        response = client.post("/v1/control/skills/refresh", json={"force": True})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["summary"]["ok"] is True
    assert "refresh" in payload["summary"]
    assert "skills" in payload["summary"]
    assert "watcher" in payload["summary"]


def test_gateway_api_skills_refresh_alias_returns_summary(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)

    with TestClient(app) as client:
        response = client.post("/api/skills/refresh", json={"force": False})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["summary"]["ok"] is True
    assert payload["summary"]["refresh"]["refreshed"] in {True, False}
    assert payload["summary"]["watcher"] is not None


def test_gateway_skills_doctor_endpoint_returns_summary(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)

    with TestClient(app) as client:
        response = client.post("/v1/control/skills/doctor", json={"include_all": False})

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload["ok"], bool)
    assert payload["summary"]["action"] == "skills_doctor"
    assert "skills" in payload["summary"]
    assert "status_counts" in payload["summary"]
    assert "recommendations" in payload["summary"]


def test_gateway_api_skills_doctor_alias_returns_summary(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)

    with TestClient(app) as client:
        response = client.post("/api/skills/doctor", json={"status": "missing_requirements"})

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload["ok"], bool)
    assert payload["summary"]["action"] == "skills_doctor"
    assert payload["summary"]["status_filter"] == "missing_requirements"


def test_gateway_memory_snapshot_create_endpoint_returns_version(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)

    with TestClient(app) as client:
        response = client.post("/v1/control/memory/snapshot/create", json={"tag": "manual"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["summary"]["ok"] is True
    assert payload["summary"]["version_id"]


def test_gateway_memory_snapshot_rollback_endpoint_returns_counts(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)

    with TestClient(app) as client:
        create = client.post("/v1/control/memory/snapshot/create", json={"tag": "rollback-test"})
        version_id = create.json()["summary"]["version_id"]
        response = client.post("/v1/control/memory/snapshot/rollback", json={"version_id": version_id, "confirm": True})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["summary"]["ok"] is True
    assert payload["summary"]["version_id"] == version_id
    assert "counts" in payload["summary"]


def test_gateway_discord_refresh_endpoint_calls_channel_operator_hook(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)
    fake_channel = SimpleNamespace(operator_refresh_transport=AsyncMock(return_value={"ok": True, "gateway_restarted": True}))
    app.state.runtime.channels._channels["discord"] = fake_channel

    with TestClient(app) as client:
        response = client.post("/v1/control/channels/discord/refresh", json={})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["summary"]["gateway_restarted"] is True
    fake_channel.operator_refresh_transport.assert_awaited_once_with()


def test_gateway_autonomy_wake_endpoint_calls_runtime_wake_submitter(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        channels={},
    )
    app = create_app(cfg)
    app.state.runtime.autonomy_wake.submit = AsyncMock(return_value={"status": "ok", "kind": "proactive", "delivered": 0})

    with TestClient(app) as client:
        response = client.post("/v1/control/autonomy/wake", json={"kind": "proactive"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["summary"]["kind"] == "proactive"
    app.state.runtime.autonomy_wake.submit.assert_awaited()


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
        listed_payload = listed.json()
        assert listed_payload["status"]["lock_backend"] in {"fcntl", "portalocker", "threading"}
        assert listed_payload["count"] == 1
        jobs = listed_payload["jobs"]
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

        status_response = client.get("/v1/cron/status")
        assert status_response.status_code == 200
        assert status_response.json()["count"] == 1

        job_response = client.get(f"/v1/cron/{job_id}", params={"session_id": "cli:cron"})
        assert job_response.status_code == 200
        assert job_response.json()["job"]["id"] == job_id

        disabled = client.post(f"/v1/cron/{job_id}/disable", json={"session_id": "cli:cron"})
        assert disabled.status_code == 200
        assert disabled.json()["status"] == "disabled"
        assert disabled.json()["job"]["enabled"] is False

        enabled = client.post(f"/v1/cron/{job_id}/enable", json={"session_id": "cli:cron"})
        assert enabled.status_code == 200
        assert enabled.json()["status"] == "enabled"
        assert enabled.json()["job"]["enabled"] is True

        deleted = client.delete(f"/v1/cron/{job_id}")
        assert deleted.status_code == 200
        deleted_payload = deleted.json()
        assert deleted_payload["ok"] is True
        assert deleted_payload["status"] == "removed"

        listed_empty = client.get("/v1/cron/list", params={"session_id": "cli:cron"})
        assert listed_empty.status_code == 200
        assert listed_empty.json()["jobs"] == []


def test_gateway_cron_delete_uses_to_thread_and_preserves_payload(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={"heartbeat": {"enabled": False}},
        channels={},
    )
    app = create_app(cfg)
    job_id = "job-missing"

    with TestClient(app) as client:
        with patch("clawlite.gateway.server.asyncio.to_thread", new=AsyncMock(return_value=False)) as to_thread_mock:
            deleted = client.delete(f"/v1/cron/{job_id}")

    assert deleted.status_code == 200
    payload = deleted.json()
    assert payload == {"ok": False, "status": "not_found"}
    to_thread_mock.assert_awaited_once_with(app.state.runtime.cron.remove_job, job_id)


def test_route_cron_job_timeout_returns_engine_run_timeout_and_skips_channel_send() -> None:
    class _Engine:
        async def run(
            self,
            *,
            session_id: str,
            user_text: str,
            channel: str | None = None,
            chat_id: str | None = None,
            runtime_metadata: dict[str, Any] | None = None,
        ):
            del session_id, user_text, channel, chat_id, runtime_metadata
            await asyncio.sleep(0.05)
            return SimpleNamespace(text="late", model="fake/test")

    runtime = SimpleNamespace(
        engine=_Engine(),
        channels=SimpleNamespace(send=AsyncMock(return_value="msg-1")),
    )
    job = SimpleNamespace(
        id="job-1",
        session_id="telegram:chat42",
        payload=SimpleNamespace(prompt="run check", channel="telegram", target="chat42"),
    )

    async def _scenario() -> None:
        with patch.object(gateway_server, "GATEWAY_CRON_ENGINE_TIMEOUT_S", new=0.01):
            result = await _route_cron_job(runtime, job)

        assert result == "engine_run_timeout"
        runtime.channels.send.assert_not_awaited()

    asyncio.run(_scenario())


def test_route_cron_job_forwards_resolved_context_to_engine_and_channel_send() -> None:
    seen: list[dict[str, Any]] = []

    class _Engine:
        async def run(
            self,
            *,
            session_id: str,
            user_text: str,
            channel: str | None = None,
            chat_id: str | None = None,
            runtime_metadata: dict[str, Any] | None = None,
        ):
            seen.append(
                {
                    "session_id": session_id,
                    "user_text": user_text,
                    "channel": channel,
                    "chat_id": chat_id,
                    "runtime_metadata": runtime_metadata,
                }
            )
            return SimpleNamespace(text="done", model="fake/test")

    runtime = SimpleNamespace(
        engine=_Engine(),
        channels=SimpleNamespace(send=AsyncMock(return_value="msg-1")),
    )
    job = SimpleNamespace(
        id="job-2",
        session_id="telegram:chat42",
        payload=SimpleNamespace(
            prompt="run check",
            channel="",
            target="",
            runtime_metadata={"reply_to_message_id": "7"},
        ),
    )

    async def _scenario() -> None:
        result = await _route_cron_job(runtime, job)
        assert result == "done"

    asyncio.run(_scenario())

    assert seen == [
        {
            "session_id": "telegram:chat42",
            "user_text": "run check",
            "channel": "telegram",
            "chat_id": "chat42",
            "runtime_metadata": {"reply_to_message_id": "7"},
        }
    ]
    runtime.channels.send.assert_awaited_once_with(channel="telegram", target="chat42", text="done")


def test_gateway_job_workers_forward_context_for_agent_and_skill_runs(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={"heartbeat": {"enabled": False}},
        channels={},
    )
    app = create_app(cfg)
    seen: list[dict[str, Any]] = []
    agent_seen = threading.Event()
    skill_seen = threading.Event()

    def _job_state(job: Any) -> dict[str, Any]:
        if job is None:
            return {"status": None, "error": "", "result": ""}
        return {
            "status": getattr(job, "status", None),
            "error": str(getattr(job, "error", "") or ""),
            "result": str(getattr(job, "result", "") or ""),
        }

    async def _capture_run(
        *,
        session_id: str,
        user_text: str,
        channel: str | None = None,
        chat_id: str | None = None,
        runtime_metadata: dict[str, Any] | None = None,
    ):
        seen.append(
            {
                "session_id": session_id,
                "user_text": user_text,
                "channel": channel,
                "chat_id": chat_id,
                "runtime_metadata": runtime_metadata,
                }
            )
        if session_id == "telegram:42":
            agent_seen.set()
        elif session_id == "discord:99":
            skill_seen.set()
        return SimpleNamespace(text="ok", model="fake/test")

    app.state.runtime.engine.run = _capture_run
    app.state.runtime.skills_loader.load_skill_content = lambda name: "Skill body" if name == "demo" else None

    with TestClient(app):
        agent_job = app.state.runtime.job_queue.submit(
            "agent_run",
            {
                "task": "run agent task",
                "channel": "telegram",
                "target": "42",
                "runtime_metadata": {"reply_to_message_id": "7"},
            },
            session_id="telegram:42",
        )
        skill_job = app.state.runtime.job_queue.submit(
            "skill_exec",
            {
                "skill": "demo",
                "task": "run skill task",
                "channel": "discord",
                "chat_id": "99",
                "runtime_metadata": {"custom_id": "btn-1"},
            },
            session_id="discord:99",
        )

        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            agent_status = app.state.runtime.job_queue.status(agent_job.id)
            skill_status = app.state.runtime.job_queue.status(skill_job.id)
            if (
                agent_seen.is_set()
                and skill_seen.is_set()
                and agent_status is not None
                and skill_status is not None
                and agent_status.status == "done"
                and skill_status.status == "done"
            ):
                break
            time.sleep(0.05)
        else:
            raise AssertionError(
                "timed out waiting for job workers to finish "
                f"(agent_seen={agent_seen.is_set()} agent={_job_state(agent_status)} "
                f"skill_seen={skill_seen.is_set()} skill={_job_state(skill_status)})"
            )

    forwarded = [row for row in seen if row["session_id"] in {"telegram:42", "discord:99"}]
    assert forwarded == [
        {
            "session_id": "telegram:42",
            "user_text": "run agent task",
            "channel": "telegram",
            "chat_id": "42",
            "runtime_metadata": {"reply_to_message_id": "7"},
        },
        {
            "session_id": "discord:99",
            "user_text": "Skill context:\nSkill body\n\nTask: run skill task",
            "channel": "discord",
            "chat_id": "99",
            "runtime_metadata": {"custom_id": "btn-1"},
        },
    ]


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


def test_gateway_heartbeat_trigger_reports_quota_pressure_and_notices_on_repeat(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={"heartbeat": {"enabled": True, "interval_s": 9999}},
        channels={},
    )
    app = create_app(cfg)
    counters = {"quota": 0, "global": 0, "total": 0}

    async def _engine_run(*, session_id: str, user_text: str):
        del session_id, user_text
        return SimpleNamespace(text="HEARTBEAT_OK", model="fake/test")

    app.state.runtime.engine.run = _engine_run

    def _status() -> dict[str, object]:
        return {
            "running": True,
            "worker_state": "running",
            "dropped_backpressure": counters["total"],
            "dropped_quota": counters["quota"],
            "dropped_global_backpressure": counters["global"],
            "pending_by_kind": {"heartbeat": 1},
            "kind_limits": {"heartbeat": 1},
            "by_kind": {
                "heartbeat": {
                    "dropped_backpressure": counters["total"],
                    "dropped_quota": counters["quota"],
                    "dropped_global_backpressure": counters["global"],
                }
            },
        }

    async def _submit(**_kwargs):
        counters["quota"] += 1
        counters["total"] += 1
        return HeartbeatDecision(action="skip", reason="wake_backpressure")

    with TestClient(app) as client:
        app.state.runtime.channels.send = AsyncMock(return_value="ok")
        app.state.runtime.autonomy_wake.status = _status
        app.state.runtime.autonomy_wake.submit = AsyncMock(side_effect=_submit)

        first = client.post("/v1/control/heartbeat/trigger")
        second = client.post("/v1/control/heartbeat/trigger")

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["decision"]["reason"] == "wake_quota_backpressure"
        assert second.json()["decision"]["reason"] == "wake_quota_backpressure"
        assert app.state.runtime.channels.send.await_count == 1

        send_kwargs = app.state.runtime.channels.send.await_args.kwargs
        metadata = dict(send_kwargs["metadata"])
        assert metadata["autonomy_action"] == "wake_backpressure"
        assert metadata["pressure_kind"] == "heartbeat"
        assert metadata["pressure_class"] == "quota"
        assert metadata["pressure_streak"] == 2
        assert "heartbeat wakes throttled by quota backpressure" in str(send_kwargs["text"])
        state = json.loads(Path(app.state.runtime.heartbeat.state_path).read_text(encoding="utf-8"))
        assert state["wake_backpressure_count"] >= 2
        assert state["wake_pressure_by_reason"]["wake_quota_backpressure"] >= 2
        assert state["last_pressure_reason"] == "wake_quota_backpressure"


def test_gateway_diagnostics_exposes_proactive_wake_policy_delay(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        agents={"defaults": {"memory": {"proactive": True}}},
        gateway={"heartbeat": {"enabled": False}, "diagnostics": {"enabled": True, "require_auth": False}},
        channels={},
    )
    app = create_app(cfg)
    counters = {"coalesced": 0}

    def _status() -> dict[str, object]:
        return {
            "running": True,
            "worker_state": "running",
            "dropped_backpressure": 0,
            "dropped_quota": 0,
            "dropped_global_backpressure": 0,
            "pending_by_kind": {"proactive": 1},
            "kind_limits": {"proactive": 1},
            "by_kind": {
                "proactive": {
                    "coalesced": counters["coalesced"],
                    "dropped_backpressure": 0,
                    "dropped_quota": 0,
                    "dropped_global_backpressure": 0,
                }
            },
        }

    async def _submit(**_kwargs):
        counters["coalesced"] = 1
        return {
            "status": "ok",
            "scanned": 0,
            "delivered": 0,
            "failed": 0,
            "replayed": 0,
            "next_step_sent": False,
            "error": "",
        }

    app.state.runtime.autonomy_wake.status = _status
    app.state.runtime.autonomy_wake.submit = AsyncMock(side_effect=_submit)

    with TestClient(app) as client:
        deadline = time.monotonic() + 2.0
        payload: dict[str, object] = {}
        while time.monotonic() < deadline:
            payload = client.get("/v1/diagnostics").json()
            runner = payload["memory_monitor"]["runner"]
            if int(runner.get("policy_event_count", 0) or 0) >= 1:
                break
            time.sleep(0.05)

        runner = payload["memory_monitor"]["runner"]
        assert runner["policy_event_count"] >= 1
        assert runner["delayed_count"] >= 1
        assert runner["last_policy_action"] == "delayed"
        assert runner["last_policy_reason"] == "coalesced"
        assert runner["policy_by_action"]["delayed"] >= 1
        assert runner["recent_policy_events"][-1]["summary"] == "proactive wake delayed by coalesced pending run"


def test_gateway_diagnostics_exposes_cron_wake_policy_discard(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        scheduler=SchedulerConfig(heartbeat_interval_seconds=9999),
        gateway={"heartbeat": {"enabled": False}, "diagnostics": {"enabled": True, "require_auth": False}},
        channels={},
    )
    app = create_app(cfg)
    counters = {"quota": 0, "global": 0, "total": 0}
    job_id = asyncio.run(
        app.state.runtime.cron.add_job(
            session_id="cli:cron-policy",
            expression="every 60",
            prompt="run wake policy check",
            name="cron-policy",
            metadata={"run_once": True},
        )
    )
    job = app.state.runtime.cron.get_job(job_id)
    assert job is not None
    job.next_run_iso = (gateway_server.dt.datetime.now(gateway_server.dt.timezone.utc) - gateway_server.dt.timedelta(seconds=1)).isoformat()
    app.state.runtime.cron._save()

    def _status() -> dict[str, object]:
        return {
            "running": True,
            "worker_state": "running",
            "dropped_backpressure": counters["total"],
            "dropped_quota": counters["quota"],
            "dropped_global_backpressure": counters["global"],
            "pending_by_kind": {"cron": 1},
            "kind_limits": {"cron": 1},
            "by_kind": {
                "cron": {
                    "coalesced": 0,
                    "dropped_backpressure": counters["total"],
                    "dropped_quota": counters["quota"],
                    "dropped_global_backpressure": counters["global"],
                }
            },
        }

    async def _submit(**_kwargs):
        counters["quota"] = 1
        counters["total"] = 1
        return "cron_backpressure_skipped"

    app.state.runtime.autonomy_wake.status = _status
    app.state.runtime.autonomy_wake.submit = AsyncMock(side_effect=_submit)

    with TestClient(app) as client:
        deadline = time.monotonic() + 3.0
        payload: dict[str, object] = {}
        while time.monotonic() < deadline:
            payload = client.get("/v1/diagnostics").json()
            wake_policy = payload["cron"]["wake_policy"]
            if int(wake_policy.get("discarded_count", 0) or 0) >= 1:
                break
            time.sleep(0.05)

        wake_policy = payload["cron"]["wake_policy"]
        assert wake_policy["policy_event_count"] >= 1
        assert wake_policy["discarded_count"] >= 1
        assert wake_policy["last_policy_action"] == "discarded"
        assert wake_policy["last_policy_reason"] == "quota"
        assert wake_policy["policy_by_reason"]["quota"] >= 1
        assert wake_policy["recent_policy_events"][-1]["summary"] == f"cron wake discarded by quota policy job_id={job_id}"
