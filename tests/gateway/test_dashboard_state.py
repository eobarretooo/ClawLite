from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from clawlite.gateway.dashboard_state import (
    dashboard_channels_summary,
    dashboard_cron_summary,
    dashboard_preview,
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
        self_evolution_payload={"enabled": False},
        runtime_posture_payload={"autonomy_posture": "disabled"},
    )

    assert payload["control_plane"] == {"wrapped": {"ok": True}}
    assert payload["provider"] == {
        "telemetry": {"provider": "ollama"},
        "autonomy": {"mode": "allowed"},
        "status": {"ok": True, "provider": "openai"},
    }
    assert payload["runtime"] == {"posture": {"autonomy_posture": "disabled"}}
    assert payload["skills"] == {"loaded": 4}
