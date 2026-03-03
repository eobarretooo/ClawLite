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

## Persistence degraded mode (engine fail-soft)

- Engine responses continue even if session or memory persistence fails for a turn.
- During degraded storage, session history or consolidated memory can be partially missing until storage recovers.
- Check logs for persistence operation failures (`user_session_append`, `assistant_session_append`, `memory_consolidate`) and affected `session`.
- After recovery, monitor subsequent turns to confirm session append and memory consolidation are succeeding again.
- In `/v1/diagnostics` (`gateway.diagnostics.include_config=true`), verify `environment.engine.persistence` counters: `attempts`, `retries`, `failures`, `success`, and per-operation totals.
- For session file integrity, verify `environment.engine.session_store.read_corrupt_lines` and `read_repaired_files`; growth indicates malformed JSONL lines were detected and best-effort repaired.
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
