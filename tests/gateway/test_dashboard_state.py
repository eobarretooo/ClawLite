from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from clawlite.gateway.dashboard_state import (
    dashboard_channels_summary,
    dashboard_provider_budget_summary,
    dashboard_cron_summary,
    dashboard_provider_health_summary,
    dashboard_preview,
    dashboard_runtime_policy_summary,
    dashboard_runtime_posture_summary,
    dashboard_state_payload,
    dashboard_self_evolution_summary,
    operator_channel_summary,
    recent_dashboard_sessions,
)


class _FakeSessions:
    def __init__(self, root: Path, messages: dict[str, list[dict[str, object]]]) -> None:
        self.root = root
        self._messages = messages

    def _restore_session_id(self, stem: str) -> str:
        return stem.replace("__", ":")

    def read(self, session_id: str, limit: int = 1) -> list[dict[str, object]]:
        return list(self._messages.get(session_id, []))[:limit]


class _FakeSubagents:
    def __init__(self, runs: dict[str, list[SimpleNamespace]]) -> None:
        self._runs = runs

    def list_runs(self, *, session_id: str, active_only: bool = False) -> list[SimpleNamespace]:
        rows = list(self._runs.get(session_id, []))
        if not active_only:
            return rows
        return [row for row in rows if row.status in {"queued", "running"}]


class _FakeCron:
    def list_jobs(self) -> list[dict[str, object]]:
        return [{"job_id": "cron-1"}, {"job_id": "cron-2"}]

    def status(self) -> dict[str, object]:
        return {"running": True}


def test_dashboard_preview_normalizes_and_truncates() -> None:
    assert dashboard_preview(" hello   world ") == "hello world"
    assert dashboard_preview("abcdefghij", max_chars=6) == "abc..."


def test_recent_dashboard_sessions_builds_rows(tmp_path: Path) -> None:
    session_path = tmp_path / "cli__alpha.jsonl"
    session_path.write_text("{}", encoding="utf-8")
    session_path.touch()

    sessions = _FakeSessions(
        tmp_path,
        {
            "cli:alpha": [
                {"role": "assistant", "content": "last message from assistant"},
            ]
        },
    )
    subagents = _FakeSubagents(
        {
            "cli:alpha": [
                SimpleNamespace(status="running"),
                SimpleNamespace(status="completed"),
            ]
        }
    )

    payload = recent_dashboard_sessions(sessions=sessions, subagents=subagents, limit=5)
    assert payload["count"] == 1
    assert payload["items"][0]["session_id"] == "cli:alpha"
    assert payload["items"][0]["active_subagents"] == 1
    assert payload["items"][0]["subagent_statuses"] == {"completed": 1, "running": 1}
    assert payload["items"][0]["updated_at"]


def test_dashboard_channel_helpers_shape_operational_rows() -> None:
    channels = dashboard_channels_summary(
        {
            "telegram": {"enabled": True, "status": "ok", "pending": 1},
            "slack": {"enabled": False, "worker_state": "stopped"},
        }
    )
    assert channels["count"] == 2
    assert channels["items"][0]["name"] == "slack"
    assert channels["items"][1]["state"] == "ok"

    channel = SimpleNamespace(operator_status=lambda: {"offset_next": 42})
    assert operator_channel_summary(channel) == {"available": True, "offset_next": 42}
    assert operator_channel_summary(None) == {"available": False}


def test_dashboard_cron_and_self_evolution_summaries() -> None:
    cron_payload = dashboard_cron_summary(cron=_FakeCron(), limit=1)
    assert cron_payload["status"] == {"running": True}
    assert cron_payload["count"] == 2
    assert cron_payload["jobs"] == [{"job_id": "cron-1"}]

    evolution = SimpleNamespace(enabled=True, status=lambda: {"last_outcome": "ok"})
    evo_payload = dashboard_self_evolution_summary(
        evolution=evolution,
        runner_state={"running": True},
    )
    assert evo_payload["enabled"] is True
    assert evo_payload["status"] == {"last_outcome": "ok"}
    assert evo_payload["runner"] == {"running": True}


def test_dashboard_runtime_posture_summary_surfaces_compact_operator_state() -> None:
    payload = dashboard_runtime_posture_summary(
        autonomy_payload={
            "enabled": True,
            "running": True,
            "session_id": "autonomy:system",
            "no_progress_reason": "repeated_idle_snapshot",
            "no_progress_streak": 2,
            "no_progress_backoff_remaining_s": 30.0,
            "provider_backoff_remaining_s": 0.0,
            "cooldown_remaining_s": 0.0,
            "last_result_excerpt": "AUTONOMY_IDLE",
        },
        autonomy_wake_payload={
            "running": True,
            "queue_depth": 1,
            "pending_count": 1,
            "dropped_backpressure": 2,
            "dropped_quota": 0,
        },
        supervisor_payload={
            "worker_state": "running",
            "incident_count": 1,
            "consecutive_error_count": 0,
        },
        self_evolution_payload={
            "status": {
                "enabled": True,
                "background_enabled": True,
                "activation_mode": "session_canary",
                "enabled_for_sessions": ["autonomy:canary"],
                "require_approval": True,
                "cooldown_remaining_s": 42.0,
                "last_review_status": "awaiting_approval",
            },
            "runner": {
                "enabled": True,
                "activation_mode": "session_canary",
            },
        },
    )

    assert payload["autonomy_posture"] == "no_progress_backoff"
    assert payload["wake_posture"] == "busy"
    assert payload["approval_posture"] == "approval_required"
    assert payload["summary_posture"] == "no_progress_backoff"
    assert payload["summary_tone"] == "warn"
    assert payload["self_evolution"]["enabled_for_sessions_count"] == 1
    assert payload["autonomy"]["no_progress_reason"] == "repeated_idle_snapshot"
    assert "no-progress guard" in payload["operator_hint"]


def test_dashboard_runtime_posture_summary_prefers_wake_error_and_disabled_review_state() -> None:
    payload = dashboard_runtime_posture_summary(
        autonomy_payload={
            "enabled": True,
            "running": True,
            "session_id": "autonomy:system",
        },
        autonomy_wake_payload={
            "running": False,
            "last_error": "wake crashed",
            "queue_depth": 0,
            "pending_count": 0,
        },
        supervisor_payload={},
        self_evolution_payload={
            "status": {
                "enabled": False,
                "background_enabled": False,
                "require_approval": False,
            },
            "runner": {
                "enabled": False,
            },
        },
    )

    assert payload["autonomy_posture"] == "running"
    assert payload["wake_posture"] == "error"
    assert payload["approval_posture"] == "disabled"
    assert payload["summary_posture"] == "error"
    assert payload["summary_tone"] == "danger"


def test_dashboard_runtime_policy_summary_surfaces_canary_block_and_review_gate() -> None:
    payload = dashboard_runtime_policy_summary(
        config=SimpleNamespace(
            gateway=SimpleNamespace(
                autonomy=SimpleNamespace(
                    self_evolution_enabled=True,
                    self_evolution_require_approval=True,
                    self_evolution_enabled_for_sessions=["autonomy:canary-a", "autonomy:canary-b"],
                    session_id="autonomy:system",
                )
            )
        ),
        self_evolution_payload={
            "status": {
                "enabled": True,
                "background_enabled": False,
                "activation_mode": "session_canary",
                "activation_reason": "autonomy_session_not_allowlisted",
                "enabled_for_sessions": ["autonomy:canary-a", "autonomy:canary-b"],
                "autonomy_session_id": "autonomy:system",
                "require_approval": True,
                "last_review_status": "awaiting_approval",
            },
            "runner": {
                "enabled": True,
                "activation_mode": "session_canary",
            },
        }
    )

    assert payload["approval_mode"] == "approval_required"
    assert payload["activation_scope"] == "session_canary"
    assert payload["policy_posture"] == "blocked"
    assert payload["policy_tone"] == "warn"
    assert payload["policy_block"] == "autonomy_session_not_allowlisted"
    assert payload["self_evolution"]["current_session_allowed"] is False
    assert payload["self_evolution"]["enabled_for_sessions_sample"] == ["autonomy:canary-a", "autonomy:canary-b"]
    assert payload["drift"]["posture"] == "aligned_blocked"
    assert payload["drift"]["reason"] == "autonomy_session_not_allowlisted"
    assert payload["drift"]["configured"]["activation_scope"] == "session_canary"
    assert payload["drift"]["effective"]["activation_scope"] == "session_canary"
    assert "outside the canary allowlist" in payload["policy_hint"]


def test_dashboard_runtime_policy_summary_marks_disabled_background_loop_as_manual_only() -> None:
    payload = dashboard_runtime_policy_summary(
        config=SimpleNamespace(
            gateway=SimpleNamespace(
                autonomy=SimpleNamespace(
                    self_evolution_enabled=False,
                    self_evolution_require_approval=False,
                    self_evolution_enabled_for_sessions=[],
                    session_id="autonomy:system",
                )
            )
        ),
        self_evolution_payload={
            "status": {
                "enabled": False,
                "background_enabled": False,
                "require_approval": False,
            },
            "runner": {
                "enabled": False,
            },
        }
    )

    assert payload["approval_mode"] == "disabled"
    assert payload["activation_scope"] == "disabled"
    assert payload["policy_posture"] == "manual_only"
    assert payload["policy_tone"] == "warn"
    assert payload["policy_block"] == "disabled_by_config"
    assert payload["self_evolution"]["current_session_allowed"] is False
    assert payload["drift"]["posture"] == "aligned"
    assert payload["drift"]["configured"]["activation_scope"] == "disabled"
    assert payload["drift"]["effective"]["activation_scope"] == "disabled"
    assert "only explicit/manual runs can proceed" in payload["policy_hint"]


def test_dashboard_runtime_policy_summary_surfaces_runtime_policy_drift_against_config() -> None:
    payload = dashboard_runtime_policy_summary(
        config=SimpleNamespace(
            gateway=SimpleNamespace(
                autonomy=SimpleNamespace(
                    self_evolution_enabled=True,
                    self_evolution_require_approval=False,
                    self_evolution_enabled_for_sessions=[],
                    session_id="autonomy:system",
                )
            )
        ),
        self_evolution_payload={
            "status": {
                "enabled": True,
                "background_enabled": True,
                "activation_mode": "global",
                "activation_reason": "",
                "enabled_for_sessions": [],
                "autonomy_session_id": "autonomy:system",
                "require_approval": True,
                "last_review_status": "awaiting_approval",
            },
            "runner": {
                "enabled": True,
                "activation_mode": "global",
            },
        },
    )

    assert payload["approval_mode"] == "approval_required"
    assert payload["drift"]["posture"] == "approval_mismatch"
    assert payload["drift"]["reason"] == "approval_mode_mismatch"
    assert payload["drift"]["configured"]["require_approval"] is False
    assert payload["drift"]["effective"]["require_approval"] is True


def test_dashboard_runtime_policy_summary_treats_reordered_allowlist_as_aligned() -> None:
    payload = dashboard_runtime_policy_summary(
        config=SimpleNamespace(
            gateway=SimpleNamespace(
                autonomy=SimpleNamespace(
                    self_evolution_enabled=True,
                    self_evolution_require_approval=False,
                    self_evolution_enabled_for_sessions=["autonomy:canary-a", "autonomy:canary-b"],
                    session_id="autonomy:canary-a",
                )
            )
        ),
        self_evolution_payload={
            "status": {
                "enabled": True,
                "background_enabled": True,
                "activation_mode": "session_canary",
                "activation_reason": "",
                "enabled_for_sessions": ["autonomy:canary-b", "autonomy:canary-a"],
                "autonomy_session_id": "autonomy:canary-a",
                "require_approval": False,
            },
            "runner": {
                "enabled": True,
                "activation_mode": "session_canary",
                "enabled_for_sessions": ["autonomy:canary-b", "autonomy:canary-a"],
                "autonomy_session_id": "autonomy:canary-a",
            },
        },
    )

    assert payload["drift"]["posture"] == "aligned"
    assert payload["drift"]["reason"] == ""


def test_dashboard_runtime_policy_summary_uses_effective_enabled_state_when_background_runner_active() -> None:
    payload = dashboard_runtime_policy_summary(
        config=SimpleNamespace(
            gateway=SimpleNamespace(
                autonomy=SimpleNamespace(
                    self_evolution_enabled=True,
                    self_evolution_require_approval=False,
                    self_evolution_enabled_for_sessions=[],
                    session_id="autonomy:system",
                )
            )
        ),
        self_evolution_payload={
            "status": {
                "enabled": False,
                "background_enabled": True,
                "activation_mode": "global",
                "activation_reason": "",
                "enabled_for_sessions": [],
                "autonomy_session_id": "autonomy:system",
                "require_approval": False,
            },
            "runner": {
                "enabled": True,
                "activation_mode": "global",
                "autonomy_session_id": "autonomy:system",
            },
        },
    )

    assert payload["approval_mode"] == "direct_commit"
    assert payload["policy_posture"] == "direct_commit"
    assert payload["self_evolution"]["enabled"] is True
    assert payload["drift"]["posture"] == "aligned"


def test_dashboard_provider_health_summary_surfaces_healthy_cached_route() -> None:
    payload = dashboard_provider_health_summary(
        provider_telemetry_payload={
            "provider": "openai",
            "summary": {
                "state": "healthy",
                "transport": "openai_compatible",
                "hints": ["Cached provider route and capability posture look steady."],
            },
        },
        provider_autonomy_payload={
            "provider": "openai",
            "state": "healthy",
            "suppression_reason": "",
            "suppression_backoff_s": 0.0,
        },
        provider_status_payload={
            "ok": True,
            "provider": "openai",
            "selected_provider": "openai",
            "active_provider": "openai",
            "active_model": "openai/gpt-4o-mini",
            "transport": "openai_compatible",
            "base_url": "https://api.openai.com/v1",
            "active_matches_selected": True,
            "last_live_probe": {
                "ok": True,
                "transport": "openai_compatible",
                "checked_at": "2026-03-27T12:00:00+00:00",
                "matches_current_model": True,
                "matches_current_base_url": True,
            },
            "last_capability_probe": {
                "checked": True,
                "detail": "model_listed",
                "current_model_listed": True,
                "matched_model": "openai/gpt-4o-mini",
                "listed_model_count": 2,
                "listed_model_sample": ["openai/gpt-4o-mini", "openai/gpt-4.1-mini"],
            },
        },
    )

    assert payload["health_posture"] == "healthy"
    assert payload["health_tone"] == "ok"
    assert payload["probe"]["posture"] == "matched"
    assert payload["capability"]["posture"] == "listed"
    assert payload["route"]["active_matches_selected"] is True


def test_dashboard_provider_health_summary_prefers_provider_suppression() -> None:
    payload = dashboard_provider_health_summary(
        provider_telemetry_payload={
            "provider": "failover",
            "summary": {
                "state": "degraded",
                "suppression_reason": "quota",
            },
        },
        provider_autonomy_payload={
            "provider": "failover",
            "state": "degraded",
            "suppression_reason": "quota",
            "suppression_backoff_s": 1800.0,
            "suppression_hint": "Provider is suppressed because quota is exhausted.",
            "last_error_class": "quota",
        },
        provider_status_payload={
            "ok": True,
            "provider": "failover",
            "selected_provider": "failover",
        },
    )

    assert payload["health_posture"] == "suppressed"
    assert payload["health_tone"] == "danger"
    assert payload["autonomy"]["suppression_reason"] == "quota"
    assert payload["probe"]["posture"] == "missing"
    assert "quota" in payload["operator_hint"]


def test_dashboard_provider_health_summary_preserves_selected_and_active_route_context() -> None:
    payload = dashboard_provider_health_summary(
        provider_telemetry_payload={
            "provider": "anthropic",
            "summary": {
                "state": "healthy",
            },
        },
        provider_autonomy_payload={
            "provider": "anthropic",
            "state": "healthy",
        },
        provider_status_payload={
            "ok": True,
            "provider": "anthropic",
            "selected_provider": "anthropic",
            "active_provider": "openai",
            "active_model": "openai/gpt-4o-mini",
            "transport": "openai_compatible",
            "active_matches_selected": False,
            "last_live_probe": {
                "ok": True,
                "matches_current_model": False,
                "matches_current_base_url": False,
            },
        },
    )

    assert payload["health_posture"] == "cache_stale"
    assert payload["route"]["selected_provider"] == "anthropic"
    assert payload["route"]["active_provider"] == "openai"
    assert payload["route"]["active_matches_selected"] is False


def test_dashboard_provider_budget_summary_surfaces_quota_exhaustion() -> None:
    payload = dashboard_provider_budget_summary(
        provider_telemetry_payload={
            "provider": "failover",
            "model": "openai/gpt-4o-mini",
            "summary": {
                "state": "degraded",
                "suppression_reason": "quota",
                "hints": ["Provider quota or billing appears exhausted."],
            },
            "counters": {
                "requests": 12,
                "successes": 9,
                "auth_errors": 0,
                "rate_limit_errors": 0,
                "http_errors": 2,
                "last_error_class": "quota",
            },
        },
        provider_autonomy_payload={
            "provider": "failover",
            "state": "degraded",
            "suppression_reason": "quota",
            "suppression_backoff_s": 1800.0,
            "suppression_hint": "Provider is suppressed because quota is exhausted.",
            "last_error_class": "quota",
        },
        provider_status_payload={
            "ok": True,
            "provider": "failover",
            "selected_provider": "failover",
            "active_provider": "openai",
            "active_model": "openai/gpt-4o-mini",
            "transport": "openai_compatible",
        },
    )

    assert payload["budget_posture"] == "quota_exhausted"
    assert payload["budget_tone"] == "danger"
    assert payload["quota"]["posture"] == "exhausted"
    assert payload["rate_limit"]["posture"] == "clear"
    assert "quota" in payload["operator_hint"].lower()


def test_dashboard_provider_budget_summary_marks_non_budget_auth_block() -> None:
    payload = dashboard_provider_budget_summary(
        provider_telemetry_payload={
            "provider": "openai",
            "summary": {
                "state": "degraded",
                "hints": ["Authentication was rejected; review the provider key."],
            },
            "counters": {
                "requests": 4,
                "successes": 0,
                "auth_errors": 2,
                "rate_limit_errors": 0,
                "http_errors": 2,
                "last_error_class": "auth",
            },
        },
        provider_autonomy_payload={
            "provider": "openai",
            "state": "degraded",
            "suppression_reason": "auth",
            "suppression_backoff_s": 900.0,
            "last_error_class": "auth",
        },
        provider_status_payload={
            "ok": True,
            "provider": "openai",
            "selected_provider": "openai",
            "active_provider": "openai",
            "active_model": "openai/gpt-4o-mini",
        },
    )

    assert payload["budget_posture"] == "non_budget_block"
    assert payload["budget_tone"] == "warn"
    assert payload["quota"]["posture"] == "clear"
    assert payload["rate_limit"]["posture"] == "clear"
    assert "not quota" in payload["operator_hint"].lower()


def test_dashboard_provider_budget_summary_does_not_stick_on_historical_rate_limit_errors() -> None:
    payload = dashboard_provider_budget_summary(
        provider_telemetry_payload={
            "provider": "openai",
            "summary": {
                "state": "healthy",
                "hints": ["Cached provider route and capability posture look steady."],
            },
            "counters": {
                "requests": 18,
                "successes": 17,
                "auth_errors": 0,
                "rate_limit_errors": 3,
                "http_errors": 1,
                "last_error_class": "",
            },
        },
        provider_autonomy_payload={
            "provider": "openai",
            "state": "healthy",
            "suppression_reason": "",
            "suppression_backoff_s": 0.0,
            "last_error_class": "",
        },
        provider_status_payload={
            "ok": True,
            "provider": "openai",
            "selected_provider": "openai",
            "active_provider": "openai",
            "active_model": "openai/gpt-4o-mini",
        },
    )

    assert payload["budget_posture"] == "clear"
    assert payload["rate_limit"]["posture"] == "clear"
    assert payload["rate_limit"]["error_count"] == 3


def test_dashboard_state_payload_assembles_sections() -> None:
    payload = dashboard_state_payload(
        contract_version="2026-03-02",
        generated_at="2026-03-17T00:00:00+00:00",
        control_plane={"ok": True},
        control_plane_to_dict=lambda value: {"wrapped": value},
        queue_payload={"pending": 1},
        sessions_payload={"count": 2},
        channels_payload={"count": 3},
        channels_dispatcher_payload={"running": True},
        channels_delivery_payload={"ok": True},
        channels_inbound_payload={"ok": True},
        channels_recovery_payload={"ok": True},
        discord_payload={"available": True},
        telegram_payload={"available": False},
        cron_payload={"running": True},
        heartbeat_payload={"enabled": True},
        subagents_payload={"active": 1},
        supervisor_payload={"healthy": True},
        skills_payload={"loaded": 4},
        workspace_payload={"ok": True},
        handoff_payload={"items": []},
        onboarding_payload={"status": "ready"},
        bootstrap_payload={"ok": True},
        memory_payload={"profile": {}},
        provider_telemetry_payload={"provider": "ollama"},
        provider_autonomy_payload={"mode": "allowed"},
        provider_status_payload={"ok": True, "provider": "openai"},
        provider_health_payload={"health_posture": "healthy"},
        provider_budget_payload={"budget_posture": "clear"},
        self_evolution_payload={"enabled": False},
        runtime_posture_payload={"autonomy_posture": "disabled"},
        runtime_policy_payload={"policy_posture": "manual_only"},
    )

    assert payload["control_plane"] == {"wrapped": {"ok": True}}
    assert payload["provider"] == {
        "telemetry": {"provider": "ollama"},
        "autonomy": {"mode": "allowed"},
        "status": {"ok": True, "provider": "openai"},
        "health": {"health_posture": "healthy"},
        "budget": {"budget_posture": "clear"},
    }
    assert payload["runtime"] == {
        "posture": {"autonomy_posture": "disabled"},
        "policy": {"policy_posture": "manual_only"},
    }
    assert payload["skills"] == {"loaded": 4}
