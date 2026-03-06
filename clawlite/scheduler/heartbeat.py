from __future__ import annotations

import asyncio
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Literal

from clawlite.utils.logging import bind_event, setup_logging

HEARTBEAT_TOKEN = "HEARTBEAT_OK"
DEFAULT_HEARTBEAT_ACK_MAX_CHARS = 300
DEFAULT_ACTIONABLE_EXCERPT_MAX_CHARS = 240


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


class HeartbeatService:
    def __init__(
        self,
        interval_seconds: int = 1800,
        *,
        state_path: str | Path | None = None,
        ack_max_chars: int = DEFAULT_HEARTBEAT_ACK_MAX_CHARS,
        actionable_excerpt_max_chars: int = DEFAULT_ACTIONABLE_EXCERPT_MAX_CHARS,
    ) -> None:
        setup_logging()
        self.interval_seconds = max(5, int(interval_seconds))
        self.ack_max_chars = max(0, int(ack_max_chars))
        self.actionable_excerpt_max_chars = max(0, int(actionable_excerpt_max_chars))
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
            "last_check_iso": "",
            "last_action": "skip",
            "last_reason": "not_started",
            "last_ok_iso": "",
            "last_actionable_iso": "",
            "last_error": "",
            "ticks": 0,
            "run_count": 0,
            "skip_count": 0,
            "error_count": 0,
        }
        self._load_state()

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

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

    def _load_state(self) -> None:
        if not self.state_path.exists():
            return
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(payload, dict):
            return
        self._state = self._migrate_state(payload)

    def _migrate_state(self, payload: dict[str, Any]) -> dict[str, Any]:
        state = dict(self._state)
        state.update(payload)

        legacy_flat: dict[str, Any] = {}
        for key in ("action", "reason", "text"):
            if key in payload:
                legacy_flat[key] = payload.get(key)

        raw_decision = payload.get("last_decision")
        if isinstance(raw_decision, dict):
            decision = HeartbeatDecision.from_result(raw_decision)
        elif legacy_flat:
            decision = HeartbeatDecision.from_result(legacy_flat)
        else:
            action = str(state.get("last_action", "") or "").strip().lower()
            reason = str(state.get("last_reason", "") or "").strip()
            text = str(state.get("last_actionable_excerpt", "") or "").strip()
            seed = {
                "action": action if action in {"run", "skip"} else "skip",
                "reason": reason or "not_started",
                "text": text,
            }
            decision = HeartbeatDecision.from_result(seed)

        state["last_decision"] = {
            "action": decision.action,
            "reason": decision.reason,
            "text": decision.text,
        }
        loaded_action = str(payload.get("last_action", "") or "").strip().lower()
        state["last_action"] = loaded_action if loaded_action in {"run", "skip"} else decision.action
        state["last_reason"] = str(payload.get("last_reason", "") or decision.reason)
        state["last_check_iso"] = str(payload.get("last_check_iso", "") or state.get("last_tick_iso", "") or "")

        if decision.reason == "heartbeat_ok" and not str(state.get("last_ok_iso", "") or ""):
            state["last_ok_iso"] = str(state.get("last_skip_iso", "") or state.get("last_check_iso", "") or "")
        else:
            state["last_ok_iso"] = str(state.get("last_ok_iso", "") or "")

        if decision.action == "run" and not str(state.get("last_actionable_iso", "") or ""):
            state["last_actionable_iso"] = str(state.get("last_run_iso", "") or state.get("last_check_iso", "") or "")
        else:
            state["last_actionable_iso"] = str(state.get("last_actionable_iso", "") or "")

        excerpt = str(state.get("last_actionable_excerpt", "") or decision.text or "").strip()
        if excerpt:
            state["last_actionable_excerpt"] = self._bound_excerpt(excerpt)
        elif "last_actionable_excerpt" in state:
            state.pop("last_actionable_excerpt", None)
        return state

    def _bound_excerpt(self, text: str) -> str:
        if self.actionable_excerpt_max_chars <= 0:
            return ""
        value = text.strip()
        if len(value) <= self.actionable_excerpt_max_chars:
            return value
        return value[: self.actionable_excerpt_max_chars]

    def _save_state(self) -> None:
        payload = json.dumps(self._state, ensure_ascii=False, indent=2)
        tmp_path: Path | None = None
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=str(self.state_path.parent),
                prefix=f".{self.state_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
                tmp_path = Path(handle.name)
            os.replace(str(tmp_path), str(self.state_path))
        except Exception as exc:
            bind_event("heartbeat.state").error("heartbeat save_state_failed path={} error={}", self.state_path, exc)
            if tmp_path is not None:
                try:
                    tmp_path.unlink(missing_ok=True)
                except OSError:
                    pass

    async def _save_state_async(self) -> None:
        await asyncio.to_thread(self._save_state)

    @property
    def last_decision(self) -> HeartbeatDecision:
        row = self._state.get("last_decision")
        if isinstance(row, dict):
            return HeartbeatDecision.from_result(row)
        return HeartbeatDecision(action="skip", reason="state_unavailable")

    async def _execute_tick(self, on_tick: TickHandler, *, trigger: str) -> HeartbeatDecision:
        decision = HeartbeatDecision(action="skip", reason="unknown")
        async with self._tick_lock:
            now_iso = self._utc_now_iso()
            self._state["last_tick_iso"] = now_iso
            self._state["last_trigger"] = trigger
            self._state["ticks"] = int(self._state.get("ticks", 0) or 0) + 1
            try:
                bind_event("heartbeat.tick").debug("heartbeat tick trigger={}", trigger)
                result = await on_tick()
                decision = HeartbeatDecision.from_result(result, ack_max_chars=self.ack_max_chars)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._state["error_count"] = int(self._state.get("error_count", 0) or 0) + 1
                self._state["last_error"] = str(exc)
                decision = HeartbeatDecision(action="skip", reason="tick_error")
                bind_event("heartbeat.tick").error("heartbeat error={}", exc)

            self._state["last_decision"] = {
                "action": decision.action,
                "reason": decision.reason,
                "text": decision.text,
            }
            self._state["last_check_iso"] = now_iso
            self._state["last_action"] = decision.action
            self._state["last_reason"] = decision.reason
            if decision.reason == "heartbeat_ok":
                self._state["last_ok_iso"] = now_iso
            if decision.action == "run":
                self._state["run_count"] = int(self._state.get("run_count", 0) or 0) + 1
                self._state["last_run_iso"] = now_iso
                self._state["last_actionable_iso"] = now_iso
                excerpt = self._bound_excerpt(decision.text)
                if excerpt:
                    self._state["last_actionable_excerpt"] = excerpt
                else:
                    self._state.pop("last_actionable_excerpt", None)
                bind_event("heartbeat.tick").info("heartbeat run reason={}", decision.reason)
            else:
                self._state["skip_count"] = int(self._state.get("skip_count", 0) or 0) + 1
                self._state["last_skip_iso"] = now_iso
                bind_event("heartbeat.tick").debug("heartbeat skip reason={}", decision.reason)
            await self._save_state_async()
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
            task_state, task_error = self._task_snapshot()
            if task_state in {"failed", "cancelled", "done"}:
                if task_error:
                    self._state["last_error"] = task_error
                self._task = None
            else:
                return
        self._running = True
        bind_event("heartbeat.lifecycle").info("heartbeat started interval_seconds={}", self.interval_seconds)

        async def _loop() -> None:
            first_tick = True
            supervisor_backoff_seconds = 0.1
            while self._running:
                try:
                    trigger = "startup" if first_tick else await self._next_trigger_source()
                    first_tick = False
                    if not self._running:
                        break
                    decision = await self._execute_tick(on_tick, trigger=trigger)
                    if trigger == "now" and self._trigger_waiters:
                        waiter = self._trigger_waiters.pop(0)
                        if not waiter.done():
                            waiter.set_result(decision)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    bind_event("heartbeat.loop").error("heartbeat supervisor error={}", exc)
                    if self._running:
                        await asyncio.sleep(supervisor_backoff_seconds)

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
        task_state, task_error = self._task_snapshot()
        last_error = task_error or str(self._state.get("last_error", "") or "")
        return {
            "running": bool(self._running and task_state == "running"),
            "worker_state": task_state,
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
            "last_error": last_error,
        }
