from __future__ import annotations

from typing import Any


def _memory_number(value: Any, *, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _memory_preview(value: Any, *, max_chars: int = 120) -> str:
    text = " ".join(str(value or "").strip().split())
    if len(text) <= max_chars:
        return text
    return f"{text[: max(1, max_chars - 3)]}..."


def memory_analysis_snapshot(memory_store: Any) -> dict[str, Any]:
    analysis_payload: dict[str, Any] = {}
    analysis_stats = getattr(memory_store, "analysis_stats", None)
    if callable(analysis_stats):
        try:
            raw_analysis = analysis_stats()
        except Exception:
            raw_analysis = {}
        if isinstance(raw_analysis, dict):
            analysis_payload = raw_analysis
    return analysis_payload


def memory_quality_snapshot(memory_store: Any) -> dict[str, Any]:
    quality_payload: dict[str, Any] = {}
    quality_state_snapshot = getattr(memory_store, "quality_state_snapshot", None)
    if callable(quality_state_snapshot):
        try:
            raw_quality = quality_state_snapshot()
        except Exception:
            raw_quality = {}
        if isinstance(raw_quality, dict):
            quality_payload = raw_quality
    return quality_payload


def memory_remediation_summary(
    *,
    analysis_payload: dict[str, Any],
    quality_payload: dict[str, Any],
    suggestions_payload: dict[str, Any],
    versions_payload: dict[str, Any],
) -> dict[str, Any]:
    analysis = dict(analysis_payload or {}) if isinstance(analysis_payload, dict) else {}
    quality = dict(quality_payload or {}) if isinstance(quality_payload, dict) else {}
    suggestions = dict(suggestions_payload or {}) if isinstance(suggestions_payload, dict) else {}
    versions = dict(versions_payload or {}) if isinstance(versions_payload, dict) else {}

    semantic = dict(analysis.get("semantic") or {}) if isinstance(analysis.get("semantic"), dict) else {}
    current = dict(quality.get("current") or {}) if isinstance(quality.get("current"), dict) else {}
    trend = dict(quality.get("trend") or {}) if isinstance(quality.get("trend"), dict) else {}
    current_drift = dict(current.get("drift") or {}) if isinstance(current.get("drift"), dict) else {}

    score = round(_memory_number(current.get("score")), 3)
    semantic_coverage = round(_memory_number(semantic.get("coverage_ratio")), 3)
    versions_ok = versions.get("ok", True) is not False
    versions_error = dict(versions.get("error") or {}) if isinstance(versions.get("error"), dict) else {}
    versions_count = max(
        0,
        int(
            versions.get("count", len(versions.get("versions", []) or []))
            or 0
        ),
    )
    suggestion_count = max(
        0,
        int(
            suggestions.get("count", len(suggestions.get("suggestions", []) or []))
            or 0
        ),
    )
    suggestion_rows = list(suggestions.get("suggestions", []) or [])
    suggestion_rows.sort(
        key=lambda row: (
            -_memory_number((row or {}).get("priority")),
            str((row or {}).get("created_at", "")),
        )
    )
    top_suggestion = dict(suggestion_rows[0] or {}) if suggestion_rows else {}
    top_suggestion_text = _memory_preview(top_suggestion.get("text", ""))
    top_suggestion_trigger = str(top_suggestion.get("trigger", "") or "").strip()
    top_suggestion_priority = round(_memory_number(top_suggestion.get("priority")), 3)
    drift_assessment = str(current_drift.get("assessment", "") or trend.get("assessment", "") or "").strip()
    degrading_streak = max(0, int(trend.get("degrading_streak", 0) or 0))
    semantic_total_records = max(0, int(semantic.get("total_records", 0) or 0))
    semantic_missing_records = max(0, int(semantic.get("missing_records", 0) or 0))

    if suggestions.get("ok") is False:
        posture = "suggestions_unavailable"
        tone = "warn"
        priority = "refresh_suggestions"
        summary = "suggestions unavailable"
        hint = "Refresh memory suggestions before relying on the remediation queue."
    elif suggestion_count > 0 and top_suggestion_text:
        posture = "guided"
        tone = "warn"
        priority = "review_suggestion"
        summary = top_suggestion_text
        hint = (
            f"Start with the highest-priority suggestion from {top_suggestion_trigger or 'memory_suggest'} "
            "before lower-priority cleanup."
        )
    elif score > 0.0 and (score < 65.0 or drift_assessment == "degrading"):
        posture = "quality_attention"
        tone = "warn"
        priority = "inspect_quality"
        summary = f"{int(round(score))} score | {drift_assessment or 'drift unknown'}"
        hint = "Inspect memory quality and follow the top recommendation before widening recall-heavy flows."
    elif semantic_total_records > 0 and semantic_coverage < 0.4:
        posture = "coverage_attention"
        tone = "warn"
        priority = "inspect_overview"
        summary = f"{int(round(semantic_coverage * 100))}% semantic coverage"
        hint = "Inspect memory overview and raise semantic coverage before depending on proactive recall."
    elif not versions_ok:
        posture = "versions_unavailable"
        tone = "warn"
        priority = "inspect_versions"
        summary = "snapshots unavailable"
        hint = (
            f"{str(versions_error.get('type', 'error') or 'error')} | "
            f"{str(versions_error.get('message', 'Memory versions snapshot failed.') or 'Memory versions snapshot failed.')}"
        )
    elif versions_count <= 0:
        posture = "snapshot_missing"
        tone = "warn"
        priority = "create_snapshot"
        summary = "no snapshots yet"
        hint = "Create a memory snapshot before risky cleanup or rollback-sensitive changes."
    else:
        posture = "clear"
        tone = "ok"
        priority = "none"
        summary = "no immediate remediation"
        hint = "Current memory signals do not suggest immediate operator action."

    return {
        "posture": posture,
        "tone": tone,
        "priority": priority,
        "summary": summary,
        "hint": hint,
        "suggestions": {
            "count": suggestion_count,
            "source": str(suggestions.get("source", "") or ""),
            "top_trigger": top_suggestion_trigger,
            "top_priority": top_suggestion_priority,
            "top_text": top_suggestion_text,
        },
        "quality": {
            "score": score,
            "trend": str(trend.get("assessment", "") or ""),
            "degrading_streak": degrading_streak,
        },
        "analysis": {
            "semantic_coverage_ratio": semantic_coverage,
            "semantic_total_records": semantic_total_records,
            "semantic_missing_records": semantic_missing_records,
        },
        "versions": {
            "ok": versions_ok,
            "count": versions_count,
            "error_type": str(versions_error.get("type", "") or ""),
        },
    }


def dashboard_memory_summary(
    *,
    memory_monitor: Any,
    memory_store: Any,
    config: Any,
    memory_profile_snapshot_fn,
    memory_suggest_snapshot_fn,
    memory_version_snapshot_fn,
) -> dict[str, Any]:
    monitor_payload: dict[str, Any]
    if memory_monitor is None:
        monitor_payload = {"enabled": False}
    else:
        try:
            monitor_payload = dict(memory_monitor.telemetry())
        except Exception:
            monitor_payload = {"enabled": False, "error": "memory_monitor_unavailable"}
        monitor_payload["enabled"] = True
    analysis_payload = memory_analysis_snapshot(memory_store)
    profile_payload = memory_profile_snapshot_fn(config)
    suggestions_payload = memory_suggest_snapshot_fn(config, refresh=False)
    versions_payload = memory_version_snapshot_fn(config)
    quality_payload = memory_quality_snapshot(memory_store)

    return {
        "monitor": monitor_payload,
        "analysis": analysis_payload,
        "profile": profile_payload,
        "suggestions": suggestions_payload,
        "versions": versions_payload,
        "quality": quality_payload,
        "remediation": memory_remediation_summary(
            analysis_payload=analysis_payload,
            quality_payload=quality_payload,
            suggestions_payload=suggestions_payload,
            versions_payload=versions_payload,
        ),
    }
