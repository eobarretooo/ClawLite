# Configuration

Default file: `~/.clawlite/config.json`

Main fields (summary):
- `workspace_path`, `state_path`
- `provider` and `providers` (active model, credentials/base per provider)
- `provider` reliability controls: retry (`retry_*`), circuit breaker (`circuit_*`), optional `fallback_model`
- `agents.defaults` (model, limits, temperature)
- `gateway.host`, `gateway.port`
- `gateway.auth` (API auth control)
- `gateway.diagnostics` (exposure and protection of `/v1/diagnostics`)
- `gateway.heartbeat` (enable/disable and interval for gateway heartbeat)
- `gateway.supervisor` (runtime health checks + bounded auto-recovery loop)
- `scheduler.timezone` (timezone for cron)
- `channels` (telegram/discord/slack/whatsapp + extras)

## Environment variables

- `CLAWLITE_MODEL`
- `CLAWLITE_WORKSPACE`
- `CLAWLITE_LITELLM_BASE_URL`
- `CLAWLITE_LITELLM_API_KEY`
- `CLAWLITE_GATEWAY_HOST`
- `CLAWLITE_GATEWAY_PORT`
- `CLAWLITE_GATEWAY_AUTH_MODE` (`off|optional|required`)
- `CLAWLITE_GATEWAY_AUTH_TOKEN`
- `CLAWLITE_GATEWAY_AUTH_ALLOW_LOOPBACK` (`true/false`)
- `CLAWLITE_GATEWAY_DIAGNOSTICS_ENABLED` (`true/false`)
- `CLAWLITE_GATEWAY_DIAGNOSTICS_REQUIRE_AUTH` (`true/false`)

Note: provider-specific key variables (`OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `GEMINI_API_KEY`, etc.) are still valid for provider credential resolution.

## Current gateway schema

`gateway` no longer uses `gateway.token` as the main field. The current format is:

```json
{
  "gateway": {
    "host": "127.0.0.1",
    "port": 8787,
    "auth": {
      "mode": "off",
      "token": "",
      "allow_loopback_without_auth": true,
      "header_name": "Authorization",
      "query_param": "token",
      "protect_health": false
    },
    "diagnostics": {
      "enabled": true,
      "require_auth": true,
      "include_config": false
    },
    "heartbeat": {
      "enabled": true,
      "interval_s": 1800
    },
    "supervisor": {
      "enabled": true,
      "interval_s": 20,
      "cooldown_s": 30
    }
  }
}
```

Compatibility: if legacy `gateway.token` exists, the loader migrates it to `gateway.auth.token` and sets `gateway.auth.mode=required` when needed.

## Heartbeat (compatibility note)

- Current preference: `gateway.heartbeat.interval_s`.
- Legacy field: `scheduler.heartbeat_interval_seconds`.
- If `gateway.heartbeat.interval_s` is not explicitly set, the loader uses the legacy value from `scheduler`.

## Runtime supervisor

- `gateway.supervisor.enabled` enables the 24/7 health supervisor loop.
- `gateway.supervisor.interval_s` controls supervisor tick cadence.
- `gateway.supervisor.cooldown_s` applies per-component cooldown before another recovery attempt.
- Snake case and camelCase are accepted (`interval_s` / `intervalS`, `cooldown_s` / `cooldownS`).

## Automatic provider resolution

- `provider.model` defines the preferred provider (`gemini/...`, `openrouter/...`, `openai/...`, `groq/...`).
- If the key is not in `provider.litellm_api_key`, the runtime tries provider-specific environment variables.
- `provider.litellm_base_url` is optional for common providers: runtime applies provider default base URL.
- Provider reliability fields are additive and backward-compatible:
  - `retry_max_attempts`, `retry_initial_backoff_s`, `retry_max_backoff_s`, `retry_jitter_s`
  - `circuit_failure_threshold`, `circuit_cooldown_s`
  - `fallback_model` (optional second model path for retryable provider failures)

## Telegram (main options)

In `channels.telegram`, besides `enabled` and `token`, the most used operational fields are:
- `mode` (`polling` is the active runtime path today; webhook fields are kept for compatibility/future integration)
- `webhook_enabled`, `webhook_secret`, `webhook_path`
- `poll_interval_s`, `poll_timeout_s`
- `reconnect_initial_s`, `reconnect_max_s`
- `send_timeout_s`, `send_retry_attempts`
- `send_backoff_base_s`, `send_backoff_max_s`, `send_backoff_jitter`
- `send_circuit_failure_threshold`, `send_circuit_cooldown_s`
- `typing_enabled` (enable Telegram typing keepalive during processing)
- `typing_interval_s` (cadence between typing refresh calls)
- `typing_max_ttl_s` (max total typing keepalive duration per inbound)
- `typing_timeout_s` (HTTP timeout for typing API calls)
- `typing_circuit_failure_threshold` (consecutive typing auth failures before opening typing circuit)
- `typing_circuit_cooldown_s` (cooldown while typing auth circuit is open)

## Example

See: [config.example.json](./config.example.json)
