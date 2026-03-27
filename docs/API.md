# API (Gateway)

Default base URL: `http://127.0.0.1:8787`

## Auth (summary)

- `gateway.auth.mode=off`: no authentication.
- `gateway.auth.mode=optional`: accepts requests without token, but invalid token returns `401`.
- `gateway.auth.mode=required`: requires token (except loopback when `allow_loopback_without_auth=true`).
- Token can be sent via configurable header (default `Authorization`, with or without `Bearer ` prefix) or configurable query param (default `token`).
- If a gateway token is configured, the control-plane routes (`/v1/status`, `/v1/dashboard/state`, `/v1/chat`, control mutations, approvals/grants, and `WS /v1/ws`) require that token even when the gateway is otherwise open on loopback.
- The packaged dashboard now prefers a short-lived `#handoff=` bootstrap credential instead of putting the raw gateway token in the browser URL. `POST /api/dashboard/session` still accepts the raw gateway token for legacy/manual flows, but the packaged shell exchanges the handoff first and then uses the derived dashboard-session credential only on dashboard-scoped aliases such as `/api/status`, `/api/dashboard/state`, `/api/diagnostics`, `/api/token`, `/api/message`, `/api/tools/catalog`, `/api/tools/approvals`, `/api/tools/approvals/*`, `/api/tools/approvals/audit`, `/api/tools/approvals/audit/export`, `/api/tools/grants/revoke`, `/api/provider/status`, `/v1/control/*`, and `WS /ws`. That derived credential is bound to a per-tab dashboard client id, so dashboard-scoped requests must present both values. The short-lived handoff itself is consumed on the first successful exchange in the running gateway process, which blocks replay of the same bootstrap credential. Generic `/v1/*` routes and `WS /v1/ws` still require the raw gateway token. The packaged Tools tab now uses that same scoped flow not only for live approval inspection/review but also for filtered grant cleanup, read-only approval audit inspection, and bounded audit export.
- `/health` only requires auth when `gateway.auth.protect_health=true` and mode is `required`.
- `/v1/diagnostics` depends on `gateway.diagnostics.enabled` and may require auth with `gateway.diagnostics.require_auth=true`.
- Every HTTP response now includes `X-Request-ID`. HTTP error envelopes also echo that same value as `request_id` in the JSON body.

## `GET /`

Entrypoint do dashboard local do gateway. Serve um shell HTML/CSS/JS empacotado com visão operacional para status, diagnostics, sessions, automation, tools e chat ao vivo.

The packaged dashboard treats bootstrap URLs as a one-time handoff path: it scrubs `#handoff=` from the address bar after load, exchanges that short-lived bootstrap credential for a scoped dashboard-session credential, keeps only that derived session plus its per-tab dashboard client id in the current browser tab, and seeds live chat with a per-tab `dashboard:operator:<id>` session instead of a fixed shared browser identity.

## `GET /v1/dashboard/state`

Resumo agregado para o dashboard local.

If a gateway token is configured, this endpoint requires that token even when the gateway is otherwise open on loopback.

Additive note:
- `skills.managed` now carries a compact marketplace-lifecycle summary for the packaged dashboard, with `count`, `ready_count`, unfiltered `blocked_count`, additive `visible_blocked_count`, `disabled_count`, `status_counts`, a bounded `items` preview of managed marketplace skills, and an additive `blockers` summary (`count`, `by_kind`, `top_kind`, `top_detail`, `top_hint`, and bounded `examples`) for the currently visible managed blocker slice.

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
  "ws": {
    "active_connections": 0,
    "last_connection_id": "ws-abc123",
    "last_request_id": "req-42",
    "last_error_connection_id": "ws-abc123",
    "last_error_request_id": "req-42",
    "last_error_code": "unsupported_method",
    "last_error_message": "unsupported req method: unsupported.method",
    "last_error_status": 400
  },
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

This aggregated dashboard payload now also includes queue/dead-letter stats plus `channels_dispatcher`, `channels_delivery`, `channels_inbound`, `channels_recovery`, `supervisor`, and a compact `ws` block so the packaged control plane can render operator recovery cards and recent WebSocket correlation hints without scraping the full diagnostics payload. The dashboard handoff block intentionally redacts raw gateway secrets: it keeps `gateway_url` plus `gateway_token_masked`, but does not return `gateway_token` or `dashboard_url_with_token`.

The additive `provider.status` block now mirrors the current cached provider status used by `clawlite provider status`: it includes the selected/active provider hint plus any persisted `last_live_probe` and `last_capability_probe` summaries so the packaged dashboard can surface cached provider probe posture without forcing a new network probe on every refresh.

The additive `provider.health` block now mirrors a bounded operator summary derived from `provider.status`, provider autonomy suppression state, and provider telemetry summary: it includes `health_posture`, `health_tone`, `operator_hint`, plus nested `route`, `probe`, `capability`, and `autonomy` detail so the packaged Automation tab can surface cached-route drift, suppression, model-list posture, and recovery guidance without scraping the raw provider payloads separately.

The additive `provider.budget` block now mirrors a bounded quota/rate-limit posture derived from the same live provider telemetry, autonomy suppression state, and cached route context: it includes `budget_posture`, `budget_tone`, `operator_hint`, plus nested `route`, `quota`, `rate_limit`, and `telemetry` detail so the packaged Automation tab can distinguish exhausted quota, live rate limiting, and non-budget provider blocks without scraping the raw counters directly.

The additive `runtime.posture` block now mirrors the runtime/operator posture already implied by autonomy, wake, supervisor, and self-evolution state: it summarizes `autonomy_posture`, `wake_posture`, `approval_posture`, a derived `summary_posture` / `summary_tone`, and a compact `operator_hint`, while also carrying bounded nested detail for `autonomy`, `autonomy_wake`, `self_evolution`, and `supervisor` so the packaged Automation tab can show a compact runtime posture card without scraping the full diagnostics payload.

The additive `runtime.policy` block now mirrors the active self-evolution/operator policy instead of runtime activity: it summarizes `approval_mode`, `activation_scope`, `policy_posture`, `policy_tone`, `policy_block`, and `policy_hint`, while also carrying bounded nested detail for self-evolution policy inputs such as `enabled_for_sessions_count`, `enabled_for_sessions_sample`, `autonomy_session_id`, `current_session_allowed`, `activation_reason`, and `last_review_status` so the packaged Automation tab can surface canary/manual-only/approval policy without scraping full diagnostics.

That same additive `runtime.policy` block now also carries a bounded nested `drift` section so operators can compare configured self-evolution policy against the effective runtime policy without reconstructing it by hand. The `drift` payload includes `posture`, `tone`, `reason`, `hint`, plus compact `configured` and `effective` snapshots for enablement, approval gate, activation scope, canary allowlist counts/samples, and autonomy session binding.

## `GET /v1/control/provider/status`

Returns the compact cached provider status for the provider currently selected by the runtime/config, reusing the same local probe cache surfaced by `clawlite provider status`.

Example response:

```json
{
  "ok": true,
  "provider": "openai",
  "selected_provider": "openai",
  "active_provider": "openai",
  "active_model": "openai/gpt-4o-mini",
  "transport": "openai_compatible",
  "base_url": "https://api.openai.com/v1",
  "last_live_probe": {
    "provider": "openai",
    "transport": "openai_compatible",
    "ok": true,
    "checked_at": "2026-03-27T10:00:00+00:00"
  },
  "last_capability_probe": {
    "provider": "openai",
    "checked": true,
    "current_model_listed": true,
    "detail": "model_listed",
    "listed_model_count": 2,
    "listed_model_sample": ["openai/gpt-4o-mini", "openai/gpt-4.1-mini"]
  }
}
```

Alias compatível: `GET /api/provider/status`. When a gateway token is configured, the packaged dashboard alias also accepts the derived dashboard-session credential; `GET /v1/control/provider/status` itself still expects the raw gateway token.

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

## `POST /v1/control/skills/refresh`

Refreshes live runtime skill discovery and returns the same summary blocks used by the dashboard Knowledge tab.

Example request:

```json
{
  "force": true
}
```

Example response:

```json
{
  "ok": true,
  "summary": {
    "ok": true,
    "refresh": {
      "refreshed": true,
      "debounced": false
    },
    "skills": {
      "available": 12,
      "runnable": 9
    },
    "watcher": {
      "task_state": "running",
      "last_error": ""
    },
    "contract_issues": {
      "count": 0
    },
    "missing_requirements": {
      "count": 2
    }
  }
}
```

Alias compatível: `POST /api/skills/refresh`.

## `POST /v1/control/skills/doctor`

Builds the same actionable blocked-skills report used by `clawlite skills doctor`, but from the live runtime control plane.

Example request:

```json
{
  "include_all": false,
  "status": "missing_requirements",
  "source": "builtin",
  "query": "github"
}
```

Example response:

```json
{
  "ok": false,
  "summary": {
    "ok": false,
    "action": "skills_doctor",
    "summary": {
      "available": 12,
      "runnable": 9
    },
    "watcher": {
      "task_state": "running",
      "last_error": ""
    },
    "status_counts": {
      "missing_requirements": 1,
      "ready": 11
    },
    "status_filter": "missing_requirements",
    "source_filter": "builtin",
    "query": "github",
    "count": 1,
    "recommendations": [
      "Export GH_TOKEN, set skills.entries.github.apiKey manually, or run clawlite skills config github."
    ],
    "skills": [
      {
        "name": "github",
        "status": "missing_requirements",
        "hint": "Export GH_TOKEN, set skills.entries.github.apiKey manually, or run clawlite skills config github."
      }
    ]
  }
}
```

Alias compatível: `POST /api/skills/doctor`.

## `POST /v1/control/skills/validate`

Runs a forced-or-debounced live refresh and then returns the same actionable blocked-skills report used by `clawlite skills doctor`, all in one control-plane call.

Example request:

```json
{
  "force": true,
  "include_all": false,
  "status": "missing_requirements",
  "source": "builtin",
  "query": "github"
}
```

Example response:

```json
{
  "ok": false,
  "summary": {
    "ok": false,
    "action": "skills_validate",
    "refresh": {
      "refreshed": true,
      "debounced": false
    },
    "summary": {
      "available": 12,
      "runnable": 9
    },
    "watcher": {
      "task_state": "running",
      "last_error": ""
    },
    "doctor": {
      "action": "skills_doctor"
    },
    "status_filter": "missing_requirements",
    "source_filter": "builtin",
    "query": "github",
    "count": 1,
    "recommendations": [
      "Export GH_TOKEN, set skills.entries.github.apiKey manually, or run clawlite skills config github."
    ]
  }
}
```

Alias compatível: `POST /api/skills/validate`.

## `POST /v1/control/skills/sync`

Runs the same managed marketplace sync used by `clawlite skills sync`, then refreshes runtime skill discovery and returns the resulting managed inventory snapshot.

Example request:

```json
{}
```

Example response:

```json
{
  "ok": true,
  "summary": {
    "ok": true,
    "action": "sync",
    "managed_root": "/home/user/.clawlite/marketplace",
    "skills_root": "/home/user/.clawlite/marketplace/skills",
    "returncode": 0,
    "refresh": {
      "refreshed": true
    },
    "managed_count": 2,
    "ready_count": 1,
    "blocked_count": 1,
    "disabled_count": 0,
    "status_counts": {
      "missing_requirements": 1,
      "ready": 1
    },
    "managed": {
      "ok": true,
      "action": "managed",
      "count": 2,
      "total_count": 2
    },
    "skills": [
      {
        "slug": "github-helper",
        "status": "missing_requirements"
      }
    ]
  }
}
```

Alias compatível: `POST /api/skills/sync`.

## `GET /v1/control/skills/managed`

Returns the live marketplace-managed skills inventory used by `clawlite skills managed`, but from the running control plane.

Query params:

- `status`: optional lifecycle filter such as `ready` or `missing_requirements`
- `query`: optional case-insensitive filter across slug, name, skill key, description, and hint

Example response:

```json
{
  "ok": true,
  "summary": {
    "ok": true,
    "action": "managed",
    "managed_root": "/home/user/.clawlite/marketplace",
    "skills_root": "/home/user/.clawlite/marketplace/skills",
    "count": 1,
    "total_count": 2,
    "ready_count": 1,
    "blocked_count": 1,
    "visible_blocked_count": 1,
    "disabled_count": 0,
    "status_filter": "missing_requirements",
    "query": "github",
    "status_counts": {
      "missing_requirements": 1,
      "ready": 1
    },
    "blockers": {
      "count": 1,
      "by_kind": {
        "env": 1
      },
      "top_kind": "env",
      "top_detail": "GH_TOKEN",
      "top_hint": "Export GH_TOKEN, set skills.entries.github.apiKey manually, or run clawlite skills config github.",
      "examples": [
        {
          "slug": "github-helper",
          "status": "missing_requirements",
          "blocker_kind": "env",
          "blocker_detail": "GH_TOKEN"
        }
      ]
    },
    "skills": [
      {
        "slug": "github-helper",
        "name": "GitHub Helper",
        "status": "missing_requirements",
        "blocker_kind": "env",
        "blocker_detail": "GH_TOKEN",
        "hint": "Export GH_TOKEN, set skills.entries.github.apiKey manually, or run clawlite skills config github."
      }
    ]
  }
}
```

Alias compatível: `GET /api/skills/managed`.

The additive `summary.blockers` block and `visible_blocked_count` are scoped to the currently visible slice after `status` and `query` filters are applied, while `blocked_count` remains the unfiltered blocked total for the full managed inventory. That split lets dashboard/CLI operators distinguish “all managed blockers” from “the blockers still visible in this filtered triage pass”.

## `POST /v1/control/memory/doctor`

Runs the same read-only memory diagnostics used by `clawlite memory doctor`, but from the running control plane.

Example request:

```json
{}
```

Example response:

```json
{
  "ok": true,
  "summary": {
    "ok": true,
    "repair_applied": false,
    "counts": {
      "history": 12,
      "curated": 4,
      "total": 16
    },
    "diagnostics": {
      "history_read_corrupt_lines": 0,
      "history_repaired_files": 0
    },
    "files": {
      "history": {
        "size_bytes": 2048
      }
    }
  }
}
```

Alias compatível: `POST /api/memory/doctor`.

## `POST /v1/control/memory/overview`

Runs the same lightweight overview used by `clawlite memory overview`, but from the running control plane.

Example request:

```json
{}
```

Example response:

```json
{
  "ok": true,
  "summary": {
    "ok": true,
    "counts": {
      "history": 12,
      "curated": 4,
      "total": 16
    },
    "semantic_coverage": 0.625,
    "proactive_enabled": true,
    "paths": {
      "memory_home": "/home/user/.clawlite/memory",
      "history": "/home/user/.clawlite/state/memory.jsonl",
      "curated": "/home/user/.clawlite/state/memory_curated.json",
      "embeddings": "/home/user/.clawlite/memory/embeddings.json",
      "versions": "/home/user/.clawlite/memory/versions"
    }
  }
}
```

Alias compatível: `POST /api/memory/overview`.

## `POST /v1/control/memory/quality`

Computes and persists the same quality-state report used by `clawlite memory quality`, but from the running control plane.

Example request:

```json
{}
```

Example response:

```json
{
  "ok": true,
  "summary": {
    "ok": true,
    "report": {
      "score": 74,
      "drift": {
        "assessment": "stable"
      },
      "recommendations": [
        "Quality is stable; continue monitoring and periodic memory snapshots."
      ]
    },
    "state": {
      "updated_at": "2026-03-25T00:00:00+00:00",
      "current": {
        "score": 74
      },
      "trend": {
        "available": true,
        "assessment": "stable",
        "window_points": 1
      }
    },
    "quality_state_path": "/home/user/.clawlite/memory/quality-state.json"
  }
}
```

Alias compatível: `POST /api/memory/quality`.

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

Response baseline:
- `tool_count`: total live tool ids exported by the runtime
- `summary`: additive catalog summary with `group_count`, `alias_count`, `ws_method_count`, `cacheable_count`, `custom_timeout_count`, and `largest_group`
- `groups[*].count`: additive count for that tool group
- `groups[*].tools[*].cacheable`: whether the tool participates in result caching
- `groups[*].tools[*].default_timeout_s`: additive per-tool timeout override when the tool publishes one
- `schema[*].cacheable` / `schema[*].default_timeout_s`: the same metadata when `include_schema=true`

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

## `GET /v1/tools/approvals/audit`

Returns the recent bounded in-memory audit trail for tool approval reviews and grant revokes tracked by the running gateway.
Rows are additive and read-only, and keep a compact sanitized `approval_context` instead of replaying raw arguments.
If a gateway token is configured, this endpoint requires that token even when the gateway is otherwise open on loopback.

Query params:
- `action`: optional action filter (`review`, `revoke_grant`, or empty for all)
- `session_id`: optional session filter
- `channel`: optional channel filter
- `request_id`: optional request/grant lineage filter
- `tool`: optional exact tool filter
- `rule`: optional exact approval rule filter
- `limit`: max rows to return

Response baseline:
- `count`: number of returned audit rows
- `changed_count`: rows that changed approval/grant state
- `unchanged_count`: rows that were no-op or denied
- `error_count`: rows that carry an `error`
- `latest_reason`: bounded reason/note/error summary for the latest visible audit row
- `latest_reason_source`: where that latest reason came from (`note`, `error`, `decision`, `status`, or `result`)
- `request_history_request_id`: echoed request drill-down id when one is active
- `request_history_count`: bounded count of history rows for that drilled-down request lineage
- `request_history`: compact bounded request history for the active `request_id`, ignoring the current `action` filter so one request can show review plus revoke lineage together
- `action_counts`: additive counts by action (`review`, `revoke_grant`)
- `status_counts`: additive counts by row status
- `entries`: audit rows with `action`, `status`, `changed`, request/grant identifiers, sanitized `approval_context`, additive `reason_source` / `reason_summary`, and timing fields such as `audit_age_s`

Alias compatível: `GET /api/tools/approvals/audit`.

## `GET /v1/tools/approvals/audit/export`

Exports the current bounded filtered approval-audit slice as NDJSON (`application/x-ndjson`), one row per line.
This route reuses the same filters as `GET /v1/tools/approvals/audit`, but returns text suitable for handoff or archival instead of the JSON summary envelope.
If a gateway token is configured, this endpoint requires that token even when the gateway is otherwise open on loopback.

Query params:
- `action`: optional action filter (`review`, `revoke_grant`, or empty for all)
- `session_id`: optional session filter
- `channel`: optional channel filter
- `request_id`: optional request/grant lineage filter
- `tool`: optional exact tool filter
- `rule`: optional exact approval rule filter
- `limit`: max rows to export

Response baseline:
- body: UTF-8 NDJSON, one compact audit row per line
- `Content-Type`: `application/x-ndjson`
- `Content-Disposition`: attachment filename hint for the exported audit slice

Alias compatível: `GET /api/tools/approvals/audit/export`.

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
  "rule": "browser:evaluate",
  "request_id": "7f4b0a3c91d2a6ef",
  "scope": "exact"
}
```

Any field may be omitted to widen the match:
- include `request_id` + `scope="exact"` to revoke one exact reviewed grant instead of every grant sharing the same session/channel/rule
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
  `in_flight`, `by_method`, `by_path`, `by_status`, `last_request_id`,
  `last_request_method`, `last_request_path`, `last_request_started_at`,
  `last_error_request_id`, `last_error_method`, `last_error_path`,
  `last_error_at`, `last_error_status`, `last_error_code`,
  `last_error_message` e `latency_ms` (`count`, `min`, `max`, `avg`).
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
- Essa credencial derivada é aceita apenas nas superfícies de dashboard/control-plane que optam por ela (`/api/status`, `/api/dashboard/state`, `/api/diagnostics`, `/api/token`, `/api/message`, `/api/tools/catalog`, `/api/provider/status`, `/v1/control/*`, e `WS /ws`).
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
