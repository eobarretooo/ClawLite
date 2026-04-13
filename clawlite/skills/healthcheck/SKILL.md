---
name: healthcheck
description: "Run ClawLite runtime health checks, validate configuration and provider connectivity, and guide host hardening with safe, approval-first operations. Use when the user asks for system status, readiness verification, operational review, or machine hardening guidance."
metadata: {"clawlite":{"emoji":"🛡️"}}
script: healthcheck
---

# Healthcheck

Run diagnostic checks on ClawLite runtime health, configuration validity, provider connectivity, and host security posture.

## Workflow

1. **Baseline diagnostics**: Run read-only checks to assess current state (see commands below).
2. **Analyze results**: Identify what is healthy, what is degraded, and what is at risk.
3. **Recommend fixes**: Present a step-by-step remediation plan for any issues found.
4. **Get approval**: Require explicit user confirmation before any state-changing action.
5. **Apply fixes**: Execute approved changes in staged, reversible steps with rollback notes.
6. **Verify**: Re-run baseline checks to confirm fixes resolved the issues.

## Baseline Checks (Read-Only)

Run these before proposing any changes:

| Command | Purpose |
|---------|---------|
| `clawlite status` | Overall runtime state |
| `clawlite validate config` | Configuration file validity |
| `clawlite validate provider` | Provider connectivity and auth |
| `clawlite validate channels` | Channel adapter health |
| `clawlite validate preflight --gateway-url http://127.0.0.1:8787` | Full pre-flight readiness |
| `GET /v1/status` | Gateway liveness probe |
| `GET /v1/diagnostics` | Detailed runtime diagnostics |

## Host Hardening Guardrails

- Confirm how the user connects (local, SSH, VPN, remote desktop) before touching access controls.
- Use staged, reversible changes with rollback notes for every modification.
- Never claim ClawLite changes OS firewall, SSH, or update policy automatically — those are host-level tasks requiring explicit user action.

## Cron Safety

Schedule recurring health checks with `clawlite cron add/list/remove/enable/disable/run`. Only use cron commands after explicit user approval.

## Example

User: "Is my ClawLite instance healthy?"

1. Run `clawlite status` and `clawlite validate config`.
2. Run `clawlite validate provider` and `clawlite validate channels`.
3. Hit `GET /v1/diagnostics` for runtime telemetry.
4. Report: "Config valid. Provider: connected. Channels: Telegram healthy, Email degraded (IMAP timeout). Recommendation: check IMAP credentials and network access."

## Output Format

1. **Current posture**: What is healthy and what is at risk.
2. **Remediation plan**: Exact step-by-step commands and actions.
3. **Verification plan**: Which `status`, `validate`, and endpoint checks to re-run after fixes.
