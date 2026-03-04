# ClawLite Roadmap

## Priorities

### P0 - Core stability
- Consolidate a single agent execution flow (CLI + channels + gateway).
- Expand scheduler integration test coverage (cron/heartbeat).
- Harden input validation in channels and tools with external I/O.

### P1 - Operational autonomy
- Close 24/7 Linux operations with supervision and automatic recovery.
- Improve proactive channel delivery with minimum observability.
- Strengthen long-term memory and per-session context recovery.

### P2 - Ecosystem
- Improve user skills experience (discovery, execution, diagnostics).
- Evolve MCP integration and specialized providers.
- Publish more objective operations and release guides for personal deploys.

## Minimum Release Criteria

1. `pytest -q` passing.
2. Main CLI without regressions (`start`, `run`, `onboard`, `cron`, `skills`).
3. Main API working (`/health`, `/v1/chat`, `/v1/cron/*`).
4. Documentation aligned with real behavior.

## ClawLite Parity Roadmap (nanobot + OpenClaw)

### NOW (Critical parity)

#### Checklist
- [x] Replace passive channel stubs with active outbound adapters for Discord,
  Slack, and WhatsApp.
- [x] Enforce stronger tool safety policy for exec, web, and mcp.
- [x] Align gateway with production-grade contract.
- [x] Upgrade heartbeat to `HEARTBEAT_OK` + persisted check state.

#### Progress updates (2026-03-04)
- Gateway compatibility layer delivered (`/api/status`, `/api/message`,
  `/api/token`, `/ws`, `/`).
- Gateway auth now applies automatic hardening (`off` -> `required`) on
  non-loopback hosts when a token is configured; legacy env fallback
  `CLAWLITE_GATEWAY_TOKEN` is supported.
- Gateway HTTP contract stabilized with metadata (`contract_version`,
  `server_time`, `generated_at`, `uptime_s`), error envelope with `code`, and
  alias `/api/diagnostics` with parity to `/v1/diagnostics`.
- Heartbeat now persists explicit check-state with backward-compatible
  migration and fail-soft atomic write.
- ToolRegistry now applies a centralized per-channel policy for risky tools
  (`exec`, `web_fetch`, `web_search`, `mcp`) with deterministic error
  `tool_blocked_by_safety_policy:<tool>:<channel>`.
- Discord/Slack/WhatsApp now have active outbound sending with `httpx`
  (no inbound loops in this increment).

### NEXT (Operational maturity)

#### Checklist
- [ ] Improve prompt/memory pipeline.
- [ ] Expand provider + config capability.
- [ ] Align workspace/bootstrap/templates with runtime lifecycle.
- [ ] Expand CLI operations.
- [ ] Add structured observability.

#### Progress updates (2026-03-04)
- `agents.defaults.memory_window` connected end-to-end
  (config -> gateway runtime -> engine -> `sessions.read(limit=...)`) with
  visibility in `clawlite status` and `clawlite diagnostics`.
- Retrieval observability delivered in runtime diagnostics (`engine.retrieval_metrics`)
  plus deterministic operator command `clawlite memory eval` for synthetic
  retrieval regression checks.
- Provider telemetry visibility added to gateway diagnostics (`engine.provider`) with config/env control and secret-safe provider contracts.
- Codex auth UX hardened: typed `auth.providers.openai_codex`, deterministic `openai-codex/*` provider path, CLI login/status/logout, and explicit auth guidance on failures.
- Workspace/bootstrap lifecycle aligned as one-shot with persisted `bootstrap-state.json`, runtime auto-completion on successful user turns, and operator visibility in gateway/CLI diagnostics.
- Structured HTTP gateway telemetry added to diagnostics (`http`) with in-memory request counters by method/path/status and latency aggregates.
- Provider ops status expanded beyond Codex in CLI (`clawlite provider status`) with deterministic, secret-safe status for API-key providers (`openai`, `gemini`, `groq`, `deepseek`, `anthropic`, `openrouter`, `custom`).
- Strict CLI config preflight added via `clawlite validate config` with structured JSON and deterministic exit semantics (`0` ok, `2` invalid/parse/validation).
- Prompt/memory pipeline now injects session-aware recovery snippets when retrieval returns no hits, preserving fail-soft turn execution.
- Structured provider error-class telemetry added for diagnostics (`last_error_class`, `error_class_counts`, failover primary/fallback error classes and retryable/non-retryable primary failure counters).
- Turn-level structured observability added to diagnostics (`engine.turn_metrics`) with outcome counters, tool-call totals, latency buckets, and latest turn model/outcome.
- Provider/config CLI capability expanded with deterministic `clawlite provider use` (safe provider/model switch + fallback set/clear) and structured `rc` semantics.
- Per-message fallback observability added via queue dead-letter snapshots (`queue.dead_letter_recent`) in gateway diagnostics for safe operator inspection.

### FUTURE (Scale + polish)

#### Checklist
- [ ] Subagent orchestration controls.
- [ ] Memory/session retention and compaction.
- [ ] Multi-channel concurrency optimization.

## User Plan - "100%" Goals (Integrated execution)

### Practical mapping

- **Telegram 100% (typing, formatting, robust delivery)** - **Status: partial**
  (`P1` + `FUTURE`, parity `NEXT`)
  - 100% criterion: real-time typing indicator, consistent safe Markdown/HTML
    formatting, retries with backoff + idempotency, delivery confirmation, and
    observable per-message error fallback.

- **Core 100% (Memory, Agents, Heartbeat, Soul, Tools, User) with OpenClaw-level autonomy**
  - **Status: partial** (`P0` + `P1`, parity `NOW`/`NEXT`)
  - 100% criterion: stable 24/7 heartbeat with persisted state, short+long
    memory with per-session recovery, proactive agent loop without manual
    intervention, per-channel tool policies already applied, and end-to-end
    auditable user-session flow.

- **Providers 100% (robust API handling)** - **Status: partial** (`P1` + `P2`,
  parity `NEXT`)
  - 100% criterion: timeouts/retries/circuit-breaker per provider,
    deterministic error classification (auth, quota, rate, transient, fatal),
    configurable fallback between providers, and integration tests covering real
    failures.

- **Skills 100%** - **Status: partial** (`P2`, parity `NEXT`)
  - 100% criterion: reliable discovery, isolated execution with clear
    diagnostics, validated input/output contracts, and test coverage for
    critical skills.

- **Autonomy 100%** - **Status: partial** (`P1`, parity `NEXT`)
  - 100% criterion: continuous operation without an operator, automatic
    post-failure recovery, proactive decisions with safety limits, and minimum
    incident observability.

- **Subagents 100%** - **Status: partial** (`FUTURE`)
  - 100% criterion: subagent orchestration with task-based routing, context
    isolation, concurrency control, and consistent final synthesis in the main
    agent.

- **Future: advanced memory + no-approval mode (notification-only) + self-improvement**
  - **Status: missing** (`FUTURE`)
  - 100% criterion: semantic memory with compaction/retention, `no-approval`
    operational policy with audit trail and passive notifications, and a
    metrics-driven self-improvement cycle without breaking safety guardrails.

### Suggested execution order (short)

1. Close core `P0` and stabilize 24/7 operations (`P1`) as the autonomy
   foundation.
2. Complete Telegram + robust providers for channel and inference reliability.
3. Consolidate skills and proactive autonomy with structured observability.
4. Move into `FUTURE` with subagents, advanced memory, and `no-approval` mode
   with notification-only.

## ClawMemory (memU-inspired, ClawLite-native)

### Reference
- memU repository: https://github.com/NevaMind-AI/memU
- Progress (2026-03-04): added `memory_learn` + `memory_recall` tools and prompt memory snippets now carry `mem:<id8>` provenance with source markers.
- Progress (2026-03-04): AgentEngine now uses deterministic retrieval planner routes (`NO_RETRIEVE` / `RETRIEVE` / `NEXT_QUERY`) with fail-soft fallback.
- Progress (2026-03-04): retrieval ranking now adds bounded temporal awareness (recency/decay + temporal-intent marker boost) and planner sufficiency requires temporal relevance before accepting first-pass hits.
- Progress (2026-03-04): added guarded deterministic memory control/inspection tools `memory_forget` and `memory_analyze` (selector/query validation, bounded delete limit, compact stats + refs).
- Progress (2026-03-04): delivered `clawlite memory doctor` CLI snapshot with JSON diagnostics, schema hints, and optional safe repair path.
- Progress (2026-03-04): delivered per-session retention + append-time compaction (`agents.defaults.session_retention_messages`) with operator visibility in `clawlite status`/`clawlite diagnostics`.

### Vision and differentiation
- Build **ClawMemory** as a proactive memory engine that adapts ideas from
  `memU` for ClawLite architecture, focused on actionable decisions instead of
  passive storage.
- Prioritize memory-to-action loops: detect context gaps, propose next steps,
  trigger safe reminders, and feed agent planning with ranked evidence.
- Keep native operational fit: memory behavior must align with ClawLite
  channels, skills, subagents, and gateway contracts.

### Capability tracks (10)
- [ ] 1) Tool-integrated memory writes/reads (`tools`, channel events,
  gateway messages).
- [ ] 2) Temporal awareness (recency, cadence, deadlines, decay,
  periodic recall).
- [ ] 3) Multimodal memory artifacts (text-first now,
  image/audio metadata-ready).
- [ ] 4) Emotional and intent memory markers
  (tone, urgency, preference confidence).
- [ ] 5) Shared/distributed memory across sessions, devices,
  and cooperating agents.
- [ ] 6) Reasoning layers (facts, hypotheses, decisions,
  outcomes, confidence).
- [ ] 7) Versioning and branching (memory snapshots, rollback,
  branch merge strategy).
- [ ] 8) Privacy and control plane (scope, retention, redaction,
  user override).
- [ ] 9) Self-improvement loop (quality scoring, retrieval success metrics,
  drift checks).
- [ ] 10) Native integration with agents/skills/subagents
  (first-class APIs + policies).

### Implementation phases
- **Phase 1 - Foundation (2-3 weeks):** memory schema v1, storage adapters,
  indexing primitives, policy/retention baseline; deliver
  `clawlite memory doctor` and migration-safe state.
- **Phase 2 - Learn + Retrieve (3-4 weeks):** ingestion pipeline,
  ranking/retrieval API, context window composer, evaluation harness; deliver
  measurable top-k relevance and latency budgets.
- **Phase 3 - Proactivity (2-3 weeks):** trigger engine, reminder planner,
  safe autonomous suggestions, channel notification hooks; deliver opt-in
  proactive actions with audit trail.
- **Phase 4 - Optimization (2 weeks):** compaction, cache strategy,
  branch/version ops, quality telemetry dashboards; deliver cost/performance
  tuning and reliability hardening.

### Milestones
- [ ] **M1:** ClawMemory schema + storage contract finalized.
- [ ] **M2:** Retrieval API integrated into agent runtime and gateway flow.
- [ ] **M3:** Temporal scoring and recency/decay logic in production path.
- [ ] **M4:** Proactive trigger engine live with guardrails and audit logs.
- [ ] **M5:** Shared/distributed memory + branch/version controls released.
- [ ] **M6:** Self-improvement metrics loop closes with automated tuning
  reports.

### Top 5 differentiators (priority order)
1. Proactive memory-to-action orchestration (not passive recall only).
2. Native ClawLite integration with agents, skills, and subagents.
3. Temporal and intent-aware retrieval with operational triggers.
4. Privacy-first control plane with explicit user governance.
5. Versioned/branchable memory with measurable self-improvement.
