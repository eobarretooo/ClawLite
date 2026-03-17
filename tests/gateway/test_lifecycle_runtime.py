from __future__ import annotations

import asyncio
from types import SimpleNamespace

from clawlite.config.schema import AppConfig
from clawlite.gateway.lifecycle_runtime import start_subsystems


class _Lifecycle:
    def __init__(self) -> None:
        self.components: dict[str, dict[str, object]] = {}
        self.startup_error = ""

    def mark_component(self, name: str, *, running: bool, error: str = "") -> None:
        row = self.components.setdefault(name, {"enabled": True, "running": False, "last_error": ""})
        row["running"] = running
        row["last_error"] = error


def test_start_subsystems_continues_after_component_startup_timeout() -> None:
    async def _scenario() -> None:
        cfg = AppConfig(
            gateway={
                "heartbeat": {"enabled": False},
                "supervisor": {"enabled": False},
                "autonomy": {
                    "enabled": False,
                    "tuning_loop_enabled": False,
                    "self_evolution_enabled": False,
                },
                "startup_timeout_default_s": 0.01,
                "startup_timeout_channels_s": 0.01,
            }
        )
        lifecycle = _Lifecycle()
        cleanup_calls: list[str] = []
        started_steps: list[str] = []

        class _Skills:
            async def start_watcher(self) -> None:
                started_steps.append("skills_watcher")

            async def stop_watcher(self) -> None:
                cleanup_calls.append("skills_watcher")

        class _Channels:
            async def start(self, _cfg: dict[str, object]) -> None:
                await asyncio.sleep(0.3)

            async def stop(self) -> None:
                cleanup_calls.append("channels")

        class _AutonomyWake:
            async def start(self, _dispatch) -> None:
                started_steps.append("autonomy_wake")

            async def stop(self) -> None:
                cleanup_calls.append("autonomy_wake")

            def status(self) -> dict[str, object]:
                return {"restored": 0, "journal_entries": 0, "last_journal_error": ""}

        class _Cron:
            async def start(self, _submit) -> None:
                started_steps.append("cron")

            async def stop(self) -> None:
                cleanup_calls.append("cron")

        runtime = SimpleNamespace(
            skills_loader=_Skills(),
            channels=_Channels(),
            autonomy_wake=_AutonomyWake(),
            cron=_Cron(),
            job_queue=None,
            heartbeat=SimpleNamespace(start=lambda _submit: None, stop=lambda: None),
            autonomy=None,
            memory_monitor=None,
            self_evolution=None,
            supervisor=SimpleNamespace(start=lambda: None, stop=lambda: None),
        )

        async def _noop(*args, **kwargs):
            del args, kwargs
            return None

        await start_subsystems(
            cfg=cfg,
            runtime=runtime,
            lifecycle=lifecycle,
            dispatch_autonomy_wake=lambda *args, **kwargs: _noop(*args, **kwargs),
            submit_cron_wake=lambda *args, **kwargs: _noop(*args, **kwargs),
            submit_heartbeat_wake=lambda: _noop(),
            start_subagent_maintenance=lambda: _noop(),
            stop_subagent_maintenance=lambda: _noop(),
            start_job_workers=lambda: _noop(),
            stop_job_workers=lambda: _noop(),
            start_proactive_monitor=lambda: _noop(),
            stop_proactive_monitor=lambda: _noop(),
            start_memory_quality_tuning=lambda: _noop(),
            stop_memory_quality_tuning=lambda: _noop(),
            start_self_evolution=lambda: _noop(),
            stop_self_evolution=lambda: _noop(),
            resume_recoverable_subagents=lambda: _noop(),
            run_startup_bootstrap_cycle=lambda: _noop(),
            record_autonomy_event=lambda *args, **kwargs: None,
            send_autonomy_notice=_noop,
        )

        assert lifecycle.components["channels"]["running"] is False
        assert lifecycle.components["channels"]["last_error"] == "startup_timeout"
        assert "channels" in cleanup_calls
        assert "cron" in started_steps
        assert lifecycle.startup_error == ""

    asyncio.run(_scenario())
