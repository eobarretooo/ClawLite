from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Awaitable, Callable

ActionExecutor = Callable[..., Any | Awaitable[Any]]


class AutonomyActionController:
    ALLOWLIST = frozenset(
        {
            "validate_provider",
            "validate_channels",
            "diagnostics_snapshot",
            "dead_letter_replay_dry_run",
        }
    )
    DENYLIST_TOKENS = (
        "delete",
        "reset",
        "drop",
        "format",
        "rm",
        "shutdown",
        "reboot",
        "wipe",
        "truncate",
        "destroy",
    )
    ENVIRONMENT_PRESETS: dict[str, dict[str, Any]] = {
        "dev": {
            "policy": "balanced",
            "action_cooldown_s": 120.0,
            "action_rate_limit_per_hour": 20,
            "min_action_confidence": 0.55,
            "degraded_backlog_threshold": 300,
            "degraded_supervisor_error_threshold": 3,
        },
        "staging": {
            "policy": "balanced",
            "action_cooldown_s": 180.0,
            "action_rate_limit_per_hour": 14,
            "min_action_confidence": 0.65,
            "degraded_backlog_threshold": 220,
            "degraded_supervisor_error_threshold": 2,
        },
        "prod": {
            "policy": "conservative",
            "action_cooldown_s": 300.0,
            "action_rate_limit_per_hour": 8,
            "min_action_confidence": 0.75,
            "degraded_backlog_threshold": 150,
            "degraded_supervisor_error_threshold": 1,
        },
    }

    def __init__(
        self,
        *,
        max_actions_per_run: int = 1,
        action_cooldown_s: float = 120.0,
        action_rate_limit_per_hour: int = 20,
        max_replay_limit: int = 50,
        policy: str = "balanced",
        environment_profile: str = "dev",
        min_action_confidence: float = 0.55,
        degraded_backlog_threshold: int = 300,
        degraded_supervisor_error_threshold: int = 3,
        audit_path: str = "",
        audit_max_entries: int = 200,
        now_monotonic: Callable[[], float] | None = None,
    ) -> None:
        self.max_actions_per_run = max(1, int(max_actions_per_run or 1))
        self.action_cooldown_s = max(0.0, float(action_cooldown_s or 0.0))
        self.action_rate_limit_per_hour = max(1, int(action_rate_limit_per_hour or 1))
        self.max_replay_limit = max(1, int(max_replay_limit or 1))
        self.policy = self._normalize_policy(policy)
        self.environment_profile = self._normalize_environment_profile(environment_profile)
        self.min_action_confidence = self._clamp_confidence(min_action_confidence)
        self.degraded_backlog_threshold = max(1, int(degraded_backlog_threshold or 1))
        self.degraded_supervisor_error_threshold = max(1, int(degraded_supervisor_error_threshold or 1))
        self.audit_path = str(audit_path or "").strip()
        self.audit_max_entries = max(1, int(audit_max_entries or 1))
        self._now_monotonic = now_monotonic or time.monotonic
        self._lock = asyncio.Lock()

        self._totals: dict[str, int] = {
            "proposed": 0,
            "executed": 0,
            "succeeded": 0,
            "failed": 0,
            "blocked": 0,
            "simulated_runs": 0,
            "simulated_actions": 0,
            "explain_runs": 0,
            "policy_switches": 0,
            "parse_errors": 0,
            "rate_limited": 0,
            "cooldown_blocked": 0,
            "unknown_blocked": 0,
            "quality_blocked": 0,
            "quality_penalty_applied": 0,
            "degraded_blocked": 0,
            "audit_writes": 0,
            "audit_write_failures": 0,
        }
        self._per_action: dict[str, dict[str, Any]] = {name: self._new_action_status() for name in self.ALLOWLIST}
        self._recent_audits: list[dict[str, Any]] = []
        self._last_run: dict[str, Any] = {}

    def _current_guardrails(self) -> dict[str, Any]:
        return {
            "action_cooldown_s": self.action_cooldown_s,
            "action_rate_limit_per_hour": self.action_rate_limit_per_hour,
            "min_action_confidence": self.min_action_confidence,
            "degraded_backlog_threshold": self.degraded_backlog_threshold,
            "degraded_supervisor_error_threshold": self.degraded_supervisor_error_threshold,
        }

    @staticmethod
    def _normalize_policy(policy: str) -> str:
        value = str(policy or "balanced").strip().lower()
        if value not in {"balanced", "conservative"}:
            return "balanced"
        return value

    @staticmethod
    def _normalize_environment_profile(profile: str) -> str:
        value = str(profile or "dev").strip().lower()
        if value not in {"dev", "staging", "prod"}:
            return "dev"
        return value

    @staticmethod
    def _clamp_confidence(raw: Any) -> float:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = 0.0
        if value < 0.0:
            return 0.0
        if value > 1.0:
            return 1.0
        return value

    @staticmethod
    def _new_action_status() -> dict[str, Any]:
        return {
            "proposed": 0,
            "executed": 0,
            "succeeded": 0,
            "failed": 0,
            "blocked": 0,
            "rate_limited": 0,
            "cooldown_blocked": 0,
            "last_executed_at": "",
            "_last_exec_monotonic": 0.0,
            "_executed_timestamps": [],
        }

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _excerpt(value: Any, *, max_chars: int = 260) -> str:
        text = str(value or "").strip()
        if len(text) <= max_chars:
            return text
        return f"{text[: max_chars - 3]}..."

    @staticmethod
    def _clean_args(raw_args: Any) -> dict[str, Any]:
        return dict(raw_args) if isinstance(raw_args, dict) else {}

    def _default_confidence_for_action(self, action: str) -> float:
        if self.policy == "conservative":
            defaults = {
                "diagnostics_snapshot": 0.9,
                "validate_provider": 0.82,
                "validate_channels": 0.82,
                "dead_letter_replay_dry_run": 0.76,
            }
        else:
            defaults = {
                "diagnostics_snapshot": 0.86,
                "validate_provider": 0.75,
                "validate_channels": 0.75,
                "dead_letter_replay_dry_run": 0.68,
            }
        return float(defaults.get(str(action or "").strip(), 0.5))

    def _action_confidence(self, action: str, raw_confidence: Any) -> float:
        if raw_confidence is None:
            return self._default_confidence_for_action(action)
        parsed = self._clamp_confidence(raw_confidence)
        return parsed

    def _context_penalty(self, runtime_snapshot: Any) -> float:
        snapshot = runtime_snapshot if isinstance(runtime_snapshot, dict) else {}
        total_penalty = 0.0

        queue = snapshot.get("queue") if isinstance(snapshot.get("queue"), dict) else {}
        backlog_threshold = max(1, self.degraded_backlog_threshold)
        outbound_size = int(queue.get("outbound_size", 0) or 0)
        dead_letter_size = int(queue.get("dead_letter_size", 0) or 0)
        backlog = max(0, outbound_size) + max(0, dead_letter_size)
        backlog_pressure = min(1.0, float(backlog) / float(backlog_threshold))
        total_penalty += 0.35 * backlog_pressure

        supervisor = snapshot.get("supervisor") if isinstance(snapshot.get("supervisor"), dict) else {}
        incident_count = int(supervisor.get("incident_count", 0) or 0)
        consecutive_errors = int(supervisor.get("consecutive_error_count", 0) or 0)
        incident_pressure = min(1.0, float(max(0, incident_count)) / 2.0)
        error_pressure = min(1.0, float(max(0, consecutive_errors)) / float(max(1, self.degraded_supervisor_error_threshold)))
        total_penalty += 0.25 * ((0.6 * incident_pressure) + (0.4 * error_pressure))

        channels = snapshot.get("channels") if isinstance(snapshot.get("channels"), dict) else {}
        enabled_raw = channels.get("enabled_count")
        running_raw = channels.get("running_count")
        if enabled_raw is not None and running_raw is not None:
            enabled_count = max(0, int(enabled_raw or 0))
            running_count = max(0, int(running_raw or 0))
            if enabled_count > 0:
                healthy_ratio = min(1.0, float(running_count) / float(enabled_count))
                total_penalty += 0.15 * (1.0 - healthy_ratio)

        provider = snapshot.get("provider") if isinstance(snapshot.get("provider"), dict) else {}
        if bool(provider.get("circuit_open", False)):
            total_penalty += 0.2

        heartbeat = snapshot.get("heartbeat") if isinstance(snapshot.get("heartbeat"), dict) else {}
        if heartbeat.get("running") is not None and not bool(heartbeat.get("running", False)):
            total_penalty += 0.1

        cron = snapshot.get("cron") if isinstance(snapshot.get("cron"), dict) else {}
        if cron.get("running") is not None and not bool(cron.get("running", False)):
            total_penalty += 0.1

        return self._clamp_confidence(total_penalty)

    def _detect_degraded(self, runtime_snapshot: Any) -> tuple[bool, str, dict[str, int]]:
        snapshot = runtime_snapshot if isinstance(runtime_snapshot, dict) else {}
        queue = snapshot.get("queue", {}) if isinstance(snapshot.get("queue"), dict) else {}
        supervisor = snapshot.get("supervisor", {}) if isinstance(snapshot.get("supervisor"), dict) else {}
        outbound_size = int(queue.get("outbound_size", 0) or 0)
        dead_letter_size = int(queue.get("dead_letter_size", 0) or 0)
        backlog = max(0, outbound_size) + max(0, dead_letter_size)
        incident_count = int(supervisor.get("incident_count", 0) or 0)
        supervisor_errors = int(supervisor.get("consecutive_error_count", 0) or 0)
        details = {
            "queue_backlog": backlog,
            "incident_count": incident_count,
            "supervisor_error_count": supervisor_errors,
        }
        if backlog >= self.degraded_backlog_threshold:
            return (True, "queue_backlog", details)
        if incident_count > 0:
            return (True, "supervisor_incidents", details)
        if supervisor_errors >= self.degraded_supervisor_error_threshold:
            return (True, "supervisor_errors", details)
        return (False, "", details)

    def _append_recent_audits(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        self._recent_audits.extend(dict(row) for row in rows)
        if len(self._recent_audits) > self.audit_max_entries:
            self._recent_audits = self._recent_audits[-self.audit_max_entries :]

    def _persist_audits(self, rows: list[dict[str, Any]]) -> None:
        if not self.audit_path or not rows:
            return
        target = Path(self.audit_path)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("a", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps(row, ensure_ascii=False))
                    handle.write("\n")
            self._totals["audit_writes"] += len(rows)
        except Exception:
            self._totals["audit_write_failures"] += 1

    @classmethod
    def _extract_first_json_object(cls, raw_text: str) -> dict[str, Any] | None:
        text = str(raw_text or "")
        decoder = json.JSONDecoder()
        for idx, char in enumerate(text):
            if char != "{":
                continue
            try:
                parsed, _ = decoder.raw_decode(text[idx:])
            except JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return dict(parsed)
        return None

    def _parse_actions(self, raw_text: str) -> tuple[list[dict[str, Any]], bool]:
        text = str(raw_text or "").strip()
        if text == "AUTONOMY_IDLE" or text.startswith("AUTONOMY_IDLE\n"):
            return ([], False)
        payload = self._extract_first_json_object(text)
        if payload is None:
            return ([], True)
        if "actions" in payload:
            raw_actions = payload.get("actions")
            if not isinstance(raw_actions, list):
                return ([], True)
            actions: list[dict[str, Any]] = []
            for row in raw_actions:
                if not isinstance(row, dict):
                    continue
                action_name = str(row.get("action", "") or "").strip()
                if not action_name:
                    continue
                actions.append(
                    {
                        "action": action_name,
                        "args": self._clean_args(row.get("args")),
                        "confidence": row.get("confidence"),
                    }
                )
            return (actions, False)
        action_name = str(payload.get("action", "") or "").strip()
        if not action_name:
            return ([], True)
        return (
            [
                {
                    "action": action_name,
                    "args": self._clean_args(payload.get("args")),
                    "confidence": payload.get("confidence"),
                }
            ],
            False,
        )

    def _per_action_row(self, action: str) -> dict[str, Any]:
        row = self._per_action.get(action)
        if row is None:
            row = self._new_action_status()
            self._per_action[action] = row
        return row

    def _prune_rate_window(self, row: dict[str, Any], *, now: float) -> list[float]:
        raw = row.get("_executed_timestamps")
        timestamps = list(raw) if isinstance(raw, list) else []
        window_start = now - 3600.0
        pruned = [float(value) for value in timestamps if float(value) >= window_start]
        row["_executed_timestamps"] = pruned
        return pruned

    def _rate_window(self, row: dict[str, Any], *, now: float, mutate: bool) -> list[float]:
        raw = row.get("_executed_timestamps")
        timestamps = list(raw) if isinstance(raw, list) else []
        window_start = now - 3600.0
        pruned = [float(value) for value in timestamps if float(value) >= window_start]
        if mutate:
            row["_executed_timestamps"] = pruned
        return pruned

    @classmethod
    def _denylisted(cls, action: str) -> bool:
        lowered = str(action or "").strip().lower()
        for token in cls.DENYLIST_TOKENS:
            if token in lowered:
                return True
        return False

    def _trace_row(self, gate: str, blocked: bool, reason: str = "") -> dict[str, Any]:
        row = {"gate": gate, "result": "block" if blocked else "pass"}
        if reason:
            row["reason"] = reason
        return row

    def _clamp_dead_letter_args(self, action: str, args: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(args)
        if action == "dead_letter_replay_dry_run":
            raw_limit = normalized.get("limit", self.max_replay_limit)
            try:
                parsed_limit = int(raw_limit)
            except (TypeError, ValueError):
                parsed_limit = self.max_replay_limit
            normalized["limit"] = max(0, min(self.max_replay_limit, parsed_limit))
            normalized["dry_run"] = True
        return normalized

    def _evaluate_gates(
        self,
        *,
        index: int,
        action: str,
        args: dict[str, Any],
        action_row: dict[str, Any],
        now: float,
        degraded: bool,
        degraded_reason: str,
        context_penalty: float,
        base_confidence: float,
        effective_confidence: float,
        runtime_snapshot: dict[str, Any] | None,
        executors: dict[str, ActionExecutor] | None,
    ) -> dict[str, Any]:
        _ = runtime_snapshot
        trace: list[dict[str, Any]] = []

        if index >= self.max_actions_per_run:
            trace.append(self._trace_row("max_actions_per_run", True, "max_actions_per_run"))
            return {
                "decision": "blocked",
                "gate": "max_actions_per_run",
                "reason": "max_actions_per_run",
                "trace": trace,
                "args": dict(args),
                "executor_available": bool(executors is not None and action in executors),
                "base_confidence": base_confidence,
                "context_penalty": context_penalty,
                "effective_confidence": effective_confidence,
                "degraded": degraded,
                "degraded_reason": degraded_reason,
            }
        trace.append(self._trace_row("max_actions_per_run", False))

        if action not in self.ALLOWLIST or self._denylisted(action):
            trace.append(self._trace_row("allowlist", True, "unknown_or_denylisted"))
            return {
                "decision": "blocked",
                "gate": "allowlist",
                "reason": "unknown_or_denylisted",
                "trace": trace,
                "args": dict(args),
                "executor_available": bool(executors is not None and action in executors),
                "base_confidence": base_confidence,
                "context_penalty": context_penalty,
                "effective_confidence": effective_confidence,
                "degraded": degraded,
                "degraded_reason": degraded_reason,
            }
        trace.append(self._trace_row("allowlist", False))

        if degraded and action != "diagnostics_snapshot":
            trace.append(self._trace_row("degraded_runtime", True, "degraded_runtime"))
            return {
                "decision": "blocked",
                "gate": "degraded_runtime",
                "reason": "degraded_runtime",
                "trace": trace,
                "args": dict(args),
                "executor_available": bool(executors is not None and action in executors),
                "base_confidence": base_confidence,
                "context_penalty": context_penalty,
                "effective_confidence": effective_confidence,
                "degraded": degraded,
                "degraded_reason": degraded_reason,
            }
        trace.append(self._trace_row("degraded_runtime", False))

        if action != "diagnostics_snapshot" and effective_confidence < self.min_action_confidence:
            trace.append(self._trace_row("quality_gate", True, "quality_gate"))
            return {
                "decision": "blocked",
                "gate": "quality_gate",
                "reason": "quality_gate",
                "trace": trace,
                "args": dict(args),
                "executor_available": bool(executors is not None and action in executors),
                "base_confidence": base_confidence,
                "context_penalty": context_penalty,
                "effective_confidence": effective_confidence,
                "degraded": degraded,
                "degraded_reason": degraded_reason,
            }
        trace.append(self._trace_row("quality_gate", False))

        timestamps = self._rate_window(action_row, now=now, mutate=False)
        if len(timestamps) >= self.action_rate_limit_per_hour:
            trace.append(self._trace_row("rate_limit", True, "rate_limited"))
            return {
                "decision": "blocked",
                "gate": "rate_limit",
                "reason": "rate_limited",
                "trace": trace,
                "args": dict(args),
                "executor_available": bool(executors is not None and action in executors),
                "base_confidence": base_confidence,
                "context_penalty": context_penalty,
                "effective_confidence": effective_confidence,
                "degraded": degraded,
                "degraded_reason": degraded_reason,
            }
        trace.append(self._trace_row("rate_limit", False))

        last_exec = float(action_row.get("_last_exec_monotonic", 0.0) or 0.0)
        if self.action_cooldown_s > 0 and last_exec > 0 and now < (last_exec + self.action_cooldown_s):
            trace.append(self._trace_row("cooldown", True, "cooldown"))
            return {
                "decision": "blocked",
                "gate": "cooldown",
                "reason": "cooldown",
                "trace": trace,
                "args": dict(args),
                "executor_available": bool(executors is not None and action in executors),
                "base_confidence": base_confidence,
                "context_penalty": context_penalty,
                "effective_confidence": effective_confidence,
                "degraded": degraded,
                "degraded_reason": degraded_reason,
            }
        trace.append(self._trace_row("cooldown", False))

        normalized_args = self._clamp_dead_letter_args(action, args)
        trace.append(self._trace_row("dry_run_enforcement", False))
        executor_available = bool(executors is None or action in executors)
        if executors is not None and not executor_available:
            trace.append(self._trace_row("executor_available", True, "executor_missing"))
            return {
                "decision": "blocked",
                "gate": "executor_available",
                "reason": "executor_missing",
                "trace": trace,
                "args": dict(normalized_args),
                "executor_available": False,
                "base_confidence": base_confidence,
                "context_penalty": context_penalty,
                "effective_confidence": effective_confidence,
                "degraded": degraded,
                "degraded_reason": degraded_reason,
            }

        trace.append(self._trace_row("executor_available", False))
        return {
            "decision": "allow",
            "gate": "all_gates_passed",
            "reason": "allowed",
            "trace": trace,
            "args": dict(normalized_args),
            "executor_available": executor_available,
            "base_confidence": base_confidence,
            "context_penalty": context_penalty,
            "effective_confidence": effective_confidence,
            "degraded": degraded,
            "degraded_reason": degraded_reason,
        }

    def _build_decision_view(
        self,
        raw_text: str,
        *,
        runtime_snapshot: dict[str, Any] | None,
        executors: dict[str, ActionExecutor] | None,
    ) -> dict[str, Any]:
        now = self._now_monotonic()
        context_penalty = self._context_penalty(runtime_snapshot)
        degraded, degraded_reason, _ = self._detect_degraded(runtime_snapshot)
        actions, parse_error = self._parse_actions(raw_text)
        action_decisions: list[dict[str, Any]] = []
        proposed = 0
        allowed = 0
        blocked = 0

        for index, row in enumerate(actions):
            action = str(row.get("action", "") or "").strip()
            args = self._clean_args(row.get("args"))
            if not action:
                continue
            base_confidence = self._action_confidence(action, row.get("confidence"))
            effective_confidence = self._clamp_confidence(base_confidence - context_penalty)
            action_row = self._per_action_row(action)
            decision = self._evaluate_gates(
                index=index,
                action=action,
                args=args,
                action_row=action_row,
                now=now,
                degraded=degraded,
                degraded_reason=degraded_reason,
                context_penalty=context_penalty,
                base_confidence=base_confidence,
                effective_confidence=effective_confidence,
                runtime_snapshot=runtime_snapshot,
                executors=executors,
            )
            proposed += 1
            if decision["decision"] == "allow":
                allowed += 1
            else:
                blocked += 1
            action_decisions.append(
                {
                    "index": index,
                    "action": action,
                    "args": dict(decision.get("args", {})),
                    "decision": decision["decision"],
                    "gate": decision["gate"],
                    "reason": decision["reason"],
                    "base_confidence": decision["base_confidence"],
                    "context_penalty": decision["context_penalty"],
                    "effective_confidence": decision["effective_confidence"],
                    "degraded": decision["degraded"],
                    "degraded_reason": decision["degraded_reason"],
                    "executor_available": decision["executor_available"],
                    "trace": list(decision["trace"]),
                }
            )

        return {
            "parse_error": bool(parse_error),
            "proposed": proposed,
            "allowed": allowed,
            "blocked": blocked,
            "degraded": degraded,
            "degraded_reason": degraded_reason,
            "policy": self.policy,
            "environment_profile": self.environment_profile,
            "min_action_confidence": self.min_action_confidence,
            "actions": action_decisions,
        }

    @staticmethod
    def _overall_risk_level(risk_counts: dict[str, int]) -> str:
        if int(risk_counts.get("high", 0) or 0) > 0:
            return "high"
        if int(risk_counts.get("medium", 0) or 0) > 0:
            return "medium"
        return "low"

    def _classify_risk(self, action_decision: dict[str, Any]) -> tuple[str, str]:
        gate = str(action_decision.get("gate", "") or "")
        decision = str(action_decision.get("decision", "") or "")
        confidence = self._clamp_confidence(action_decision.get("effective_confidence", 0.0))

        if gate == "allowlist":
            return ("high", "Action blocked by allowlist/denylist; keep blocked and revise proposal.")
        if gate == "degraded_runtime":
            return ("high", "Runtime degraded; run diagnostics first and retry after recovery.")
        if confidence < 0.35:
            return ("high", "Effective confidence is very low; require stronger evidence.")
        if gate in {"quality_gate", "rate_limit", "cooldown"}:
            return ("medium", "Guardrail blocked this action; wait/tune policy or improve confidence.")
        if decision == "allow" and confidence < 0.65:
            return ("medium", "Action allowed with moderate confidence; monitor before broader changes.")
        return ("low", "Action is within policy and confidence guardrails.")

    def set_environment_profile(self, profile: str, *, actor: str = "control", reason: str = "") -> dict[str, Any]:
        normalized = self._normalize_environment_profile(profile)
        if normalized != str(profile or "").strip().lower():
            raise ValueError("invalid_environment_profile")

        preset = dict(self.ENVIRONMENT_PRESETS.get(normalized, {}))
        if not preset:
            raise ValueError("invalid_environment_profile")

        previous = {
            "environment_profile": self.environment_profile,
            "policy": self.policy,
            **self._current_guardrails(),
        }

        self.environment_profile = normalized
        self.policy = self._normalize_policy(preset.get("policy", self.policy))
        self.action_cooldown_s = max(0.0, float(preset.get("action_cooldown_s", self.action_cooldown_s) or 0.0))
        self.action_rate_limit_per_hour = max(
            1,
            int(preset.get("action_rate_limit_per_hour", self.action_rate_limit_per_hour) or 1),
        )
        self.min_action_confidence = self._clamp_confidence(preset.get("min_action_confidence", self.min_action_confidence))
        self.degraded_backlog_threshold = max(
            1,
            int(preset.get("degraded_backlog_threshold", self.degraded_backlog_threshold) or 1),
        )
        self.degraded_supervisor_error_threshold = max(
            1,
            int(preset.get("degraded_supervisor_error_threshold", self.degraded_supervisor_error_threshold) or 1),
        )
        self._totals["policy_switches"] += 1

        new_values = {
            "environment_profile": self.environment_profile,
            "policy": self.policy,
            **self._current_guardrails(),
        }
        changed_at = self._utc_now_iso()
        row = {
            "kind": "policy_change",
            "at": changed_at,
            "actor": str(actor or "control"),
            "reason": str(reason or ""),
            "previous": dict(previous),
            "new": dict(new_values),
        }
        self._append_recent_audits([row])
        self._persist_audits([row])
        return {
            "at": changed_at,
            "actor": str(actor or "control"),
            "reason": str(reason or ""),
            "previous": previous,
            "new": new_values,
        }

    def explain(self, raw_text: str, runtime_snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
        simulation = self._build_decision_view(raw_text, runtime_snapshot=runtime_snapshot, executors=None)
        self._totals["explain_runs"] += 1

        risk_counts = {"low": 0, "medium": 0, "high": 0}
        explained_actions: list[dict[str, Any]] = []
        for row in simulation["actions"]:
            risk_level, recommendation = self._classify_risk(row)
            risk_counts[risk_level] += 1
            explained_actions.append(
                {
                    **dict(row),
                    "risk_level": risk_level,
                    "recommendation": recommendation,
                }
            )

        return {
            **dict(simulation),
            "overall_risk": self._overall_risk_level(risk_counts),
            "risk_counts": risk_counts,
            "actions": explained_actions,
        }

    def simulate(
        self,
        raw_text: str,
        executors: dict[str, ActionExecutor] | None = None,
        runtime_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = self._build_decision_view(raw_text, runtime_snapshot=runtime_snapshot, executors=executors)

        self._totals["simulated_runs"] += 1
        self._totals["simulated_actions"] += int(result.get("proposed", 0) or 0)
        return result

    async def process(
        self,
        raw_text: str,
        executors: dict[str, ActionExecutor],
        runtime_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        async with self._lock:
            now = self._now_monotonic()
            run_started_at = self._utc_now_iso()
            run_id = f"{int(now * 1000)}-{int(time.time() * 1000)}"
            run_audits: list[dict[str, Any]] = []
            run_proposed = 0
            run_executed = 0
            run_succeeded = 0
            run_failed = 0
            run_blocked = 0
            quality_rows: list[dict[str, float]] = []
            degraded, degraded_reason, degraded_details = self._detect_degraded(runtime_snapshot)
            context_penalty = self._context_penalty(runtime_snapshot)

            actions, parse_error = self._parse_actions(raw_text)
            if parse_error:
                self._totals["parse_errors"] += 1
                run_blocked += 1

            for index, row in enumerate(actions):
                action = str(row.get("action", "") or "").strip()
                args = self._clean_args(row.get("args"))
                base_confidence = self._action_confidence(action, row.get("confidence"))
                effective_confidence = self._clamp_confidence(base_confidence - context_penalty)
                if not action:
                    continue
                quality_rows.append(
                    {
                        "base": base_confidence,
                        "penalty": context_penalty,
                        "effective": effective_confidence,
                    }
                )
                run_proposed += 1
                self._totals["proposed"] += 1
                action_row = self._per_action_row(action)
                action_row["proposed"] += 1
                if context_penalty > 0.0:
                    self._totals["quality_penalty_applied"] += 1

                decision = self._evaluate_gates(
                    index=index,
                    action=action,
                    args=args,
                    action_row=action_row,
                    now=now,
                    degraded=degraded,
                    degraded_reason=degraded_reason,
                    context_penalty=context_penalty,
                    base_confidence=base_confidence,
                    effective_confidence=effective_confidence,
                    runtime_snapshot=runtime_snapshot,
                    executors=None,
                )
                args = dict(decision.get("args", args))

                if decision["decision"] == "blocked":
                    self._totals["blocked"] += 1
                    run_blocked += 1
                    action_row["blocked"] += 1
                    gate = str(decision.get("gate", ""))
                    if gate == "allowlist":
                        self._totals["unknown_blocked"] += 1
                    elif gate == "degraded_runtime":
                        self._totals["degraded_blocked"] += 1
                    elif gate == "quality_gate":
                        self._totals["quality_blocked"] += 1
                    elif gate == "rate_limit":
                        self._totals["rate_limited"] += 1
                        action_row["rate_limited"] += 1
                    elif gate == "cooldown":
                        self._totals["cooldown_blocked"] += 1
                        action_row["cooldown_blocked"] += 1
                    audit_row = {
                        "action": action,
                        "status": "blocked",
                        "reason": decision["reason"],
                        "gate": decision["gate"],
                        "trace": list(decision["trace"]),
                        "args": dict(args),
                        "confidence": effective_confidence,
                        "base_confidence": base_confidence,
                        "context_penalty": context_penalty,
                        "effective_confidence": effective_confidence,
                    }
                    if gate == "quality_gate":
                        audit_row["min_action_confidence"] = self.min_action_confidence
                    if gate == "degraded_runtime":
                        audit_row["degraded_reason"] = degraded_reason
                        audit_row["degraded"] = dict(degraded_details)
                    run_audits.append(audit_row)
                    continue

                executor = executors.get(action)
                if not callable(executor):
                    self._totals["failed"] += 1
                    run_failed += 1
                    action_row["failed"] += 1
                    run_audits.append(
                        {
                            "action": action,
                            "status": "failed",
                            "reason": "executor_missing",
                            "gate": "executor_available",
                            "trace": list(decision["trace"]) + [self._trace_row("executor_available", True, "executor_missing")],
                            "args": dict(args),
                            "confidence": effective_confidence,
                            "base_confidence": base_confidence,
                            "context_penalty": context_penalty,
                            "effective_confidence": effective_confidence,
                        }
                    )
                    continue

                self._totals["executed"] += 1
                run_executed += 1
                action_row["executed"] += 1
                action_row["_last_exec_monotonic"] = now
                action_row["last_executed_at"] = self._utc_now_iso()
                self._prune_rate_window(action_row, now=now).append(now)

                try:
                    result = executor(**args)
                    if asyncio.iscoroutine(result):
                        result = await result
                    self._totals["succeeded"] += 1
                    run_succeeded += 1
                    action_row["succeeded"] += 1
                    run_audits.append(
                        {
                            "action": action,
                            "status": "succeeded",
                            "gate": "execution",
                            "trace": list(decision["trace"]) + [self._trace_row("execution", False)],
                            "args": dict(args),
                            "confidence": effective_confidence,
                            "base_confidence": base_confidence,
                            "context_penalty": context_penalty,
                            "effective_confidence": effective_confidence,
                            "result_excerpt": self._excerpt(result),
                        }
                    )
                except Exception as exc:
                    self._totals["failed"] += 1
                    run_failed += 1
                    action_row["failed"] += 1
                    run_audits.append(
                        {
                            "action": action,
                            "status": "failed",
                            "gate": "execution",
                            "trace": list(decision["trace"]) + [self._trace_row("execution", True, "execution_failed")],
                            "args": dict(args),
                            "confidence": effective_confidence,
                            "base_confidence": base_confidence,
                            "context_penalty": context_penalty,
                            "effective_confidence": effective_confidence,
                            "error": self._excerpt(exc),
                        }
                    )

            if parse_error:
                run_audits.append({"action": "", "status": "parse_error", "reason": "no_valid_action_json", "confidence": 0.0})

            recent_rows = [
                {
                    "kind": "action",
                    "run_id": run_id,
                    "at": run_started_at,
                    "policy": self.policy,
                    "raw_excerpt": self._excerpt(raw_text),
                    **dict(row),
                }
                for row in run_audits
            ]
            run_summary_row = {
                "kind": "run",
                "run_id": run_id,
                "at": run_started_at,
                "policy": self.policy,
                "raw_excerpt": self._excerpt(raw_text),
                "proposed": run_proposed,
                "executed": run_executed,
                "succeeded": run_succeeded,
                "failed": run_failed,
                "blocked": run_blocked,
                "parse_error": bool(parse_error),
                "degraded": degraded,
                "degraded_reason": degraded_reason,
                "degraded_details": dict(degraded_details),
            }
            persisted_rows = recent_rows + [run_summary_row]

            quality_summary = {
                "count": len(quality_rows),
                "avg_base_confidence": 0.0,
                "avg_context_penalty": 0.0,
                "avg_effective_confidence": 0.0,
                "max_context_penalty": 0.0,
                "max_base_confidence": 0.0,
                "max_effective_confidence": 0.0,
            }
            if quality_rows:
                row_count = float(len(quality_rows))
                sum_base = sum(row["base"] for row in quality_rows)
                sum_penalty = sum(row["penalty"] for row in quality_rows)
                sum_effective = sum(row["effective"] for row in quality_rows)
                quality_summary["avg_base_confidence"] = sum_base / row_count
                quality_summary["avg_context_penalty"] = sum_penalty / row_count
                quality_summary["avg_effective_confidence"] = sum_effective / row_count
                quality_summary["max_context_penalty"] = max(row["penalty"] for row in quality_rows)
                quality_summary["max_base_confidence"] = max(row["base"] for row in quality_rows)
                quality_summary["max_effective_confidence"] = max(row["effective"] for row in quality_rows)

            self._append_recent_audits(persisted_rows)
            self._persist_audits(persisted_rows)

            self._last_run = {
                "at": run_started_at,
                "raw_excerpt": self._excerpt(raw_text),
                "proposed": run_proposed,
                "executed": run_executed,
                "succeeded": run_succeeded,
                "failed": run_failed,
                "blocked": run_blocked,
                "parse_error": bool(parse_error),
                "degraded": degraded,
                "degraded_reason": degraded_reason,
                "degraded_details": dict(degraded_details),
                "quality": quality_summary,
                "audits": run_audits,
            }
            return self.status()

    def export_audit(self, limit: int = 100) -> dict[str, Any]:
        max_limit = max(1, int(limit or 100))
        safe_limit = min(max_limit, self.audit_max_entries)
        path = self.audit_path
        if not path:
            entries = self._recent_audits[-safe_limit:]
            return {"ok": True, "path": "", "count": len(entries), "entries": entries}

        target = Path(path)
        if not target.exists():
            return {"ok": True, "path": str(target), "count": 0, "entries": []}

        try:
            parsed: list[dict[str, Any]] = []
            with target.open("r", encoding="utf-8") as handle:
                for line in handle:
                    text = line.strip()
                    if not text:
                        continue
                    try:
                        row = json.loads(text)
                    except JSONDecodeError:
                        continue
                    if isinstance(row, dict):
                        parsed.append(row)
            if len(parsed) > safe_limit:
                parsed = parsed[-safe_limit:]
            return {"ok": True, "path": str(target), "count": len(parsed), "entries": parsed}
        except Exception:
            return {"ok": False, "path": str(target), "count": 0, "entries": []}

    def status(self) -> dict[str, Any]:
        now = self._now_monotonic()
        per_action_out: dict[str, dict[str, Any]] = {}
        for action, row in sorted(self._per_action.items()):
            timestamps = self._prune_rate_window(row, now=now)
            per_action_out[action] = {
                "proposed": int(row.get("proposed", 0) or 0),
                "executed": int(row.get("executed", 0) or 0),
                "succeeded": int(row.get("succeeded", 0) or 0),
                "failed": int(row.get("failed", 0) or 0),
                "blocked": int(row.get("blocked", 0) or 0),
                "rate_limited": int(row.get("rate_limited", 0) or 0),
                "cooldown_blocked": int(row.get("cooldown_blocked", 0) or 0),
                "last_executed_at": str(row.get("last_executed_at", "") or ""),
                "executed_last_hour": len(timestamps),
            }
        return {
            "max_actions_per_run": self.max_actions_per_run,
            "policy": self.policy,
            "environment_profile": self.environment_profile,
            "min_action_confidence": self.min_action_confidence,
            "degraded_backlog_threshold": self.degraded_backlog_threshold,
            "degraded_supervisor_error_threshold": self.degraded_supervisor_error_threshold,
            "action_cooldown_s": self.action_cooldown_s,
            "action_rate_limit_per_hour": self.action_rate_limit_per_hour,
            "max_replay_limit": self.max_replay_limit,
            "audit_path": self.audit_path,
            "audit_max_entries": self.audit_max_entries,
            "totals": dict(self._totals),
            "per_action": per_action_out,
            "last_run": dict(self._last_run),
            "recent_audits": list(self._recent_audits),
        }
