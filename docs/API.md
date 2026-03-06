# API (Gateway)

Default base URL: `http://127.0.0.1:8787`

## Auth (summary)

- `gateway.auth.mode=off`: no authentication.
- `gateway.auth.mode=optional`: accepts requests without token, but invalid token returns `401`.
- `gateway.auth.mode=required`: requires token (except loopback when `allow_loopback_without_auth=true`).
- Token can be sent via configurable header (default `Authorization`, with or without `Bearer ` prefix) or configurable query param (default `token`).
- `/health` only requires auth when `gateway.auth.protect_health=true` and mode is `required`.
- `/v1/diagnostics` depends on `gateway.diagnostics.enabled` and may require auth with `gateway.diagnostics.require_auth=true`.

## `GET /`

Entrypoint leve do gateway (HTML estático e determinístico) com visão rápida dos endpoints disponíveis.

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
    "autonomy": {"enabled": false, "running": false, "last_error": "disabled"},
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

Queue diagnostics are additive and may include delivery/dead-letter observability fields: `inbound_published`, `outbound_enqueued`, `outbound_dropped`, `dead_letter_enqueued`, `dead_letter_replayed`, `dead_letter_replay_attempts`, `dead_letter_replay_skipped`, `dead_letter_replay_dropped`, `dead_letter_reason_counts`, bounded per-message dead-letter snapshots in `dead_letter_recent`, and best-effort oldest-age gauges (`outbound_oldest_age_s`, `dead_letter_oldest_age_s`).

Scheduler diagnostics/status payloads are additive and include reliability telemetry:
- `heartbeat` may include trigger/reason counters, state-save counters, `consecutive_error_count`, and `state_last_error`.
- `cron` may include load/save durability counters plus service-level execution/schedule counters; cron jobs include per-job health fields (`last_status`, `last_error`, `consecutive_failures`, `run_count`).

## `GET /v1/diagnostics`

If `gateway.diagnostics.enabled=false`, returns `404` with `{"error":"diagnostics_disabled","status":404}`.

`channels` entries are additive and may include channel-specific `signals` maps for operational counters/state.

`channels_delivery` is additive and includes manager-level delivery counters with this shape:

- `total`: aggregate counters (`attempts`, `success`, `failures`, `dead_lettered`, `replayed`, `channel_unavailable`, `policy_dropped`, `delivery_confirmed`, `delivery_failed_final`, `idempotency_suppressed`)
- `per_channel`: same counter schema keyed by channel name
- `recent`: bounded per-message outcomes (newest first), including safe delivery metadata such as `outcome`, `idempotency_key`, `dead_letter_reason`, `last_error`, `send_result`, `receipt`, and replay marker

`memory_monitor` is additive and reports proactive memory monitor telemetry:

- `enabled`: monitor activation status (`agents.defaults.memory.proactive` + runtime wiring)
- counters: `scans`, `generated`, `deduped`, `low_priority_skipped`, `cooldown_skipped`, `sent`, `failed`
- queue/state: `pending`, `cooldown_seconds`, `suggestions_path`

Purpose: operational visibility for proactive memory suggestions (generation, suppression, and delivery outcomes) without exposing raw memory content.

Memory quality tuning diagnostics (stages 15-18) are additive and may appear in:

- top-level `engine.memory_quality`: persisted quality/tuning state summary
- top-level `memory_quality_tuning`: runtime tuning loop snapshot/counters

`environment` telemetry remains separate from the memory quality payload and is gated by `gateway.diagnostics.include_config=true`.

Expected additive keys include quality layer scores and stage18 tuning telemetry/action metadata:

- reasoning layers: `fact`, `hypothesis`, `decision`, `outcome` (quality scoring context)
- telemetry maps: `actions_by_layer`, `actions_by_playbook`, `actions_by_action`, `action_status_by_layer`
- latest action metadata: `last_action_metadata` (for example `template_id`, `backfill_limit`, `snapshot_tag`, `action_variant`, plus playbook context such as `playbook_id`, `weakest_layer`, `severity`)

When `gateway.diagnostics.include_config=true`, `environment` may include additive engine persistence telemetry, session-recovery telemetry under `environment.engine.session_recovery`, memory-store durability/recovery telemetry under `environment.engine.memory_store`, nested session-store durability/recovery diagnostics, tool execution telemetry under `environment.engine.tools` (`total` + `per_tool` counters), and provider telemetry under `environment.engine.provider`.

Provider telemetry keys are additive and may include: `requests`, `successes`, `retries`, `timeouts`, `network_errors`, `http_errors`, `auth_errors`, `rate_limit_errors`, `server_errors`, `circuit_open`, `circuit_open_count`, `circuit_close_count`, `consecutive_failures`, `last_error`, `last_status_code`.

Supervisor telemetry is additive under `supervisor` and may include: `ticks`, `incident_count`, `recovery_attempts`, `recovery_success`, `recovery_failures`, `recovery_skipped_cooldown`, `component_incidents`, `last_incident`, `last_recovery_at`, `last_error`, `consecutive_error_count`, and `cooldown_active`.

Autonomy telemetry is additive under `autonomy` and may include: `running`, `enabled`, `session_id`, `ticks`, `run_attempts`, `run_success`, `run_failures`, `skipped_backlog`, `skipped_cooldown`, `skipped_disabled`, `last_run_at`, `last_result_excerpt`, `last_error`, `consecutive_error_count`, `last_snapshot`, and `cooldown_remaining_s`.

Autonomy action execution telemetry is additive under top-level `autonomy_actions` and may include: policy/profile settings (`policy`, `environment_profile`, `min_action_confidence`, degraded thresholds, audit path/limits), `totals` (`proposed`, `executed`, `succeeded`, `failed`, `blocked`, `simulated_runs`, `simulated_actions`, `explain_runs`, `policy_switches`, `parse_errors`, `rate_limited`, `cooldown_blocked`, `unknown_blocked`, `quality_blocked`, `quality_penalty_applied`, `degraded_blocked`, `audit_writes`, `audit_write_failures`), `per_action`, `last_run`, and bounded `recent_audits`.

`autonomy_actions.last_run.quality` is additive and may include confidence quality summary fields (`count`, `avg_base_confidence`, `avg_context_penalty`, `avg_effective_confidence`, `max_base_confidence`, `max_context_penalty`, `max_effective_confidence`).

Action audit rows in `autonomy_actions.last_run.audits`/`autonomy_actions.recent_audits` may include confidence fields (`base_confidence`, `context_penalty`, `effective_confidence`) plus decision trace fields (`gate`, `trace`).

Example response:

```json
{
  "schema_version": "2026-03-02",
  "control_plane": {"ready": true, "phase": "running", "components": {}, "auth": {}},
  "queue": {
    "inbound_size": 0,
    "inbound_published": 0,
    "outbound_size": 0,
    "outbound_enqueued": 0,
    "outbound_dropped": 0,
    "dead_letter_size": 0,
    "dead_letter_enqueued": 0,
    "dead_letter_replayed": 0,
    "dead_letter_replay_attempts": 0,
    "dead_letter_replay_skipped": 0,
    "dead_letter_replay_dropped": 0,
    "dead_letter_reason_counts": {},
    "dead_letter_recent": [],
    "topics": 0,
    "stop_sessions": 0
  },
  "channels": {},
  "channels_delivery": {
    "total": {},
    "per_channel": {},
    "recent": []
  },
  "cron": {},
  "heartbeat": {},
  "supervisor": {},
  "autonomy": {},
  "autonomy_actions": {},
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

When proactive memory is enabled, the same trigger path may also scan and deliver memory suggestions (including next-step follow-up suggestions) through channel delivery. This side effect is fail-soft and does not change heartbeat decision semantics.

## `POST /v1/control/autonomy/trigger`

Request body is optional:

```json
{
  "force": true
}
```

## `POST /v1/control/autonomy/simulate`

Control-plane dry-run endpoint for autonomy action policy simulation against a runtime snapshot.

Request:

```json
{
  "text": "{\"actions\":[{\"action\":\"validate_provider\",\"args\":{}}]}",
  "runtime_snapshot": {
    "queue": {"outbound_size": 0, "dead_letter_size": 0},
    "supervisor": {"incident_count": 0, "consecutive_error_count": 0}
  }
}
```

- `runtime_snapshot` is optional. When omitted, the gateway uses the current internal runtime snapshot.
- Simulation is side-effect-free for action execution (no executor calls, no cooldown/rate mutation) and increments only simulation counters.

Response:

```json
{
  "ok": true,
  "simulation": {
    "parse_error": false,
    "proposed": 2,
    "allowed": 1,
    "blocked": 1,
    "degraded": false,
    "degraded_reason": "",
    "policy": "balanced",
    "environment_profile": "dev",
    "min_action_confidence": 0.55,
    "actions": [
      {
        "index": 0,
        "action": "validate_provider",
        "args": {},
        "decision": "allow",
        "gate": "all_gates_passed",
        "reason": "allowed",
        "base_confidence": 0.75,
        "context_penalty": 0.0,
        "effective_confidence": 0.75,
        "degraded": false,
        "degraded_reason": "",
        "executor_available": true,
        "trace": [
          {"gate": "max_actions_per_run", "result": "pass"},
          {"gate": "allowlist", "result": "pass"}
        ]
      }
    ]
  },
  "autonomy_actions": {
    "totals": {
      "simulated_runs": 1,
      "simulated_actions": 2
    }
  }
}
```

## `POST /v1/control/autonomy/explain`

Control-plane explainability endpoint using the same parser/gate path as autonomy simulation/execution, without executing actions.

Request:

```json
{
  "text": "{\"actions\":[{\"action\":\"validate_provider\",\"confidence\":0.9,\"args\":{}},{\"action\":\"delete_all\",\"args\":{}}]}",
  "runtime_snapshot": {
    "queue": {"outbound_size": 0, "dead_letter_size": 0},
    "supervisor": {"incident_count": 0, "consecutive_error_count": 0}
  }
}
```

Response:

```json
{
  "ok": true,
  "explanation": {
    "parse_error": false,
    "proposed": 2,
    "allowed": 1,
    "blocked": 1,
    "overall_risk": "high",
    "risk_counts": {"low": 1, "medium": 0, "high": 1},
    "policy": "balanced",
    "environment_profile": "dev",
    "min_action_confidence": 0.55,
    "degraded": false,
    "degraded_reason": "",
    "actions": [
      {
        "action": "validate_provider",
        "decision": "allow",
        "gate": "all_gates_passed",
        "effective_confidence": 0.75,
        "risk_level": "low",
        "recommendation": "Action is within policy and confidence guardrails."
      }
    ]
  },
  "autonomy_actions": {
    "totals": {
      "explain_runs": 1
    }
  }
}
```

## `POST /v1/control/autonomy/policy`

Control-plane endpoint for runtime policy preset switching (`dev`, `staging`, `prod`) with auditable policy-change records.

Request:

```json
{
  "environment_profile": "prod",
  "reason": "release hardening",
  "actor": "control"
}
```

Response:

```json
{
  "ok": true,
  "update": {
    "at": "2026-03-03T00:00:00+00:00",
    "actor": "control",
    "reason": "release hardening",
    "previous": {
      "environment_profile": "dev",
      "policy": "balanced"
    },
    "new": {
      "environment_profile": "prod",
      "policy": "conservative",
      "action_cooldown_s": 300.0,
      "action_rate_limit_per_hour": 8,
      "min_action_confidence": 0.75,
      "degraded_backlog_threshold": 150,
      "degraded_supervisor_error_threshold": 1
    }
  },
  "autonomy_actions": {
    "totals": {
      "policy_switches": 1
    }
  }
}
```

- Invalid `environment_profile` returns `400` with `{"error":"invalid_environment_profile","status":400}`.

## `GET /v1/control/autonomy/audit?limit=100`

Control-plane endpoint to export persisted autonomy action audit rows (JSONL-backed, fail-soft).

Example response:

```json
{
  "ok": true,
  "path": "/home/user/.clawlite/state/autonomy-actions-audit.jsonl",
  "count": 2,
  "entries": [
    {
      "kind": "action",
      "action": "validate_provider",
      "status": "succeeded"
    },
    {
      "kind": "run",
      "proposed": 1,
      "executed": 1
    }
  ]
}
```

- Default is `force=true` for explicit operator-triggered runs.
- With `force=false`, disabled state, queue backlog guard, and cooldown guard may skip execution.
- Returns a non-crashing status summary even when autonomy is disabled.

Example response:

```json
{
  "ok": true,
  "forced": true,
  "autonomy": {
    "enabled": false,
    "run_attempts": 1,
    "run_success": 1,
    "run_failures": 0
  },
  "autonomy_actions": {
    "totals": {
      "proposed": 1,
      "executed": 1,
      "succeeded": 1
    }
  }
}
```

## `POST /v1/control/dead-letter/replay`

Control-plane endpoint for bounded dead-letter replay.

Request body (all fields optional):

```json
{
  "limit": 100,
  "channel": "telegram",
  "reason": "send_failed",
  "session_id": "telegram:123",
  "dry_run": false
}
```

Behavior:

- Replays only dead-letter entries matching provided filters.
- Replay is bounded by `limit`.
- `dry_run=true` performs matching/scan without enqueuing outbound events.
- Returns additive summary for auditability (`scanned`, `matched`, `replayed`, `kept`, `dropped`, `replayed_by_channel`).

## `POST /v1/chat`

Request:

```json
{
  "session_id": "telegram:123",
  "text": "remind me to drink water"
}
```

Alias compatível: `POST /api/message` (mesma request/response e mesma política de autenticação).

Nota operacional: o tool `message` suporta acoes Telegram (`send`, `reply`, `edit`, `delete`, `react`, `create_topic`) via argumentos de `action` e bridge de metadata (`_telegram_action*`), preservando o fluxo normal de envio e inline keyboard.

## `GET /v1/status`

Estado do control-plane do gateway.

Campos de contrato estavel:
- `contract_version`: versao do contrato HTTP do gateway.
- `server_time`: timestamp UTC ISO-8601 gerado no servidor.

Alias compatível: `GET /api/status` (mesmo payload e mesma política de autenticação).

## `GET /v1/diagnostics`

Snapshot operacional do gateway para debug e operacao.

Campos baseline de contrato:
- `generated_at`: timestamp UTC ISO-8601 da geracao do snapshot.
- `uptime_s`: uptime do processo do gateway em segundos.
- `contract_version`: versao estavel do contrato HTTP do gateway.
- `channels_delivery`: contadores de entrega agregados do `ChannelManager` (`total` e `per_channel`).
- `memory_monitor`: telemetria do monitor proativo de memoria (`enabled`, contadores de scan/geracao/entrega, pendencias, cooldown e path do backlog).
- `channels_delivery.recent`: snapshots por mensagem (mais recentes primeiro) com outcome e recibo seguro por envio, sem texto da mensagem.
  Inclui contadores aditivos de confirmacao/falha final e supressao de duplicatas (`delivery_confirmed`, `delivery_failed_final`, `idempotency_suppressed`).
- `http`: telemetria HTTP em memoria (aditiva) com `total_requests`,
  `in_flight`, `by_method`, `by_path`, `by_status` e `latency_ms`
  (`count`, `min`, `max`, `avg`).

Alias compatível: `GET /api/diagnostics` (mesmo payload e mesma política de autenticação).

## `GET /api/token`

Diagnóstico de autenticação do gateway.
- Nunca retorna token em texto puro.
- Retorna apenas estado (`token_configured`) e versão mascarada determinística (`token_masked`).
- Segue a mesma política de autenticação dos endpoints de control-plane.

## `POST <telegram webhook path>`

- Telegram webhook endpoint is dynamic and comes from `channels.telegram.webhook_path` (default: `/api/webhooks/telegram`).
- Enabled only when Telegram channel is enabled and running in active webhook mode.
- Validates `X-Telegram-Bot-Api-Secret-Token` against channel secret when configured.
- Accepts JSON object payload up to 1 MB and returns `{ "ok": true, "processed": <bool> }`.
- Applies a 5s body-read timeout and returns `408` with code `telegram_webhook_payload_timeout` on slow/incomplete payload reads.

Response:

```json
{
  "ok": true,
  "processed": true
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

Alias compatível: `WS /ws` (mesmo comportamento, incluindo autenticação).

## Envelope de erro HTTP

Para erros HTTP, o gateway retorna envelope estavel com:
- `error`
- `status`
- `code` (quando `error` for string, `code` repete esse valor)
