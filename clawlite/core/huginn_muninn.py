"""
Huginn & Muninn — Odin's Twin Ravens
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Huginn (Thought) and Muninn (Memory) fly across the nine worlds each day,
returning to Odin's shoulders to whisper what they have seen and remembered.

  *"Huginn and Muninn fly each day over the spacious earth.
   I fear for Huginn, that he come not back,
   yet more anxious am I for Muninn."*
      — Grímnismál, stanza 20

In ClawLite, they run as parallel pre-analysis coroutines before each
autonomy tick:

  HUGINN (Thought) — rune ᚺ (Hagalaz: disruptive pattern-breaker)
  Scans the system snapshot for patterns that need immediate attention:
  task backlogs, error trends, stalled sessions, health anomalies.
  Returns a structured action-priority analysis.

  MUNINN (Memory) — rune ᛗ (Mannaz: mind, memory, humanity)
  Sweeps memory metadata for staleness, category drift, and consolidation
  opportunities. Returns a memory health report with maintenance guidance.

Both ravens fly concurrently via asyncio.gather(). Their combined counsel
is merged into the autonomy snapshot under "ravens_counsel" before the
run_callback sees it. This enriches the agent's reasoning without adding
latency — the ravens fly while the engine prepares.

Architecture:
  wrap_with_ravens(callback) → new callback
    └─ ravens_consult(snapshot)
         ├─ huginn: _huginn_analyze(snapshot)  ─┐
         └─ muninn: _muninn_analyze(snapshot)  ─┴─ asyncio.gather()

Usage:
  from clawlite.core.huginn_muninn import wrap_with_ravens

  service = AutonomyService(
      ...,
      run_callback=wrap_with_ravens(your_run_callback),
  )

The ravens NEVER raise — if analysis fails, they return a neutral insight
and autonomy continues unaffected. Odin's ravens do not block Ragnarök.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

RunCallback = Callable[[dict[str, Any]], Awaitable[Any]]

# ── Constants ──────────────────────────────────────────────────────────────────

_HUGINN_RUNE = "ᚺ"   # Hagalaz — disruption, pattern-recognition, hail
_MUNINN_RUNE = "ᛗ"   # Mannaz — mind, memory, the human record
_STALL_THRESHOLD_HOURS = 4.0      # sessions idle > 4h flagged as stalled
_MEMORY_STALE_HOURS = 48.0        # memory not updated in 48h flagged stale
_HIGH_ERROR_RATE = 0.25           # >25% failures = rising error trend
_LOW_ERROR_RATE = 0.05            # <5% failures = falling error trend
_CONSOLIDATION_ITEM_THRESHOLD = 50  # >50 items in a category → suggest compaction


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hours_since(iso_str: str) -> float:
    """Return hours elapsed since an ISO timestamp. Returns 0.0 on parse error."""
    if not iso_str:
        return 0.0
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = now - dt
        return max(0.0, delta.total_seconds() / 3600.0)
    except Exception:
        return 0.0


# ── Insight dataclasses ────────────────────────────────────────────────────────

@dataclass(slots=True)
class HuginnInsight:
    """
    Huginn's analytical report — what needs attention right now.

    Huginn (Thought) observes the living world and returns with urgent news.
    High-priority items should influence the autonomy agent's next action.
    """
    priority: str                    # "high" | "medium" | "low" | "none"
    attention_items: list[str]       # human-readable items needing focus
    error_trend: str                 # "rising" | "stable" | "falling" | "unknown"
    stalled_sessions: list[str]      # session_ids idle > _STALL_THRESHOLD_HOURS
    health_warnings: list[str]       # component health anomalies
    suggested_action: str            # highest-priority recommended next action
    rune: str = _HUGINN_RUNE

    def to_dict(self) -> dict[str, Any]:
        return {
            "raven": "huginn",
            "rune": self.rune,
            "priority": self.priority,
            "attention_items": self.attention_items,
            "error_trend": self.error_trend,
            "stalled_sessions": self.stalled_sessions,
            "health_warnings": self.health_warnings,
            "suggested_action": self.suggested_action,
        }


@dataclass(slots=True)
class MuninnInsight:
    """
    Muninn's memory report — what has been forgotten or needs tending.

    Muninn (Memory) flies across all realms of stored knowledge and returns
    with what has grown stale, what is thriving, and what needs the Norns'
    attention before it is lost.
    """
    stale_categories: list[str]      # categories not updated within stale threshold
    top_categories: list[str]        # most active categories by item count
    consolidation_needed: bool       # True if any category exceeds threshold
    total_memory_items: int          # sum across all categories
    oldest_item_age_hours: float     # age in hours of the least-recently-touched item
    suggested_action: str            # memory maintenance recommendation
    rune: str = _MUNINN_RUNE

    def to_dict(self) -> dict[str, Any]:
        return {
            "raven": "muninn",
            "rune": self.rune,
            "stale_categories": self.stale_categories,
            "top_categories": self.top_categories,
            "consolidation_needed": self.consolidation_needed,
            "total_memory_items": self.total_memory_items,
            "oldest_item_age_hours": round(self.oldest_item_age_hours, 2),
            "suggested_action": self.suggested_action,
        }


@dataclass(slots=True)
class RavensCounsel:
    """
    The combined counsel of Huginn and Muninn.

    Both ravens return together — their whispers are merged into
    "ravens_counsel" in the autonomy snapshot, ready for the agent engine.
    """
    huginn: HuginnInsight
    muninn: MuninnInsight
    consulted_at: str = field(default_factory=_utc_now)

    @property
    def combined_priority(self) -> str:
        """Highest priority across both ravens."""
        order = {"high": 3, "medium": 2, "low": 1, "none": 0}
        h = order.get(self.huginn.priority, 0)
        m = 1 if (self.muninn.consolidation_needed or self.muninn.stale_categories) else 0
        level = max(h, m)
        return {3: "high", 2: "medium", 1: "low", 0: "none"}[level]

    def to_dict(self) -> dict[str, Any]:
        return {
            "consulted_at": self.consulted_at,
            "combined_priority": self.combined_priority,
            "huginn": self.huginn.to_dict(),
            "muninn": self.muninn.to_dict(),
        }

    def summary_lines(self) -> list[str]:
        """Return a short human-readable summary for logs."""
        lines = [
            f"{_HUGINN_RUNE} Huginn [{self.huginn.priority}]: {self.huginn.suggested_action or 'no action'}",
            f"{_MUNINN_RUNE} Muninn [{'consolidate' if self.muninn.consolidation_needed else 'steady'}]: "
            f"{self.muninn.suggested_action or 'no action'}",
        ]
        if self.huginn.stalled_sessions:
            lines.append(f"  Stalled sessions: {', '.join(self.huginn.stalled_sessions[:3])}")
        if self.muninn.stale_categories:
            lines.append(f"  Stale memory: {', '.join(self.muninn.stale_categories[:3])}")
        return lines


# ── Huginn analysis ────────────────────────────────────────────────────────────

def _huginn_analyze_sync(snapshot: dict[str, Any]) -> HuginnInsight:
    """
    Synchronous core of Huginn's analysis.
    Reads the snapshot dict and returns structured thought-insight.
    """
    attention: list[str] = []
    health_warnings: list[str] = []
    stalled: list[str] = []
    suggested = ""

    # ── Health anomalies ──────────────────────────────────────────────────────
    health = snapshot.get("health") or {}
    if isinstance(health, dict):
        for component, status in health.items():
            if isinstance(status, dict):
                if not status.get("running", True):
                    health_warnings.append(f"{component}: not running")
                    attention.append(f"Component '{component}' is down")
                last_err = str(status.get("last_error", "") or "").strip()
                if last_err and last_err != "none":
                    health_warnings.append(f"{component}: {last_err[:80]}")

    # ── Error trend from worker/job stats ────────────────────────────────────
    error_trend = "unknown"
    workers = snapshot.get("workers") or snapshot.get("queue") or {}
    if isinstance(workers, dict):
        total = int(workers.get("total", 0) or 0)
        failed = int(workers.get("failed", 0) or 0)
        done = int(workers.get("done", 0) or 0)
        if total > 0:
            fail_rate = failed / total
            if fail_rate > _HIGH_ERROR_RATE:
                error_trend = "rising"
                attention.append(f"High job failure rate: {fail_rate:.0%}")
            elif fail_rate < _LOW_ERROR_RATE and done > 0:
                error_trend = "falling"
            else:
                error_trend = "stable"
        pending = int(workers.get("pending_jobs", 0) or 0)
        if pending > 20:
            attention.append(f"Job backlog: {pending} pending")

    # ── Stalled session detection ─────────────────────────────────────────────
    sessions = snapshot.get("sessions") or {}
    if isinstance(sessions, dict):
        for sid, sess_data in sessions.items():
            if not isinstance(sess_data, dict):
                continue
            last_active = str(sess_data.get("last_active_at", "") or "")
            if _hours_since(last_active) > _STALL_THRESHOLD_HOURS:
                stalled.append(str(sid))
    if stalled:
        attention.append(f"{len(stalled)} session(s) stalled > {_STALL_THRESHOLD_HOURS:.0f}h")

    # ── Autonomy stats ────────────────────────────────────────────────────────
    auto_stats = snapshot.get("autonomy") or {}
    if isinstance(auto_stats, dict):
        consec_errors = int(auto_stats.get("consecutive_error_count", 0) or 0)
        if consec_errors >= 3:
            attention.append(f"Autonomy: {consec_errors} consecutive errors")
            health_warnings.append(f"autonomy: {consec_errors} consecutive failures")
        last_err = str(auto_stats.get("last_error", "") or "").strip()
        if last_err:
            health_warnings.append(f"autonomy_last_error: {last_err[:80]}")

    # ── Derive priority and suggestion ────────────────────────────────────────
    if health_warnings or error_trend == "rising" or (len(stalled) > 2):
        priority = "high"
        suggested = (
            health_warnings[0] if health_warnings
            else f"Investigate rising errors ({error_trend})"
        )
    elif attention:
        priority = "medium"
        suggested = attention[0]
    elif error_trend == "falling":
        priority = "low"
        suggested = "System recovering — monitor for stability"
    else:
        priority = "none"
        suggested = "All systems nominal — no immediate action needed"

    return HuginnInsight(
        priority=priority,
        attention_items=attention,
        error_trend=error_trend,
        stalled_sessions=stalled,
        health_warnings=health_warnings,
        suggested_action=suggested,
    )


async def _huginn_analyze(snapshot: dict[str, Any]) -> HuginnInsight:
    """Async wrapper so Huginn can fly alongside Muninn."""
    return _huginn_analyze_sync(snapshot)


# ── Muninn analysis ────────────────────────────────────────────────────────────

def _muninn_analyze_sync(snapshot: dict[str, Any]) -> MuninnInsight:
    """
    Synchronous core of Muninn's analysis.
    Reads memory metadata from the snapshot and returns a memory health report.
    """
    stale: list[str] = []
    category_counts: dict[str, int] = {}
    total_items = 0
    oldest_age = 0.0
    consolidation_needed = False

    memory_meta = snapshot.get("memory") or snapshot.get("memory_meta") or {}
    if isinstance(memory_meta, dict):
        for category, cat_data in memory_meta.items():
            if not isinstance(cat_data, dict):
                continue
            count = int(cat_data.get("count", 0) or cat_data.get("items", 0) or 0)
            category_counts[str(category)] = count
            total_items += count

            # Staleness check
            updated_at = str(cat_data.get("updated_at", "") or "")
            age = _hours_since(updated_at)
            if age > oldest_age:
                oldest_age = age
            if age > _MEMORY_STALE_HOURS and count > 0:
                stale.append(str(category))

            # Consolidation check
            if count > _CONSOLIDATION_ITEM_THRESHOLD:
                consolidation_needed = True

    # Top categories by item count
    top = sorted(category_counts.items(), key=lambda kv: -kv[1])[:5]
    top_categories = [k for k, _ in top if k]

    # Derive suggestion
    if stale and consolidation_needed:
        suggested = (
            f"Compact oversize categories and refresh {len(stale)} stale "
            f"realm(s): {', '.join(stale[:3])}"
        )
    elif consolidation_needed:
        oversize = [c for c, n in category_counts.items() if n > _CONSOLIDATION_ITEM_THRESHOLD]
        suggested = f"Consolidate oversize category/categories: {', '.join(oversize[:3])}"
    elif stale:
        suggested = f"Refresh {len(stale)} stale memory realm(s): {', '.join(stale[:3])}"
    elif total_items == 0:
        suggested = "Memory realms are empty — no action needed yet"
    else:
        suggested = f"Memory healthy — {total_items} item(s) across {len(category_counts)} realm(s)"

    return MuninnInsight(
        stale_categories=stale,
        top_categories=top_categories,
        consolidation_needed=consolidation_needed,
        total_memory_items=total_items,
        oldest_item_age_hours=oldest_age,
        suggested_action=suggested,
    )


async def _muninn_analyze(snapshot: dict[str, Any]) -> MuninnInsight:
    """Async wrapper so Muninn can fly alongside Huginn."""
    return _muninn_analyze_sync(snapshot)


# ── Main API ───────────────────────────────────────────────────────────────────

async def ravens_consult(snapshot: dict[str, Any]) -> RavensCounsel:
    """
    Send both ravens out and await their return.

    Both fly concurrently — neither waits for the other. Their insights are
    merged into a RavensCounsel and returned to Odin (the autonomy agent).
    """
    huginn_result, muninn_result = await asyncio.gather(
        _huginn_analyze(snapshot),
        _muninn_analyze(snapshot),
    )
    return RavensCounsel(huginn=huginn_result, muninn=muninn_result)


def wrap_with_ravens(run_callback: RunCallback) -> RunCallback:
    """
    Wrap an AutonomyService run_callback with pre-tick raven analysis.

    The returned callback runs both ravens in parallel, merges their counsel
    into snapshot["ravens_counsel"], then calls the original callback with
    the enriched snapshot.

    The ravens NEVER raise — on any error, they return a neutral insight and
    the original callback proceeds with the unmodified snapshot.

    Usage:
        service = AutonomyService(
            ...,
            run_callback=wrap_with_ravens(original_run_callback),
        )
    """
    async def _wrapped(snapshot: dict[str, Any]) -> Any:
        try:
            counsel = await ravens_consult(snapshot)
            snapshot = dict(snapshot)
            snapshot["ravens_counsel"] = counsel.to_dict()
        except Exception:
            pass  # Ravens do not block Ragnarök
        return await run_callback(snapshot)

    return _wrapped


__all__ = [
    "HuginnInsight",
    "MuninnInsight",
    "RavensCounsel",
    "ravens_consult",
    "wrap_with_ravens",
]
