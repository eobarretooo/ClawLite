# ClawLite Roadmap

## P0 — Core stability

- Consolidate a single agent execution flow (CLI + channels + gateway)
- Expand scheduler integration test coverage (cron/heartbeat)
- Harden input validation in channels and tools with external I/O
- Telegram reliability hardening in progress: deterministic soak/recovery tests now cover repeated polling reconnects and outbound transient retry cycles; continue runtime tuning for near-100% stability.

## P1 — Operational autonomy

- Achieve 24/7 Linux operation with supervision and automatic recovery
- Improve proactive delivery through channels with minimum observability
- Strengthen long-term memory and per-session context recovery

## P2 — Ecosystem

- Improve user skills experience (discovery, execution, diagnostics)
- Evolve MCP integration and specialized providers
- Publish more objective operations and release guides for personal deployment

## Minimum release criteria

1. `pytest -q` passing
2. Main CLI without regression (`start`, `run`, `onboard`, `cron`, `skills`)
3. Main API working (`/health`, `/v1/chat`, `/v1/cron/*`)
4. Documentation aligned with real behavior
