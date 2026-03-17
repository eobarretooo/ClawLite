from __future__ import annotations

from typing import Any, Awaitable, Callable

from clawlite.utils.logging import bind_event


async def _handle_channels_started(
    *,
    runtime: Any,
    lifecycle: Any,
    record_autonomy_event: Callable[..., None],
    send_autonomy_notice: Callable[..., Awaitable[None]],
) -> None:
    replay_component = lifecycle.components.setdefault(
        "delivery_replay",
        {"enabled": True, "running": False, "last_error": "", "replayed": 0, "failed": 0, "skipped": 0},
    )
    replay_summary = runtime.channels.startup_replay_status()
    replay_component["enabled"] = bool(replay_summary.get("enabled", True))
    replay_component["running"] = bool(replay_summary.get("running", False))
    replay_component["last_error"] = str(replay_summary.get("last_error", "") or "")
    replay_component["replayed"] = int(replay_summary.get("replayed", 0) or 0)
    replay_component["failed"] = int(replay_summary.get("failed", 0) or 0)
    replay_component["skipped"] = int(replay_summary.get("skipped", 0) or 0)
    record_autonomy_event(
        "channels",
        "startup_delivery_replay",
        "ok" if not replay_component["last_error"] else "failed",
        summary=(
            f"startup delivery replay replayed={replay_component['replayed']} "
            f"failed={replay_component['failed']} skipped={replay_component['skipped']}"
        ),
        metadata=dict(replay_summary),
    )
    if replay_component["replayed"] > 0 or replay_component["failed"] > 0 or bool(replay_component["last_error"]):
        await send_autonomy_notice(
            "channels",
            "startup_delivery_replay",
            "ok" if not replay_component["last_error"] else "failed",
            text=(
                "Autonomy notice: startup delivery replay "
                f"replayed={replay_component['replayed']} failed={replay_component['failed']} "
                f"skipped={replay_component['skipped']}."
            ),
            metadata={
                "source": "delivery_replay",
                **dict(replay_summary),
            },
        )

    inbound_component = lifecycle.components.setdefault(
        "inbound_replay",
        {"enabled": True, "running": False, "last_error": "", "replayed": 0, "remaining": 0},
    )
    inbound_summary = runtime.channels.startup_inbound_replay_status()
    inbound_component["enabled"] = bool(inbound_summary.get("enabled", True))
    inbound_component["running"] = bool(inbound_summary.get("running", False))
    inbound_component["last_error"] = str(inbound_summary.get("last_error", "") or "")
    inbound_component["replayed"] = int(inbound_summary.get("replayed", 0) or 0)
    inbound_component["remaining"] = int(inbound_summary.get("remaining", 0) or 0)
    record_autonomy_event(
        "channels",
        "startup_inbound_replay",
        "ok" if not inbound_component["last_error"] else "failed",
        summary=(
            f"startup inbound replay replayed={inbound_component['replayed']} "
            f"remaining={inbound_component['remaining']}"
        ),
        metadata=dict(inbound_summary),
    )
    if inbound_component["replayed"] > 0 or bool(inbound_component["last_error"]):
        await send_autonomy_notice(
            "channels",
            "startup_inbound_replay",
            "ok" if not inbound_component["last_error"] else "failed",
            text=(
                "Autonomy notice: startup inbound replay "
                f"replayed={inbound_component['replayed']} remaining={inbound_component['remaining']}."
            ),
            metadata={
                "source": "inbound_replay",
                **dict(inbound_summary),
            },
        )


async def _handle_autonomy_wake_started(
    *,
    runtime: Any,
    lifecycle: Any,
    record_autonomy_event: Callable[..., None],
    send_autonomy_notice: Callable[..., Awaitable[None]],
) -> None:
    wake_component = lifecycle.components.setdefault(
        "wake_replay",
        {"enabled": True, "running": False, "last_error": "", "restored": 0, "pending": 0},
    )
    wake_summary = runtime.autonomy_wake.status()
    wake_component["enabled"] = True
    wake_component["running"] = False
    wake_component["last_error"] = str(wake_summary.get("last_journal_error", "") or "")
    wake_component["restored"] = int(wake_summary.get("restored", 0) or 0)
    wake_component["pending"] = int(wake_summary.get("journal_entries", 0) or 0)
    record_autonomy_event(
        "autonomy",
        "startup_wake_replay",
        "ok" if not wake_component["last_error"] else "failed",
        summary=(
            f"startup wake replay restored={wake_component['restored']} "
            f"pending={wake_component['pending']}"
        ),
        metadata=dict(wake_summary),
    )
    if wake_component["restored"] > 0 or bool(wake_component["last_error"]):
        await send_autonomy_notice(
            "autonomy",
            "startup_wake_replay",
            "ok" if not wake_component["last_error"] else "failed",
            text=(
                "Autonomy notice: startup wake replay "
                f"restored={wake_component['restored']} pending={wake_component['pending']}."
            ),
            metadata={
                "source": "wake_replay",
                **dict(wake_summary),
            },
        )


async def _rollback_started_subsystems(*, started: list[tuple[str, Callable[[], Awaitable[Any]]]], lifecycle: Any) -> None:
    for stop_name, stop in reversed(started):
        try:
            await stop()
            lifecycle.mark_component(stop_name, running=False)
            bind_event("gateway.lifecycle").info("subsystem rollback stopped name={}", stop_name)
        except Exception as stop_exc:
            lifecycle.mark_component(stop_name, running=False, error=str(stop_exc))
            bind_event("gateway.lifecycle").error("subsystem rollback failed name={} error={}", stop_name, stop_exc)


async def start_subsystems(
    *,
    cfg: Any,
    runtime: Any,
    lifecycle: Any,
    dispatch_autonomy_wake: Callable[[str, dict[str, Any]], Awaitable[Any]],
    submit_cron_wake: Callable[[Any], Awaitable[str | None]],
    submit_heartbeat_wake: Callable[[], Awaitable[Any]],
    start_subagent_maintenance: Callable[[], Awaitable[None]],
    stop_subagent_maintenance: Callable[[], Awaitable[None]],
    start_job_workers: Callable[[], Awaitable[None]],
    stop_job_workers: Callable[[], Awaitable[None]],
    start_proactive_monitor: Callable[[], Awaitable[None]],
    stop_proactive_monitor: Callable[[], Awaitable[None]],
    start_memory_quality_tuning: Callable[[], Awaitable[None]],
    stop_memory_quality_tuning: Callable[[], Awaitable[None]],
    start_self_evolution: Callable[[], Awaitable[None]],
    stop_self_evolution: Callable[[], Awaitable[None]],
    resume_recoverable_subagents: Callable[[], Awaitable[dict[str, Any]]],
    run_startup_bootstrap_cycle: Callable[[], Awaitable[dict[str, Any]]],
    record_autonomy_event: Callable[..., None],
    send_autonomy_notice: Callable[..., Awaitable[None]],
) -> None:
    started: list[tuple[str, Callable[[], Awaitable[Any]]]] = []
    steps: list[tuple[str, Callable[[], Awaitable[Any]], Callable[[], Awaitable[Any]], bool]] = [
        ("skills_watcher", lambda: runtime.skills_loader.start_watcher(), lambda: runtime.skills_loader.stop_watcher(), True),
        ("channels", lambda: runtime.channels.start(cfg.to_dict()), lambda: runtime.channels.stop(), True),
        ("autonomy_wake", lambda: runtime.autonomy_wake.start(dispatch_autonomy_wake), lambda: runtime.autonomy_wake.stop(), True),
        ("cron", lambda: runtime.cron.start(submit_cron_wake), lambda: runtime.cron.stop(), True),
        ("subagent_maintenance", start_subagent_maintenance, stop_subagent_maintenance, True),
        ("job_workers", start_job_workers, stop_job_workers, bool(runtime.job_queue is not None)),
        ("heartbeat", lambda: runtime.heartbeat.start(submit_heartbeat_wake), lambda: runtime.heartbeat.stop(), bool(cfg.gateway.heartbeat.enabled)),
        ("autonomy", lambda: runtime.autonomy.start(), lambda: runtime.autonomy.stop(), bool(runtime.autonomy is not None and cfg.gateway.autonomy.enabled)),
        ("proactive_monitor", start_proactive_monitor, stop_proactive_monitor, bool(runtime.memory_monitor is not None)),
        ("memory_quality_tuning", start_memory_quality_tuning, stop_memory_quality_tuning, bool(cfg.gateway.autonomy.tuning_loop_enabled)),
        ("self_evolution", start_self_evolution, stop_self_evolution, bool(cfg.gateway.autonomy.self_evolution_enabled and runtime.self_evolution is not None)),
        ("supervisor", lambda: runtime.supervisor.start(), lambda: runtime.supervisor.stop(), bool(cfg.gateway.supervisor.enabled)),
    ]

    for name, start_fn, stop_fn, enabled in steps:
        lifecycle.components.setdefault(name, {"enabled": enabled, "running": False, "last_error": ""})
        lifecycle.components[name]["enabled"] = enabled
        if not enabled:
            lifecycle.mark_component(name, running=False, error="disabled")
            continue
        try:
            await start_fn()
            if name == "channels":
                await _handle_channels_started(
                    runtime=runtime,
                    lifecycle=lifecycle,
                    record_autonomy_event=record_autonomy_event,
                    send_autonomy_notice=send_autonomy_notice,
                )
            elif name == "autonomy_wake":
                await _handle_autonomy_wake_started(
                    runtime=runtime,
                    lifecycle=lifecycle,
                    record_autonomy_event=record_autonomy_event,
                    send_autonomy_notice=send_autonomy_notice,
                )
            lifecycle.mark_component(name, running=True)
            started.append((name, stop_fn))
            bind_event("gateway.lifecycle").info("subsystem started name={}", name)
        except Exception as exc:
            lifecycle.mark_component(name, running=False, error=str(exc))
            lifecycle.startup_error = str(exc)
            bind_event("gateway.lifecycle").error("subsystem failed to start name={} error={}", name, exc)
            await _rollback_started_subsystems(started=started, lifecycle=lifecycle)
            raise RuntimeError(f"gateway_startup_failed:{name}") from exc

    try:
        replay_result = await resume_recoverable_subagents()
        bind_event("gateway.lifecycle").info(
            "subagent replay startup replayed={} failed={}",
            int(replay_result.get("replayed", 0) or 0),
            int(replay_result.get("failed", 0) or 0),
        )
    except Exception as exc:
        row = lifecycle.components.setdefault(
            "subagent_replay",
            {"enabled": True, "running": False, "last_error": "", "replayed": 0, "failed": 0},
        )
        row["running"] = False
        row["last_error"] = str(exc)
        record_autonomy_event(
            "subagents",
            "startup_replay",
            "failed",
            summary="startup replay failed",
            metadata={"error": str(exc)},
        )
        bind_event("gateway.lifecycle").warning("subagent replay startup failed error={}", exc)

    try:
        bootstrap_result = await run_startup_bootstrap_cycle()
        if bool(bootstrap_result.get("attempted", False)):
            bind_event("gateway.lifecycle").info(
                "bootstrap startup cycle status={} reason={}",
                str(bootstrap_result.get("status", "") or "unknown"),
                str(bootstrap_result.get("reason", "") or ""),
            )
    except Exception as exc:
        lifecycle.components.setdefault(
            "bootstrap",
            {"enabled": True, "running": False, "pending": False, "last_status": "", "last_error": ""},
        )["last_error"] = str(exc)
        bind_event("gateway.lifecycle").warning("bootstrap startup cycle failed error={}", exc)


async def stop_subsystems(
    *,
    cfg: Any,
    runtime: Any,
    lifecycle: Any,
    stop_subagent_maintenance: Callable[[], Awaitable[None]],
    stop_proactive_monitor: Callable[[], Awaitable[None]],
    stop_memory_quality_tuning: Callable[[], Awaitable[None]],
    stop_self_evolution: Callable[[], Awaitable[None]],
) -> None:
    steps: list[tuple[str, Callable[[], Awaitable[Any]], bool]] = [
        ("supervisor", lambda: runtime.supervisor.stop(), bool(cfg.gateway.supervisor.enabled)),
        ("autonomy", lambda: runtime.autonomy.stop(), bool(runtime.autonomy is not None and cfg.gateway.autonomy.enabled)),
        ("heartbeat", lambda: runtime.heartbeat.stop(), bool(cfg.gateway.heartbeat.enabled)),
        ("subagent_maintenance", stop_subagent_maintenance, True),
        ("proactive_monitor", stop_proactive_monitor, bool(runtime.memory_monitor is not None)),
        ("memory_quality_tuning", stop_memory_quality_tuning, bool(cfg.gateway.autonomy.tuning_loop_enabled)),
        ("self_evolution", stop_self_evolution, bool(cfg.gateway.autonomy.self_evolution_enabled and runtime.self_evolution is not None)),
        ("cron", lambda: runtime.cron.stop(), True),
        ("autonomy_wake", lambda: runtime.autonomy_wake.stop(), True),
        ("channels", lambda: runtime.channels.stop(), True),
        ("skills_watcher", lambda: runtime.skills_loader.stop_watcher(), True),
    ]
    for name, stop_fn, enabled in steps:
        if not enabled:
            lifecycle.mark_component(name, running=False, error="disabled")
            continue
        try:
            await stop_fn()
            lifecycle.mark_component(name, running=False)
            bind_event("gateway.lifecycle").info("subsystem stopped name={}", name)
        except Exception as exc:
            lifecycle.mark_component(name, running=False, error=str(exc))
            bind_event("gateway.lifecycle").error("subsystem stop failed name={} error={}", name, exc)


__all__ = [
    "start_subsystems",
    "stop_subsystems",
]
