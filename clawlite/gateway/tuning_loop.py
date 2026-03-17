from __future__ import annotations

import asyncio
import datetime as dt
from typing import Any, Awaitable, Callable


async def run_memory_quality_tuning_tick(
    *,
    runtime: Any,
    now: dt.datetime,
    tuning_runner_state: dict[str, Any],
    collect_memory_quality_inputs: Callable[[], Awaitable[tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]]],
    parse_iso: Callable[[str], dt.datetime | None],
    plan_tuning_action: Callable[..., dict[str, Any]],
    resolve_notify_variant: Callable[..., tuple[str, str]],
    resolve_backfill_limit: Callable[..., int],
    resolve_snapshot_tag: Callable[..., str],
    build_tuning_action_entry: Callable[..., dict[str, Any] | None],
    record_tuning_runner_action: Callable[..., None],
    build_tuning_patch: Callable[..., dict[str, Any]],
    resolve_tuning_layer: Callable[[str], str],
    send_autonomy_notice: Callable[..., Awaitable[Any]],
    record_autonomy_event: Callable[..., None],
    tuning_loop_interval_seconds: int,
    tuning_loop_timeout_seconds: float,
    tuning_degrading_streak_threshold: int,
    tuning_recent_actions_limit: int,
    tuning_loop_cooldown_seconds: int,
    tuning_actions_per_hour_cap: int,
    tuning_error_backoff_seconds: int,
    log_warning: Callable[[Exception], None],
) -> None:
    now_iso = now.isoformat(timespec="seconds")
    memory_store = getattr(runtime.engine, "memory", None)
    update_quality_fn = getattr(memory_store, "update_quality_state", None)
    snapshot_fn = getattr(memory_store, "quality_state_snapshot", None)
    update_tuning_fn = getattr(memory_store, "update_quality_tuning_state", None)

    if not callable(update_quality_fn) or not callable(snapshot_fn):
        tuning_runner_state["last_result"] = "unsupported"
        tuning_runner_state["last_error"] = "memory_quality_methods_unavailable"
        tuning_runner_state["last_run_iso"] = now_iso
        tuning_runner_state["next_run_iso"] = (now + dt.timedelta(seconds=tuning_loop_interval_seconds)).isoformat(
            timespec="seconds"
        )
        return

    action = ""
    action_status = "noop"
    action_reason = ""
    action_metadata: dict[str, Any] = {}
    tick_error = ""
    next_wait_seconds = tuning_loop_interval_seconds

    try:
        retrieval_metrics, turn_metrics, semantic_metrics, reasoning_layer_metrics = await collect_memory_quality_inputs()

        def _call_quality_update_tuning() -> Any:
            kwargs = {
                "retrieval_metrics": retrieval_metrics,
                "turn_stability_metrics": turn_metrics,
                "semantic_metrics": {
                    "enabled": bool(semantic_metrics.get("enabled", False)),
                    "coverage_ratio": float(semantic_metrics.get("coverage_ratio", 0.0) or 0.0),
                },
                "sampled_at": now_iso,
            }
            if reasoning_layer_metrics:
                try:
                    return update_quality_fn(
                        **kwargs,
                        reasoning_layer_metrics=reasoning_layer_metrics,
                    )
                except TypeError:
                    return update_quality_fn(**kwargs)
            return update_quality_fn(**kwargs)

        report = await asyncio.wait_for(
            asyncio.to_thread(_call_quality_update_tuning),
            timeout=tuning_loop_timeout_seconds,
        )
        snapshot = await asyncio.wait_for(asyncio.to_thread(snapshot_fn), timeout=tuning_loop_timeout_seconds)
        tuning_state = snapshot.get("tuning", {}) if isinstance(snapshot, dict) else {}
        plan = plan_tuning_action(
            report=report if isinstance(report, dict) else {},
            tuning_state=tuning_state if isinstance(tuning_state, dict) else {},
            now=now,
            parse_iso=parse_iso,
            degrading_streak_threshold=tuning_degrading_streak_threshold,
            recent_actions_limit=tuning_recent_actions_limit,
            cooldown_seconds=tuning_loop_cooldown_seconds,
            actions_per_hour_cap=tuning_actions_per_hour_cap,
        )
        drift = str(plan.get("drift", "") or "")
        score = int(plan.get("score", 0) or 0)
        weakest_layer = str(plan.get("weakest_layer", "") or "")
        degrading_streak = int(plan.get("degrading_streak", 0) or 0)
        severity = str(plan.get("severity", "") or "")
        action = str(plan.get("action", "") or "")
        playbook_id = str(plan.get("playbook_id", "") or "")
        action_reason = str(plan.get("action_reason", "") or "")
        action_status = str(plan.get("action_status", action_status) or action_status)
        action_metadata = dict(plan.get("action_metadata", {}) or {})

        if action and bool(plan.get("should_execute", False)):
            if action == "notify_operator":
                layer_suffix = f" layer={weakest_layer}." if weakest_layer else ""
                template_id, text_marker = resolve_notify_variant(
                    layer=weakest_layer,
                    severity=severity,
                )
                action_metadata["template_id"] = template_id
                await send_autonomy_notice(
                    "memory_quality_tuning",
                    action,
                    "ok",
                    text=(
                        f"Memory quality drift detected ({severity}). "
                        f"score={score} streak={degrading_streak}.{layer_suffix} "
                        f"variant={text_marker} Monitoring in progress."
                    ),
                    metadata={
                        "source": "memory_quality_tuning",
                        "trigger": "quality_loop",
                        "drift": drift,
                        **action_metadata,
                    },
                    summary=f"notice sent for {action}",
                    event_at=now_iso,
                )
                action_status = "ok"
            elif action == "semantic_backfill":
                missing_records = int(semantic_metrics.get("missing_records", 0) or 0)
                backfill_limit = resolve_backfill_limit(
                    layer=weakest_layer,
                    severity=severity,
                    missing_records=missing_records,
                )
                action_metadata["backfill_limit"] = backfill_limit
                backfill_fn = getattr(memory_store, "backfill_embeddings", None)
                if callable(backfill_fn):
                    await asyncio.wait_for(
                        asyncio.to_thread(backfill_fn, limit=backfill_limit),
                        timeout=tuning_loop_timeout_seconds,
                    )
                    action_status = "ok"
                else:
                    action_status = "unsupported"
            elif action == "memory_snapshot":
                snapshot_memory_fn = getattr(memory_store, "snapshot", None)
                snapshot_tag = resolve_snapshot_tag(layer=weakest_layer, severity=severity)
                action_metadata["snapshot_tag"] = snapshot_tag
                if callable(snapshot_memory_fn):
                    await asyncio.wait_for(
                        asyncio.to_thread(snapshot_memory_fn, snapshot_tag),
                        timeout=tuning_loop_timeout_seconds,
                    )
                    action_status = "ok"
                else:
                    action_status = "unsupported"

        action_entry = build_tuning_action_entry(
            action=action,
            status=action_status,
            reason=action_reason,
            at=now_iso,
            metadata=action_metadata,
        )

        if action_status == "ok":
            tuning_runner_state["action_count"] = int(tuning_runner_state.get("action_count", 0) or 0) + 1

        if action:
            record_tuning_runner_action(
                tuning_runner_state,
                weakest_layer=weakest_layer,
                action=action,
                playbook_id=playbook_id,
                action_status=action_status,
                action_metadata=action_metadata,
                resolve_tuning_layer=resolve_tuning_layer,
            )

        if callable(update_tuning_fn):
            tuning_patch = build_tuning_patch(
                degrading_streak=degrading_streak,
                now_iso=now_iso,
                interval_seconds=tuning_loop_interval_seconds,
                action_entry=action_entry,
            )
            await asyncio.wait_for(asyncio.to_thread(update_tuning_fn, tuning_patch), timeout=tuning_loop_timeout_seconds)

        tuning_runner_state["success_count"] = int(tuning_runner_state.get("success_count", 0) or 0) + 1
        tuning_runner_state["last_result"] = "ok"
        tuning_runner_state["last_error"] = ""
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        tick_error = str(exc)
        next_wait_seconds = tuning_error_backoff_seconds
        tuning_runner_state["error_count"] = int(tuning_runner_state.get("error_count", 0) or 0) + 1
        tuning_runner_state["last_result"] = "error"
        tuning_runner_state["last_error"] = tick_error
        log_warning(exc)
        if callable(update_tuning_fn):
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(
                        update_tuning_fn,
                        {
                            "last_run_at": now_iso,
                            "next_run_at": (now + dt.timedelta(seconds=tuning_error_backoff_seconds)).isoformat(timespec="seconds"),
                            "last_error": tick_error,
                        },
                    ),
                    timeout=tuning_loop_timeout_seconds,
                )
            except Exception:
                pass
    finally:
        tuning_runner_state["last_run_iso"] = now_iso
        tuning_runner_state["next_run_iso"] = (now + dt.timedelta(seconds=next_wait_seconds)).isoformat(timespec="seconds")
        tuning_runner_state["last_action"] = str(action or "")
        tuning_runner_state["last_action_status"] = str(action_status or "")
        tuning_runner_state["last_action_reason"] = str(action_reason or "")
        if tick_error and not tuning_runner_state.get("last_error"):
            tuning_runner_state["last_error"] = tick_error
        if tick_error:
            record_autonomy_event(
                "memory_quality_tuning",
                "tuning_tick",
                "failed",
                summary=f"memory quality tuning failed: {tick_error}",
                metadata={
                    "error": tick_error,
                    "last_action": action,
                    "last_action_status": action_status,
                },
                event_at=now_iso,
            )
        elif action:
            record_autonomy_event(
                "memory_quality_tuning",
                action,
                action_status or "ok",
                summary=f"{action} -> {action_status or 'ok'}",
                metadata={
                    "reason": action_reason,
                    **dict(action_metadata),
                },
                event_at=now_iso,
            )
        elif str(tuning_runner_state.get("last_result", "") or "") == "unsupported":
            record_autonomy_event(
                "memory_quality_tuning",
                "tuning_tick",
                "unsupported",
                summary="memory quality methods unavailable",
                metadata={"error": str(tuning_runner_state.get("last_error", "") or "")},
                event_at=now_iso,
            )


__all__ = ["run_memory_quality_tuning_tick"]
