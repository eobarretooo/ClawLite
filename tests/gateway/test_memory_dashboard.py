from __future__ import annotations

from types import SimpleNamespace

from clawlite.gateway.memory_dashboard import (
    dashboard_memory_summary,
    memory_analysis_snapshot,
    memory_quality_snapshot,
    memory_remediation_summary,
)


class _FakeMonitor:
    def telemetry(self) -> dict[str, object]:
        return {"pending": 2}


class _BrokenMonitor:
    def telemetry(self) -> dict[str, object]:
        raise RuntimeError("boom")


class _FakeMemoryStore:
    def analysis_stats(self) -> dict[str, object]:
        return {"semantic": {"enabled": True}}

    def quality_state_snapshot(self) -> dict[str, object]:
        return {"tuning": {"enabled": True}}


def test_memory_dashboard_helpers_collect_analysis_and_quality() -> None:
    store = _FakeMemoryStore()
    assert memory_analysis_snapshot(store) == {"semantic": {"enabled": True}}
    assert memory_quality_snapshot(store) == {"tuning": {"enabled": True}}


def test_dashboard_memory_summary_includes_all_sections() -> None:
    payload = dashboard_memory_summary(
        memory_monitor=_FakeMonitor(),
        memory_store=_FakeMemoryStore(),
        config=SimpleNamespace(name="cfg"),
        memory_profile_snapshot_fn=lambda _cfg: {"profile": "ok"},
        memory_suggest_snapshot_fn=lambda _cfg, refresh=False: {"refresh": refresh, "count": 1},
        memory_version_snapshot_fn=lambda _cfg: {"versions": []},
    )
    assert payload["monitor"] == {"pending": 2, "enabled": True}
    assert payload["analysis"] == {"semantic": {"enabled": True}}
    assert payload["profile"] == {"profile": "ok"}
    assert payload["suggestions"] == {"refresh": False, "count": 1}
    assert payload["versions"] == {"versions": []}
    assert payload["quality"] == {"tuning": {"enabled": True}}
    assert payload["remediation"]["priority"] == "create_snapshot"
    assert payload["remediation"]["posture"] == "snapshot_missing"


def test_dashboard_memory_summary_fail_soft_when_monitor_errors() -> None:
    payload = dashboard_memory_summary(
        memory_monitor=_BrokenMonitor(),
        memory_store=SimpleNamespace(),
        config=SimpleNamespace(name="cfg"),
        memory_profile_snapshot_fn=lambda _cfg: {},
        memory_suggest_snapshot_fn=lambda _cfg, refresh=False: {"refresh": refresh},
        memory_version_snapshot_fn=lambda _cfg: {},
    )
    assert payload["monitor"]["enabled"] is True
    assert payload["monitor"]["error"] == "memory_monitor_unavailable"
    assert payload["analysis"] == {}
    assert payload["quality"] == {}


def test_memory_remediation_summary_prefers_top_suggestion_when_available() -> None:
    payload = memory_remediation_summary(
        analysis_payload={
            "semantic": {
                "coverage_ratio": 0.72,
                "total_records": 120,
                "missing_records": 12,
            }
        },
        quality_payload={
            "current": {
                "score": 81,
            },
            "trend": {
                "assessment": "stable",
            },
        },
        suggestions_payload={
            "count": 2,
            "source": "pending",
            "suggestions": [
                {
                    "text": "Review retrieval gaps for Discord ticket history.",
                    "trigger": "discord_gap",
                    "priority": 0.91,
                    "created_at": "2026-03-27T10:00:00+00:00",
                },
                {
                    "text": "Lower-priority suggestion",
                    "trigger": "memory_gap",
                    "priority": 0.2,
                    "created_at": "2026-03-27T10:05:00+00:00",
                },
            ],
        },
        versions_payload={"count": 3},
    )

    assert payload["posture"] == "guided"
    assert payload["priority"] == "review_suggestion"
    assert payload["suggestions"]["top_trigger"] == "discord_gap"
    assert payload["suggestions"]["count"] == 2


def test_memory_remediation_summary_surfaces_quality_attention_without_suggestions() -> None:
    payload = memory_remediation_summary(
        analysis_payload={
            "semantic": {
                "coverage_ratio": 0.84,
                "total_records": 140,
                "missing_records": 10,
            }
        },
        quality_payload={
            "current": {
                "score": 52,
                "drift": {
                    "assessment": "degrading",
                },
            },
            "trend": {
                "assessment": "degrading",
                "degrading_streak": 3,
            },
        },
        suggestions_payload={"count": 0, "suggestions": []},
        versions_payload={"count": 2},
    )

    assert payload["posture"] == "quality_attention"
    assert payload["priority"] == "inspect_quality"
    assert payload["quality"]["score"] == 52.0
    assert payload["quality"]["degrading_streak"] == 3


def test_memory_remediation_summary_surfaces_versions_unavailable_instead_of_snapshot_missing() -> None:
    payload = memory_remediation_summary(
        analysis_payload={
            "semantic": {
                "coverage_ratio": 0.84,
                "total_records": 140,
                "missing_records": 10,
            }
        },
        quality_payload={
            "current": {
                "score": 82,
            },
            "trend": {
                "assessment": "stable",
            },
        },
        suggestions_payload={"count": 0, "suggestions": []},
        versions_payload={
            "ok": False,
            "error": {
                "type": "RuntimeError",
                "message": "versions-path-unavailable",
            },
        },
    )

    assert payload["posture"] == "versions_unavailable"
    assert payload["priority"] == "inspect_versions"
    assert payload["versions"]["ok"] is False
    assert payload["versions"]["error_type"] == "RuntimeError"
