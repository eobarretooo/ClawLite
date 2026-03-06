# Changelog

Relevant ClawLite changes.

## [Unreleased]

### Changed
- Markdown documentation cleanup to reflect only the current runtime.
- Updated README, CONTRIBUTING, SECURITY, and ROADMAP for current commands/flows.
- Updated documentation to remove stale legacy pages.
- Stage 18 memory-quality tuning increment documented: layer-specific playbook execution fields (`template_id`, `backfill_limit`, `snapshot_tag`, `action_variant`) and diagnostics telemetry maps (`actions_by_layer`, `actions_by_playbook`, `actions_by_action`, `action_status_by_layer`, `last_action_metadata`).
- Stage 19 release-closure docs finalized across roadmap/readme/api/operations with conservative completion status for reasoning layers, self-improvement loop, native integration, and milestone M6.
- ClawMemory hardening shipped: hybrid semantic+BM25 retrieval, async memorize/retrieve APIs, proactive monitor integrated with heartbeat/diagnostics, multimodal ingest fallback, memory profile/privacy/versioning controls, branch/checkout/merge lifecycle, and optional backend embedding sync (`sqlite` default, `pgvector` optional).
- Operational maturity increment: `clawlite provider set-auth` / `clawlite provider clear-auth` and `clawlite heartbeat trigger` integrated into operator runbooks.
- Diagnostics now expose WebSocket telemetry visibility for runtime operator checks.
- Release preflight workflow added with `clawlite validate preflight` and `scripts/release_preflight.sh` automation.

### Removed
- Legacy internal analysis/context files that are not part of public documentation.

### Fixed
- `.gitignore` adjusted to ignore only session artifacts at repository root, allowing workspace templates to be versioned.
- Memory search adjusted to prioritize lexical overlap and avoid unstable BM25 ranking on small corpora.

## [0.5.0-beta.2] - 2026-03-02

### Changed
- Consolidated modular runtime refactor (`core/tools/bus/channels/gateway/scheduler/providers/session/config/workspace/skills/cli`).
- Broad documentation cleanup to reflect only current CLI/API and flows.
- README redesigned with product positioning and explicit roadmap.

### Added
- Real execution of `SKILL.md` skills via `command/script` in runtime (`run_skill`).
- Versioning of workspace templates (`IDENTITY`, `SOUL`, `USER`, `memory/MEMORY`).

### Fixed
- Fixed memory retrieval for queries with negative BM25 score.
