from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from clawlite.utils.logging import bind_event, setup_logging


@dataclass(slots=True)
class SupervisorIncident:
    component: str
    reason: str
    recoverable: bool = True


IncidentCheck = Callable[[], Awaitable[list[SupervisorIncident | dict[str, Any]]]]
RecoveryHandler = Callable[[str, str], Awaitable[bool]]
NowMonotonic = Callable[[], float]
NowUTC = Callable[[], datetime]


class RuntimeSupervisor:
    def __init__(
        self,
        *,
        interval_s: float = 20.0,
        cooldown_s: float = 30.0,
        incident_checks: IncidentCheck | None = None,
        recover: RecoveryHandler | None = None,
        now_monotonic: NowMonotonic | None = None,
        now_utc: NowUTC | None = None,
    ) -> None:
        setup_logging()
        self.interval_s = max(1.0, float(interval_s))
        self.cooldown_s = max(0.0, float(cooldown_s))
        self._incident_checks = incident_checks
        self._recover = recover
        self._now_monotonic = now_monotonic or time.monotonic
        self._now_utc = now_utc or (lambda: datetime.now(timezone.utc))
        self._task: asyncio.Task[Any] | None = None
        self._running = False

        self._ticks = 0
        self._incident_count = 0
        self._recovery_attempts = 0
        self._recovery_success = 0
        self._recovery_failures = 0
        self._recovery_skipped_cooldown = 0
        self._component_incidents: dict[str, int] = {}
        self._last_incident: dict[str, str] = {"component": "", "reason": "", "at": ""}
        self._last_recovery_at = ""
        self._last_error = ""
        self._consecutive_error_count = 0
        self._cooldown_until: dict[str, float] = {}

    def _task_snapshot(self) -> tuple[str, str]:
        task = self._task
        if task is None:
            return ("stopped", "")
        if task.cancelled():
            return ("cancelled", "")
        if not task.done():
            return ("running", "")
        try:
            exc = task.exception()
        except asyncio.CancelledError:
            return ("cancelled", "")
        if exc is not None:
            return ("failed", str(exc))
        return ("done", "")

    @staticmethod
    def _incident_from_any(row: SupervisorIncident | dict[str, Any]) -> SupervisorIncident | None:
        if isinstance(row, SupervisorIncident):
            return row
        if not isinstance(row, dict):
            return None
        component = str(row.get("component", "") or "").strip()
        reason = str(row.get("reason", "") or "").strip()
        if not component or not reason:
            return None
        return SupervisorIncident(component=component, reason=reason, recoverable=bool(row.get("recoverable", True)))

    def _record_error(self, exc: Exception) -> None:
        self._last_error = str(exc)
        self._consecutive_error_count += 1
        bind_event("supervisor.tick").error("supervisor tick error={}", exc)

    def _record_incident(self, incident: SupervisorIncident) -> None:
        self._incident_count += 1
        self._component_incidents[incident.component] = int(self._component_incidents.get(incident.component, 0) or 0) + 1
        self._last_incident = {
            "component": incident.component,
            "reason": incident.reason,
            "at": self._now_utc().isoformat(),
        }

    async def _recover_component(self, *, component: str, reason: str) -> bool:
        if self._recover is None:
            return False
        self._recovery_attempts += 1
        self._last_recovery_at = self._now_utc().isoformat()
        try:
            ok = bool(await self._recover(component, reason))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._record_error(exc)
            ok = False
        if ok:
            self._recovery_success += 1
            return True
        self._recovery_failures += 1
        return False

    async def run_once(self) -> dict[str, Any]:
        self._ticks += 1
        now = self._now_monotonic()
        try:
            rows = [] if self._incident_checks is None else await self._incident_checks()
            incidents: list[SupervisorIncident] = []
            for row in rows:
                item = self._incident_from_any(row)
                if item is not None:
                    incidents.append(item)

            for incident in incidents:
                self._record_incident(incident)
                if not incident.recoverable:
                    continue
                cooldown_until = float(self._cooldown_until.get(incident.component, 0.0) or 0.0)
                if now < cooldown_until:
                    self._recovery_skipped_cooldown += 1
                    continue
                await self._recover_component(component=incident.component, reason=incident.reason)
                self._cooldown_until[incident.component] = now + self.cooldown_s

            self._last_error = ""
            self._consecutive_error_count = 0
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._record_error(exc)
        return self.status()

    async def _run_loop(self) -> None:
        while self._running:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._record_error(exc)
            if not self._running:
                break
            await asyncio.sleep(self.interval_s)

    async def start(self) -> None:
        if self._task is not None:
            if self._task.done() or self._task.cancelled():
                self._task = None
            else:
                return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        bind_event("supervisor.lifecycle").info("supervisor started interval_s={} cooldown_s={}", self.interval_s, self.cooldown_s)

    async def stop(self) -> None:
        self._running = False
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            self._record_error(exc)
        self._task = None
        bind_event("supervisor.lifecycle").info("supervisor stopped")

    def status(self) -> dict[str, Any]:
        now = self._now_monotonic()
        task_state, task_error = self._task_snapshot()
        cooldown_active: dict[str, float] = {}
        for component, until in self._cooldown_until.items():
            remaining = max(0.0, float(until) - now)
            if remaining > 0:
                cooldown_active[component] = round(remaining, 3)
        return {
            "running": bool(self._running and task_state == "running"),
            "worker_state": task_state,
            "interval_s": self.interval_s,
            "cooldown_s": self.cooldown_s,
            "ticks": self._ticks,
            "incident_count": self._incident_count,
            "recovery_attempts": self._recovery_attempts,
            "recovery_success": self._recovery_success,
            "recovery_failures": self._recovery_failures,
            "recovery_skipped_cooldown": self._recovery_skipped_cooldown,
            "component_incidents": dict(self._component_incidents),
            "last_incident": dict(self._last_incident),
            "last_recovery_at": self._last_recovery_at,
            "last_error": task_error or self._last_error,
            "consecutive_error_count": self._consecutive_error_count,
            "cooldown_active": cooldown_active,
        }
