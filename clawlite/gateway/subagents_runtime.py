from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable


async def run_subagent_maintenance_loop(
    *,
    engine: Any,
    state: dict[str, Any],
    stop_event: asyncio.Event,
    interval_seconds: float,
    utc_now_iso: Callable[[], str],
    log_warning: Callable[[Exception], None],
) -> None:
    while True:
        try:
            swept = await engine.subagents.sweep_async()
            state["ticks"] = int(state.get("ticks", 0) or 0) + 1
            state["success_count"] = int(state.get("success_count", 0) or 0) + 1
            state["last_result"] = dict(swept or {})
            state["last_error"] = ""
            state["last_run_iso"] = utc_now_iso()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            state["ticks"] = int(state.get("ticks", 0) or 0) + 1
            state["error_count"] = int(state.get("error_count", 0) or 0) + 1
            state["last_error"] = str(exc)
            state["last_run_iso"] = utc_now_iso()
            log_warning(exc)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
            return
        except asyncio.TimeoutError:
            continue


async def resume_recoverable_subagents(
    *,
    component: dict[str, Any],
    engine: Any,
    record_autonomy_event: Callable[..., None],
    send_autonomy_notice: Callable[..., Awaitable[Any]],
    log_warning: Callable[..., None],
    log_info: Callable[..., None],
    now_iso: Callable[[], str],
) -> dict[str, Any]:
    component["enabled"] = True
    component["running"] = True
    component["last_error"] = ""
    resume_factory = getattr(engine, "_subagent_resume_runner_factory", None)
    if not callable(resume_factory):
        component["running"] = False
        component["last_error"] = "resume_runner_factory_missing"
        return {"replayed": 0, "replayed_groups": 0, "failed": 0, "failed_groups": 0}

    auto_replay_reasons = {"manager_restart", "orphaned_task", "orphaned_queue_entry"}
    rows = [
        run
        for run in engine.subagents.list_resumable_runs(limit=128)
        if str(dict(getattr(run, "metadata", {}) or {}).get("last_status_reason", "") or "").strip() in auto_replay_reasons
    ][:64]
    replayed = 0
    failed: list[dict[str, str]] = []
    grouped_run_ids: dict[str, set[str]] = {}
    failed_group_ids: set[str] = set()

    for run in rows:
        metadata = dict(getattr(run, "metadata", {}) or {})
        group_id = str(metadata.get("parallel_group_id", "") or "").strip()
        group_key = group_id or str(getattr(run, "run_id", "") or "").strip()
        try:
            await engine.subagents.resume(
                run_id=str(getattr(run, "run_id", "") or ""),
                runner=resume_factory(run),
            )
        except Exception as exc:
            failed.append(
                {
                    "run_id": str(getattr(run, "run_id", "") or "").strip(),
                    "group_id": group_id,
                    "error": str(exc),
                }
            )
            failed_group_ids.add(group_key)
            continue
        replayed += 1
        grouped_run_ids.setdefault(group_key, set()).add(str(getattr(run, "run_id", "") or "").strip())

    await asyncio.sleep(0)
    component["running"] = False
    component["replayed"] = replayed
    component["replayed_groups"] = len(grouped_run_ids)
    component["failed"] = len(failed)
    component["failed_groups"] = len(failed_group_ids)
    component["last_group_ids"] = sorted(grouped_run_ids.keys())[-8:]
    component["last_failed_runs"] = failed[-8:]
    component["last_run_iso"] = now_iso()

    if failed:
        component["last_error"] = failed[-1]["error"]
        log_warning(
            "subagent replay completed replayed={} failed={} last_error={}",
            replayed,
            len(failed),
            component["last_error"],
        )
    elif replayed:
        log_info("subagent replay completed replayed={}", replayed)

    event_at = str(component.get("last_run_iso", "") or "")
    record_autonomy_event(
        "subagents",
        "startup_replay",
        "ok" if not failed else "partial",
        summary=f"startup replay replayed={replayed} failed={len(failed)}",
        metadata={
            "replayed": replayed,
            "replayed_groups": len(grouped_run_ids),
            "failed": len(failed),
            "failed_groups": len(failed_group_ids),
            "group_ids": sorted(grouped_run_ids.keys())[-8:],
        },
        event_at=event_at,
    )
    if replayed or failed:
        await send_autonomy_notice(
            "subagents",
            "startup_replay",
            "ok" if not failed else "partial",
            text=(
                "Autonomy notice: startup subagent replay "
                f"replayed={replayed} failed={len(failed)} groups={len(grouped_run_ids)}."
            ),
            metadata={
                "source": "subagents",
                "replayed": replayed,
                "replayed_groups": len(grouped_run_ids),
                "failed": len(failed),
                "failed_groups": len(failed_group_ids),
                "group_ids": sorted(grouped_run_ids.keys())[-8:],
            },
            event_at=event_at,
        )
    return {
        "replayed": replayed,
        "failed": len(failed),
    }


__all__ = [
    "resume_recoverable_subagents",
    "run_subagent_maintenance_loop",
]
