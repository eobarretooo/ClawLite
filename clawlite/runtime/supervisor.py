from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from clawlite.utils.logging import bind_event, setup_logging


@dataclass(slots=True)
class SupervisorIncident:
    component: str
    reason: str
    recoverable: bool = True


@dataclass(frozen=True, slots=True)
class SupervisorComponentPolicy:
    cooldown_s: float | None = None
    max_recoveries: int = 0
    budget_window_s: float = 3600.0


IncidentCheck = Callable[[], Awaitable[list[SupervisorIncident | dict[str, Any]]]]
RecoveryHandler = Callable[[str, str], Awaitable[bool]]
IncidentHandler = Callable[[SupervisorIncident], Awaitable[None]]
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
        on_incident: IncidentHandler | None = None,
        component_policies: dict[str, SupervisorComponentPolicy | dict[str, Any]] | None = None,
        now_monotonic: NowMonotonic | None = None,
        now_utc: NowUTC | None = None,
    ) -> None:
        setup_logging()
        self.interval_s = max(1.0, float(interval_s))
        self.cooldown_s = max(0.0, float(cooldown_s))
        self._incident_checks = incident_checks
        self._recover = recover
        self._on_incident = on_incident
        self._now_monotonic = now_monotonic or time.monotonic
        self._now_utc = now_utc or (lambda: datetime.now(timezone.utc))
        self._component_policies = self._normalize_component_policies(component_policies)
        self._task: asyncio.Task[Any] | None = None
        self._running = False

        self._ticks = 0
        self._incident_count = 0
        self._recovery_attempts = 0
        self._recovery_success = 0
        self._recovery_failures = 0
        self._recovery_skipped_cooldown = 0
        self._recovery_skipped_budget = 0
        self._component_incidents: dict[str, int] = {}
        self._component_recovery: dict[str, dict[str, Any]] = {}
        self._component_recovery_windows: dict[str, deque[float]] = {}
        self._last_incident: dict[str, str] = {"component": "", "reason": "", "at": ""}
        self._last_recovery_at = ""
        self._last_error = ""
        self._consecutive_error_count = 0
        self._cooldown_until: dict[str, float] = {}

    @staticmethod
    def _normalize_component_name(value: str) -> str:
        return str(value or "").strip().lower()

    @classmethod
    def _coerce_component_policy(cls, raw: SupervisorComponentPolicy | dict[str, Any] | None) -> SupervisorComponentPolicy:
        if isinstance(raw, SupervisorComponentPolicy):
            cooldown = raw.cooldown_s
            if cooldown is not None:
                cooldown = max(0.0, float(cooldown))
            return SupervisorComponentPolicy(
                cooldown_s=cooldown,
                max_recoveries=max(0, int(raw.max_recoveries or 0)),
                budget_window_s=max(1.0, float(raw.budget_window_s or 3600.0)),
            )
        if not isinstance(raw, dict):
            return SupervisorComponentPolicy()
        cooldown_raw = raw.get("cooldown_s", raw.get("cooldownS"))
        cooldown: float | None
        if cooldown_raw is None or cooldown_raw == "":
            cooldown = None
        else:
            cooldown = max(0.0, float(cooldown_raw))
        max_recoveries_raw = raw.get("max_recoveries", raw.get("maxRecoveries", 0))
        budget_window_raw = raw.get("budget_window_s", raw.get("budgetWindowS", 3600.0))
        return SupervisorComponentPolicy(
            cooldown_s=cooldown,
            max_recoveries=max(0, int(max_recoveries_raw or 0)),
            budget_window_s=max(1.0, float(budget_window_raw or 3600.0)),
        )

    @classmethod
    def _normalize_component_policies(
        cls,
        raw: dict[str, SupervisorComponentPolicy | dict[str, Any]] | None,
    ) -> dict[str, SupervisorComponentPolicy]:
        policies: dict[str, SupervisorComponentPolicy] = {}
        for component, policy in dict(raw or {}).items():
            name = cls._normalize_component_name(component)
            if not name:
                continue
            policies[name] = cls._coerce_component_policy(policy)
        return policies

    def _policy_for_component(self, component: str) -> SupervisorComponentPolicy:
        name = self._normalize_component_name(component)
        return self._component_policies.get(name, SupervisorComponentPolicy())

    def _resolved_cooldown_s(self, component: str) -> float:
        policy = self._policy_for_component(component)
        if policy.cooldown_s is None:
            return self.cooldown_s
        return max(0.0, float(policy.cooldown_s))

    def _ensure_component_recovery(self, component: str) -> dict[str, Any]:
        name = self._normalize_component_name(component)
        row = self._component_recovery.get(name)
        if row is None:
            row = {
                "attempts": 0,
                "success": 0,
                "failures": 0,
                "skipped_cooldown": 0,
                "skipped_budget": 0,
                "last_recovery_at": "",
                "last_error": "",
                "last_reason": "",
            }
            self._component_recovery[name] = row
        return row

    def _recovery_window(self, component: str, *, now: float | None = None) -> deque[float]:
        name = self._normalize_component_name(component)
        policy = self._policy_for_component(name)
        if policy.max_recoveries <= 0:
            self._component_recovery_windows.pop(name, None)
            return deque()
        window = self._component_recovery_windows.setdefault(name, deque())
        current = self._now_monotonic() if now is None else float(now)
        cutoff = current - float(policy.budget_window_s)
        while window and float(window[0]) <= cutoff:
            window.popleft()
        return window

    def _budget_remaining(self, component: str, *, now: float | None = None) -> int | None:
        policy = self._policy_for_component(component)
        if policy.max_recoveries <= 0:
            return None
        window = self._recovery_window(component, now=now)
        return max(0, int(policy.max_recoveries) - len(window))

    def _consume_recovery_budget(self, component: str, *, now: float) -> None:
        policy = self._policy_for_component(component)
        if policy.max_recoveries <= 0:
            return
        window = self._recovery_window(component, now=now)
        window.append(float(now))

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
        component = self._normalize_component_name(incident.component)
        self._component_incidents[component] = int(self._component_incidents.get(component, 0) or 0) + 1
        self._ensure_component_recovery(component)
        self._last_incident = {
            "component": component,
            "reason": incident.reason,
            "at": self._now_utc().isoformat(),
        }

    async def _notify_incident(self, incident: SupervisorIncident) -> None:
        if self._on_incident is None:
            return
        try:
            await self._on_incident(incident)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._record_error(exc)

    async def _recover_component(self, *, component: str, reason: str) -> bool:
        if self._recover is None:
            return False
        normalized_component = self._normalize_component_name(component)
        row = self._ensure_component_recovery(normalized_component)
        self._recovery_attempts += 1
        row["attempts"] = int(row.get("attempts", 0) or 0) + 1
        row["last_reason"] = str(reason or "")
        self._last_recovery_at = self._now_utc().isoformat()
        row["last_recovery_at"] = self._last_recovery_at
        try:
            ok = bool(await self._recover(normalized_component, reason))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._record_error(exc)
            row["last_error"] = str(exc)
            ok = False
        if ok:
            self._recovery_success += 1
            row["success"] = int(row.get("success", 0) or 0) + 1
            row["last_error"] = ""
            return True
        self._recovery_failures += 1
        row["failures"] = int(row.get("failures", 0) or 0) + 1
        if not row["last_error"]:
            row["last_error"] = "recovery_returned_false"
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
                await self._notify_incident(incident)
                if not incident.recoverable:
                    continue
                component = self._normalize_component_name(incident.component)
                row = self._ensure_component_recovery(component)
                cooldown_until = float(self._cooldown_until.get(component, 0.0) or 0.0)
                if now < cooldown_until:
                    self._recovery_skipped_cooldown += 1
                    row["skipped_cooldown"] = int(row.get("skipped_cooldown", 0) or 0) + 1
                    continue
                budget_remaining = self._budget_remaining(component, now=now)
                if budget_remaining is not None and budget_remaining <= 0:
                    self._recovery_skipped_budget += 1
                    row["skipped_budget"] = int(row.get("skipped_budget", 0) or 0) + 1
                    continue
                self._consume_recovery_budget(component, now=now)
                await self._recover_component(component=component, reason=incident.reason)
                self._cooldown_until[component] = now + self._resolved_cooldown_s(component)

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
        component_recovery: dict[str, dict[str, Any]] = {}
        known_components = set(self._component_incidents) | set(self._component_recovery) | set(self._component_policies) | set(self._cooldown_until)
        for component in sorted(known_components):
            row = dict(self._ensure_component_recovery(component))
            policy = self._policy_for_component(component)
            budget_remaining = self._budget_remaining(component, now=now)
            component_recovery[component] = {
                "incidents": int(self._component_incidents.get(component, 0) or 0),
                "recovery_attempts": int(row.get("attempts", 0) or 0),
                "recovery_success": int(row.get("success", 0) or 0),
                "recovery_failures": int(row.get("failures", 0) or 0),
                "recovery_skipped_cooldown": int(row.get("skipped_cooldown", 0) or 0),
                "recovery_skipped_budget": int(row.get("skipped_budget", 0) or 0),
                "last_recovery_at": str(row.get("last_recovery_at", "") or ""),
                "last_error": str(row.get("last_error", "") or ""),
                "last_reason": str(row.get("last_reason", "") or ""),
                "cooldown_s": self._resolved_cooldown_s(component),
                "cooldown_remaining_s": round(float(cooldown_active.get(component, 0.0) or 0.0), 3),
                "max_recoveries": int(policy.max_recoveries),
                "budget_window_s": float(policy.budget_window_s),
                "recoveries_in_window": len(self._recovery_window(component, now=now)),
                "budget_remaining": budget_remaining,
            }
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
            "recovery_skipped_budget": self._recovery_skipped_budget,
            "component_incidents": dict(self._component_incidents),
            "component_recovery": component_recovery,
            "last_incident": dict(self._last_incident),
            "last_recovery_at": self._last_recovery_at,
            "last_error": task_error or self._last_error,
            "consecutive_error_count": self._consecutive_error_count,
            "cooldown_active": cooldown_active,
        }
