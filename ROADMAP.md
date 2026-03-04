# ClawLite Roadmap

## P0 — Core stability

- Consolidate a single agent execution flow (CLI + channels + gateway)
- Expand scheduler integration test coverage (cron/heartbeat)
- Harden input validation in channels and tools with external I/O

## P1 — Operational autonomy

- Close 24/7 Linux operations with supervision and automatic recovery
- Improve proactive channel delivery with minimum observability
- Strengthen long-term memory and per-session context recovery

## P2 — Ecosystem

- Improve user skills experience (discovery, execution, diagnostics)
- Evolve MCP integration and specialized providers
- Publish more objective operations and release guides for personal deploys

## Minimum release criteria

1. `pytest -q` passing
2. Main CLI without regressions (`start`, `run`, `onboard`, `cron`, `skills`)
3. Main API working (`/health`, `/v1/chat`, `/v1/cron/*`)
4. Documentation aligned with real behavior

## ClawLite Parity Roadmap (nanobot + OpenClaw)

### NOW (Critical parity)
- [x] Replace passive channel stubs with active outbound adapters for Discord, Slack, and WhatsApp.
- [x] Enforce stronger tool safety policy for exec, web, and mcp.
- [x] Align gateway with production-grade contract.
- [x] Upgrade heartbeat to HEARTBEAT_OK + persisted check state.
- Progress 2026-03-04: gateway compatibility layer delivered (`/api/status`, `/api/message`, `/api/token`, `/ws`, `/`).
- Progress 2026-03-04: gateway auth now applies automatic hardening (`off` -> `required`) on non-loopback hosts when a token is configured; legacy env fallback `CLAWLITE_GATEWAY_TOKEN` is supported.
- Progress 2026-03-04: gateway HTTP contract stabilized with metadata (`contract_version`, `server_time`, `generated_at`, `uptime_s`), error envelope with `code`, and alias `/api/diagnostics` with parity to `/v1/diagnostics`.
- Progress 2026-03-04: heartbeat now persists explicit check-state with backward-compatible migration and fail-soft atomic write.
- Progress 2026-03-04: ToolRegistry now applies a centralized per-channel policy for risky tools (`exec`, `web_fetch`, `web_search`, `mcp`) with deterministic error `tool_blocked_by_safety_policy:<tool>:<channel>`.
- Progress 2026-03-04: Discord/Slack/WhatsApp now have active outbound sending with `httpx` (no inbound loops in this increment).

### NEXT (Operational maturity)
- [ ] Improve prompt/memory pipeline.
- Progress 2026-03-04: `agents.defaults.memory_window` connected end-to-end (config -> gateway runtime -> engine -> `sessions.read(limit=...)`) with visibility in `clawlite status` and `clawlite diagnostics`.
- [ ] Expand provider + config capability.
- [ ] Align workspace/bootstrap/templates with runtime lifecycle.
- [ ] Expand CLI operations.
- [ ] Add structured observability.

### FUTURE (Scale + polish)
- [ ] Subagent orchestration controls.
- [ ] Memory/session retention and compaction.
- [ ] Multi-channel concurrency optimization.

## User plan — "100%" goals (integrated execution)

### Practical mapping
- **Telegram 100% (typing, formatting, robust delivery)** — **Status: partial** (`P1` + `FUTURE`, parity `NEXT`)  
  100% criterion: real-time typing indicator, consistent safe Markdown/HTML formatting, retries with backoff + idempotency, delivery confirmation, and observable per-message error fallback.
- **Core 100% (Memory, Agents, Heartbeat, Soul, Tools, User) with OpenClaw-level autonomy** — **Status: partial** (`P0` + `P1`, parity `NOW`/`NEXT`)  
  100% criterion: stable 24/7 heartbeat with persisted state, short+long memory with per-session recovery, proactive agent loop without manual intervention, per-channel tool policies already applied, and end-to-end auditable user-session flow.
- **Providers 100% (robust API handling)** — **Status: partial** (`P1` + `P2`, parity `NEXT`)  
  100% criterion: timeouts/retries/circuit-breaker per provider, deterministic error classification (auth, quota, rate, transient, fatal), configurable fallback between providers, and integration tests covering real failures.
- **Skills 100%** — **Status: partial** (`P2`, parity `NEXT`)  
  100% criterion: reliable discovery, isolated execution with clear diagnostics, validated input/output contracts, and test coverage for critical skills.
- **Autonomy 100%** — **Status: partial** (`P1`, parity `NEXT`)  
  100% criterion: continuous operation without an operator, automatic post-failure recovery, proactive decisions with safety limits, and minimum incident observability.
- **Subagents 100%** — **Status: partial** (`FUTURE`)  
  100% criterion: subagent orchestration with task-based routing, context isolation, concurrency control, and consistent final synthesis in the main agent.
- **Future: advanced memory + no-approval mode (notification-only) + self-improvement** — **Status: missing** (`FUTURE`)  
  100% criterion: semantic memory with compaction/retention, `no-approval` operational policy with audit trail and passive notifications, and a metrics-driven self-improvement cycle without breaking safety guardrails.

### Suggested execution order (short)
1. Close core `P0` and stabilize 24/7 operations (`P1`) as the autonomy foundation.
2. Complete Telegram + robust providers for channel and inference reliability.
3. Consolidate skills and proactive autonomy with structured observability.
4. Move into `FUTURE` with subagents, advanced memory, and `no-approval` mode with notification-only.
