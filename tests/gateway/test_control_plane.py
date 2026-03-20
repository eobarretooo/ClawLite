from __future__ import annotations

from types import SimpleNamespace

from clawlite.gateway.control_plane import (
    build_control_plane_payload,
    control_plane_auth_payload,
    parse_iso_timestamp,
    reasoning_layer_metrics_from_payload,
    semantic_metrics_from_payload,
)


def test_control_plane_auth_payload_reads_guard_shape() -> None:
    guard = SimpleNamespace(
        posture=lambda: "required",
        mode="token",
        allow_loopback_without_auth=False,
        protect_health=True,
        token="secret",
        header_name="x-clawlite-token",
        query_param="token",
    )

    payload = control_plane_auth_payload(auth_guard=guard)

    assert payload == {
        "posture": "required",
        "mode": "token",
        "allow_loopback_without_auth": False,
        "protect_health": True,
        "token_configured": True,
        "header_name": "x-clawlite-token",
        "query_param": "token",
        "dashboard_handoff_enabled": True,
        "dashboard_handoff_header_name": "",
        "dashboard_handoff_query_param": "",
        "dashboard_session_enabled": False,
        "dashboard_session_header_name": "",
        "dashboard_session_query_param": "",
        "dashboard_client_header_name": "",
        "dashboard_client_query_param": "",
    }


def test_build_control_plane_payload_preserves_components_and_flags() -> None:
    payload = build_control_plane_payload(
        ready=True,
        phase="running",
        contract_version="2026-03-04",
        server_time="2026-03-17T12:00:00+00:00",
        components={"cron": {"running": True}},
        auth_payload={"posture": "required"},
        memory_proactive_enabled=True,
    )

    assert payload["components"]["cron"]["running"] is True
    assert payload["auth"]["posture"] == "required"
    assert payload["memory_proactive_enabled"] is True


def test_parse_iso_timestamp_normalizes_zulu_and_naive_values() -> None:
    zulu = parse_iso_timestamp("2026-03-17T12:00:00Z")
    naive = parse_iso_timestamp("2026-03-17T12:00:00")

    assert zulu is not None and zulu.isoformat() == "2026-03-17T12:00:00+00:00"
    assert naive is not None and naive.isoformat() == "2026-03-17T12:00:00+00:00"
    assert parse_iso_timestamp("") is None


def test_semantic_and_reasoning_metrics_extract_expected_fields() -> None:
    semantic = semantic_metrics_from_payload(
        {"semantic": {"enabled": True, "coverage_ratio": 0.75, "missing_records": 2, "total_records": 8}}
    )
    reasoning = reasoning_layer_metrics_from_payload(
        {"reasoningLayers": {"fact": {"coverage_ratio": 0.4}}, "confidence": {"mean": 0.8}}
    )

    assert semantic == {
        "enabled": True,
        "coverage_ratio": 0.75,
        "missing_records": 2,
        "total_records": 8,
    }
    assert reasoning == {
        "reasoning_layers": {"fact": {"coverage_ratio": 0.4}},
        "confidence": {"mean": 0.8},
    }
