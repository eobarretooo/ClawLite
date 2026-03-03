# ClawLite Roadmap

## P0 — Core stability

- Consolidate a single agent execution flow (CLI + channels + gateway)
- Expand scheduler integration test coverage (cron/heartbeat)
- Harden input validation in channels and tools with external I/O
- P0 progress: engine turn finalization now uses fail-soft persistence (session append + memory consolidate best-effort with degradation logging); broader core reliability hardening remains in progress.
- P0 progress: session storage durability/recovery hardening landed with append retry+fsync behavior, malformed JSONL read-repair, and additive engine/session persistence telemetry in diagnostics.
- Telegram reliability hardening in progress: deterministic soak/recovery tests cover repeated polling reconnects, outbound transient retry cycles, and mixed-failure chaos/recovery matrix cases (chunking + formatting fallback + 429 retry-after + timeout before success); continue runtime tuning for near-100% stability.
- P0 progress: scheduler durability telemetry hardening landed for heartbeat + cron (best-effort atomic state saves with retry, non-crashing loop containment for save/schedule/job failures, and additive runtime diagnostics/per-job health fields).
- P0 progress: tool I/O reliability hardening landed with registry/engine tool telemetry, deterministic exec malformed-syntax and bounded-output behavior, plus MCP bounded transient retry and deterministic timeout/http/invalid-response errors.
- P0 progress: provider reliability hardening landed with bounded retry/backoff+jitter, Retry-After support, per-provider circuit breaker, additive provider diagnostics, and optional fallback model failover on retryable failures.

## P1 — Operational autonomy

- Achieve 24/7 Linux operation with supervision and automatic recovery
- Improve proactive delivery through channels with minimum observability
- Strengthen long-term memory and per-session context recovery
- P1 progress: runtime supervisor bootstrap landed in gateway lifecycle with additive diagnostics, bounded per-component cooldown recovery, and incident/recovery counters for heartbeat, cron, channels, and provider circuit-open observability.
- P1 progress: proactive delivery observability landed with additive queue/dead-letter telemetry, channel-manager delivery diagnostics (total + per-channel), and bounded/auditable dead-letter replay control API (`/v1/control/dead-letter/replay`).
- P1 progress: long-term memory/session recovery hardening landed with malformed memory JSONL tolerant reads + best-effort read-repair, per-session context recovery fallback (history-first with curated-memory fallback), and additive `memory_store` + `session_recovery` diagnostics in engine/gateway telemetry.
- P1 progress: autonomy loop bootstrap landed with an opt-in periodic autonomy worker (supervised review turn), bounded queue-backlog/cooldown/timeout guards, fail-soft tick isolation, additive diagnostics telemetry, and manual control endpoint (`/v1/control/autonomy/trigger`).
- P1 progress: autonomy action execution layer landed with strict allowlist + denylist blocking, per-action cooldown/hourly rate limits, dry-run-only dead-letter replay clamp, fail-soft sequential execution, and additive `autonomy_actions` telemetry/audits in diagnostics + trigger responses.
- P1 progress: autonomy reliability increment landed with action quality gates, balanced/conservative policy profiles, degraded-runtime action restrictions, and persistent/exportable autonomy audit trail (`/v1/control/autonomy/audit`).
- P1 progress: autonomy reliability increment added OpenClaw-first environment policy layering (`dev`/`staging`/`prod`) plus contextual quality scoring driven by runtime health snapshots, with additive diagnostics/audit confidence telemetry.

## P2 — Ecosystem

- Improve user skills experience (discovery, execution, diagnostics)
- Evolve MCP integration and specialized providers
- Publish more objective operations and release guides for personal deployment

## Minimum release criteria

1. `pytest -q` passing
2. Main CLI without regression (`start`, `run`, `onboard`, `cron`, `skills`)
3. Main API working (`/health`, `/v1/chat`, `/v1/cron/*`)
4. Documentation aligned with real behavior
