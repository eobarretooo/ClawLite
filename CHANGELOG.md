# Changelog

All notable changes to ClawLite are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
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
- Operators can now reject pending Telegram pairing codes from the control plane via `POST /v1/control/channels/telegram/pairing/reject` and the dashboard.
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

### Fixed
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

[Unreleased]: https://github.com/eobarretooo/ClawLite/compare/v0.5.0-beta.2...HEAD
[v0.5.0-beta.2]: https://github.com/eobarretooo/ClawLite/compare/v0.5.0-beta.1...v0.5.0-beta.2
[v0.5.0-beta.1]: https://github.com/eobarretooo/ClawLite/compare/v0.4.1...v0.5.0-beta.1
[v0.4.1]: https://github.com/eobarretooo/ClawLite/compare/v0.4.0...v0.4.1
[v0.4.0]: https://github.com/eobarretooo/ClawLite/releases/tag/v0.4.0
