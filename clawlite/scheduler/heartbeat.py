from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Literal

from clawlite.utils.logging import bind_event, setup_logging

HEARTBEAT_TOKEN = "HEARTBEAT_OK"
DEFAULT_HEARTBEAT_ACK_MAX_CHARS = 300


@dataclass(slots=True)
class HeartbeatDecision:
    action: Literal["run", "skip"]
    reason: str
    text: str = ""

    @classmethod
    def from_result(
        cls,
        result: HeartbeatDecision | dict[str, Any] | str | None,
        *,
        ack_max_chars: int = DEFAULT_HEARTBEAT_ACK_MAX_CHARS,
    ) -> HeartbeatDecision:
        if isinstance(result, HeartbeatDecision):
            return result
        if isinstance(result, dict):
            action = str(result.get("action", "skip") or "skip").strip().lower()
            reason = str(result.get("reason", "") or "").strip()
            text = str(result.get("text", "") or "").strip()
            if action not in {"run", "skip"}:
                action = "skip"
                reason = reason or "invalid_action"
            if not reason:
                reason = "contract_decision"
            return cls(action=action, reason=reason, text=text)

        raw_text = "" if result is None else str(result)
        text = raw_text.strip()
        if not text:
            return cls(action="skip", reason="empty_response")
        if cls._is_heartbeat_ok_ack(text, ack_max_chars=ack_max_chars):
            return cls(action="skip", reason="heartbeat_ok")
        if text.lower().startswith("skip"):
            return cls(action="skip", reason="legacy_skip_prefix")
        return cls(action="run", reason="actionable_response", text=text)

    @staticmethod
    def _is_heartbeat_ok_ack(text: str, *, ack_max_chars: int) -> bool:
        stripped = text.strip()
        upper = stripped.upper()
        token = HEARTBEAT_TOKEN
        if upper == token:
            return True
        if upper.startswith(token):
            suffix = stripped[len(token) :].strip(" \t\r\n-:;,.!")
            return len(suffix) <= ack_max_chars
        if upper.endswith(token):
            prefix = stripped[: len(stripped) - len(token)].strip(" \t\r\n-:;,.!")
            return len(prefix) <= ack_max_chars
        return False


TickHandler = Callable[[], Awaitable[HeartbeatDecision | dict[str, Any] | str | None]]

setup_logging()


class HeartbeatService:
    def __init__(
        self,
        interval_seconds: int = 1800,
        *,
        state_path: str | Path | None = None,
        ack_max_chars: int = DEFAULT_HEARTBEAT_ACK_MAX_CHARS,
    ) -> None:
        self.interval_seconds = max(5, int(interval_seconds))
        self.ack_max_chars = max(0, int(ack_max_chars))
        self.state_path = Path(state_path) if state_path is not None else (Path.home() / ".clawlite" / "state" / "heartbeat-state.json")
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self._task: asyncio.Task[Any] | None = None
        self._running = False
        self._pending_now = 0
        self._trigger_event = asyncio.Event()
        self._trigger_waiters: list[asyncio.Future[HeartbeatDecision]] = []
        self._tick_lock = asyncio.Lock()
        self._state: dict[str, Any] = {
            "version": 1,
            "last_tick_iso": "",
            "last_trigger": "",
            "last_decision": {"action": "skip", "reason": "not_started", "text": ""},
            "last_run_iso": "",
            "last_skip_iso": "",
            "last_error": "",
            "ticks": 0,
            "run_count": 0,
            "skip_count": 0,
            "error_count": 0,
            "consecutive_error_count": 0,
            "trigger_counts": {"startup": 0, "interval": 0, "now": 0},
            "reason_counts": {},
            "state_save_attempts": 0,
            "state_save_retries": 0,
            "state_save_failures": 0,
            "state_save_success": 0,
            "state_last_error": "",
        }
        self._load_state()

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _load_state(self) -> None:
        if not self.state_path.exists():
            return
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(payload, dict):
            return
        self._state.update(payload)

    def _save_state(self) -> None:
        payload = json.dumps(self._state, ensure_ascii=False, indent=2)
        tmp_path = self.state_path.with_name(f"{self.state_path.name}.tmp")
        for attempt in range(2):
            self._state["state_save_attempts"] = int(self._state.get("state_save_attempts", 0) or 0) + 1
            if attempt > 0:
                self._state["state_save_retries"] = int(self._state.get("state_save_retries", 0) or 0) + 1
            try:
                tmp_path.write_text(payload, encoding="utf-8")
                tmp_path.replace(self.state_path)
            except OSError as exc:
                self._state["state_save_failures"] = int(self._state.get("state_save_failures", 0) or 0) + 1
                self._state["state_last_error"] = str(exc)
                bind_event("heartbeat.state").error("heartbeat state save failed attempt={} error={}", attempt + 1, exc)
                try:
                    if tmp_path.exists():
                        tmp_path.unlink()
                except OSError:
                    pass
                if attempt == 0:
                    continue
                return
            self._state["state_save_success"] = int(self._state.get("state_save_success", 0) or 0) + 1
            self._state["state_last_error"] = ""
            return

    @property
    def last_decision(self) -> HeartbeatDecision:
        row = self._state.get("last_decision")
        if isinstance(row, dict):
            return HeartbeatDecision.from_result(row)
        return HeartbeatDecision(action="skip", reason="state_unavailable")

    async def _execute_tick(self, on_tick: TickHandler, *, trigger: str) -> HeartbeatDecision:
        now_iso = self._utc_now_iso()
        self._state["last_tick_iso"] = now_iso
        self._state["last_trigger"] = trigger
        self._state["ticks"] = int(self._state.get("ticks", 0) or 0) + 1
        trigger_counts = self._state.get("trigger_counts")
        if not isinstance(trigger_counts, dict):
            trigger_counts = {}
            self._state["trigger_counts"] = trigger_counts
        trigger_counts[trigger] = int(trigger_counts.get(trigger, 0) or 0) + 1
        decision = HeartbeatDecision(action="skip", reason="unknown")
        async with self._tick_lock:
            try:
                bind_event("heartbeat.tick").debug("heartbeat tick trigger={}", trigger)
                result = await on_tick()
                decision = HeartbeatDecision.from_result(result, ack_max_chars=self.ack_max_chars)
                self._state["consecutive_error_count"] = 0
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._state["error_count"] = int(self._state.get("error_count", 0) or 0) + 1
                self._state["consecutive_error_count"] = int(self._state.get("consecutive_error_count", 0) or 0) + 1
                self._state["last_error"] = str(exc)
                decision = HeartbeatDecision(action="skip", reason="tick_error")
                bind_event("heartbeat.tick").error("heartbeat error={}", exc)

        self._state["last_decision"] = {
            "action": decision.action,
            "reason": decision.reason,
            "text": decision.text,
        }
        reason_counts = self._state.get("reason_counts")
        if not isinstance(reason_counts, dict):
            reason_counts = {}
            self._state["reason_counts"] = reason_counts
        reason_counts[decision.reason] = int(reason_counts.get(decision.reason, 0) or 0) + 1
        if decision.action == "run":
            self._state["run_count"] = int(self._state.get("run_count", 0) or 0) + 1
            self._state["last_run_iso"] = now_iso
            bind_event("heartbeat.tick").info("heartbeat run reason={}", decision.reason)
        else:
            self._state["skip_count"] = int(self._state.get("skip_count", 0) or 0) + 1
            self._state["last_skip_iso"] = now_iso
            bind_event("heartbeat.tick").debug("heartbeat skip reason={}", decision.reason)
        self._save_state()
        return decision

    async def _next_trigger_source(self) -> str:
        if self._pending_now > 0:
            self._pending_now -= 1
            return "now"
        self._trigger_event.clear()
        try:
            await asyncio.wait_for(self._trigger_event.wait(), timeout=self.interval_seconds)
        except (asyncio.TimeoutError, TimeoutError):
            return "interval"
        if self._pending_now > 0:
            self._pending_now -= 1
            return "now"
        return "interval"

    async def start(self, on_tick: TickHandler) -> None:
        if self._task is not None:
            return
        self._running = True
        bind_event("heartbeat.lifecycle").info("heartbeat started interval_seconds={}", self.interval_seconds)

        async def _loop() -> None:
            first_tick = True
            while self._running:
                trigger = "startup" if first_tick else await self._next_trigger_source()
                first_tick = False
                if not self._running:
                    break
                decision = await self._execute_tick(on_tick, trigger=trigger)
                if trigger == "now" and self._trigger_waiters:
                    waiter = self._trigger_waiters.pop(0)
                    if not waiter.done():
                        waiter.set_result(decision)

        self._task = asyncio.create_task(_loop())

    async def trigger_now(self, on_tick: TickHandler) -> HeartbeatDecision:
        if self._task is None:
            return await self._execute_tick(on_tick, trigger="now")
        loop = asyncio.get_running_loop()
        waiter: asyncio.Future[HeartbeatDecision] = loop.create_future()
        self._trigger_waiters.append(waiter)
        self._pending_now += 1
        self._trigger_event.set()
        return await waiter

    async def stop(self) -> None:
        self._running = False
        self._trigger_event.set()
        if self._task is None:
            return
        bind_event("heartbeat.lifecycle").info("heartbeat stopping")
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            # Ignore background exceptions during shutdown.
            bind_event("heartbeat.lifecycle").error("heartbeat stop error={}", exc)
        for waiter in self._trigger_waiters:
            if not waiter.done():
                waiter.set_result(HeartbeatDecision(action="skip", reason="service_stopped"))
        self._trigger_waiters.clear()
        self._task = None
        bind_event("heartbeat.lifecycle").info("heartbeat stopped")

    def status(self) -> dict[str, Any]:
        return {
            "running": self._task is not None and self._running,
            "interval_seconds": self.interval_seconds,
            "state_path": str(self.state_path),
            "last_decision": {
                "action": self.last_decision.action,
                "reason": self.last_decision.reason,
                "text": self.last_decision.text,
            },
            "ticks": int(self._state.get("ticks", 0) or 0),
            "run_count": int(self._state.get("run_count", 0) or 0),
            "skip_count": int(self._state.get("skip_count", 0) or 0),
            "error_count": int(self._state.get("error_count", 0) or 0),
            "consecutive_error_count": int(self._state.get("consecutive_error_count", 0) or 0),
            "trigger_counts": dict(self._state.get("trigger_counts", {}) or {}),
            "reason_counts": dict(self._state.get("reason_counts", {}) or {}),
            "state_save_attempts": int(self._state.get("state_save_attempts", 0) or 0),
            "state_save_retries": int(self._state.get("state_save_retries", 0) or 0),
            "state_save_failures": int(self._state.get("state_save_failures", 0) or 0),
            "state_save_success": int(self._state.get("state_save_success", 0) or 0),
            "state_last_error": str(self._state.get("state_last_error", "") or ""),
            "last_error": str(self._state.get("last_error", "") or ""),
        }
