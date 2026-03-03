# Operations

## Start

```bash
clawlite start --host 127.0.0.1 --port 8787
```

Equivalent alias:

```bash
clawlite gateway --host 127.0.0.1 --port 8787
```

## Status and diagnostics

```bash
clawlite status
clawlite diagnostics
clawlite diagnostics --gateway-url http://127.0.0.1:8787 --token "$CLAWLITE_GATEWAY_AUTH_TOKEN"
```

## Operational validations

```bash
clawlite validate provider
clawlite validate channels
clawlite validate onboarding
```

To generate missing onboarding templates:

```bash
clawlite validate onboarding --fix
```

## Cron (CLI)

```bash
clawlite cron add --session-id cli:ops --expression "every 300" --prompt "quick status" --name "ops-check"
clawlite cron list --session-id cli:ops
clawlite cron remove --job-id <job_id>
```

Additional useful commands:

```bash
clawlite cron enable <job_id>
clawlite cron disable <job_id>
clawlite cron run <job_id>
```

## Manual heartbeat trigger via API

```bash
curl -sS -X POST http://127.0.0.1:8787/v1/control/heartbeat/trigger \
  -H "Authorization: Bearer $CLAWLITE_GATEWAY_AUTH_TOKEN"
```

## Manual autonomy trigger via API

Forced trigger (runs even if `gateway.autonomy.enabled=false`):

```bash
curl -sS -X POST http://127.0.0.1:8787/v1/control/autonomy/trigger \
  -H "Authorization: Bearer $CLAWLITE_GATEWAY_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"force": true}'
```

Guarded trigger (respects disabled/backlog/cooldown guards):

```bash
curl -sS -X POST http://127.0.0.1:8787/v1/control/autonomy/trigger \
  -H "Authorization: Bearer $CLAWLITE_GATEWAY_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"force": false}'
```

Export persisted autonomy audit trail:

```bash
curl -sS "http://127.0.0.1:8787/v1/control/autonomy/audit?limit=100" \
  -H "Authorization: Bearer $CLAWLITE_GATEWAY_AUTH_TOKEN"
```

Dry-run autonomy action simulation with decision trace:

```bash
curl -sS -X POST http://127.0.0.1:8787/v1/control/autonomy/simulate \
  -H "Authorization: Bearer $CLAWLITE_GATEWAY_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text":"{\"action\":\"validate_provider\",\"args\":{}}"}'
```

Explainability pass with deterministic risk classification/recommendations:

```bash
curl -sS -X POST http://127.0.0.1:8787/v1/control/autonomy/explain \
  -H "Authorization: Bearer $CLAWLITE_GATEWAY_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text":"{\"actions\":[{\"action\":\"validate_provider\",\"args\":{}},{\"action\":\"delete_all\",\"args\":{}}]}"}'
```

Runtime policy preset switch (`dev`/`staging`/`prod`) with auditable policy-change row:

```bash
curl -sS -X POST http://127.0.0.1:8787/v1/control/autonomy/policy \
  -H "Authorization: Bearer $CLAWLITE_GATEWAY_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"environment_profile":"prod","reason":"release hardening","actor":"ops"}'
```

## Dead-letter replay control via API

Dry-run (safe preview):

```bash
curl -sS -X POST http://127.0.0.1:8787/v1/control/dead-letter/replay \
  -H "Authorization: Bearer $CLAWLITE_GATEWAY_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"limit": 50, "channel": "telegram", "reason": "send_failed", "dry_run": true}'
```

Bounded replay:

```bash
curl -sS -X POST http://127.0.0.1:8787/v1/control/dead-letter/replay \
  -H "Authorization: Bearer $CLAWLITE_GATEWAY_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"limit": 10, "channel": "telegram", "reason": "send_failed", "session_id": "telegram:123", "dry_run": false}'
```

## Smoke tests

```bash
bash scripts/smoke_test.sh
```

## Tests

```bash
pytest -q tests
```

## Incident checklist

1. Confirm gateway: `curl -sS http://127.0.0.1:8787/health` and `clawlite diagnostics --gateway-url http://127.0.0.1:8787`.
2. Confirm minimum configuration: `clawlite validate provider` and `clawlite validate channels`.
3. If heartbeat fails, validate `gateway.heartbeat.enabled` and trigger it manually (`/v1/control/heartbeat/trigger`).
4. Before hotfix/release: `bash scripts/smoke_test.sh` and `pytest -q tests`.
5. If autonomy appears stalled, check `/v1/diagnostics` (`autonomy.running`, `ticks`, `run_attempts`, `last_error`) and use `/v1/control/autonomy/trigger` for a bounded manual turn.

## Persistence degraded mode (engine fail-soft)

- Engine responses continue even if session or memory persistence fails for a turn.
- During degraded storage, session history or consolidated memory can be partially missing until storage recovers.
- Check logs for persistence operation failures (`user_session_append`, `assistant_session_append`, `memory_consolidate`) and affected `session`.
- After recovery, monitor subsequent turns to confirm session append and memory consolidation are succeeding again.
- In `/v1/diagnostics` (`gateway.diagnostics.include_config=true`), verify `environment.engine.persistence` counters: `attempts`, `retries`, `failures`, `success`, and per-operation totals.
- For session file integrity, verify `environment.engine.session_store.read_corrupt_lines` and `read_repaired_files`; growth indicates malformed JSONL lines were detected and best-effort repaired.
- For memory history durability/recovery, verify `environment.engine.memory_store.history_read_corrupt_lines` and `history_repaired_files`; growth indicates malformed memory JSONL lines were tolerated and repaired.
- For memory consolidation behavior, verify `environment.engine.memory_store.consolidate_writes` and `consolidate_dedup_hits` to confirm checkpoint writes and per-source dedup activity.
- For per-session context recovery behavior, verify `environment.engine.session_recovery.attempts`/`hits` and `environment.engine.memory_store.session_recovery_attempts`/`session_recovery_hits`; rising attempts with low hits indicates missing recoverable context.
- Investigate sustained growth in `append_failures` or repeated retries as degraded storage signal (disk I/O, permissions, or transient filesystem instability).

## Telegram reliability runbook checks

- Check channel diagnostics/status for Telegram `signals` counters/state.
- Retry pressure: verify `send_retry_count` and `send_retry_after_count` are not continuously climbing.
- Auth breaker: verify `send_auth_breaker_open` is false during steady state; inspect `send_auth_breaker_open_count` and `send_auth_breaker_close_count` for transition history.
- Typing TTL: track `typing_ttl_stop_count` growth to confirm keepalive loops are naturally capped.
- Reconnect behavior: monitor `reconnect_count`; short bursts are expected during transient provider/network issues.

### Telegram alert thresholds

- `send_retry_count` / `send_retry_after_count`: occasional growth during provider or network turbulence is expected; investigate when both counters climb continuously for several minutes under normal traffic, or when `send_retry_after_count` dominates (rate-limit pressure).
- `send_auth_breaker_open` + open/close counters: expected state is `send_auth_breaker_open=false`; investigate immediately if it stays true after cooldown, or if `send_auth_breaker_open_count` keeps increasing without matching `send_auth_breaker_close_count` recovery.
- `typing_auth_breaker_open` + `typing_ttl_stop_count`: periodic `typing_ttl_stop_count` increments are expected (TTL cap reached); investigate if `typing_auth_breaker_open=true` persists, or if TTL stops spike with user-visible typing issues.
- `reconnect_count`: short bursts during upstream incidents are expected; investigate if reconnect bursts continue after provider/network recovery window, or if reconnect growth correlates with delayed/missed update handling.

## Scheduler reliability runbook checks

- Heartbeat (`/v1/diagnostics.heartbeat`): monitor `trigger_counts` (`startup`/`interval`/`now`) and `reason_counts`; no growth for long periods indicates a stalled loop.
- Heartbeat persistence: check `state_save_retries`, `state_save_failures`, `state_save_success`, and `state_last_error`; transient retries with ongoing success are acceptable, sustained failures are incident-level storage degradation.
- Heartbeat tick health: `consecutive_error_count` should return to `0` after recovery; sustained growth indicates recurring tick execution faults.
- Cron service (`/v1/diagnostics.cron`): monitor `save_*` and `load_*` counters plus `last_save_error`/`last_load_error`; occasional retry is transient, continuous failures indicate filesystem/permission incident.
- Cron execution health: track `job_success_count`, `job_failure_count`, and `schedule_error_count`; spikes in `schedule_error_count` usually indicate invalid schedules/timezone problems or compute regressions.
- Cron per-job health (`/v1/cron/list`): use `last_status`, `last_error`, `consecutive_failures`, and `run_count`; incident signal is repeated failures without recovery on affected jobs.

## Runtime supervisor runbook checks

- In `/v1/diagnostics.supervisor`, validate loop liveness: `running=true` and `ticks` keeps increasing.
- Monitor incident pressure: sustained growth in `incident_count` and `component_incidents` indicates recurring subsystem instability.
- Monitor recovery behavior: `recovery_attempts` should correlate with incidents; repeated growth in `recovery_failures` means failed restart paths.
- Check cooldown protection: growth in `recovery_skipped_cooldown` during incidents is expected anti-storm behavior; persistent high growth means unresolved component failures.
- Inspect `last_incident`, `cooldown_active`, `last_error`, and `consecutive_error_count` for current fault context and supervisor health.

## Runtime autonomy runbook checks

- In `/v1/diagnostics.autonomy`, validate liveness (`running=true` when enabled) and that `ticks` increases over time.
- Backpressure guard: investigate persistent growth in `skipped_backlog`; it indicates outbound/dead-letter backlog pressure.
- Cooldown guard: occasional `skipped_cooldown` growth is expected; persistent growth with low `run_attempts` means cadence/cooldown tuning is needed.
- Failure signal: monitor `run_failures`, `consecutive_error_count`, and `last_error` for repeated autonomy turn faults.
- Review `last_result_excerpt` and `last_snapshot` to confirm autonomy is reading current queue/supervisor/channel signals.

## Runtime autonomy actions runbook checks

- In `/v1/diagnostics.autonomy_actions`, verify control activity via `totals.proposed/executed/succeeded/failed/blocked`.
- Parse safety: monitor `totals.parse_errors`; sustained growth means autonomy output is not producing valid action JSON or `AUTONOMY_IDLE`.
- Quality gate: monitor `totals.quality_blocked`; sustained growth indicates low-confidence action proposals are being rejected.
- Contextual quality penalty: monitor `totals.quality_penalty_applied` and `last_run.quality` (`avg_context_penalty`, `max_context_penalty`); sustained high penalty means runtime health pressure is reducing effective confidence.
- Degraded gate: monitor `totals.degraded_blocked`; growth means runtime is degraded and only `diagnostics_snapshot` is allowed.
- Guardrails: monitor `totals.rate_limited` and `totals.cooldown_blocked` to confirm anti-storm protections are active.
- Allowlist enforcement: monitor `totals.unknown_blocked` and inspect `recent_audits` for blocked unknown/denylisted proposals.
- Confidence triage: inspect `base_confidence`, `context_penalty`, and `effective_confidence` in recent action audits to distinguish weak proposals from health-pressure suppression.
- Dead-letter action safety: `dead_letter_replay_dry_run` is always forced to `dry_run=true` and replay `limit` is clamped by `gateway.autonomy.max_replay_limit`.
- Explain-before-change workflow: use `/v1/control/autonomy/explain` (or `/v1/control/autonomy/simulate`) before relaxing guardrails; confirm `overall_risk`, `risk_counts`, and per-action recommendations match operator intent.
- Policy switch runbook: apply `/v1/control/autonomy/policy` with explicit `reason` and `actor`, then verify `autonomy_actions.environment_profile`, `totals.policy_switches`, and a `kind=policy_change` row in `/v1/control/autonomy/audit`.
- Audit durability: monitor `totals.audit_write_failures` and validate `totals.audit_writes` growth; use `/v1/control/autonomy/audit` to export persisted rows.

## Delivery observability and dead-letter runbook checks

- Queue telemetry (`/v1/diagnostics.queue`): monitor `outbound_enqueued` vs `outbound_dropped` and `dead_letter_enqueued` trends.
- Dead-letter causes: inspect `dead_letter_reason_counts`; sustained growth in one reason is the primary triage signal.
- Replay telemetry: track `dead_letter_replayed`, `dead_letter_replay_attempts`, `dead_letter_replay_skipped`, and `dead_letter_replay_dropped` after control actions.
- Channel delivery telemetry (`/v1/diagnostics.channels_delivery`): validate `total` and `per_channel` counters (`attempts`, `success`, `failures`, `dead_lettered`, `replayed`, `channel_unavailable`, `policy_dropped`).
- Replay procedure: always run `dry_run=true` first, then execute bounded replay (`limit` + optional filters), then verify post-action counters and dead-letter size.

## Tool I/O reliability checks

- In `/v1/diagnostics` with `gateway.diagnostics.include_config=true`, monitor `environment.engine.tools.total.failures`; sustained growth signals tool-layer instability.
- Track `environment.engine.tools.total.unknown_tool`; spikes usually indicate prompt/schema drift or stale tool-call plans from provider output.
- Use `environment.engine.tools.per_tool` to isolate noisy tools (`failures`, `last_error`) and validate recovery after mitigation.
- Watch logs/output for deterministic MCP errors (`mcp_error:timeout:*`, `mcp_error:http_status:*`, `mcp_error:invalid_response:*`) and confirm they do not rise continuously under normal load.

## Provider reliability checks

- In `/v1/diagnostics` with `gateway.diagnostics.include_config=true`, monitor `environment.engine.provider` counters.
- Retry pressure: investigate sustained growth in `retries`, especially when paired with `rate_limit_errors` or `server_errors`.
- Circuit health: expected steady state is `circuit_open=false`; investigate recurring growth in `circuit_open_count` without matching recovery (`circuit_close_count`).
- Fallback path (when configured) is reported under provider diagnostics with `fallback_attempts`, `fallback_success`, and `fallback_failures`.
