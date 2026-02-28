# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project follows Semantic Versioning.

## [Unreleased]

### Added
- Repository hygiene files aligned with OpenClaw-style project maintenance.
- Onboarding flow updated with explicit Workspace, Daemon and Health check steps.
- Review + Apply stage in onboarding before persisting advanced configuration.
- New onboarding docs structure: overview + CLI wizard reference for ClawLite.
- Imported missing OpenClaw skill catalogs into `skills/` with ClawLite adaptation notes.
- OpenClaw compatibility aliases in runtime skill registry (delegated and guided fallbacks).

### Changed
- README onboarding documentation to reflect QuickStart vs Advanced flow.
- Project docs rewritten to position ClawLite as a personal assistant (OpenClaw-inspired, adapted).

### Fixed
- Installer now always generates a gateway token when config has empty token value.

## [0.4.1] - 2026-02-27

### Added
- Stable CLI flow for onboarding/configure/start.
- Multi-channel + skills + MCP baseline for Linux/Termux.
