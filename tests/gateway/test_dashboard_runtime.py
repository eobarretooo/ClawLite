from __future__ import annotations

from types import SimpleNamespace

from clawlite.gateway.dashboard_runtime import dashboard_state_payload


def test_dashboard_state_payload_runtime_assembles_sections() -> None:
    runtime = SimpleNamespace(
        bus=SimpleNamespace(stats=lambda: {"queued": 0}),
        engine=SimpleNamespace(
            provider=object(),
            sessions=SimpleNamespace(),
            subagents=SimpleNamespace(status=lambda: {"active": 1}),
            memory=object(),
        ),
        channels=SimpleNamespace(
            status=lambda: {"telegram": {"enabled": True}},
            dispatcher_diagnostics=lambda: {"running": True},
            delivery_diagnostics=lambda: {"running": True},
            inbound_diagnostics=lambda: {"running": True},
            recovery_diagnostics=lambda: {"running": True},
            get_channel=lambda name: {"name": name},
        ),
        cron=SimpleNamespace(status=lambda: {"running": True}),
        heartbeat=SimpleNamespace(status=lambda: {"running": True}),
        autonomy=SimpleNamespace(status=lambda: {"enabled": True, "running": True}),
        autonomy_wake=SimpleNamespace(status=lambda: {"running": True, "queue_depth": 0, "pending_count": 0}),
        supervisor=SimpleNamespace(status=lambda: {"healthy": True}),
        workspace=SimpleNamespace(runtime_health=lambda: {"ok": True}, onboarding_status=lambda: {"done": True}, bootstrap_status=lambda: {"ok": True}),
        self_evolution=SimpleNamespace(enabled=True),
        skills_loader=SimpleNamespace(diagnostics_report=lambda: {"watcher": {"running": True}}),
        config=SimpleNamespace(),
        memory_monitor=object(),
    )

    payload = dashboard_state_payload(
        runtime=runtime,
        contract_version="2026-03-04",
        generated_at="2026-03-17T12:00:00+00:00",
        control_plane={"status": "ok"},
        control_plane_to_dict=lambda payload: dict(payload),
        recent_dashboard_sessions_payload=lambda **kwargs: {"items": [], "count": 0},
        dashboard_channels_summary_payload=lambda snapshot: {"items": list(snapshot.keys()), "count": len(snapshot)},
        dashboard_channel_posture_summary_payload=lambda **kwargs: {"summary_posture": "healthy"},
        dashboard_cron_summary_payload=lambda **kwargs: {"status": {"running": True}, "jobs": []},
        dashboard_self_evolution_summary_payload=lambda **kwargs: {"enabled": True, "runner": dict(kwargs["runner_state"])},
        dashboard_runtime_posture_summary_payload=lambda **kwargs: {"autonomy_posture": "running"},
        dashboard_runtime_policy_summary_payload=lambda **kwargs: {"policy_posture": "manual_only"},
        dashboard_provider_health_summary_payload=lambda **kwargs: {"health_posture": "healthy"},
        dashboard_provider_budget_summary_payload=lambda **kwargs: {"budget_posture": "clear"},
        dashboard_memory_summary_payload=lambda **kwargs: {"enabled": True},
        operator_channel_summary=lambda channel: {"available": True, "channel": channel["name"]},
        provider_telemetry_snapshot=lambda provider: {"provider": provider.__class__.__name__},
        provider_autonomy_snapshot=lambda **kwargs: {"suppressed": False},
        provider_status_payload_fn=lambda: {"ok": True, "provider": "openai"},
        build_dashboard_handoff=lambda config: {"next": "chat"},
        memory_profile_snapshot_fn=lambda *args, **kwargs: {"profile": True},
        memory_suggest_snapshot_fn=lambda *args, **kwargs: {"suggest": True},
        memory_version_snapshot_fn=lambda *args, **kwargs: {"version": True},
        self_evolution_runner_state={"running": True},
        dashboard_state_payload_builder=lambda **kwargs: kwargs,
    )

    assert payload["channels_payload"] == {"items": ["telegram"], "count": 1}
    assert payload["channels_posture_payload"] == {"summary_posture": "healthy"}
    assert payload["discord_payload"] == {"available": True, "channel": "discord"}
    assert payload["telegram_payload"] == {"available": True, "channel": "telegram"}
    assert payload["memory_payload"] == {"enabled": True}
    assert payload["provider_telemetry_payload"] == {"provider": "object"}
    assert payload["provider_status_payload"] == {"ok": True, "provider": "openai"}
    assert payload["provider_health_payload"] == {"health_posture": "healthy"}
    assert payload["provider_budget_payload"] == {"budget_posture": "clear"}
    assert payload["self_evolution_payload"] == {"enabled": True, "runner": {"running": True}}
    assert payload["runtime_posture_payload"] == {"autonomy_posture": "running"}
    assert payload["runtime_policy_payload"] == {"policy_posture": "manual_only"}


def test_dashboard_state_payload_runtime_reuses_single_channel_snapshot() -> None:
    counters = {
        "queue": 0,
        "dispatcher": 0,
        "delivery": 0,
        "inbound": 0,
        "recovery": 0,
    }

    def _queue_stats() -> dict[str, int]:
        counters["queue"] += 1
        return {"outbound_size": counters["queue"]}

    def _dispatcher_diag() -> dict[str, int | bool]:
        counters["dispatcher"] += 1
        return {"running": True, "active_tasks": counters["dispatcher"]}

    def _delivery_diag() -> dict[str, dict[str, int]]:
        counters["delivery"] += 1
        return {"total": {"success": counters["delivery"]}}

    def _inbound_diag() -> dict[str, dict[str, int]]:
        counters["inbound"] += 1
        return {"persistence": {"pending": counters["inbound"]}}

    def _recovery_diag() -> dict[str, dict[str, int] | bool]:
        counters["recovery"] += 1
        return {"running": True, "total": {"success": counters["recovery"]}}

    runtime = SimpleNamespace(
        bus=SimpleNamespace(stats=_queue_stats),
        engine=SimpleNamespace(
            provider=object(),
            sessions=SimpleNamespace(),
            subagents=SimpleNamespace(status=lambda: {"active": 1}),
            memory=object(),
        ),
        channels=SimpleNamespace(
            status=lambda: {"telegram": {"enabled": True}},
            dispatcher_diagnostics=_dispatcher_diag,
            delivery_diagnostics=_delivery_diag,
            inbound_diagnostics=_inbound_diag,
            recovery_diagnostics=_recovery_diag,
            get_channel=lambda name: {"name": name},
        ),
        cron=SimpleNamespace(status=lambda: {"running": True}),
        heartbeat=SimpleNamespace(status=lambda: {"running": True}),
        autonomy=SimpleNamespace(status=lambda: {"enabled": True, "running": True}),
        autonomy_wake=SimpleNamespace(status=lambda: {"running": True, "queue_depth": 0, "pending_count": 0}),
        supervisor=SimpleNamespace(status=lambda: {"healthy": True}),
        workspace=SimpleNamespace(runtime_health=lambda: {"ok": True}, onboarding_status=lambda: {"done": True}, bootstrap_status=lambda: {"ok": True}),
        self_evolution=SimpleNamespace(enabled=True),
        skills_loader=SimpleNamespace(diagnostics_report=lambda: {"watcher": {"running": True}}),
        config=SimpleNamespace(),
        memory_monitor=object(),
    )

    payload = dashboard_state_payload(
        runtime=runtime,
        contract_version="2026-03-04",
        generated_at="2026-03-17T12:00:00+00:00",
        control_plane={"status": "ok"},
        control_plane_to_dict=lambda data: dict(data),
        recent_dashboard_sessions_payload=lambda **kwargs: {"items": [], "count": 0},
        dashboard_channels_summary_payload=lambda snapshot: {"items": list(snapshot.keys()), "count": len(snapshot)},
        dashboard_channel_posture_summary_payload=lambda **kwargs: {
            "summary_posture": "healthy",
            "queue_outbound_size": kwargs["queue_payload"]["outbound_size"],
            "dispatcher_active_tasks": kwargs["channels_dispatcher_payload"]["active_tasks"],
            "delivery_success": kwargs["channels_delivery_payload"]["total"]["success"],
            "inbound_pending": kwargs["channels_inbound_payload"]["persistence"]["pending"],
            "recovery_success": kwargs["channels_recovery_payload"]["total"]["success"],
        },
        dashboard_cron_summary_payload=lambda **kwargs: {"status": {"running": True}, "jobs": []},
        dashboard_self_evolution_summary_payload=lambda **kwargs: {"enabled": True, "runner": dict(kwargs["runner_state"])},
        dashboard_runtime_posture_summary_payload=lambda **kwargs: {"autonomy_posture": "running"},
        dashboard_runtime_policy_summary_payload=lambda **kwargs: {"policy_posture": "manual_only"},
        dashboard_provider_health_summary_payload=lambda **kwargs: {"health_posture": "healthy"},
        dashboard_provider_budget_summary_payload=lambda **kwargs: {"budget_posture": "clear"},
        dashboard_memory_summary_payload=lambda **kwargs: {"enabled": True},
        operator_channel_summary=lambda channel: {"available": True, "channel": channel["name"]},
        provider_telemetry_snapshot=lambda provider: {"provider": provider.__class__.__name__},
        provider_autonomy_snapshot=lambda **kwargs: {"suppressed": False},
        provider_status_payload_fn=lambda: {"ok": True, "provider": "openai"},
        build_dashboard_handoff=lambda config: {"next": "chat"},
        memory_profile_snapshot_fn=lambda *args, **kwargs: {"profile": True},
        memory_suggest_snapshot_fn=lambda *args, **kwargs: {"suggest": True},
        memory_version_snapshot_fn=lambda *args, **kwargs: {"version": True},
        self_evolution_runner_state={"running": True},
        dashboard_state_payload_builder=lambda **kwargs: kwargs,
    )

    assert counters == {
        "queue": 1,
        "dispatcher": 1,
        "delivery": 1,
        "inbound": 1,
        "recovery": 1,
    }
    assert payload["channels_posture_payload"]["queue_outbound_size"] == payload["queue_payload"]["outbound_size"]
    assert payload["channels_posture_payload"]["dispatcher_active_tasks"] == payload["channels_dispatcher_payload"]["active_tasks"]
    assert payload["channels_posture_payload"]["delivery_success"] == payload["channels_delivery_payload"]["total"]["success"]
    assert payload["channels_posture_payload"]["inbound_pending"] == payload["channels_inbound_payload"]["persistence"]["pending"]
    assert payload["channels_posture_payload"]["recovery_success"] == payload["channels_recovery_payload"]["total"]["success"]
