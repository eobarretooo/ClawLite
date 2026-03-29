from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any


_PENDING_GATEWAY_RESTART_TASK: asyncio.Task[Any] | None = None
_PENDING_GATEWAY_RESTART_REASON: str = ""


def resolve_gateway_restart_execv(
    *,
    argv: list[str] | None = None,
    executable: str | None = None,
) -> tuple[str, list[str]]:
    resolved_argv = list(argv if argv is not None else sys.argv)
    resolved_executable = str(executable or sys.executable).strip() or sys.executable

    script_candidate = str(resolved_argv[0] if resolved_argv else "").strip()
    if script_candidate:
        script_path = Path(script_candidate).expanduser()
        if script_path.exists():
            return resolved_executable, [resolved_executable, str(script_path), *resolved_argv[1:]]

    return resolved_executable, [resolved_executable, "-m", "clawlite.cli", *resolved_argv[1:]]


async def _restart_after_delay(*, delay_s: float, execv_fn) -> None:
    bounded_delay = max(0.0, float(delay_s))
    if bounded_delay > 0:
        await asyncio.sleep(bounded_delay)
    exec_path, exec_argv = resolve_gateway_restart_execv()
    execv_fn(exec_path, exec_argv)


def schedule_gateway_restart(
    *,
    delay_s: float = 1.5,
    reason: str = "",
    execv_fn=os.execv,
) -> dict[str, Any]:
    global _PENDING_GATEWAY_RESTART_TASK, _PENDING_GATEWAY_RESTART_REASON

    existing = _PENDING_GATEWAY_RESTART_TASK
    if existing is not None and not existing.done():
        return {
            "ok": True,
            "scheduled": True,
            "coalesced": True,
            "delay_s": max(0.0, float(delay_s)),
            "reason": _PENDING_GATEWAY_RESTART_REASON,
        }

    loop = asyncio.get_running_loop()
    normalized_reason = str(reason or "").strip()
    task = loop.create_task(_restart_after_delay(delay_s=max(0.0, float(delay_s)), execv_fn=execv_fn))
    _PENDING_GATEWAY_RESTART_TASK = task
    _PENDING_GATEWAY_RESTART_REASON = normalized_reason

    def _clear(_: asyncio.Task[Any]) -> None:
        global _PENDING_GATEWAY_RESTART_TASK, _PENDING_GATEWAY_RESTART_REASON
        if _PENDING_GATEWAY_RESTART_TASK is task:
            _PENDING_GATEWAY_RESTART_TASK = None
            _PENDING_GATEWAY_RESTART_REASON = ""

    task.add_done_callback(_clear)
    return {
        "ok": True,
        "scheduled": True,
        "coalesced": False,
        "delay_s": max(0.0, float(delay_s)),
        "reason": normalized_reason,
    }


def gateway_restart_pending() -> bool:
    task = _PENDING_GATEWAY_RESTART_TASK
    return task is not None and not task.done()


def pending_gateway_restart_reason() -> str:
    return str(_PENDING_GATEWAY_RESTART_REASON or "").strip()


__all__ = [
    "gateway_restart_pending",
    "pending_gateway_restart_reason",
    "resolve_gateway_restart_execv",
    "schedule_gateway_restart",
]
