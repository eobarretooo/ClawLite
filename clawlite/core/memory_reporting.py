from __future__ import annotations

import math
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Callable


def build_memory_diagnostics(*, diagnostics: dict[str, Any], backend_diagnostics: dict[str, Any]) -> dict[str, int | str | bool]:
    def _int_metric(source: dict[str, Any], name: str) -> int:
        return int(source.get(name, 0) or 0)

    def _str_metric(source: dict[str, Any], name: str) -> str:
        return str(source.get(name, "") or "")

    def _bool_metric(source: dict[str, Any], name: str) -> bool:
        return bool(source.get(name, False))

    return {
        "history_read_corrupt_lines": _int_metric(diagnostics, "history_read_corrupt_lines"),
        "history_repaired_files": _int_metric(diagnostics, "history_repaired_files"),
        "consolidate_writes": _int_metric(diagnostics, "consolidate_writes"),
        "consolidate_dedup_hits": _int_metric(diagnostics, "consolidate_dedup_hits"),
        "session_recovery_attempts": _int_metric(diagnostics, "session_recovery_attempts"),
        "session_recovery_hits": _int_metric(diagnostics, "session_recovery_hits"),
        "working_memory_promotions": _int_metric(diagnostics, "working_memory_promotions"),
        "working_memory_promotion_skips": _int_metric(diagnostics, "working_memory_promotion_skips"),
        "working_memory_promotion_rate_limited": _int_metric(diagnostics, "working_memory_promotion_rate_limited"),
        "privacy_audit_writes": _int_metric(diagnostics, "privacy_audit_writes"),
        "privacy_audit_skipped": _int_metric(diagnostics, "privacy_audit_skipped"),
        "privacy_audit_errors": _int_metric(diagnostics, "privacy_audit_errors"),
        "privacy_ttl_deleted": _int_metric(diagnostics, "privacy_ttl_deleted"),
        "privacy_encrypt_events": _int_metric(diagnostics, "privacy_encrypt_events"),
        "privacy_encrypt_errors": _int_metric(diagnostics, "privacy_encrypt_errors"),
        "privacy_decrypt_events": _int_metric(diagnostics, "privacy_decrypt_events"),
        "privacy_decrypt_errors": _int_metric(diagnostics, "privacy_decrypt_errors"),
        "privacy_key_load_events": _int_metric(diagnostics, "privacy_key_load_events"),
        "privacy_key_create_events": _int_metric(diagnostics, "privacy_key_create_events"),
        "privacy_key_errors": _int_metric(diagnostics, "privacy_key_errors"),
        "last_error": _str_metric(diagnostics, "last_error"),
        "backend_name": _str_metric(backend_diagnostics, "backend_name"),
        "backend_supported": _bool_metric(backend_diagnostics, "backend_supported"),
        "backend_initialized": _bool_metric(backend_diagnostics, "backend_initialized"),
        "backend_init_error": _str_metric(backend_diagnostics, "backend_init_error"),
        "backend_driver": _str_metric(backend_diagnostics, "backend_driver"),
        "backend_connection_ok": _bool_metric(backend_diagnostics, "backend_connection_ok"),
        "backend_vector_extension": _bool_metric(backend_diagnostics, "backend_vector_extension"),
        "backend_vector_version": _str_metric(backend_diagnostics, "backend_vector_version"),
        "backend_vector_index": _bool_metric(backend_diagnostics, "backend_vector_index"),
        "backend_vector_index_kind": _str_metric(backend_diagnostics, "backend_vector_index_kind"),
        "backend_vector_index_error": _str_metric(backend_diagnostics, "backend_vector_index_error"),
    }


def build_memory_analysis_stats(
    *,
    history_rows: list[Any],
    curated_rows: list[Any],
    semantic_enabled: bool,
    parse_iso_timestamp: Callable[[str], datetime],
    has_temporal_markers: Callable[[str], bool],
    normalize_reasoning_layer: Callable[[str], str],
    normalize_confidence: Callable[[Any], float],
    read_embeddings_map: Callable[[], dict[str, Any]],
    on_embeddings_error: Callable[[Exception], None] | None = None,
) -> dict[str, Any]:
    combined = history_rows + curated_rows
    record_ids = {
        str(row.id or "").strip()
        for row in combined
        if str(row.id or "").strip()
    }

    now = datetime.now(timezone.utc)
    cutoff_24h = now.timestamp() - (24 * 3600)
    cutoff_7d = now.timestamp() - (7 * 24 * 3600)
    cutoff_30d = now.timestamp() - (30 * 24 * 3600)

    last_24h = 0
    last_7d = 0
    last_30d = 0
    temporal_marked_count = 0
    sources: Counter[str] = Counter()
    categories: Counter[str] = Counter()
    reasoning_layers: Counter[str] = Counter()
    confidence_values: list[float] = []
    confidence_buckets: Counter[str] = Counter()

    for row in combined:
        text = str(row.text or "")
        created_at = parse_iso_timestamp(str(row.created_at or ""))
        created_ts = created_at.timestamp() if created_at.year > 1 else 0.0

        if created_ts >= cutoff_24h:
            last_24h += 1
        if created_ts >= cutoff_7d:
            last_7d += 1
        if created_ts >= cutoff_30d:
            last_30d += 1
        if has_temporal_markers(text):
            temporal_marked_count += 1
        sources[str(row.source or "unknown")] += 1
        categories[str(getattr(row, "category", "context") or "context")] += 1
        reasoning_layers[normalize_reasoning_layer(getattr(row, "reasoning_layer", "fact"))] += 1

        confidence_value = normalize_confidence(getattr(row, "confidence", 1.0))
        if math.isfinite(confidence_value):
            confidence_values.append(confidence_value)
            bounded_confidence = max(0.0, min(1.0, confidence_value))
            if bounded_confidence < 0.4:
                confidence_buckets["low"] += 1
            elif bounded_confidence < 0.7:
                confidence_buckets["medium"] += 1
            elif bounded_confidence < 0.9:
                confidence_buckets["high"] += 1
            else:
                confidence_buckets["very_high"] += 1
        else:
            confidence_buckets["unknown"] += 1

    top_sources = [
        {"source": source, "count": count}
        for source, count in sorted(sources.items(), key=lambda item: (-item[1], item[0]))[:8]
    ]

    try:
        embeddings = read_embeddings_map()
    except Exception as exc:
        if on_embeddings_error is not None:
            on_embeddings_error(exc)
        embeddings = {}
    embedded_records = len(record_ids.intersection(set(embeddings.keys())))
    total_records = len(record_ids)
    missing_records = max(0, total_records - embedded_records)
    coverage_ratio = float(1.0 if total_records == 0 else embedded_records / total_records)

    confidence_count = len(confidence_values)
    confidence_avg = round((sum(confidence_values) / confidence_count), 6) if confidence_count else 0.0
    confidence_min = round(min(confidence_values), 6) if confidence_count else 0.0
    confidence_max = round(max(confidence_values), 6) if confidence_count else 0.0

    return {
        "counts": {
            "history": len(history_rows),
            "curated": len(curated_rows),
            "total": len(combined),
        },
        "recent": {
            "last_24h": last_24h,
            "last_7d": last_7d,
            "last_30d": last_30d,
        },
        "temporal_marked_count": temporal_marked_count,
        "top_sources": top_sources,
        "categories": {
            name: count
            for name, count in sorted(categories.items(), key=lambda item: (-item[1], item[0]))
        },
        "reasoning_layers": {
            name: count
            for name, count in sorted(reasoning_layers.items(), key=lambda item: (-item[1], item[0]))
        },
        "confidence": {
            "count": confidence_count,
            "average": confidence_avg,
            "minimum": confidence_min,
            "maximum": confidence_max,
            "buckets": {
                name: count
                for name, count in sorted(confidence_buckets.items(), key=lambda item: item[0])
            },
        },
        "semantic": {
            "enabled": bool(semantic_enabled),
            "total_records": total_records,
            "embedded_records": embedded_records,
            "missing_records": missing_records,
            "coverage_ratio": round(coverage_ratio, 6),
            "coverage_percent": round(coverage_ratio * 100.0, 2),
        },
    }
