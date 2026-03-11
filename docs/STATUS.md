# ClawLite Status

Last updated: 2026-03-10

## Summary

ClawLite is already a functional local-first agent runtime with:

- FastAPI gateway with HTTP + WebSocket control surfaces
- structured diagnostics and compatibility aliases
- persistent memory, cron, heartbeat, and subagent primitives
- channel manager plus Telegram and other outbound integrations
- provider auth lifecycle, preflight validation, and release-preflight helpers

The main engineering goal for the current cycle is not a rewrite.
It is to turn the existing runtime into a durable 24/7 operator-grade system with strong recovery, better control-plane UX, and parity with the most useful OpenClaw behaviors.

## Current Baseline

- Latest tag in the repository: `v0.5.0-beta.2`
- `main` already contains unreleased hardening work beyond that tag
- CI currently covers:
  - pytest on Python 3.10 and 3.12
  - Ruff critical lint checks
  - smoke imports
  - autonomy contract tests

## Strengths Already Present

- Gateway compatibility endpoints: `/`, `/api/status`, `/api/message`, `/api/token`, `WS /ws`
- Structured diagnostics for runtime, HTTP, provider, channels, memory, and subagents
- Supervised background loops for autonomy, channel delivery, channel recovery, subagent maintenance, and self evolution
- Workspace templates plus bootstrap/heartbeat lifecycle foundations
- Provider auth/status/validation flows and release-preflight command surface
- Durable config writes and heartbeat state persistence patterns

## Main Gaps To Close

1. Rich dashboard/control-plane UI parity with `ref/openclaw`
2. Onboarding parity for quickstart, advanced flow, live probes, and final operator handoff
3. Heartbeat parity for wake-aware scheduling, dedupe, and target-aware delivery
4. Broader provider coverage plus multi-hop failover and local runtime autodiscovery
5. Telegram/channel durability: pairing, offset safety, media ingest, replay after restart
6. Runtime recovery durability: persisted outbound/dead-letter state and component health registry
7. Skill lifecycle, hot reload, and dependency fallbacks
8. Subagent lifecycle, orchestration, and context-isolation hardening
9. Advanced memory and self-improvement pipelines after the platform is stable

## Phase Progress

- Phase 0 - docs and release hygiene: delivered in this cycle
- Active milestone: Phase 1 - dashboard and control-plane parity

Scope:

- port the richer dashboard/control-plane shell from OpenClaw into ClawLite
- preserve compatibility endpoints while improving operator UX and observability
- keep the gateway contract stable while replacing the simple root page with a real dashboard

Recent progress:

- the first dashboard slice is now served from packaged assets at `/`
- the shell already exposes token-aware status, diagnostics, tools, chat controls, heartbeat trigger, autorefresh, and a live operator event feed using the existing gateway endpoints
- the dashboard now also renders recent sessions and automation summaries from dedicated dashboard-state endpoints
- the dashboard now also exposes workspace, bootstrap, skills, and memory health views from the same aggregated control-plane payloads
- workspace onboarding state is now tracked explicitly so bootstrap seeding/completion survives template sync and shows up in the knowledge view
- the dashboard now renders shared post-onboarding guidance cards, including dashboard/token/backup/security notes and the dedicated hatch session when bootstrap is pending
- bootstrap completion is now intentionally tied to the dedicated hatch session instead of any arbitrary first user chat turn
- provider failover now keeps stronger auth/quota suppression windows and exposes those reasons in diagnostics so autonomy can back off more intelligently
- the dashboard automation view now turns provider suppression/cooldown telemetry into operator-friendly recovery cards
- the dashboard automation view now also surfaces delivery queues, dead-letter pressure, channel recovery, and supervisor recovery budgets as operator cards
- operators can now trigger live dead-letter replay from the dashboard using the existing channel manager instead of relying only on startup replay
- operators can now also trigger live channel recovery from the dashboard/control plane instead of waiting only for the background recovery supervisor
- operators can now requeue persisted inbound journal items from the control plane instead of waiting only for startup inbound replay
- Telegram transport state now has dedicated dashboard/operator visibility plus a live refresh action for webhook/offset health
- Telegram pairing approval can now be completed from the control plane/dashboard instead of only through the CLI
- Telegram offset watermark can now be advanced deliberately from the control plane when a safe manual recovery step is needed
- Telegram `next_offset` can now be synchronized directly from the control plane as a safer reconciliation path than raw watermark forcing
- Telegram `next_offset` can now also be reset explicitly from the control plane with confirmation when a full transport reset is required
- Pending Telegram pairing requests can now also be rejected directly from the control plane/dashboard
- Approved Telegram pairing entries can now be revoked directly from the control plane/dashboard
- Operators can now trigger supervisor component recovery directly from the control plane/dashboard instead of only waiting for the background supervisor loop
- Telegram status now includes operator-facing hints for webhook, offset, pairing, and transport problems
- Provider suppression/cooldown can now be cleared directly from the control plane/dashboard/CLI after the root cause is fixed

Exit criteria:

- dashboard assets are served by ClawLite
- browser reconnect/control-plane behavior is stable
- gateway compatibility endpoints remain intact

## Validation Baseline

Use these commands as the minimum local operator checks:

```bash
python -m clawlite.cli --help
python -m pytest tests/ -q --tb=short
clawlite validate config
clawlite validate preflight --gateway-url http://127.0.0.1:8787
bash scripts/smoke_test.sh
```

## Delivery Policy

- commit and push every green slice
- update docs in the same cycle as behavior changes
- reserve tags and GitHub releases for the end of a validated milestone
- keep `CHANGELOG.md` current as work lands on `main`

## Reference Repositories

- Behavioral parity reference: `/root/projetos/ref/openclaw`
- Autonomy/reliability reference: `/root/projetos/ref/nanobot`
- Memory inspiration reference: `/root/projetos/memU`

## Next Step

The next implementation target is Phase 1: port the richer dashboard/control-plane surfaces from OpenClaw into ClawLite without breaking the current gateway contract.
