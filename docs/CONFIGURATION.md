# Configuration

Default file: `~/.clawlite/config.json`

Both snake_case and camelCase keys are accepted everywhere. Unknown keys are silently ignored.

## Quick start (minimum config)

```json
{
  "agents": { "defaults": { "model": "gemini/gemini-2.5-flash" } },
  "providers": { "gemini": { "api_key": "YOUR_KEY" } }
}
```

---

## Top-level fields

| Field | Type | Default | Description |
|---|---|---|---|
| `workspace_path` | string | `~/.clawlite/workspace` | Working directory for agent file tools |
| `state_path` | string | `~/.clawlite/state` | Persistent state (sessions, memory DB) |

---

## `agents.defaults`

| Field | Default | Description |
|---|---|---|
| `model` | `gemini/gemini-2.5-flash` | LiteLLM model string |
| `max_tokens` | `8192` | Max tokens per LLM call |
| `temperature` | `0.1` | Sampling temperature |
| `max_tool_iterations` | `40` | Max tool calls per agent turn |
| `memory_window` | `100` | Recent messages kept in context |
| `session_retention_messages` | `2000` | Max messages per session (null = unlimited) |
| `reasoning_effort` | `null` | `"low"`, `"medium"`, `"high"`, or null |
| `provider` | `"auto"` | Provider hint (overridden by model prefix) |

### `agents.defaults.memory`

| Field | Default | Description |
|---|---|---|
| `semantic_search` | `false` | Enable semantic search on memory retrieval |
| `auto_categorize` | `false` | Auto-tag memories |
| `proactive` | `false` | Proactive memory injection |
| `proactive_retry_backoff_s` | `300.0` | Backoff between proactive retries |
| `proactive_max_retry_attempts` | `3` | Max proactive retries |
| `emotional_tracking` | `false` | Track emotional context in memories |
| `backend` | `"sqlite"` | `"sqlite"` or `"pgvector"` |
| `pgvector_url` | `""` | Postgres URL for pgvector backend |

---

## `providers`

Each key is a provider name. Built-in keys: `openrouter`, `gemini`, `openai`, `anthropic`, `deepseek`, `groq`, `ollama`, `vllm`, `custom`. Any other key is a custom provider.

```json
"providers": {
  "gemini":     { "api_key": "AIza..." },
  "openai":     { "api_key": "sk-..." },
  "anthropic":  { "api_key": "sk-ant-..." },
  "openrouter": { "api_key": "sk-or-..." },
  "mycompany":  { "api_key": "...", "api_base": "https://api.mycompany.com/v1" }
}
```

Per-provider fields: `api_key`, `api_base`, `extra_headers` (dict).

---

## `provider` (advanced LiteLLM settings)

| Field | Default | Description |
|---|---|---|
| `model` | `gemini/gemini-2.5-flash` | Sync'd with `agents.defaults.model` |
| `litellm_api_key` | `""` | Global API key override for LiteLLM |
| `litellm_base_url` | `https://api.openai.com/v1` | Global base URL override |
| `fallback_model` | `""` | Fallback model on primary failure |
| `retry_max_attempts` | `3` | Max LLM call retries |
| `retry_initial_backoff_s` | `0.5` | Initial retry backoff |
| `retry_max_backoff_s` | `8.0` | Maximum retry backoff |
| `retry_jitter_s` | `0.2` | Retry jitter |
| `circuit_failure_threshold` | `3` | Failures before circuit opens |
| `circuit_cooldown_s` | `30.0` | Circuit breaker cooldown |

These settings are applied by the live gateway runtime. `fallback_model` is honored during provider construction, and startup only fails fast when every configured local runtime candidate is unavailable.

---

## `gateway`

| Field | Default | Description |
|---|---|---|
| `host` | `127.0.0.1` | Listen address |
| `port` | `8787` | Listen port |

### `gateway.auth`

| Field | Default | Description |
|---|---|---|
| `mode` | `"off"` | `"off"`, `"optional"`, or `"required"` |
| `token` | `""` | Bearer token |
| `allow_loopback_without_auth` | `true` | Skip auth for 127.0.0.1 connections |
| `header_name` | `"Authorization"` | Auth header name |
| `query_param` | `"token"` | URL query param for token |
| `protect_health` | `false` | Require auth on `/health` endpoint |

### `gateway.heartbeat`

| Field | Default | Description |
|---|---|---|
| `enabled` | `true` | Enable heartbeat pings |
| `interval_s` | `1800` | Heartbeat interval in seconds (min 5) |

### `gateway.supervisor`

| Field | Default | Description |
|---|---|---|
| `enabled` | `true` | Enable supervisor watchdog |
| `interval_s` | `20` | Supervisor check interval |
| `cooldown_s` | `30` | Cooldown between supervisor actions |

### `gateway.autonomy`

| Field | Default | Description |
|---|---|---|
| `enabled` | `false` | Enable autonomous action loop |
| `interval_s` | `900` | Check interval |
| `action_policy` | `"balanced"` | `"balanced"` or `"conservative"` |
| `environment_profile` | `"dev"` | `"dev"`, `"staging"`, or `"prod"` (prod forces conservative defaults) |
| `action_cooldown_s` | `120.0` | Min seconds between actions |
| `action_rate_limit_per_hour` | `20` | Max actions per hour |
| `min_action_confidence` | `0.55` | Minimum confidence to act (0.0-1.0) |
| `max_actions_per_run` | `1` | Max actions per cycle |
| `timeout_s` | `45.0` | Action execution timeout |
| `max_queue_backlog` | `200` | Max pending queue depth |
| `session_id` | `"autonomy:system"` | Session ID for autonomous runs |
| `audit_export_path` | `""` | Path to export audit log |
| `audit_max_entries` | `200` | Max audit log entries |

**Advanced tuning fields:** `tuning_loop_enabled`, `tuning_loop_interval_s`, `tuning_loop_timeout_s`, `tuning_loop_cooldown_s`, `tuning_degrading_streak_threshold`, `tuning_recent_actions_limit`, `tuning_error_backoff_s`, `self_evolution_enabled`, `self_evolution_cooldown_s`.

---

## `channels`

### `channels.telegram`

| Field | Default | Description |
|---|---|---|
| `enabled` | `false` | Enable Telegram channel |
| `token` | `""` | Bot token from @BotFather |
| `allow_from` | `[]` | Allowed user IDs (empty = all) |
| `mode` | `"polling"` | `"polling"` or `"webhook"` |
| `dm_policy` | `"open"` | DM access: `"open"` or `"allowlist"` |
| `group_policy` | `"open"` | Group access: `"open"` or `"allowlist"` |
| `transcribe_voice` | `true` | Transcribe voice messages |
| `transcription_language` | `"pt"` | Whisper language hint |
| `transcription_model` | `"whisper-large-v3-turbo"` | Whisper model |
| `transcription_base_url` | `https://api.groq.com/openai/v1` | Whisper API base |
| `webhook_enabled` | `false` | Use webhook instead of polling |
| `webhook_url` | `""` | Public webhook URL |
| `webhook_path` | `"/api/webhooks/telegram"` | Webhook path |

### `channels.discord`

| Field | Default | Description |
|---|---|---|
| `enabled` | `false` | Enable Discord channel |
| `token` | `""` | Bot token |
| `allow_from` | `[]` | Allowed user/guild IDs |
| `typing_enabled` | `true` | Send typing indicators |

### `channels.slack`

| Field | Default | Description |
|---|---|---|
| `enabled` | `false` | Enable Slack channel |
| `bot_token` | `""` | Bot OAuth token |
| `app_token` | `""` | App-level token (for Socket Mode) |
| `allow_from` | `[]` | Allowed user IDs |

### `channels.email`

| Field | Default | Description |
|---|---|---|
| `enabled` | `false` | Enable email channel |
| `imap_host` | `""` | IMAP server hostname |
| `imap_port` | `993` | IMAP port |
| `imap_user` | `""` | IMAP username |
| `imap_password` | `""` | IMAP password |
| `imap_use_ssl` | `true` | Use SSL for IMAP |
| `smtp_host` | `""` | SMTP server hostname |
| `smtp_port` | `465` | SMTP port |
| `smtp_user` | `""` | SMTP username |
| `smtp_password` | `""` | SMTP password |
| `allow_from` | `[]` | Allowed sender addresses |
| `poll_interval_s` | `30.0` | IMAP poll interval |

---

## `tools.web`

| Field | Default | Description |
|---|---|---|
| `proxy` | `""` | HTTP proxy URL |
| `timeout` | `15.0` | Fetch timeout in seconds |
| `search_timeout` | `10.0` | Search timeout in seconds |
| `max_redirects` | `5` | Max HTTP redirects |
| `max_chars` | `12000` | Max response characters |
| `block_private_addresses` | `true` | Block RFC-1918 addresses |
| `brave_api_key` | `""` | Brave Search API key |
| `brave_base_url` | `https://api.search.brave.com/...` | Brave Search endpoint |
| `searxng_base_url` | `""` | SearXNG base URL (alternative search) |
| `allowlist` | `[]` | Allowed URL patterns |
| `denylist` | `[]` | Denied URL patterns |

## `tools.exec`

| Field | Default | Description |
|---|---|---|
| `timeout` | `60` | Command timeout in seconds |
| `path_append` | `""` | Extra PATH entries |
| `deny_patterns` | `[]` | Blocked command patterns (regex) |
| `allow_patterns` | `[]` | Allowed command patterns (regex) |
| `deny_path_patterns` | `[]` | Blocked path patterns |
| `allow_path_patterns` | `[]` | Allowed path patterns |

## `tools.mcp`

| Field | Default | Description |
|---|---|---|
| `default_timeout_s` | `20.0` | Default MCP call timeout |
| `servers` | `{}` | Named MCP server configs |

Each server under `tools.mcp.servers`:

```json
"tools": {
  "mcp": {
    "servers": {
      "my_server": {
        "url": "https://mcp.example.com",
        "timeout_s": 30.0,
        "headers": { "Authorization": "Bearer token" }
      }
    }
  }
}
```

---

## Environment variables

| Variable | Effect |
|---|---|
| `CLAWLITE_MODEL` | Override `agents.defaults.model` |
| `CLAWLITE_WORKSPACE` | Override `workspace_path` |
| `CLAWLITE_LITELLM_BASE_URL` | Override `provider.litellm_base_url` |
| `CLAWLITE_LITELLM_API_KEY` | Override `provider.litellm_api_key` |
| `CLAWLITE_GATEWAY_HOST` | Override `gateway.host` |
| `CLAWLITE_GATEWAY_PORT` | Override `gateway.port` |
| `CLAWLITE_GATEWAY_AUTH_MODE` | Override `gateway.auth.mode` |
| `CLAWLITE_GATEWAY_AUTH_TOKEN` | Override `gateway.auth.token` |
| `CLAWLITE_CONFIG_STRICT` | Set `1` to reject unknown config keys |

---

## Compatibility notes

**camelCase accepted:** All fields accept camelCase equivalents (e.g. `maxTokens`, `intervalS`, `blockPrivateAddresses`).

**Legacy fields migrated automatically:**
- `gateway.token` → `gateway.auth.token` (and sets mode to `required`)
- `scheduler.heartbeat_interval_seconds` → `gateway.heartbeat.interval_s`

**Model sync:** Setting `provider.model` or `agents.defaults.model` keeps both in sync automatically.
