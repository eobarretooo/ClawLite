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

## Telegram reliability runbook checks

- Check channel diagnostics/status for Telegram `signals` counters/state.
- Retry pressure: verify `send_retry_count` and `send_retry_after_count` are not continuously climbing.
- Auth breaker: verify `send_auth_breaker_open` is false during steady state; inspect `send_auth_breaker_open_count` and `send_auth_breaker_close_count` for transition history.
- Typing TTL: track `typing_ttl_stop_count` growth to confirm keepalive loops are naturally capped.
- Reconnect behavior: monitor `reconnect_count`; short bursts are expected during transient provider/network issues.
