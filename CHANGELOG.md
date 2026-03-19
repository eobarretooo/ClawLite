# Changelog

All notable changes to ClawLite are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- official Docker foundation with `Dockerfile`, `docker-compose.yml`, `docs/DOCKER.md`, and host-mounted `~/.clawlite` runtime state
- persisted Discord focus bindings with `/focus` / `/unfocus`, routed through the inbound interceptor before the agent loop

### Changed
- refreshed README/docs status snapshot to point at the new Docker path and the active parity track
- Discord policy/routing parity slice now includes DM/guild policy controls, guild/channel/role allowlists, bot gating, explicit session keys, configurable `reply_to_mode`, isolated slash sessions, deferred interaction replies, and persisted thread/channel bindings with idle/max-age expiry
- Discord operator flows now include native `/discord-status` and `/discord-refresh` commands handled before the agent loop

### Fixed
- `AgentEngine` now marks synthesized subagent digests with the async-safe subagent API inside the live event loop, so completed digest runs no longer leak back into later turns
- engine regressions that inspect exact tool/tool-call history now use hermetic in-memory session state instead of machine-local persisted rows
- cron scheduler regression coverage now waits on an explicit callback event instead of a fixed sleep, removing a suite-load race in `test_cron_service_add_and_run`
- `exec` and `process` now treat explicit shell wrappers such as `sh -lc`, `bash -lc`, and `cmd /c` as nested shell executions for workspace guarding, so `$HOME` / `~` style path expansion can no longer bypass `restrict_to_workspace`
- `exec` and `process` now block obvious `curl` / `wget` / PowerShell `http(s)` fetches to localhost, private ranges, and metadata-style targets, closing a network-policy bypass that sat outside `web_fetch`
- `web_fetch` and `web_search` now mark successful payloads as untrusted external content and include a safety notice so fetched pages/snippets are treated as data rather than instructions
- prompt guidance now treats browser page reads and browser evaluations as untrusted external data, while `browser.navigate` keeps the explicit external-content notice and `browser.evaluate` preserves its raw return contract
- inbound channel turns now inject a compact allowlisted subset of runtime metadata into the untrusted prompt context, so reply/thread/command/media hints reach the model without exposing raw webhook payloads

## [v0.7.0-beta.0] - 2026-03-17

### Phase 7 — Advanced memory and self-improvement (`main`, 2026-03-17)
- `self_evolution` now uses provider-direct proposal instead of the full agent/tool loop
- unsafe proposals are rejected before apply via file/path/header/diff-size policy
- successful runs now commit only inside isolated git worktree branches, leaving the live checkout untouched
- operator notices are routed through the real autonomy notice path and surfaced in diagnostics with `last_branch`
- added end-to-end smoke coverage for isolated self-evolution runs plus CI/smoke-script wiring
- `self_evolution` now supports dry-run review, configurable branch prefixes, approval-required mode, and Telegram/Discord approval callbacks that persist review state

### Plan Milestone — `plano.md` completion (2026-03-17)
- Added file-based config profiles (`config.<profile>.yaml|json`) with CLI `--profile` support and documented merge precedence
- Completed engine loop recovery with a single meta-prompt retry before fail-closed abort
- Finished incremental streaming UX for Discord, Telegram progress integration, and websocket streaming alignment
- Added session TTL, history compaction, `sqlite-vec`, `memory_compact`, and working-memory rate limiting
- Added Redis-backed message bus, opt-in runtime telemetry/OTLP hooks, and subsystem startup timeouts
- Completed WhatsApp, Slack, and IRC operational channel paths
- Added Gemini/Qwen OAuth helpers and completed custom-provider expansion path
- Kept `self_evolution` disabled by default while adding approval-ready notices and isolated branch workflows

### Robustness Milestone — Phases 1–5 (2026-03-15)

#### Phase 5 — Runtime recovery and operational autonomy (`e8ddaf1`)
- Fix critical bug: `JobQueue.start()` was never called — jobs submitted via `jobs` tool now execute
- `JobQueue.worker_status()`: live health snapshot (workers_alive, pending_jobs, running_jobs)
- `job_workers` lifecycle component: started in gateway startup sequence alongside other subsystems
- `_run_job_dispatch`: worker function supporting `agent_run` and `skill_exec` job kinds
- `RuntimeSupervisor` now monitors `job_workers`: detects dead worker pool and auto-restarts
- `SupervisorComponentPolicy` for `job_workers` (max_recoveries=8 per hour)
- `autonomy_stuck` supervisor detection: non-recoverable incident emitted when
  `consecutive_error_count >= 5` or `no_progress_streak >= 3` in the autonomy service
- 8 new tests: worker_status lifecycle, supervisor incident/recovery, job execution after late start

#### Phase 4 — Core engine hardening + background jobs (`d91a585`)
- `ContextWindowManager` — trims message history to model token budget; preserves system message and last user turn; `budget_chars` or `budget_tokens` constructor
- `TurnBudget.max_tool_calls` + `token_budget` fields — per-turn hard caps enforced in engine loop
- Engine loop-detection now emits `InboundEvent(channel="_system", text="loop_detected")` on the message bus for all three detectors (provider-plan, tool-repeat, ping-pong)
- `JobQueue` — priority async job queue with submit/status/cancel/list, concurrency control, and retry; fixed worker loop to drain pre-start submissions
- `JobJournal` — SQLite persistence for jobs (restart recovery via `restore_from_journal()`)
- `JobsTool` — agent-facing tool for submit/status/cancel/list background jobs
- `JobsConfig` — `AppConfig.jobs` sub-schema (`persist_enabled`, `persist_path`, `worker_concurrency`)
- Gateway: `JobsTool` registered, `JobQueue` wired with optional journal, `engine._bus` set for loop observability
- CLI: `clawlite jobs list|status|cancel` commands
- `SubagentManager.spawn(parent_session_id=...)` — child session prefixed `"{parent}:sub:{run_id[:8]}"`, stored in `run.metadata`

#### Phase 3 — Provider telemetry + tool resilience (`8455a59`)
- `TelemetryRegistry` + `ProviderTelemetry`: ring buffer 1000 calls/model, p50/p95 latency
- `ProviderChunk.degraded`: mid-stream recovery without exception propagation
- `LiteLLMProvider.warmup()`: connectivity probe before serving traffic
- `ToolError` + `ToolTimeoutError`: structured tool exceptions
- `ToolHealthResult` + `health_check()`: ExecTool, BrowserTool, MCPTool, PdfReadTool
- `ToolResultCache`: LRU 256 entries, 5min TTL; web_fetch + pdf_read cacheable
- `ToolRegistry` centralised timeout middleware
- `GET /metrics/providers`, `/health/providers`, `/health/tools`

#### Phase 2 — Memory hierarchy + proactive loader (`bf671ab`)
- `ResourceContext` dataclass + `resources`/`record_resources` SQLite tables
- `MemoryRecord` extended with `resource_id` + `consolidated` fields
- `ProactiveContextLoader`: background topic extraction + threaded recall with 30s cache TTL
- `LLMConsolidator`: LLM-driven consolidation with deterministic fallback
- `MemoryStore.ingest_file()`: .txt / .md / .pdf
- Memory TTL: `set_record_ttl` / `get_record_ttl` / `purge_expired_records` + `memory_ttl` table

#### Phase 1 — Config hot-reload + bus journal (`8dd97a9`)
- `ConfigWatcher`: watchfiles-based hot-reload with 500ms debounce and error-resilient reload
- `config_health()` + `GET /health/config`
- `ConfigAudit` ring buffer (last 5 configs)
- `BusConfig` in `AppConfig` (`journal_enabled`, `journal_path`)
- `BusJournal`: SQLite append/ack journal; survives restart; replay unacked messages
- `subscribe("*")` wildcard + `BusFullError` on `nowait=True` overflow
- `InboundEvent` / `OutboundEvent` typed envelopes with `envelope_version` + `correlation_id`

### Added
- Config schema fully migrated to Pydantic v2 (`clawlite/config/schema.py`) — all fields modelled with `Field`, validators, `model_validate`, and camelCase alias support (`1c60256`).
- `Base.from_dict()` classmethod on all Pydantic config models as a v1→v2 compatibility shim (`d3f8ee4`).
- `BrowserTool` (Playwright headless), `TTSTool` (edge-tts), and `PdfReadTool` (pypdf) registered in the gateway tool surface.
- Skills: `notion`, `obsidian`, `github-issues`, `spotify`, `docker`, `1password`, `apple-notes`, `trello`, `linear`, `jira` — full portfolio of 25+ integrated skills.
- `skill_creator.py` — runtime skill authoring from inside an agent session.
- Workspace templates: `AGENTS.md`, `IDENTITY.md`, `SOUL.md`, `HEARTBEAT.md`, `USER.md` — loaded and auto-repaired by `Workspace.Loader`.
- `scripts/make_demo_gif.py` — Playwright + Pillow animated README demo generator (`2c925f0`).
- Packaged dashboard shell served from `/` with status, diagnostics, sessions, automation views, tool catalog, token handling, live chat, event feed, autorefresh, and heartbeat controls over the existing gateway contract.
- Project status, autonomy execution plan, operator runbook, and release workflow docs for the current hardening cycle.
- OpenClaw-compatible filesystem and memory tool aliases to reduce migration friction (`663a8f0`).
- Native `apply_patch` and process-control tools for safer in-agent file edits and runtime operations (`a858966`).
- Session orchestration and background subagent tools in the runtime tool surface (`5e9d829`).
- Gateway tools catalog capability exposure for dashboard/runtime introspection (`6cd00df`).
- Additional OpenClaw operational skills ported into ClawLite (`461180d`, `f6be3f4`).

### Changed
- Refreshed the root README with a richer quickstart, examples, capability matrix, and clearer explanation of the current autonomy-hardening phase.
- Onboarding now emits a tokenized dashboard link, and the dashboard can bootstrap auth from the URL fragment before stripping it from the address bar; when bootstrap is pending it also exposes a one-click hatch action for the first defining turn.
- Added a dedicated `clawlite dashboard` command so operators can reopen or print the current dashboard handoff without rerunning onboarding, including backup/web-search/security guidance and bootstrap-state hints; the packaged dashboard now renders those next-step notes too.
- Fixed `clawlite start` and `clawlite gateway` so `--config` now flows into the runtime instead of silently falling back to the default config file.
- Bootstrap completion is now gated behind the dedicated hatch session, and `clawlite hatch` provides a terminal-first way to run that first defining turn safely.
- Failover diagnostics now keep auth/quota suppression reasons visible and apply longer cooldown windows so broken or exhausted providers are not hammered repeatedly.
- The dashboard automation view now surfaces provider suppression/cooldown candidates as operator cards instead of only raw JSON.
- The dashboard automation view now also surfaces delivery queues, dead-letter pressure, channel recovery loops, and supervisor recovery budgets as operator cards.
- Operators can now trigger live dead-letter replay from the control plane via `POST /v1/control/channels/replay` and the dashboard automation view.
- Operators can now trigger live channel recovery from the control plane via `POST /v1/control/channels/recover` and the dashboard automation view.
- Operators can now trigger live inbound journal replay from the control plane via `POST /v1/control/channels/inbound-replay` and the dashboard automation view.
- Operators can now inspect Telegram offset/pairing/webhook state in the dashboard and trigger a live Telegram transport refresh via `POST /v1/control/channels/telegram/refresh`.
- Operators can now approve pending Telegram pairing codes from the control plane via `POST /v1/control/channels/telegram/pairing/approve` and the dashboard.
- Operators can now deliberately advance the Telegram offset watermark from the control plane via `POST /v1/control/channels/telegram/offset/commit`.
- Operators can now synchronize Telegram `next_offset` from the control plane via `POST /v1/control/channels/telegram/offset/sync` and the CLI.
- Operators can now reset Telegram `next_offset` to zero from the control plane via `POST /v1/control/channels/telegram/offset/reset` and the CLI with explicit confirmation.
- Operators can now reject pending Telegram pairing codes from the control plane via `POST /v1/control/channels/telegram/pairing/reject` and the dashboard.
- Operators can now revoke approved Telegram pairing entries from the control plane via `POST /v1/control/channels/telegram/pairing/revoke` and the dashboard.
- Operators can now trigger runtime supervisor recovery directly from the control plane via `POST /v1/control/supervisor/recover` and the dashboard.
- Telegram runtime operator controls are now accessible from the CLI via `clawlite telegram status|refresh|offset-commit`.
- Telegram operator status now includes actionable hints for webhook, offset, pairing, and transport recovery.
- Operators can now clear provider suppression/cooldown directly from the control plane via `POST /v1/control/provider/recover`, the dashboard, and the CLI.
- Supervisor recovery is now also accessible from the CLI via `clawlite supervisor recover`.
- Manual autonomy wakes are now accessible from the control plane via `POST /v1/control/autonomy/wake`, the dashboard, and the CLI.
- Memory suggestions can now be refreshed and memory snapshots can be created directly from the control plane/dashboard.
- Memory snapshots can now also be rolled back directly from the control plane/dashboard with explicit confirmation.
- Discord gateway transport can now be inspected in the dashboard and refreshed from the control plane via `POST /v1/control/channels/discord/refresh`.
- Discord transport status/refresh are now also accessible from the CLI via `clawlite discord status|refresh`.
- `clawlite configure --flow quickstart|advanced` works again as a compatibility shortcut to the onboarding wizard.
- Heartbeat prompts now inject a cron-style current-time line from the workspace user timezone and skip model calls when `HEARTBEAT.md` exists but is effectively empty.
- Gateway root entrypoint now serves a richer operator dashboard backed by packaged HTML/CSS/JS assets instead of a single inline landing page, with a more operational UI/UX direction for control-plane work.
- Added dashboard state endpoints (`/v1/dashboard/state`, `/api/dashboard/state`) so the packaged UI can render recent sessions, cron state, channels, provider recovery, and self-evolution summaries without scraping raw diagnostics.
- Expanded dashboard-state payloads so the UI can render workspace runtime health, bootstrap cycle state, skills inventory summary, and memory monitor telemetry.
- Added workspace onboarding-state tracking inspired by `ref/openclaw`, so bootstrap seeding/completion survives across syncs and the dashboard can report onboarding progress more accurately.
- Synced README, docs index, and roadmap with the real repository state, validation commands, and milestone workflow.
- Enforced ClawLite identity in prompts and emitted outputs to avoid assistant-name drift (`6d5c99a`).
- Added layered tool policy resolution, then tightened tool-policy handling across memory-forget and run-skill paths (`e1a0033`, `1203c64`, `f6592b2`).
- Hardened long-running reliability for provider retries, channel dispatch/reuse, gateway background tasks, cron execution, and memory compaction/monitor persistence (`da50a2a`, `017844f`, `aefaade`, `2e891b1`, `60773a5`).
- Improved worker/session control with fail-closed spawn policy, bounded process sessions/output buffers, and lock-safe subagent cancel/synthesize (`a122d8e`, `5df5d81`, `33f28ca`).

### Changed
- Rewrote `docs/CONFIGURATION.md` as a full field reference for every config key (`503a335`).
- Cleaned `config.example.json` to essential fields only — minimal viable starter (`fbf6196`).
- Updated `README.md` with Configuration section, starter examples, and Telegram snippet (`ec6fb61`).
- Updated `docs/STATUS.md` to reflect actual completed state (2026-03-15).

### Fixed
- `TelegramChannelConfig.from_dict()` (and all channel/tool config models) broken after Pydantic v2 migration — added `Base.from_dict()` classmethod shim (`d3f8ee4`). Restored 127 tests that were failing.
- Reduced SSRF risk in web tooling with DNS-drift protections and explicit peer-IP verification (`67b52e3`, `d7e0e11`).
- Switched gateway secret comparisons to constant-time checks (`62bdf45`).
- Made key persistence paths atomic/durable (config writes, `apply_patch` writes, cron state fsync-before-replace) (`58d2136`, `4f05059`, `9075e8c`).
- Added timeout guards to gateway engine runs, session runners, and cron callbacks to prevent stuck loops (`64e5b02`, `a122d8e`, `2e891b1`).
- Restored provider tool schema/Codex tool-call compatibility and hardened MCP transport retries (`4077792`, `75e154e`).

### Removed
- No explicit removals in this release window.

### Technical/Agentic Session
- [SESSION ID: CLAWLITE-UNRELEASED-HARDENING] - Focus: post-beta hardening for safety, reliability, and runtime control.
- **Objective:** consolidate high-risk fixes and OpenClaw-compatibility tooling while preserving ClawLite behavior under sustained operation.

### Technical Changes
- Added identity enforcement, OpenClaw-compatible aliases, `apply_patch`/process tools, and session/subagent orchestration tools.
- Introduced layered tool-policy resolution and gateway tools catalog exposure.
- Hardened provider/channel/gateway/cron/memory paths with bounded buffers, retries, timeouts, async offloading, and lock-safe cancellation.
- Applied security controls across web-fetch SSRF checks, constant-time gateway auth compare, and atomic/durable file writes.

### Design Decisions
- Prioritized defense-in-depth and fail-closed defaults on runtime-critical paths.
- Scoped changes to commit-backed hardening milestones instead of introducing new feature domains.

### Verification Status
- Verified through iterative runtime smoke paths, gateway execution-timeout checks, cron stability checks, and regression fixes shipped as focused patches.

## [v0.5.0-beta.2] - 2026-03-02

### Added
- New modular subsystem implementations for engine, dynamic tools, event bus, channels, scheduler, providers, session store, config loader, workspace templates, gateway, and CLI command interface (`c729d9b`, `1de0a80`, `153eedc`, `c9dd253`, `1dd1e7e`, `e4e6d24`, `c7f0d33`, `ac5537e`, `0593ea9`, `3afa9d5`, `6dba831`).
- Unified runtime orchestration contracts (`AgentLoop`, `AgentRequest`/`AgentResponse`) to route gateway, channels, cron, and heartbeat through one pipeline (`6b1655a`, `81faede`, `f95446b`).
- Nanobot-style skill runtime with package-local discovery, markdown skills, and execution bindings (`3cd4cc2`, `385a51e`, `d181388`).

### Changed
- Rewrote ClawLite into a modular architecture and standardized cross-module integration for command flow, gateway operations, session persistence, and agent execution.
- Modernized onboarding/start/run command surfaces and workspace rendering to fit the new module layout (`6dba831`, `b0f23d5`, `0593ea9`).

### Fixed
- Added targeted compatibility fixes during migration, including Codex 429 retry handling, bootstrap first-install gating, and termux/proot startup stabilization (`752f781`, `cbf1747`, `6edba39`, `c048842`, `8c1c80a`).
- Reduced decomposition regressions by normalizing shared helper usage and keeping runtime request interfaces consistent (`e0bc442`, `f95446b`).

### Removed
- Removed legacy architecture stack and obsolete skill/docs bundles that conflicted with the rewritten modular core (`e3aa896`, `6138228`).

### Technical/Agentic Session
- [SESSION ID: CLAWLITE-V050B2-MODULAR-REWRITE] - Focus: full modular architecture migration with legacy retirement.
- **Objective:** transition ClawLite from a tightly coupled runtime to explicit subsystem boundaries without breaking core operator workflows.

### Technical Changes
- Split runtime responsibilities into dedicated modules across core execution, tools, bus, channels, scheduling, providers, session/config/workspace, gateway, and CLI.
- Unified orchestration through shared request/response contracts and AgentLoop-based routing.
- Replaced legacy bundles with package-local skill discovery and updated docs/runtime conventions.

### Design Decisions
- Established module boundaries before feature parity expansion to limit regression blast radius.
- Removed legacy paths once equivalent modular paths were live to avoid dual-stack drift.

### Verification Status
- Completed via staged integration checks across gateway chat/ws/health flows, channel/cron routing, and CLI startup/onboarding smoke runs.

## [v0.5.0-beta.1] - 2026-03-01

### Added
- OpenClaw-style dashboard control panels and expanded gateway parity endpoints for sessions/talk/models/update flows (`cb250b3`, `a97e615`).
- Channel parity expansion with Google Chat, IRC, Signal, and iMessage adapters, including config/webhook support (`245f5a0`).
- Outbound delivery reliability surface with telemetry, resilient send flow, policy checks, and recovery test/runbook coverage (`b01d3a6`, `189409b`, `9cb4fd0`, `3d6e103`).
- Installation and update iteration milestones: self-update channels, dependency auto-repair, proot wrappers/scripts, and codex-cli auth reuse (`fc73848`, `2b8e17a`, `690d21b`, `5426056`, `a68d030`, `0f94f7e`).
- Onboarding wizard improvements with quickstart/advanced guidance, live provider key checks, and live Telegram checks (`f1750a1`, `4ae2433`, `096d3f7`).

### Changed
- Expanded dashboard coverage to full control panels and aligned docs with shipped API/ws capabilities (`cb250b3`, `b29edc4`).
- Iterated onboarding/install/termux experience with safer defaults and clearer diagnostics across Linux/Termux paths (`74b7946`, `9700c75`, `4825090`).
- Strengthened outbound governance using circuit-breaker/outage policy controls and operational runbook checklists (`9cb4fd0`, `3d6e103`).

### Fixed
- Hardened webhook validation/auth/sanitization/rate-limit behavior across newly added channels (`1f65c58`).
- Patched dashboard observability signal gaps by mirroring outbound failures into dashboard logs (`a6e3fc7`).
- Fixed auth/offline/install/channel edge cases encountered during parity expansion (termux oauth handling, offline provider fallback, Slack listener/token validation, stale update cache) (`b422411`, `6c49ef7`, `25c7fb7`, `917596d`, `4825090`).

### Removed
- No explicit removals in this release.

## [v0.4.1] - 2026-02-27

### Added
- Learning stack milestones: task tracker + preference learning, continuous learning pipeline integration, dashboard learning stats API, and `clawlite stats` command (`30ff8eb`, `c079de6`, `7814c6c`, `2e6c8d2`).
- Voice interaction pipeline for Telegram/WhatsApp with STT/TTS support (`7e83c46`).
- Persistent session-memory architecture with semantic search/compaction and automatic session-summary save on exit (`62ca376`, `09d8bc7`).

### Changed
- Improved operator control surfaces with OpenClaw-style interactive configure flow plus richer `status` and `doctor` commands (`b040a2a`, `c2c0cdf`).
- Updated quickstart/docs to reflect guided setup and voice-enabled onboarding path (`f410dbf`, `6cf79fc`).

### Fixed
- Fixed configure behavior in non-TTY smoke runs and replaced deprecated locale calls to maintain runtime compatibility (`c0e7754`, `686ecbf`).
- Added CLI alias correction for gateway startup command parity (`769fc0a`).

### Removed
- No explicit removals in this release.

## [v0.4.0] - 2026-02-27

### Added
- Initial ClawLite foundation: core CLI/runtime/memory/tools/installer and first gateway server onboarding flow (`dc11699`, `9493f87`).
- Large skills-catalog baseline, including registry/listing and broad skill imports/registrations (coding-agent, GitHub, Gmail, calendar, browser/web, docker/ssh/supabase/aws, media/voice, and more) (`afbba4f` plus skill commits through `c737dcc`).
- Dashboard API and WebSocket baseline for chat/log streams, telemetry, and local persistence (`d194739`), followed by real-chat and advanced telemetry integration (`9814967`).
- Supporting runtime milestones: persistent SQLite workers/local routing, secure skill marketplace workflow, interactive provider auth/configure flows, and workspace bootstrap templates (`4457546`, `c3eb5f8`, `5e15d81`, `e9c8f53`, `561bfde`).

### Changed
- Established project conventions for workspace/operator flows and documentation baseline during first public milestone.
- Iterated dashboard and configuration UX while preserving compatibility with the initial CLI-gateway-dashboard loop (`f0d020f`, `fd901c5`).

### Fixed
- Fixed early bring-up issues in skills and CLI/auth error handling during first end-to-end stabilization (`9f3a81d`, `7aaaaab`).
- Added integration coverage for CLI+gateway+dashboard scenarios to catch foundational regressions (`5c9c065`).

### Removed
- No explicit removals in this release.

### Technical/Agentic Session
- [SESSION ID: CLAWLITE-V040-FOUNDATION] - Focus: bootstrap the first complete ClawLite runtime baseline.
- **Objective:** deliver a functional initial release spanning CLI, gateway, onboarding/configuration, skills catalog, dashboard APIs/ws, and docs.

### Technical Changes
- Implemented foundational runtime surfaces (CLI/runtime/memory/tools/installer) and initial gateway onboarding flow.
- Shipped broad skills catalog and registry support to make the runtime useful from day one.
- Added dashboard API/WebSocket streams plus follow-up telemetry/chat integration for an operable control surface.

### Design Decisions
- Prioritized end-to-end operability and feature breadth over deep subsystem optimization in the first milestone.
- Established API/ws-backed dashboard early to keep operations visible while other subsystems matured.

### Verification Status
- Validated through foundational smoke runs and integration tests spanning CLI, gateway, and dashboard pathways.

[Unreleased]: https://github.com/eobarretooo/ClawLite/compare/v0.7.0-beta.0...HEAD
[v0.7.0-beta.0]: https://github.com/eobarretooo/ClawLite/compare/v0.6.0-beta.0...v0.7.0-beta.0
[v0.5.0-beta.2]: https://github.com/eobarretooo/ClawLite/compare/v0.5.0-beta.1...v0.5.0-beta.2
[v0.5.0-beta.1]: https://github.com/eobarretooo/ClawLite/compare/v0.4.1...v0.5.0-beta.1
[v0.4.1]: https://github.com/eobarretooo/ClawLite/compare/v0.4.0...v0.4.1
[v0.4.0]: https://github.com/eobarretooo/ClawLite/releases/tag/v0.4.0
