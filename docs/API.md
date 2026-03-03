# API (Gateway)

Default base URL: `http://127.0.0.1:8787`

## Auth (summary)

- `gateway.auth.mode=off`: no authentication.
- `gateway.auth.mode=optional`: accepts requests without token, but invalid token returns `401`.
- `gateway.auth.mode=required`: requires token (except loopback when `allow_loopback_without_auth=true`).
- Token can be sent via configurable header (default `Authorization`, with or without `Bearer ` prefix) or configurable query param (default `token`).
- `/health` only requires auth when `gateway.auth.protect_health=true` and mode is `required`.
- `/v1/diagnostics` depends on `gateway.diagnostics.enabled` and may require auth with `gateway.diagnostics.require_auth=true`.

## `GET /health`

Example response:

```json
{
  "ok": true,
  "ready": true,
  "phase": "running",
  "channels": {},
  "queue": {
    "inbound_size": 0,
    "outbound_size": 0,
    "outbound_dropped": 0,
    "dead_letter_size": 0,
    "topics": 0,
    "stop_sessions": 0
  }
}
```

## `GET /v1/status`

Example response:

```json
{
  "ready": true,
  "phase": "running",
  "components": {
    "channels": {"enabled": true, "running": true, "last_error": ""},
    "cron": {"enabled": true, "running": true, "last_error": ""},
    "heartbeat": {"enabled": true, "running": true, "last_error": ""},
    "supervisor": {"enabled": true, "running": true, "last_error": ""},
    "engine": {"enabled": true, "running": true, "last_error": ""}
  },
  "auth": {
    "posture": "open",
    "mode": "off",
    "allow_loopback_without_auth": true,
    "protect_health": false,
    "token_configured": false,
    "header_name": "Authorization",
    "query_param": "token"
  }
}
```

Channel diagnostics returned via health/diagnostics use additive maps and may include per-channel `signals` entries.

Scheduler diagnostics/status payloads are additive and include reliability telemetry:
- `heartbeat` may include trigger/reason counters, state-save counters, `consecutive_error_count`, and `state_last_error`.
- `cron` may include load/save durability counters plus service-level execution/schedule counters; cron jobs include per-job health fields (`last_status`, `last_error`, `consecutive_failures`, `run_count`).

## `GET /v1/diagnostics`

If `gateway.diagnostics.enabled=false`, returns `404` with `{"error":"diagnostics_disabled","status":404}`.

`channels` entries are additive and may include channel-specific `signals` maps for operational counters/state.

When `gateway.diagnostics.include_config=true`, `environment` may include additive engine persistence telemetry, nested session-store durability/recovery diagnostics, tool execution telemetry under `environment.engine.tools` (`total` + `per_tool` counters), and provider telemetry under `environment.engine.provider`.

Provider telemetry keys are additive and may include: `requests`, `successes`, `retries`, `timeouts`, `network_errors`, `http_errors`, `auth_errors`, `rate_limit_errors`, `server_errors`, `circuit_open`, `circuit_open_count`, `circuit_close_count`, `consecutive_failures`, `last_error`, `last_status_code`.

Supervisor telemetry is additive under `supervisor` and may include: `ticks`, `incident_count`, `recovery_attempts`, `recovery_success`, `recovery_failures`, `recovery_skipped_cooldown`, `component_incidents`, `last_incident`, `last_recovery_at`, `last_error`, `consecutive_error_count`, and `cooldown_active`.

Example response:

```json
{
  "schema_version": "2026-03-02",
  "control_plane": {"ready": true, "phase": "running", "components": {}, "auth": {}},
  "queue": {
    "inbound_size": 0,
    "outbound_size": 0,
    "outbound_dropped": 0,
    "dead_letter_size": 0,
    "topics": 0,
    "stop_sessions": 0
  },
  "channels": {},
  "cron": {},
  "heartbeat": {},
  "supervisor": {},
  "environment": {}
}
```

## `POST /v1/control/heartbeat/trigger`

No body.

Example response:

```json
{
  "ok": true,
  "decision": {
    "action": "skip",
    "reason": "nothing_to_do",
    "text": "HEARTBEAT_OK"
  }
}
```

If heartbeat is disabled (`gateway.heartbeat.enabled=false`), returns `409` with `{"error":"heartbeat_disabled","status":409}`.

## `POST /v1/chat`

Request:

```json
{
  "session_id": "telegram:123",
  "text": "remind me to drink water"
}
```

Response:

```json
{
  "text": "...",
  "model": "gemini/gemini-2.5-flash"
}
```

## `POST /v1/cron/add`

Request:

```json
{
  "session_id": "telegram:123",
  "expression": "every 120",
  "prompt": "remind me to stretch",
  "name": "stretch"
}
```

Response:

```json
{
  "ok": true,
  "status": "created",
  "id": "job_xxx"
}
```

## `GET /v1/cron/list?session_id=...`

Example response:

```json
{
  "jobs": []
}
```

## `DELETE /v1/cron/{job_id}`

Example response:

```json
{
  "ok": true,
  "status": "removed"
}
```

## `WS /v1/ws`

WebSocket for chat.

Input message:

```json
{"session_id":"cli:ws","text":"hello"}
```

Output message:

```json
{"text":"...","model":"gemini/gemini-2.5-flash"}
```
