# Changelog

Relevant ClawLite changes.

## [Unreleased]

### Changed
- Markdown documentation cleanup to reflect only the current runtime.
- Updated README, CONTRIBUTING, SECURITY, and ROADMAP for current commands/flows.
- Updated documentation to remove stale legacy pages.

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
