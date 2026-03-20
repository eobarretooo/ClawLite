from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable


def _quality_payload_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _quality_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _quality_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _quality_trend_rows(*, history: list[Any], current: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [dict(row) for row in history if isinstance(row, dict)]
    if not current:
        return rows
    if not rows:
        return [dict(current)]
    last = _quality_payload_dict(rows[-1])
    current_sampled_at = str(current.get("sampled_at", "") or "")
    last_sampled_at = str(last.get("sampled_at", "") or "")
    if current_sampled_at and current_sampled_at != last_sampled_at:
        rows.append(dict(current))
    elif not current_sampled_at and current != last:
        rows.append(dict(current))
    return rows


def _quality_streak(values: list[str], target: str) -> int:
    count = 0
    for value in reversed(values):
        if value != target:
            break
        count += 1
    return count


def quality_state_trend(*, history: list[Any], current: dict[str, Any]) -> dict[str, Any]:
    rows = _quality_trend_rows(history=history, current=current)
    if not rows:
        return {
            "available": False,
            "assessment": "insufficient_history",
            "window_points": 0,
            "window_start_sampled_at": "",
            "window_end_sampled_at": "",
            "score_change": 0,
            "hit_rate_change": 0.0,
            "semantic_coverage_change": 0.0,
            "reasoning_balance_change": 0.0,
            "score_range": {"min": 0, "max": 0},
            "degrading_streak": 0,
            "improving_streak": 0,
            "weakest_layers": {},
        }

    scores = [_quality_int(row.get("score", 0)) for row in rows]
    first = _quality_payload_dict(rows[0])
    last = _quality_payload_dict(rows[-1])
    first_retrieval = _quality_payload_dict(first.get("retrieval", {}))
    last_retrieval = _quality_payload_dict(last.get("retrieval", {}))
    first_semantic = _quality_payload_dict(first.get("semantic", {}))
    last_semantic = _quality_payload_dict(last.get("semantic", {}))
    first_reasoning = _quality_payload_dict(first.get("reasoning_layers", {}))
    last_reasoning = _quality_payload_dict(last.get("reasoning_layers", {}))
    assessments = [
        str(_quality_payload_dict(row.get("drift", {})).get("assessment", "") or "").strip().lower()
        for row in rows
    ]

    weakest_layers: dict[str, int] = {}
    for row in rows:
        weakest = str(_quality_payload_dict(row.get("reasoning_layers", {})).get("weakest_layer", "") or "").strip()
        if weakest:
            weakest_layers[weakest] = int(weakest_layers.get(weakest, 0) or 0) + 1

    score_change = _quality_int(last.get("score", 0)) - _quality_int(first.get("score", 0))
    hit_rate_change = round(_quality_float(last_retrieval.get("hit_rate", 0.0)) - _quality_float(first_retrieval.get("hit_rate", 0.0)), 6)
    semantic_coverage_change = round(
        _quality_float(last_semantic.get("coverage_ratio", 0.0)) - _quality_float(first_semantic.get("coverage_ratio", 0.0)),
        6,
    )
    reasoning_balance_change = round(
        _quality_float(last_reasoning.get("balance_score", 0.0)) - _quality_float(first_reasoning.get("balance_score", 0.0)),
        6,
    )
    degrading_streak = _quality_streak(assessments, "degrading")
    improving_streak = _quality_streak(assessments, "improving")

    if len(rows) < 2:
        assessment = "insufficient_history"
    elif (
        degrading_streak >= 2
        or score_change <= -6
        or hit_rate_change <= -0.08
        or semantic_coverage_change <= -0.08
        or reasoning_balance_change <= -0.08
    ):
        assessment = "degrading"
    elif (
        improving_streak >= 2
        or score_change >= 6
        or hit_rate_change >= 0.08
        or semantic_coverage_change >= 0.08
        or reasoning_balance_change >= 0.08
    ):
        assessment = "improving"
    else:
        assessment = "stable"

    return {
        "available": True,
        "assessment": assessment,
        "window_points": len(rows),
        "window_start_sampled_at": str(first.get("sampled_at", "") or ""),
        "window_end_sampled_at": str(last.get("sampled_at", "") or ""),
        "score_change": score_change,
        "hit_rate_change": hit_rate_change,
        "semantic_coverage_change": semantic_coverage_change,
        "reasoning_balance_change": reasoning_balance_change,
        "score_range": {"min": min(scores), "max": max(scores)},
        "degrading_streak": degrading_streak,
        "improving_streak": improving_streak,
        "weakest_layers": dict(sorted(weakest_layers.items())),
    }


def quality_state_snapshot(
    *,
    quality_state_path: Path,
    load_json_dict: Callable[[Path, dict[str, Any]], dict[str, Any]],
    default_quality_state: Callable[[], dict[str, Any]],
    normalize_quality_tuning_state: Callable[[Any], dict[str, Any]],
) -> dict[str, Any]:
    payload = load_json_dict(quality_state_path, default_quality_state())
    history_raw = payload.get("history", [])
    history = history_raw if isinstance(history_raw, list) else []
    baseline = payload.get("baseline", {}) if isinstance(payload.get("baseline", {}), dict) else {}
    current = payload.get("current", {}) if isinstance(payload.get("current", {}), dict) else {}
    tuning = normalize_quality_tuning_state(payload.get("tuning", {}))
    return {
        "version": 1,
        "updated_at": str(payload.get("updated_at", "") or ""),
        "baseline": baseline,
        "current": current,
        "history": history,
        "trend": quality_state_trend(history=history, current=current),
        "tuning": tuning,
    }


def normalize_quality_tuning_state(
    *,
    raw: Any,
    default_quality_tuning_state: Callable[[], dict[str, Any]],
    quality_int: Callable[..., int],
    max_recent_actions: int,
) -> dict[str, Any]:
    payload = dict(raw) if isinstance(raw, dict) else {}
    defaults = default_quality_tuning_state()
    recent_actions_raw = payload.get("recent_actions", payload.get("recentActions", defaults["recent_actions"]))
    if not isinstance(recent_actions_raw, list):
        recent_actions_raw = []

    normalized_recent_actions: list[dict[str, Any]] = []
    for row in recent_actions_raw:
        if isinstance(row, dict):
            entry = dict(row)
            for key in ("action", "status", "reason", "at"):
                if key in entry:
                    entry[key] = str(entry.get(key, "") or "")
            normalized_recent_actions.append(entry)
        elif row is not None:
            normalized_recent_actions.append({"action": str(row)})

    return {
        "degrading_streak": quality_int(payload.get("degrading_streak", defaults["degrading_streak"])),
        "last_action": str(payload.get("last_action", defaults["last_action"]) or ""),
        "last_action_at": str(payload.get("last_action_at", defaults["last_action_at"]) or ""),
        "last_action_status": str(payload.get("last_action_status", defaults["last_action_status"]) or ""),
        "last_reason": str(payload.get("last_reason", defaults["last_reason"]) or ""),
        "next_run_at": str(payload.get("next_run_at", defaults["next_run_at"]) or ""),
        "last_run_at": str(payload.get("last_run_at", defaults["last_run_at"]) or ""),
        "last_error": str(payload.get("last_error", defaults["last_error"]) or ""),
        "recent_actions": normalized_recent_actions[-max(1, int(max_recent_actions or 1)) :],
    }


def merge_quality_tuning_state(
    *,
    current: Any,
    patch: Any,
    normalize_quality_tuning_state: Callable[[Any], dict[str, Any]],
    quality_int: Callable[..., int],
) -> dict[str, Any]:
    merged = normalize_quality_tuning_state(current)
    payload = dict(patch) if isinstance(patch, dict) else {}
    if not payload:
        return merged

    for key in (
        "degrading_streak",
        "last_action",
        "last_action_at",
        "last_action_status",
        "last_reason",
        "next_run_at",
        "last_run_at",
        "last_error",
    ):
        if key not in payload:
            continue
        if key == "degrading_streak":
            merged[key] = quality_int(payload.get(key), minimum=0, default=int(merged.get(key, 0) or 0))
        else:
            merged[key] = str(payload.get(key, "") or "")

    if "recentActions" in payload and "recent_actions" not in payload:
        recent_patch_raw = payload.get("recentActions")
    else:
        recent_patch_raw = payload.get("recent_actions")

    if isinstance(recent_patch_raw, list):
        merged["recent_actions"] = normalize_quality_tuning_state(
            {"recent_actions": list(merged.get("recent_actions", [])) + list(recent_patch_raw)}
        )["recent_actions"]
    elif isinstance(recent_patch_raw, dict):
        merged["recent_actions"] = normalize_quality_tuning_state(
            {"recent_actions": list(merged.get("recent_actions", [])) + [recent_patch_raw]}
        )["recent_actions"]

    return merged


def update_quality_tuning_state(
    *,
    previous_state: dict[str, Any],
    tuning_patch: dict[str, Any] | None,
    merge_quality_tuning_state: Callable[[Any, Any], dict[str, Any]],
    utcnow_iso: Callable[[], str],
    atomic_write_text_locked: Callable[[Path, str], None],
    quality_state_path: Path,
) -> dict[str, Any]:
    tuning = merge_quality_tuning_state(previous_state.get("tuning", {}), tuning_patch)
    updated_at = str(previous_state.get("updated_at", "") or utcnow_iso())
    if isinstance(tuning_patch, dict) and tuning_patch:
        updated_at = utcnow_iso()

    state = {
        "version": 1,
        "updated_at": updated_at,
        "baseline": previous_state.get("baseline", {}),
        "current": previous_state.get("current", {}),
        "history": previous_state.get("history", []),
        "tuning": tuning,
    }
    atomic_write_text_locked(
        quality_state_path,
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    return tuning


def update_quality_state(
    *,
    previous_state: dict[str, Any],
    retrieval_metrics: dict[str, Any] | None,
    turn_stability_metrics: dict[str, Any] | None,
    semantic_metrics: dict[str, Any] | None,
    reasoning_layer_metrics: dict[str, Any] | None,
    gateway_metrics: dict[str, Any] | None,
    sampled_at: str,
    tuning_patch: dict[str, Any] | None,
    quality_int: Callable[..., int],
    quality_float: Callable[..., float],
    quality_reasoning_metrics_payload: Callable[[dict[str, Any]], dict[str, Any]],
    merge_quality_tuning_state: Callable[[Any, Any], dict[str, Any]],
    utcnow_iso: Callable[[], str],
    atomic_write_text_locked: Callable[[Path, str], None],
    quality_state_path: Path,
    max_quality_history: int,
) -> dict[str, Any]:
    previous = previous_state.get("current", {}) if isinstance(previous_state.get("current", {}), dict) else {}

    retrieval_raw = retrieval_metrics if isinstance(retrieval_metrics, dict) else {}
    turn_raw = turn_stability_metrics if isinstance(turn_stability_metrics, dict) else {}
    semantic_raw = semantic_metrics if isinstance(semantic_metrics, dict) else {}
    reasoning_raw = reasoning_layer_metrics if isinstance(reasoning_layer_metrics, dict) else {}

    attempts = quality_int(retrieval_raw.get("attempts"))
    hits = quality_int(retrieval_raw.get("hits"))
    rewrites = quality_int(retrieval_raw.get("rewrites"))
    if hits > attempts:
        hits = attempts
    hit_rate = quality_float((float(hits) / float(attempts)) if attempts else retrieval_raw.get("hit_rate", 0.0))

    turn_successes = quality_int(turn_raw.get("successes"))
    turn_errors = quality_int(turn_raw.get("errors"))
    turn_total = turn_successes + turn_errors
    success_rate = quality_float(
        (float(turn_successes) / float(turn_total)) if turn_total else turn_raw.get("success_rate", 1.0),
        default=1.0,
    )
    error_rate = quality_float(1.0 - success_rate)

    semantic_coverage = quality_float(semantic_raw.get("coverage_ratio", 0.0))
    reasoning_payload = quality_reasoning_metrics_payload(reasoning_raw)

    reasoning_present = bool(
        reasoning_payload["provided"]
        and (reasoning_payload["has_distribution_signal"] or reasoning_payload["has_confidence_signal"])
    )
    confidence_average = float(reasoning_payload["confidence"]["average"])
    if not bool(reasoning_payload["has_confidence_signal"]):
        confidence_average = 0.5
    balance_score = float(reasoning_payload["balance_score"])
    weakest_ratio = float(reasoning_payload["weakest_ratio"])
    imbalance_penalty = 0.0
    if reasoning_present and weakest_ratio < 0.12:
        imbalance_penalty = min(1.0, (0.12 - weakest_ratio) / 0.12)

    reasoning_adjustment = 0.0
    if reasoning_present:
        reasoning_adjustment = ((balance_score - 0.5) * 3.0) + ((confidence_average - 0.5) * 3.0) - (imbalance_penalty * 2.0)
        reasoning_adjustment = max(-6.0, min(6.0, reasoning_adjustment))

    score_float = (hit_rate * 55.0) + (success_rate * 30.0) + (semantic_coverage * 15.0) + reasoning_adjustment
    score = quality_int(round(score_float), minimum=0)
    if score > 100:
        score = 100

    previous_score = quality_int(previous.get("score", 0))
    previous_hit_rate = quality_float(previous.get("retrieval", {}).get("hit_rate", 0.0)) if isinstance(previous.get("retrieval", {}), dict) else 0.0

    baseline_payload = previous_state.get("baseline", {}) if isinstance(previous_state.get("baseline", {}), dict) else {}
    baseline_score = quality_int(baseline_payload.get("score", score), default=score)
    baseline_hit_rate = (
        quality_float(baseline_payload.get("retrieval", {}).get("hit_rate", hit_rate))
        if isinstance(baseline_payload.get("retrieval", {}), dict)
        else hit_rate
    )

    score_delta_prev = score - previous_score
    score_delta_baseline = score - baseline_score
    hit_rate_delta_prev = round(hit_rate - previous_hit_rate, 6)
    hit_rate_delta_baseline = round(hit_rate - baseline_hit_rate, 6)

    previous_reasoning = previous.get("reasoning_layers", {}) if isinstance(previous.get("reasoning_layers", {}), dict) else {}
    previous_balance = quality_float(previous_reasoning.get("balance_score", balance_score), default=balance_score)
    previous_confidence_payload = previous_reasoning.get("confidence", {}) if isinstance(previous_reasoning.get("confidence", {}), dict) else {}
    previous_confidence_average = quality_float(
        previous_confidence_payload.get("average", confidence_average),
        default=confidence_average,
    )
    previous_weakest_ratio = quality_float(previous_reasoning.get("weakest_ratio", weakest_ratio), default=weakest_ratio)

    reasoning_balance_delta = round(balance_score - previous_balance, 6) if reasoning_present and bool(previous) else 0.0
    reasoning_confidence_delta = (
        round(confidence_average - previous_confidence_average, 6) if reasoning_present and bool(previous) else 0.0
    )
    reasoning_weakest_ratio_delta = (
        round(weakest_ratio - previous_weakest_ratio, 6) if reasoning_present and bool(previous) else 0.0
    )

    reasoning_degrading = bool(
        reasoning_present
        and bool(previous)
        and (
            reasoning_balance_delta <= -0.1
            or reasoning_confidence_delta <= -0.12
            or reasoning_weakest_ratio_delta <= -0.1
        )
    )
    reasoning_improving = bool(
        reasoning_present
        and bool(previous)
        and reasoning_balance_delta >= 0.1
        and reasoning_confidence_delta >= 0.08
        and reasoning_weakest_ratio_delta >= 0.08
    )

    if previous:
        score_degrading_threshold = -4 if reasoning_present else -5
        score_improving_threshold = 4 if reasoning_present else 5
        if score_delta_prev <= score_degrading_threshold or hit_rate_delta_prev <= -0.08 or reasoning_degrading:
            drift_assessment = "degrading"
        elif score_delta_prev >= score_improving_threshold or hit_rate_delta_prev >= 0.08 or reasoning_improving:
            drift_assessment = "improving"
        else:
            drift_assessment = "stable"
    else:
        drift_assessment = "baseline"

    recommendations: list[str] = []
    if attempts < 5:
        recommendations.append("Increase retrieval sample size to reduce score variance.")
    if hit_rate < 0.7:
        recommendations.append("Improve retrieval hit rate with stronger memory curation and query rewrites.")
    if error_rate > 0.2:
        recommendations.append("Reduce turn error rate by investigating recent memory and privacy failures.")
    if bool(semantic_raw.get("enabled", False)) and semantic_coverage < 0.6:
        recommendations.append("Run semantic embedding backfill to improve retrieval coverage.")
    if reasoning_present and weakest_ratio < 0.15:
        recommendations.append(
            f"Strengthen {reasoning_payload['weakest_layer']} reasoning coverage to rebalance memory quality signals."
        )
    if reasoning_present and balance_score < 0.65:
        recommendations.append("Rebalance reasoning layers by increasing underrepresented records in recent sessions.")
    if reasoning_present and confidence_average < 0.6:
        recommendations.append("Raise confidence quality by validating uncertain memories before promotion.")
    if drift_assessment == "degrading":
        recommendations.append("Quality drift detected; review memory diagnostics and recent regressions.")
    if not recommendations:
        recommendations.append("Quality is stable; continue monitoring and periodic memory snapshots.")

    report = {
        "sampled_at": str(sampled_at or utcnow_iso()),
        "score": score,
        "retrieval": {
            "attempts": attempts,
            "hits": hits,
            "rewrites": rewrites,
            "hit_rate": round(hit_rate, 6),
        },
        "turn_stability": {
            "successes": turn_successes,
            "errors": turn_errors,
            "success_rate": round(success_rate, 6),
            "error_rate": round(error_rate, 6),
        },
        "drift": {
            "assessment": drift_assessment,
            "score_delta_previous": score_delta_prev,
            "score_delta_baseline": score_delta_baseline,
            "hit_rate_delta_previous": hit_rate_delta_prev,
            "hit_rate_delta_baseline": hit_rate_delta_baseline,
            "reasoning_balance_delta_previous": reasoning_balance_delta,
            "reasoning_confidence_delta_previous": reasoning_confidence_delta,
            "reasoning_weakest_ratio_delta_previous": reasoning_weakest_ratio_delta,
        },
        "semantic": {
            "enabled": bool(semantic_raw.get("enabled", False)),
            "coverage_ratio": round(semantic_coverage, 6),
        },
        "reasoning_layers": {
            "total_records": int(reasoning_payload["total_records"]),
            "distribution": reasoning_payload["distribution"],
            "balance_score": float(reasoning_payload["balance_score"]),
            "weakest_layer": str(reasoning_payload["weakest_layer"]),
            "weakest_ratio": float(reasoning_payload["weakest_ratio"]),
            "confidence": reasoning_payload["confidence"],
        },
        "recommendations": recommendations,
    }
    if isinstance(gateway_metrics, dict) and gateway_metrics:
        report["gateway"] = gateway_metrics

    history = previous_state.get("history", []) if isinstance(previous_state.get("history", []), list) else []
    history.append(report)
    bounded_history = history[-max(1, int(max_quality_history or 1)) :]
    baseline = baseline_payload if baseline_payload else report

    state = {
        "version": 1,
        "updated_at": str(report["sampled_at"]),
        "baseline": baseline,
        "current": report,
        "history": bounded_history,
        "tuning": merge_quality_tuning_state(previous_state.get("tuning", {}), tuning_patch),
    }
    atomic_write_text_locked(
        quality_state_path,
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    return report
