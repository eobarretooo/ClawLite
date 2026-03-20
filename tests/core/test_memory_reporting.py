from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from clawlite.core.memory_reporting import (
    build_memory_analysis_stats,
    build_memory_diagnostics,
)


def test_build_memory_diagnostics_shapes_backend_and_runtime_counters() -> None:
    payload = build_memory_diagnostics(
        diagnostics={
            "history_read_corrupt_lines": 1,
            "history_repaired_files": 2,
            "consolidate_writes": 3,
            "consolidate_dedup_hits": 4,
            "session_recovery_attempts": 5,
            "session_recovery_hits": 6,
            "working_memory_promotions": 7,
            "working_memory_promotion_skips": 8,
            "privacy_audit_writes": 9,
            "privacy_audit_skipped": 10,
            "privacy_audit_errors": 11,
            "privacy_ttl_deleted": 12,
            "privacy_encrypt_events": 13,
            "privacy_encrypt_errors": 14,
            "privacy_decrypt_events": 15,
            "privacy_decrypt_errors": 16,
            "privacy_key_load_events": 17,
            "privacy_key_create_events": 18,
            "privacy_key_errors": 19,
            "last_error": "boom",
        },
        backend_diagnostics={
            "backend_name": "sqlite",
            "backend_supported": True,
            "backend_initialized": True,
            "backend_init_error": "",
            "backend_driver": "sqlite3",
            "backend_connection_ok": True,
            "backend_vector_extension": False,
            "backend_vector_version": "",
            "backend_vector_index": False,
            "backend_vector_index_kind": "",
            "backend_vector_index_error": "",
        },
    )
    assert payload["history_read_corrupt_lines"] == 1
    assert payload["backend_name"] == "sqlite"
    assert payload["backend_vector_index"] is False
    assert payload["last_error"] == "boom"


def test_build_memory_analysis_stats_computes_reasoning_and_semantic_summary() -> None:
    rows = [
        SimpleNamespace(
            id="a",
            text="temporal marker yesterday",
            created_at="2026-03-17T00:00:00+00:00",
            source="session:a",
            category="context",
            reasoning_layer="fact",
            confidence=0.95,
        ),
        SimpleNamespace(
            id="b",
            text="plain row",
            created_at="2026-03-17T00:00:00+00:00",
            source="session:b",
            category="plan",
            reasoning_layer="decision",
            confidence=0.55,
        ),
    ]

    payload = build_memory_analysis_stats(
        history_rows=rows,
        curated_rows=[],
        semantic_enabled=True,
        parse_iso_timestamp=lambda value: datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc),
        has_temporal_markers=lambda text: "yesterday" in text,
        normalize_reasoning_layer=lambda value: str(value or "fact"),
        normalize_confidence=lambda value: float(value),
        read_embeddings_map=lambda: {"a": [0.1, 0.2]},
    )

    assert payload["counts"]["history"] == 2
    assert payload["temporal_marked_count"] == 1
    assert payload["reasoning_layers"]["fact"] == 1
    assert payload["reasoning_layers"]["decision"] == 1
    assert payload["semantic"]["embedded_records"] == 1
    assert payload["semantic"]["missing_records"] == 1


def test_build_memory_analysis_stats_fail_soft_on_embedding_read_error() -> None:
    errors: list[str] = []
    payload = build_memory_analysis_stats(
        history_rows=[
            SimpleNamespace(
                id="a",
                text="row",
                created_at="2026-03-17T00:00:00+00:00",
                source="session:a",
                category="context",
                reasoning_layer="fact",
                confidence=0.8,
            )
        ],
        curated_rows=[],
        semantic_enabled=False,
        parse_iso_timestamp=lambda value: datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc),
        has_temporal_markers=lambda _text: False,
        normalize_reasoning_layer=lambda value: str(value or "fact"),
        normalize_confidence=lambda value: float(value),
        read_embeddings_map=lambda: (_ for _ in ()).throw(RuntimeError("embed boom")),
        on_embeddings_error=lambda exc: errors.append(str(exc)),
    )
    assert payload["semantic"]["embedded_records"] == 0
    assert payload["semantic"]["missing_records"] == 1
    assert errors == ["embed boom"]
