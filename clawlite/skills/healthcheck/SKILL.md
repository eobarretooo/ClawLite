---
name: healthcheck
description: Host hardening and ClawLite runtime health checklist with safe, approval-first operations.
metadata: {"clawlite":{"emoji":"🛡️"}}
---

# Healthcheck

Use this skill when the user asks for machine hardening, runtime health, readiness checks, or operational review.

## Baseline checks (read-only)

- `clawlite status`
- `clawlite validate config`
- `clawlite validate provider`
- `clawlite validate channels`
- `clawlite validate preflight --gateway-url http://127.0.0.1:8787`
- Gateway probes: `GET /v1/status` and `GET /v1/diagnostics`

Prefer these checks before proposing any changes.

## Host hardening guardrails

- Confirm how the user connects (local, SSH, VPN, remote desktop) before touching access controls.
- Require explicit approval before any state-changing action.
- Use staged, reversible changes with rollback notes.
- Never claim ClawLite changes OS firewall/SSH/update policy automatically; those are host-level tasks.

## Cron safety

`clawlite cron list/add/remove/enable/disable/run` can schedule operational checks.

Only use cron commands after explicit user approval.

## Output format

Return:

1. Current posture (what is healthy / what is risky)
2. Exact remediation plan (step-by-step)
3. Verification plan (`status`, `validate`, and endpoint re-checks)
