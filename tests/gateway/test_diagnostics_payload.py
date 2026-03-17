from __future__ import annotations

import asyncio
from types import SimpleNamespace

from clawlite.gateway.diagnostics_payload import (
    diagnostics_environment_payload,
    diagnostics_payload,
)


def test_diagnostics_environment_payload_respects_include_config() -> None:
    assert diagnostics_environment_payload(
        include_config=False,
        workspace_path="/workspace",
        state_path="/state",
        provider_model="gpt-5.4",
    ) == {}
    assert diagnostics_environment_payload(
        include_config=True,
        workspace_path="/workspace",
        state_path="/state",
        provider_model="gpt-5.4",
    ) == {
        "workspace_path": "/workspace",
        "state_path": "/state",
        "provider_model": "gpt-5.4",
    }


def test_diagnostics_payload_assembles_engine_and_runner_sections() -> None:
    class _FakeEngine:
        provider = object()

        @staticmethod
        def retrieval_metrics_snapshot() -> dict[str, int]:
            return {"retrieval_attempts": 3}

        @staticmethod
        def turn_metrics_snapshot() -> dict[str, int]:
            return {"turns_success": 2}

        subagents = SimpleNamespace(status=lambda: {"active": 1})

    runtime = SimpleNamespace(
        engine=_FakeEngine(),
        bus=SimpleNamespace(stats=lambda: {"queued": 0}),
        channels=SimpleNamespace(
            status=lambda: {"telegram": {"enabled": True}},
            dispatcher_diagnostics=lambda: {"running": True},
            delivery_diagnostics=lambda: {"running": True},
            inbound_diagnostics=lambda: {"running": True},
            recovery_diagnostics=lambda: {"running": True},
        ),
        cron=SimpleNamespace(status=lambda: {"running": True}),
        heartbeat=SimpleNamespace(status=lambda: {"running": True}),
        autonomy=SimpleNamespace(status=lambda: {"enabled": True}),
        supervisor=SimpleNamespace(status=lambda: {"healthy": True}),
        autonomy_wake=SimpleNamespace(status=lambda: {"enabled": True}),
        autonomy_log=SimpleNamespace(snapshot=lambda: {"items": []}),
        workspace=SimpleNamespace(runtime_health=lambda: {"ok": True}),
        memory_monitor=object(),
        self_evolution=SimpleNamespace(status=lambda: {"enabled": True, "run_count": 2}),
        skills_loader=SimpleNamespace(diagnostics_report=lambda: {"watcher": {"running": True}}),
    )
    cfg = SimpleNamespace(
        workspace_path="/workspace",
        state_path="/state",
        agents=SimpleNamespace(defaults=SimpleNamespace(model="gpt-5.4")),
        gateway=SimpleNamespace(diagnostics=SimpleNamespace(include_config=True, include_provider_telemetry=True)),
    )

    async def _scenario() -> None:
        payload = await diagnostics_payload(
            cfg=cfg,
            runtime=runtime,
            contract_version="2026-03-04",
            generated_at="2026-03-17T12:00:00+00:00",
            started_monotonic=0.0,
            control_plane_payload={"status": "ok"},
            bootstrap_payload={"pending": False},
            memory_quality_cache={},
            collect_memory_analysis_metrics=lambda: asyncio.sleep(0, result=({"enabled": True}, {})),
            engine_memory_payloads=lambda **kwargs: {"memory": {"available": True}},
            engine_memory_quality_payload=lambda **kwargs: asyncio.sleep(0, result={"available": True, "updated": True}),
            engine_memory_integration_payload=lambda **kwargs: {"available": True},
            provider_telemetry_snapshot=lambda provider: {"provider": provider.__class__.__name__},
            memory_monitor_payload=lambda **kwargs: {"enabled": True, "runner": dict(kwargs["proactive_runner_state"])},
            http_snapshot=lambda: asyncio.sleep(0, result={"requests": 1}),
            ws_snapshot=lambda: asyncio.sleep(0, result={"connections": 1}),
            proactive_runner_state={"running": True},
            cron_wake_state={"policy": "auto"},
            subagent_maintenance_state={"running": True},
            tuning_runner_state={"running": True},
            self_evolution_runner_state={"running": True},
        )

        assert payload["environment"]["workspace_path"] == "/workspace"
        assert payload["engine"]["memory"] == {"available": True}
        assert payload["engine"]["memory_quality"]["available"] is True
        assert payload["engine"]["provider"]["provider"] == "object"
        assert payload["cron"]["wake_policy"] == {"policy": "auto"}
        assert payload["subagents"]["runner"] == {"running": True}
        assert payload["memory_monitor"]["runner"] == {"running": True}
        assert payload["self_evolution"]["runner"] == {"running": True}
        assert payload["http"] == {"requests": 1}
        assert payload["ws"] == {"connections": 1}

    asyncio.run(_scenario())
