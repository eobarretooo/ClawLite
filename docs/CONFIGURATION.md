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
- `gateway.autonomy` (opt-in periodic autonomy review worker)
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
- `CLAWLITE_GATEWAY_DIAGNOSTICS_INCLUDE_PROVIDER_TELEMETRY` (`true/false`)

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
      "include_config": false,
      "include_provider_telemetry": true
    },
    "heartbeat": {
      "enabled": true,
      "interval_s": 1800
    },
    "supervisor": {
      "enabled": true,
      "interval_s": 20,
      "cooldown_s": 30
    },
    "autonomy": {
      "enabled": false,
      "interval_s": 900,
      "cooldown_s": 300,
      "timeout_s": 45.0,
      "max_queue_backlog": 200,
      "session_id": "autonomy:system",
      "max_actions_per_run": 1,
      "action_policy": "balanced",
      "environment_profile": "dev",
      "action_cooldown_s": 120.0,
      "action_rate_limit_per_hour": 20,
      "max_replay_limit": 50,
      "min_action_confidence": 0.55,
      "degraded_backlog_threshold": 300,
      "degraded_supervisor_error_threshold": 3,
      "audit_export_path": "",
      "audit_max_entries": 200
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

## Runtime autonomy bootstrap

- `gateway.autonomy.enabled` is opt-in and defaults to `false` to avoid unexpected model usage/cost.
- `gateway.autonomy.interval_s` controls periodic autonomy ticks.
- `gateway.autonomy.cooldown_s` enforces minimum spacing between non-forced runs.
- `gateway.autonomy.timeout_s` bounds each autonomy turn with timeout containment.
- `gateway.autonomy.max_queue_backlog` skips non-forced ticks when `outbound_size + dead_letter_size` is high.
- `gateway.autonomy.session_id` defines the engine session used for autonomy turns.
- `gateway.autonomy.max_actions_per_run` bounds autonomous action execution per run (default `1`).
- `gateway.autonomy.action_policy` supports `balanced` (default) and `conservative` profiles.
- `gateway.autonomy.environment_profile` supports `dev` (default), `staging`, and `prod` policy layering.
- `gateway.autonomy.action_cooldown_s` enforces per-action cooldown (default `120s`).
- `gateway.autonomy.action_rate_limit_per_hour` enforces per-action hourly cap (default `20`).
- `gateway.autonomy.max_replay_limit` clamps `dead_letter_replay_dry_run.limit` (default `50`).
- `gateway.autonomy.min_action_confidence` blocks low-confidence action proposals before execution.
- `gateway.autonomy.degraded_backlog_threshold` and `gateway.autonomy.degraded_supervisor_error_threshold` define degraded-runtime guardrails.
- `gateway.autonomy.audit_export_path` sets JSONL persistence path for autonomy action audit rows. Empty uses runtime default (`<state_path>/autonomy-actions-audit.jsonl`).
- `gateway.autonomy.audit_max_entries` bounds in-memory/export batch size for recent audit reads.
- Environment profile behavior applies only to omitted guardrail fields (explicit values always win): `dev` keeps current defaults, `staging` applies moderate tightening, and `prod` applies strict defaults aligned with conservative behavior.
- Action policy fallback: if `action_policy` is omitted and `environment_profile=prod`, policy defaults to `conservative`; otherwise it defaults to `balanced`.
- Conservative policy behavior remains additive: omitted guardrail fields auto-tighten to `action_cooldown_s=300`, `action_rate_limit_per_hour=8`, `min_action_confidence=0.75`, `degraded_backlog_threshold=150`, and `degraded_supervisor_error_threshold=1`.
- Snake case and camelCase are accepted (`interval_s`/`intervalS`, `cooldown_s`/`cooldownS`, `timeout_s`/`timeoutS`, `max_queue_backlog`/`maxQueueBacklog`, `session_id`/`sessionId`, `max_actions_per_run`/`maxActionsPerRun`, `action_policy`/`actionPolicy`, `environment_profile`/`environmentProfile`, `action_cooldown_s`/`actionCooldownS`, `action_rate_limit_per_hour`/`actionRateLimitPerHour`, `max_replay_limit`/`maxReplayLimit`, `min_action_confidence`/`minActionConfidence`, `degraded_backlog_threshold`/`degradedBacklogThreshold`, `degraded_supervisor_error_threshold`/`degradedSupervisorErrorThreshold`, `audit_export_path`/`auditExportPath`, `audit_max_entries`/`auditMaxEntries`).

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
