# API (Gateway)

Default base URL: `http://127.0.0.1:8787`

## Auth (summary)

- `gateway.auth.mode=off`: no authentication.
- `gateway.auth.mode=optional`: accepts requests without token, but invalid token returns `401`.
- `gateway.auth.mode=required`: requires token (except loopback when `allow_loopback_without_auth=true`).
- Token can be sent via configurable header (default `Authorization`, with or without `Bearer ` prefix) or configurable query param (default `token`).
- If a gateway token is configured, the control-plane routes (`/v1/status`, `/v1/dashboard/state`, `/v1/chat`, control mutations, approvals/grants, and `WS /v1/ws`) require that token even when the gateway is otherwise open on loopback.
- The packaged dashboard now prefers a short-lived `#handoff=` bootstrap credential instead of putting the raw gateway token in the browser URL. `POST /api/dashboard/session` still accepts the raw gateway token for legacy/manual flows, but the packaged shell exchanges the handoff first and then uses the derived dashboard-session credential only on dashboard-scoped aliases such as `/api/status`, `/api/dashboard/state`, `/api/diagnostics`, `/api/token`, `/api/message`, `/api/tools/catalog`, `/v1/control/*`, and `WS /ws`. That derived credential is bound to a per-tab dashboard client id, so dashboard-scoped requests must present both values. The short-lived handoff itself is consumed on the first successful exchange in the running gateway process, which blocks replay of the same bootstrap credential. Generic `/v1/*` routes and `WS /v1/ws` still require the raw gateway token.
- `/health` only requires auth when `gateway.auth.protect_health=true` and mode is `required`.
- `/v1/diagnostics` depends on `gateway.diagnostics.enabled` and may require auth with `gateway.diagnostics.require_auth=true`.
- Every HTTP response now includes `X-Request-ID`. HTTP error envelopes also echo that same value as `request_id` in the JSON body.

## `GET /`

Entrypoint do dashboard local do gateway. Serve um shell HTML/CSS/JS empacotado com visão operacional para status, diagnostics, sessions, automation, tools e chat ao vivo.

The packaged dashboard treats bootstrap URLs as a one-time handoff path: it scrubs `#handoff=` from the address bar after load, exchanges that short-lived bootstrap credential for a scoped dashboard-session credential, keeps only that derived session plus its per-tab dashboard client id in the current browser tab, and seeds live chat with a per-tab `dashboard:operator:<id>` session instead of a fixed shared browser identity.

## `GET /v1/dashboard/state`

Resumo agregado para o dashboard local.

If a gateway token is configured, this endpoint requires that token even when the gateway is otherwise open on loopback.

Example response:

```json
{
  "contract_version": "2026-03-04",
  "generated_at": "2026-03-10T12:00:00+00:00",
  "control_plane": {
    "ready": true,
    "phase": "running",
    "contract_version": "2026-03-04",
    "server_time": "2026-03-10T12:00:00+00:00",
    "components": {},
    "auth": {}
  },
  "sessions": {
    "count": 2,
    "items": [
      {
        "session_id": "dashboard:operator:a1b2c3d4e5f6",
        "last_role": "assistant",
        "last_preview": "Runtime ready.",
        "active_subagents": 0,
        "subagent_statuses": {},
        "updated_at": "2026-03-10T11:59:10+00:00"
      }
    ]
  },
  "channels": {
    "count": 1,
    "items": [
      {
        "name": "telegram",
        "enabled": true,
        "state": "running",
        "summary": "enabled | running"
      }
    ]
  },
  "cron": {
    "status": {"running": true, "jobs": 1},
    "jobs": []
  },
  "heartbeat": {},
  "subagents": {},
  "workspace": {},
  "handoff": {
    "gateway_url": "http://127.0.0.1:8787",
    "gateway_token_masked": "****abcd",
    "bootstrap_pending": true,
    "recommended_first_message": "Wake up, my friend!",
    "hatch_session_id": "hatch:operator",
    "guidance": [
      {
        "id": "dashboard",
        "title": "Dashboard",
        "body": "Open the local control plane with `clawlite dashboard --no-open`."
      }
    ]
  },
  "onboarding": {
    "state_path": "~/.clawlite/workspace/memory/onboarding-state.json",
    "bootstrap_exists": true,
    "bootstrap_seeded_at": "2026-03-10T12:00:00+00:00",
    "onboarding_completed_at": "",
    "completed": false
  },
  "bootstrap": {},
  "memory": {
    "monitor": {},
    "analysis": {},
    "profile": {},
    "suggestions": {},
    "quality": {}
  },
  "skills": {},
  "provider": {
    "telemetry": {},
    "autonomy": {}
  },
  "self_evolution": {
    "enabled": false,
    "status": {},
    "runner": {}
  }
}
```

Alias compatível: `GET /api/dashboard/state` (mesmo payload). When a gateway token is configured, the packaged dashboard alias also accepts the derived dashboard-session credential described above; `/v1/dashboard/state` itself still expects the raw gateway token.

This aggregated dashboard payload now also includes queue/dead-letter stats plus `channels_dispatcher`, `channels_delivery`, `channels_inbound`, `channels_recovery`, and `supervisor` blocks so the packaged control plane can render operator recovery cards without scraping the full diagnostics payload. The dashboard handoff block intentionally redacts raw gateway secrets: it keeps `gateway_url` plus `gateway_token_masked`, but does not return `gateway_token` or `dashboard_url_with_token`.

## `POST /v1/control/memory/suggest/refresh`

Refreshes proactive memory suggestions using the live runtime memory monitor.

Example response:

```json
{
  "ok": true,
  "summary": {
    "ok": true,
    "count": 2,
    "source": "scan"
  }
}
```

Alias compatível: `POST /api/memory/suggest/refresh`.

## `POST /v1/control/memory/snapshot/create`

Creates a new memory snapshot version from the live runtime state.

Example request:

```json
{
  "tag": "dashboard"
}
```

Example response:

```json
{
  "ok": true,
  "summary": {
    "ok": true,
    "version_id": "20260312T120000Z-dashboard"
  }
}
```

Alias compatível: `POST /api/memory/snapshot/create`.

## `POST /v1/control/memory/snapshot/rollback`

Rolls memory state back to a stored snapshot version after explicit confirmation.

Example request:

```json
{
  "version_id": "20260312T120000Z-dashboard",
  "confirm": true
}
```

Example response:

```json
{
  "ok": true,
  "summary": {
    "ok": true,
    "version_id": "20260312T120000Z-dashboard",
    "counts": {
      "before": 10,
      "after": 10
    }
  }
}
```

Alias compatível: `POST /api/memory/snapshot/rollback`.

## `POST /v1/control/channels/discord/refresh`

Refreshes Discord gateway transport state using the live channel instance.

Example response:

```json
{
  "ok": true,
  "summary": {
    "ok": true,
    "gateway_restarted": true,
    "status": {
      "connected": false,
      "gateway_task_state": "running",
      "gateway_session_task_state": "running",
      "gateway_session_waiting_for": "ready",
      "gateway_reconnect_attempt": 1,
      "gateway_reconnect_backoff_s": 2.0,
      "gateway_reconnect_retry_in_s": 1.2,
      "gateway_reconnect_state": "backoff",
      "gateway_last_connect_at": "2026-03-23T12:10:00+00:00",
      "gateway_last_ready_at": "2026-03-23T12:10:03+00:00",
      "gateway_last_disconnect_at": "2026-03-23T12:11:40+00:00",
      "gateway_last_disconnect_reason": "discord_gateway_heartbeat_timeout",
      "gateway_last_lifecycle_outcome": "disconnected",
      "gateway_last_lifecycle_at": "2026-03-23T12:11:40+00:00"
    }
  }
}
```

Alias compatível: `POST /api/channels/discord/refresh`.

## `POST /v1/control/channels/replay`

Replays retained dead-letter outbound events through the live channel manager.

Example request:

```json
{
  "limit": 25,
  "channel": "",
  "reason": "",
  "session_id": "",
  "reasons": []
}
```

Example response:

```json
{
  "ok": true,
  "summary": {
    "restored": 0,
    "restored_idempotency_keys": 0,
    "replayed": 2,
    "failed": 0,
    "skipped": 1,
    "suppressed": 0,
    "remaining": 1
  }
}
```

Alias compatível: `POST /api/channels/replay`.

## `POST /v1/control/channels/recover`

Triggers operator-requested channel recovery through the live channel manager.

Example request:

```json
{
  "channel": "",
  "force": true
}
```

Example response:

```json
{
  "ok": true,
  "summary": {
    "attempted": 2,
    "recovered": 1,
    "failed": 0,
    "skipped_healthy": 3,
    "skipped_cooldown": 0,
    "not_found": 0,
    "forced": true
  }
}
```

Alias compatível: `POST /api/channels/recover`.

## `POST /v1/control/channels/inbound-replay`

Requeues persisted inbound events through the live channel manager.

Example request:

```json
{
  "limit": 100,
  "channel": "",
  "session_id": "",
  "force": false
}
```

Example response:

```json
{
  "ok": true,
  "summary": {
    "replayed": 3,
    "remaining": 5,
    "skipped_busy": 0
  }
}
```

Alias compatível: `POST /api/channels/inbound-replay`.

## `POST /v1/control/channels/telegram/refresh`

Refreshes Telegram transport state using the live channel instance.

Example response:

```json
{
  "ok": true,
  "summary": {
    "offset_reloaded": true,
    "webhook_deleted": true,
    "webhook_activated": true,
    "connected": true,
    "status": {
      "offset_next": 89,
      "offset_pending_count": 0,
      "pairing_pending_count": 1
    }
  }
}
```

Alias compatível: `POST /api/channels/telegram/refresh`.

## `POST /v1/control/channels/telegram/pairing/approve`

Approves a pending Telegram pairing request by code through the live Telegram channel.

Example request:

```json
{
  "code": "ABCD1234"
}
```

Example response:

```json
{
  "ok": true,
  "summary": {
    "ok": true,
    "code": "ABCD1234",
    "request": {
      "chat_id": "1",
      "user_id": "2"
    }
  }
}
```

Alias compatível: `POST /api/channels/telegram/pairing/approve`.

## `POST /v1/control/channels/telegram/pairing/reject`

Rejects and removes a pending Telegram pairing request by code.

Example request:

```json
{
  "code": "WXYZ9999"
}
```

Example response:

```json
{
  "ok": true,
  "summary": {
    "ok": true,
    "code": "WXYZ9999",
    "request": {
      "chat_id": "1",
      "user_id": "2"
    }
  }
}
```

Alias compatível: `POST /api/channels/telegram/pairing/reject`.

## `POST /v1/control/channels/telegram/pairing/revoke`

Revokes an already approved Telegram pairing entry.

Example request:

```json
{
  "entry": "@alice"
}
```

Example response:

```json
{
  "ok": true,
  "summary": {
    "ok": true,
    "removed_entry": "@alice"
  }
}
```

Alias compatível: `POST /api/channels/telegram/pairing/revoke`.

## `POST /v1/control/channels/telegram/offset/commit`

Advances the Telegram safe watermark by force-committing a specific `update_id`.

Example request:

```json
{
  "update_id": 144
}
```

Example response:

```json
{
  "ok": true,
  "summary": {
    "ok": true,
    "update_id": 144,
    "status": {
      "offset_watermark_update_id": 144,
      "offset_next": 145
    }
  }
}
```

Alias compatível: `POST /api/channels/telegram/offset/commit`.

## `POST /v1/control/channels/telegram/offset/sync`

Synchronizes the Telegram `next_offset` directly, with optional reset support.

Example request:

```json
{
  "next_offset": 145,
  "allow_reset": false
}
```

Example response:

```json
{
  "ok": true,
  "summary": {
    "ok": true,
    "next_offset": 145,
    "status": {
      "offset_watermark_update_id": 144,
      "offset_next": 145
    }
  }
}
```

Alias compatível: `POST /api/channels/telegram/offset/sync`.

## `POST /v1/control/channels/telegram/offset/reset`

Resets Telegram `next_offset` to zero after an explicit confirmation flag.

Example request:

```json
{
  "confirm": true
}
```

Example response:

```json
{
  "ok": true,
  "summary": {
    "ok": true,
    "next_offset": 0
  }
}
```

Alias compatível: `POST /api/channels/telegram/offset/reset`.

## `POST /v1/control/provider/recover`

Clears provider failover suppression/cooldown state through the live runtime provider.

Example request:

```json
{
  "role": "primary",
  "model": ""
}
```

Example response:

```json
{
  "ok": true,
  "summary": {
    "ok": true,
    "cleared": 1,
    "matched": 1
  }
}
```

Alias compatível: `POST /api/provider/recover`.

## `POST /v1/control/autonomy/wake`

Triggers a manual autonomy wake through the live wake coordinator.

Example request:

```json
{
  "kind": "proactive"
}
```

Example response:

```json
{
  "ok": true,
  "summary": {
    "kind": "proactive",
    "result": {
      "status": "ok"
    }
  }
}
```

Alias compatível: `POST /api/autonomy/wake`.

## `POST /v1/control/supervisor/recover`

Triggers operator-requested runtime supervisor recovery for one component or all tracked components.

Example request:

```json
{
  "component": "heartbeat",
  "force": true,
  "reason": "operator_recover"
}
```

Example response:

```json
{
  "ok": true,
  "summary": {
    "attempted": 1,
    "recovered": 1,
    "failed": 0,
    "forced": true
  }
}
```

Alias compatível: `POST /api/supervisor/recover`.

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
    "channels_dispatcher": {"enabled": true, "running": true, "last_error": ""},
    "channels_recovery": {"enabled": true, "running": true, "last_error": ""},
    "cron": {"enabled": true, "running": true, "last_error": ""},
    "heartbeat": {"enabled": true, "running": true, "last_error": ""},
    "subagent_maintenance": {"enabled": true, "running": true, "last_error": ""},
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
- `autonomy` may include `last_error_kind`, `skipped_provider_backoff`, `provider_backoff_remaining_s`, `provider_backoff_reason`, `provider_backoff_provider`, and a trimmed provider snapshot in `last_snapshot.provider`.
- `autonomy` may also include `skipped_no_progress`, `no_progress_reason`, `no_progress_streak`, and `no_progress_backoff_remaining_s` when the continuous loop is intentionally paused after repeated identical `AUTONOMY_IDLE` outcomes on an unchanged runtime snapshot.
- `last_snapshot.provider` may include `suppression_reason`, `suppression_backoff_s`, and `suppression_hint` when autonomy is intentionally holding off on provider calls.
- provider summary payloads may also include `suppressed_candidates` when failover candidates are in longer auth/quota/config suppression windows instead of a short transient cooldown.
- failover provider payloads may also include per-candidate `health_score`, `health_state`, `error_ratio`, `latency_p50_ms`, and top-level `fallback_health_order` to explain which ready fallback will be preferred next.
- `supervisor` may include per-component recovery budgets and cooldown telemetry in `component_recovery`, plus aggregate `recovery_skipped_budget` counters.
- control-plane `components` may include `subagent_maintenance`, a background sweeper loop that keeps subagent queue/run state fresh and recoverable.

## `GET /v1/diagnostics`

If `gateway.diagnostics.enabled=false`, returns `404` with `{"error":"diagnostics_disabled","status":404}`.

`channels` entries are additive and may include channel-specific `signals` maps for operational counters/state.

For Telegram, `signals` may also include safe-offset reliability fields such as `offset_next`, `offset_watermark_update_id`, `offset_highest_completed_update_id`, `offset_pending_count`, and `offset_min_pending_update_id`, plus additive counters like `offset_safe_advance_count`, `polling_stale_update_skip_count`, `webhook_stale_update_skip_count`, `media_download_count`, `media_download_error_count`, `media_transcription_count`, and `media_transcription_error_count`.

For Discord, the nested channel `status` payload may also include policy and focus-binding fields such as `dm_policy`, `group_policy`, `allow_bots`, `reply_to_mode`, `slash_isolated_sessions`, `guild_allowlist_count`, `policy_allowed_count`, `policy_blocked_count`, `thread_bindings_enabled`, `thread_binding_state_path`, `thread_binding_idle_timeout_s`, `thread_binding_max_age_s`, and `thread_binding_count`.

`channels_delivery` is additive and includes manager-level delivery counters with this shape:

- `total`: aggregate counters (`attempts`, `success`, `failures`, `dead_lettered`, `replayed`, `channel_unavailable`, `policy_dropped`, `delivery_confirmed`, `delivery_failed_final`, `idempotency_suppressed`)
- `per_channel`: same counter schema keyed by channel name
- `recent`: bounded per-message outcomes (newest first), including safe delivery metadata such as `outcome`, `idempotency_key`, `dead_letter_reason`, `last_error`, `send_result`, `receipt`, and replay marker

`memory_monitor` is additive and reports proactive memory monitor telemetry:

- `enabled`: monitor activation status (`agents.defaults.memory.proactive` + runtime wiring)
- counters: `scans`, `generated`, `deduped`, `low_priority_skipped`, `cooldown_skipped`, `sent`, `failed`
- queue/state: `pending`, `cooldown_seconds`, `suggestions_path`

Purpose: operational visibility for proactive memory suggestions (generation, suppression, and delivery outcomes) without exposing raw memory content.

`channels_recovery` is additive and reports the channel-manager recovery supervisor loop:

- loop state: `enabled`, `running`, `task_state`, `last_error`
- config: `interval_s`, `cooldown_s`
- counters: `total` (`attempts`, `success`, `failures`, `skipped_cooldown`)
- per-channel recovery telemetry: `per_channel`

Purpose: operational visibility for automatic channel worker recovery and whether the recovery supervisor itself is still alive.

`channels_dispatcher` is additive and reports the channel-manager dispatcher loop:

- loop state: `enabled`, `running`, `task_state`, `last_error`
- config/limits: `max_concurrency`, `max_per_session`, `session_slots_max_entries`
- current load: `session_slots`, `active_tasks`, `active_sessions`

Purpose: operational visibility for whether inbound dispatch is still draining the bus and whether the runtime supervisor had to restart the dispatcher loop.

`self_evolution` is additive and reports the self-improvement engine plus its background loop runner:

- engine status: `enabled`, `background_enabled`, `activation_mode`, `activation_reason`, `enabled_for_sessions`, `autonomy_session_id`, `run_count`, `committed_count`, `dry_run_count`, `last_outcome`, `last_error`, `last_branch`, `last_review_status`, `branch_prefix`, `require_approval`, `cooldown_remaining_s`, `locked`
- runner status: nested `runner` map with `enabled`, `running`, `cooldown_seconds`, `activation_mode`, `activation_reason`, `enabled_for_sessions`, `autonomy_session_id`, `ticks`, `success_count`, `error_count`, `last_result`, `last_error`, `last_run_iso`

Purpose: operational visibility for whether the self-evolution worker is actually alive, not just configured, which isolated branch the latest successful run produced, whether operator approval is expected before merge, what the latest persisted human review decision was, and whether a session-canary allowlist is keeping the background loop disabled.

`subagents` is additive and reports persisted subagent manager/runtime telemetry:

- manager snapshot: `state_path`, concurrency/queue/quota limits, `run_count`, `running_count`, `queued_count`, `resumable_count`, `queue_depth`, `status_counts`
- maintenance snapshot: `maintenance_interval_s` plus `maintenance` counters (`sweep_runs`, `last_sweep_at`, `last_sweep_changed`, `last_sweep_stats`, `totals`)
- runner snapshot: nested `runner` map for the gateway background maintenance loop (`enabled`, `running`, `interval_seconds`, `ticks`, `success_count`, `error_count`, `last_result`, `last_error`, `last_run_iso`)

Purpose: operational visibility for subagent replay/sweep health, heartbeat freshness, and supervisor-managed maintenance recovery.

Memory quality tuning diagnostics (stages 15-18) are additive and may appear in:

- top-level `engine.memory_quality`: persisted quality/tuning state summary
- top-level `memory_quality_tuning`: runtime tuning loop snapshot/counters

When available, `engine.memory_quality.state.trend` is an additive summary over the bounded quality history window and may include:

- `assessment`: `improving`, `stable`, `degrading`, or `insufficient_history`
- `window_points`, `window_start_sampled_at`, `window_end_sampled_at`
- `score_change`, `hit_rate_change`, `semantic_coverage_change`, `reasoning_balance_change`
- `score_range`, `degrading_streak`, `improving_streak`, `weakest_layers`

`environment` telemetry remains separate from the memory quality payload and is gated by `gateway.diagnostics.include_config=true`.

Expected additive keys include quality layer scores and stage18 tuning telemetry/action metadata:

- reasoning layers: `fact`, `hypothesis`, `decision`, `outcome` (quality scoring context)
- telemetry maps: `actions_by_layer`, `actions_by_playbook`, `actions_by_action`, `action_status_by_layer`
- latest action metadata: `last_action_metadata` (for example `template_id`, `backfill_limit`, `snapshot_tag`, `action_variant`, plus playbook context such as `playbook_id`, `weakest_layer`, `severity`)

When `gateway.diagnostics.include_config=true`, `environment` may include additive engine persistence telemetry, session-recovery telemetry under `environment.engine.session_recovery`, memory-store durability/recovery telemetry under `environment.engine.memory_store`, nested session-store durability/recovery diagnostics, tool execution telemetry under `environment.engine.tools` (`total` + `per_tool` counters), and provider telemetry under `environment.engine.provider`.

Memory backend diagnostics are additive and may also include vector-index state such as `backend_vector_index`, `backend_vector_index_kind`, and `backend_vector_index_error`.

Provider telemetry keys are additive and may include: `requests`, `successes`, `retries`, `timeouts`, `network_errors`, `http_errors`, `auth_errors`, `rate_limit_errors`, `server_errors`, `circuit_open`, `circuit_open_count`, `circuit_close_count`, `consecutive_failures`, `last_error`, `last_status_code`.

Supervisor telemetry is additive under `supervisor` and may include: `ticks`, `incident_count`, `recovery_attempts`, `recovery_success`, `recovery_failures`, `recovery_skipped_cooldown`, `component_incidents`, `last_incident`, `last_recovery_at`, `last_error`, `consecutive_error_count`, and `cooldown_active`.

Autonomy telemetry is additive under `autonomy` and may include: `running`, `enabled`, `session_id`, `ticks`, `run_attempts`, `run_success`, `run_failures`, `skipped_backlog`, `skipped_cooldown`, `skipped_disabled`, `last_run_at`, `last_result_excerpt`, `last_error`, `consecutive_error_count`, `last_snapshot`, and `cooldown_remaining_s`.

Autonomy telemetry may also include no-progress guard fields: `skipped_no_progress`, `no_progress_reason`, `no_progress_streak`, and `no_progress_backoff_remaining_s`.

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
  "channels_dispatcher": {},
  "channels_delivery": {
    "total": {},
    "per_channel": {},
    "recent": []
  },
  "channels_recovery": {},
  "cron": {},
  "heartbeat": {},
  "supervisor": {},
  "autonomy": {},
  "subagents": {},
  "self_evolution": {},
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

## `GET /v1/tools/catalog`

Returns the live gateway tool catalog, grouped by runtime area and compatibility aliases.

Query params:
- `include_schema=true` to include the JSON-schema rows for each tool.

Alias compatível: `GET /api/tools/catalog`.

## `GET /v1/tools/approvals`

Returns the live queue of approval-gated tool requests tracked by the running gateway.
Each request includes the existing raw `arguments_preview` plus structured `approval_context` for operator UX, such as exec command metadata, env override keys, cwd, or browser/web target hosts.
If a gateway token is configured, this endpoint requires that token even when the gateway is otherwise open on loopback.

Query params:
- `status`: `pending`, `approved`, `rejected`, or `all`
- `session_id`: optional session filter
- `channel`: optional channel filter
- `tool`: optional exact tool filter
- `rule`: optional exact matched approval rule filter
- `include_grants=true`: also returns active temporary approval grants
- `limit`: max rows to return

Response baseline:
- `count`: number of returned approval requests
- `requests`: request snapshots with `request_id`, `tool`, `session_id`, `channel`, optional `requester_actor`, `matched_approval_specifiers`, `status`, and remaining TTL fields such as `expires_in_s`
- `grant_count`: number of returned active grants
- `grants`: active grants with `session_id`, `channel`, `rule`, `scope`, optional `request_id`, and `expires_in_s`

Alias compatível: `GET /api/tools/approvals`.

## `POST /v1/tools/approvals/{request_id}/approve`

Approves one pending tool request and creates the temporary grant bound to the reviewed request fingerprint plus the same session, channel, and matched specifier set. When `requester_actor` was recorded on the original request, only that same actor can review it from the native channel interaction path; generic HTTP review fails closed with `approval_channel_bound`. If a gateway token is configured, this endpoint requires that token even when the gateway is otherwise open on loopback. Generic HTTP reviews record the reviewer as `control-plane`; caller-supplied actor labels are ignored.

Request body:

```json
{
  "note": "approved after review"
}
```

Alias compatível: `POST /api/tools/approvals/{request_id}/approve`.

For actor-bound channel requests, inspect the queue over HTTP/CLI if needed, but perform the actual review from the original Telegram/Discord button callback instead of the generic control-plane endpoint.

## `POST /v1/tools/approvals/{request_id}/reject`

Rejects one pending tool request without creating a grant. If a gateway token is configured, this endpoint requires that token even when the gateway is otherwise open on loopback. Generic HTTP reviews record the reviewer as `control-plane`; caller-supplied actor labels are ignored.

Request body:

```json
{
  "note": "use a safer command"
}
```

Alias compatível: `POST /api/tools/approvals/{request_id}/reject`.

## `POST /v1/tools/grants/revoke`

Revokes one or more active temporary tool-approval grants before their TTL expires.
If a gateway token is configured, this endpoint requires that token even when the gateway is otherwise open on loopback.

Request body:

```json
{
  "session_id": "telegram:123",
  "channel": "telegram",
  "rule": "browser:evaluate"
}
```

Any field may be omitted to widen the match:
- omit `rule` to revoke all grants for the session/channel
- omit `channel` to revoke all grants for the session
- omit `session_id` to revoke every grant matching the remaining filters

Response baseline:
- `summary.removed_count`: number of grants removed
- `summary.removed`: rows with `session_id`, `channel`, `rule`, `scope`, and optional `request_id`

Alias compatível: `POST /api/tools/grants/revoke`.

## `POST /v1/chat`

Request:

```json
{
  "session_id": "telegram:123",
  "text": "remind me to drink water",
  "channel": "telegram",
  "chat_id": "123",
  "runtime_metadata": {
    "reply_to_message_id": "456"
  }
}
```

Alias compatível: `POST /api/message` (mesma request/response). When a gateway token is configured, the dashboard alias also accepts the derived dashboard-session credential; `POST /v1/chat` itself still expects the raw gateway token.

Campos opcionais:
- `channel`: dica explícita de canal quando a requisição HTTP não veio de um adapter já normalizado.
- `chat_id`: identificador do alvo/chat a preservar no contexto do turno.
- `runtime_metadata`: objeto JSON opcional com metadata inbound adicional. O gateway só aceita objeto e ignora outros tipos; o prompt do agente continua vendo apenas a allowlist segura/untrusted já documentada.

Nota operacional: o tool `message` suporta acoes Telegram (`send`, `reply`, `edit`, `delete`, `react`, `create_topic`) via argumentos de `action` e bridge de metadata (`_telegram_action*`), enquanto Discord permanece em `send` com suporte a botões via `discord_components`. Canais sem capability explícita permanecem no contrato conservador de `send`.

If a gateway token is configured, this endpoint requires that token even when the gateway is otherwise open on loopback.

Rate limiting:
- When `gateway.rate_limit.enabled=true`, `POST /v1/chat`, `POST /api/message`, and WebSocket chat sends may return `429` / `gateway_rate_limited`.
- HTTP responses set `Retry-After` and include `retry_after_s` in the JSON payload.
- Relevant config fields today: `gateway.rate_limit.window_s`, `gateway.rate_limit.chat_requests_per_window`, `gateway.rate_limit.ws_chat_requests_per_window`, and `gateway.rate_limit.exempt_loopback`.

## `GET /v1/status`

Estado do control-plane do gateway.

If a gateway token is configured, this endpoint requires that token even when the gateway is otherwise open on loopback.

Campos de contrato estavel:
- `contract_version`: versao do contrato HTTP do gateway.
- `server_time`: timestamp UTC ISO-8601 gerado no servidor.

Alias compatível: `GET /api/status` (mesmo payload). When a gateway token is configured, the dashboard alias also accepts the derived dashboard-session credential; `GET /v1/status` itself still expects the raw gateway token.

## `GET /v1/diagnostics`

Snapshot operacional do gateway para debug e operacao.

Campos baseline de contrato:
- `generated_at`: timestamp UTC ISO-8601 da geracao do snapshot.
- `uptime_s`: uptime do processo do gateway em segundos.
- `contract_version`: versao estavel do contrato HTTP do gateway.
- `control_plane.components.subagent_maintenance`: estado do loop de manutencao/sweep de subagentes supervisionado pela gateway.
- `control_plane.components.channels_dispatcher`: estado do dispatcher de mensagens inbound dos canais.
- `control_plane.components.channels_recovery`: estado do supervisor interno de recuperacao dos canais.
- `control_plane.components.self_evolution`: estado do loop de self-evolution supervisionado pela gateway.
- `channels_dispatcher`: estado do loop de dispatch dos canais, com limites e carga atual.
- `channels_delivery`: contadores de entrega agregados do `ChannelManager` (`total` e `per_channel`).
- `channels_recovery`: estado do loop de recovery dos canais, com contadores agregados e telemetria por canal.
- `self_evolution`: estado do motor de self-evolution e do runner em background.
- `memory_monitor`: telemetria do monitor proativo de memoria (`enabled`, contadores de scan/geracao/entrega, pendencias, cooldown e path do backlog).
- `subagents`: snapshot operacional do `SubagentManager`, incluindo limites, contagens por status, telemetria de sweep/manutencao e o estado do runner de manutencao em background.
- `channels_delivery.recent`: snapshots por mensagem (mais recentes primeiro) com outcome e recibo seguro por envio, sem texto da mensagem.
  Inclui contadores aditivos de confirmacao/falha final e supressao de duplicatas (`delivery_confirmed`, `delivery_failed_final`, `idempotency_suppressed`).
- `http`: telemetria HTTP em memoria (aditiva) com `total_requests`,
  `in_flight`, `by_method`, `by_path`, `by_status` e `latency_ms`
  (`count`, `min`, `max`, `avg`).
- `ws`: telemetria WebSocket em memoria (aditiva) com `connections_opened`,
  `connections_closed`, `active_connections`, `frames_in`, `frames_out`,
  `last_connection_id`, `last_connection_path`, `last_connection_opened_at`,
  `last_connection_closed_id`, `last_connection_closed_at`, `last_request_id`,
  `last_error_connection_id`, `last_error_request_id`, `last_error_at`,
  `last_error_code`, `last_error_message`, `last_error_status`, e mapas
  agregados como `by_path`, `by_message_type_in`, `by_message_type_out`,
  `req_methods` e `error_codes`.

Alias compatível: `GET /api/diagnostics` (mesmo payload). When a gateway token is configured, the dashboard alias also accepts the derived dashboard-session credential; `GET /v1/diagnostics` itself stays on the raw gateway-token path when diagnostics auth is enabled.

## `GET /api/token`

Diagnóstico de autenticação do gateway.
- Nunca retorna token em texto puro.
- Retorna apenas estado (`token_configured`) e versão mascarada determinística (`token_masked`).
- Quando o dashboard-session flow estiver habilitado, também informa `dashboard_handoff_enabled`, `dashboard_handoff_header_name`, `dashboard_handoff_query_param`, `dashboard_session_enabled`, `dashboard_session_header_name`, `dashboard_session_query_param`, `dashboard_client_header_name`, e `dashboard_client_query_param`.
- Aceita tanto o gateway token bruto quanto a credencial derivada do dashboard.

## `POST /api/dashboard/session`

Troca um bootstrap de dashboard por uma credencial derivada e efêmera para o dashboard empacotado.

- Aceita preferencialmente o handoff curto do dashboard (`X-ClawLite-Dashboard-Handoff` / `dashboard_handoff`) e ainda aceita o gateway token bruto no header normal de autenticação para flows legados ou manuais; query-param de token bruto não é aceito aqui. O handoff curto é de uso único dentro do processo atual do gateway: depois de um exchange bem-sucedido, uma nova tentativa com o mesmo valor falha com `401`.
- Também requer um client id do dashboard no header `X-ClawLite-Dashboard-Client` (ou no nome configurado informado pelo bootstrap).
- Retorna um `session_token` opaco com `token_type=\"dashboard_session\"`, `bootstrap_kind`, `expires_at`, `expires_in_s`, e os nomes de header/query aceitos pelo shell do dashboard tanto para o handoff bootstrap quanto para a sessão derivada e o client binding.
- A credencial derivada fica vinculada a esse client id de aba e só é aceita quando o mesmo identificador acompanha os requests HTTP/WS do dashboard.
- Essa credencial derivada é aceita apenas nas superfícies de dashboard/control-plane que optam por ela (`/api/status`, `/api/dashboard/state`, `/api/diagnostics`, `/api/token`, `/api/message`, `/api/tools/catalog`, `/v1/control/*`, e `WS /ws`).
- A mesma credencial não substitui o gateway token bruto em `/v1/status`, `/v1/chat`, `/v1/tools/*`, ou `WS /v1/ws`.

## `POST <telegram webhook path>`

- Telegram webhook endpoint is dynamic and comes from `channels.telegram.webhook_path` (default: `/api/webhooks/telegram`).
- Enabled only when Telegram channel is enabled and running in active webhook mode.
- Validates `X-Telegram-Bot-Api-Secret-Token` against channel secret when configured.
- Accepts JSON object payload up to 1 MB and returns `{ "ok": true, "processed": <bool> }`.
- Applies a 5s body-read timeout and returns `408` with code `telegram_webhook_payload_timeout` on slow/incomplete payload reads.
- `processed=false` is valid for stale or duplicate webhook redeliveries that were safely ignored.

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
  "status": {
    "running": true,
    "jobs": 1,
    "lock_backend": "fcntl"
  },
  "session_id": "cli:cron",
  "count": 1,
  "enabled_count": 1,
  "disabled_count": 0,
  "status_counts": {
    "idle": 1
  },
  "jobs": []
}
```

## `GET /v1/cron/status`

Returns the same operational envelope as `GET /v1/cron/list`, but scoped to all cron jobs instead of a single session.

## `GET /v1/cron/{job_id}?session_id=...`

Example response:

```json
{
  "status": {
    "running": true,
    "jobs": 1,
    "lock_backend": "fcntl"
  },
  "job": {
    "id": "job_xxx",
    "name": "stretch",
    "session_id": "telegram:123",
    "enabled": true,
    "last_status": "idle"
  }
}
```

## `POST /v1/cron/{job_id}/enable`

Body:

```json
{
  "session_id": "telegram:123"
}
```

Response:

```json
{
  "ok": true,
  "status": "enabled",
  "cron_status": {
    "running": true,
    "jobs": 1,
    "lock_backend": "fcntl"
  },
  "job": {
    "id": "job_xxx",
    "enabled": true
  }
}
```

`POST /v1/cron/{job_id}/disable` has the same shape, but returns `"status": "disabled"`.

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

The initial `connect.challenge` event now also includes an additive
`params.connection_id` for that socket. This does not change the later request or
response envelopes; it only gives operators a stable correlation handle that matches
the `ws` telemetry snapshot returned by `GET /v1/diagnostics`.

Input message:

```json
{
  "session_id": "cli:ws",
  "text": "hello",
  "channel": "telegram",
  "chat_id": "123",
  "runtime_metadata": {
    "reply_to_message_id": "456"
  }
}
```

No envelope `req` moderno, WebSocket também aceita `sessionId`, `chatId` e `runtimeMetadata`.
Os campos opcionais têm a mesma semântica do `POST /v1/chat`, e `runtime_metadata` / `runtimeMetadata` inválido é ignorado em vez de virar erro de contrato.

Output message:

```json
{"text":"...","model":"gemini/gemini-2.5-flash"}
```

Quando `stream=true` for usado no envelope `req` moderno, o gateway envia eventos `chat.chunk`
antes do `res` final. Esses eventos podem ser coalescidos pelo transporte para juntar chunks muito
pequenos do provider em blocos mais úteis, preservando a ordem e o campo `accumulated`. Os limites
desse coalescing podem ser ajustados em `gateway.websocket.coalesce_enabled`,
`gateway.websocket.coalesce_min_chars`, `gateway.websocket.coalesce_max_chars` e
`gateway.websocket.coalesce_profile` (`compact`, `newline`, `paragraph`, `raw`).

Alias compatível: `WS /ws` (mesmo comportamento de chat/streaming). When a gateway token is configured, `WS /v1/ws` still requires that raw token even on loopback, while the dashboard alias `WS /ws` also accepts the derived dashboard-session credential.

## Envelope de erro HTTP

Para erros HTTP, o gateway retorna envelope estavel com:
- `error`
- `status`
- `code` (quando `error` for string, `code` repete esse valor)
- `request_id` (o mesmo valor devolvido no header `X-Request-ID`)
