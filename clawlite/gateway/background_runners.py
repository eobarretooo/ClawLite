from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable


async def run_proactive_monitor_loop(
    *,
    state: dict[str, Any],
    stop_event: asyncio.Event,
    interval_seconds: int,
    is_running: Callable[[], bool],
    submit_proactive_wake: Callable[[], Awaitable[dict[str, Any]]],
    utc_now_iso: Callable[[], str],
    log_error: Callable[[Exception], None],
) -> None:
    first_tick = True
    while is_running():
        if not first_tick:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
            except (asyncio.TimeoutError, TimeoutError):
                pass
            if stop_event.is_set() or not is_running():
                break
        first_tick = False

        state["ticks"] = int(state.get("ticks", 0) or 0) + 1
        state["last_trigger"] = "startup" if state["ticks"] == 1 else "interval"
        state["last_run_iso"] = utc_now_iso()
        try:
            scan_result = await submit_proactive_wake()
            status = str(scan_result.get("status", "") or "").strip().lower()
            if status.endswith("backpressure"):
                state["backpressure_count"] = int(state.get("backpressure_count", 0) or 0) + 1
                pressure_reason = str(scan_result.get("pressure_class", "") or status.removeprefix("wake_")).strip() or "backpressure"
                backpressure_by_reason = state.get("backpressure_by_reason")
                if not isinstance(backpressure_by_reason, dict):
                    backpressure_by_reason = {}
                    state["backpressure_by_reason"] = backpressure_by_reason
                backpressure_by_reason[pressure_reason] = int(backpressure_by_reason.get(pressure_reason, 0) or 0) + 1
                state["last_backpressure_reason"] = pressure_reason
            elif status in {"ok", "disabled"}:
                state["success_count"] = int(state.get("success_count", 0) or 0) + 1
            else:
                state["error_count"] = int(state.get("error_count", 0) or 0) + 1
            state["delivered_count"] = int(state.get("delivered_count", 0) or 0) + int(scan_result.get("delivered", 0) or 0)
            state["replayed_count"] = int(state.get("replayed_count", 0) or 0) + int(scan_result.get("replayed", 0) or 0)
            state["last_result"] = status or "unknown"
            state["last_error"] = str(scan_result.get("error", "") or "")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            state["error_count"] = int(state.get("error_count", 0) or 0) + 1
            state["last_result"] = "error"
            state["last_error"] = str(exc)
            log_error(exc)


async def run_self_evolution_loop(
    *,
    self_evolution: Any,
    state: dict[str, Any],
    stop_event: asyncio.Event,
    utc_now_iso: Callable[[], str],
    log_error: Callable[[Exception], None],
) -> None:
    cooldown = float(getattr(self_evolution, "cooldown_s", 3600.0))
    while True:
        try:
            state["ticks"] = int(state.get("ticks", 0) or 0) + 1
            result = await self_evolution.run_once()
            state["success_count"] = int(state.get("success_count", 0) or 0) + 1
            state["last_result"] = str((result or {}).get("last_outcome", "") or "")
            state["last_error"] = ""
            state["last_run_iso"] = utc_now_iso()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            state["error_count"] = int(state.get("error_count", 0) or 0) + 1
            state["last_result"] = "error"
            state["last_error"] = str(exc)
            state["last_run_iso"] = utc_now_iso()
            log_error(exc)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=cooldown)
            return
        except asyncio.TimeoutError:
            continue


__all__ = [
    "run_proactive_monitor_loop",
    "run_self_evolution_loop",
]
