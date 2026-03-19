# Configuration

Default file: `~/.clawlite/config.json`

Both snake_case and camelCase keys are accepted everywhere. Unknown keys are silently ignored.

Profiles are layered on top of the base file. For example, `clawlite --config ./config.yaml --profile prod status` loads:

1. `config.yaml`
2. `config.prod.yaml` or `config.prod.json` when present beside the base file
3. environment variables

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
| `context_token_budget` | `7000` | Total prompt/context token budget used by the prompt shaper |
| `semantic_history_summary_enabled` | `false` | Opt-in LLM compaction for trimmed conversation history after deterministic trimming |
| `tool_result_compaction_enabled` | `false` | Opt-in LLM compaction for oversized text-like tool results before they re-enter model history |
| `tool_result_compaction_threshold_chars` | `3200` | Minimum tool-result size before compaction is attempted |
| `workspace_prompt_file_max_bytes` | `16384` | Per-file byte ceiling for prompt-ingested workspace markdown before skip/truncate rules apply |

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

Each key is a provider name. Built-in typed keys include `openrouter`, `gemini`, `openai`, `anthropic`, `deepseek`, `groq`, `ollama`, `vllm`, and `custom`. Additional provider blocks such as `azure_openai`, `aihubmix`, `siliconflow`, or `cerebras` are stored in the dynamic provider map automatically.

```json
"providers": {
  "gemini":     { "api_key": "AIza..." },
  "openai":     { "api_key": "sk-..." },
  "azure_openai": { "api_key": "azure-key", "api_base": "https://example-resource.openai.azure.com/openai/v1" },
  "anthropic":  { "api_key": "sk-ant-..." },
  "openrouter": { "api_key": "sk-or-..." },
  "mycompany":  { "api_key": "...", "api_base": "https://api.mycompany.com/v1" }
}
```

Per-provider fields: `api_key`, `api_base`, `extra_headers` (dict).

---

## `skills`

Skill config is read from the raw config payload, so `skills.entries` can carry per-skill overrides even though the typed runtime schema does not model every custom field yet.

```yaml
skills:
  entries:
    gh-issues:
      enabled: true
      apiKey: ghp_example_token
    env-skill:
      env:
        CUSTOM_TOKEN: secret-value
```

Supported fields:

| Field | Description |
|---|---|
| `allowBundled` | Optional allowlist for builtin skills only; workspace and marketplace skills stay eligible |
| `entries.<skill>.enabled` | Disable a skill without editing the skill itself |
| `entries.<skill>.env` | Inject host env vars into `command` skills when the variable is not already set |
| `entries.<skill>.apiKey` | Convenience field for skills declaring `metadata.openclaw.primaryEnv` |

Operator shortcut: `clawlite skills config <name> --api-key ... --env KEY=VALUE --enable` writes those overrides back to the active config or profile file.

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
| `startup_timeout_default_s` | `15.0` | Default startup timeout per subsystem |
| `startup_timeout_channels_s` | `30.0` | Startup timeout for channel manager bootstrap |
| `startup_timeout_autonomy_s` | `10.0` | Startup timeout for autonomy loop bootstrap |
| `startup_timeout_supervisor_s` | `5.0` | Startup timeout for supervisor bootstrap |

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
| `self_evolution_branch_prefix` | `"self-evolution"` | Prefix used for isolated self-evolution git branches |
| `self_evolution_require_approval` | `false` | Include approval-ready operator notice payloads for committed self-evolution runs |

**Advanced tuning fields:** `tuning_loop_enabled`, `tuning_loop_interval_s`, `tuning_loop_timeout_s`, `tuning_loop_cooldown_s`, `tuning_degrading_streak_threshold`, `tuning_recent_actions_limit`, `tuning_error_backoff_s`, `self_evolution_enabled`, `self_evolution_cooldown_s`, `self_evolution_branch_prefix`, `self_evolution_require_approval`.

### `gateway.websocket`

| Field | Default | Description |
|---|---|---|
| `coalesce_enabled` | `true` | Coalesce small provider stream chunks into fewer `chat.chunk` WS events |
| `coalesce_min_chars` | `24` | Minimum buffered chars before newline/sentence coalescing is eligible to flush |
| `coalesce_max_chars` | `120` | Hard flush ceiling for buffered chunk text before the next `chat.chunk` event |

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
| `status` | `""` | Optional static Discord presence status: `online`, `idle`, `dnd`, or `invisible` |
| `activity` | `""` | Optional Discord activity text |
| `activity_type` | `4` | Discord activity type (`0-5`); `4` is custom status |
| `activity_url` | `""` | Optional streaming URL when `activity_type=1` |
| `auto_presence` | `{}` | Optional auto-presence loop config (`enabled`, `interval_s`, `min_update_interval_s`, `healthy_text`, `degraded_text`, `exhausted_text`) |

### `channels.slack`

| Field | Default | Description |
|---|---|---|
| `enabled` | `false` | Enable Slack channel |
| `bot_token` | `""` | Bot OAuth token |
| `app_token` | `""` | App-level token (for Socket Mode) |
| `allow_from` | `[]` | Allowed user IDs |
| `send_retry_attempts` | `3` | Max outbound retry attempts |
| `send_retry_after_default_s` | `1.0` | Default retry delay when Slack omits `Retry-After` |
| `socket_mode_enabled` | `true` | Start inbound Socket Mode worker when `app_token` is present |
| `socket_backoff_base_s` | `1.0` | Base reconnect delay for Socket Mode |
| `socket_backoff_max_s` | `30.0` | Max reconnect delay for Socket Mode |
| `typing_enabled` | `true` | Enables the working-indicator lifecycle |
| `working_indicator_enabled` | `true` | Adds/removes a reaction while a turn is running |
| `working_indicator_emoji` | `"hourglass_flowing_sand"` | Emoji name used for the working indicator |

### `channels.whatsapp`

| Field | Default | Description |
|---|---|---|
| `enabled` | `false` | Enable WhatsApp channel |
| `allow_from` | `[]` | Allowed sender ids |
| `bridge_url` | `"ws://localhost:3001"` | Bridge URL normalized to HTTP `/send` and `/typing` |
| `bridge_token` | `""` | Optional bearer token for the bridge |
| `timeout_s` | `10.0` | Bridge HTTP timeout |
| `webhook_path` | `"/api/webhooks/whatsapp"` | Gateway webhook path |
| `webhook_secret` | `""` | Shared secret for inbound webhook auth |
| `send_retry_attempts` | `1` | Max outbound retry attempts (set higher explicitly for flaky bridges) |
| `send_retry_after_default_s` | `1.0` | Default retry delay for 429/5xx bridge responses |
| `typing_enabled` | `true` | Enables bridge typing keepalive |
| `typing_interval_s` | `4.0` | Seconds between `/typing` calls |

### `channels.irc`

| Field | Default | Description |
|---|---|---|
| `enabled` | `false` | Enable IRC channel |
| `host` | `"irc.libera.chat"` | IRC server hostname |
| `port` | `6697` | IRC server port |
| `nick` | `"clawlite"` | IRC nick |
| `username` | `"clawlite"` | IRC username |
| `realname` | `"ClawLite"` | IRC realname / gecos |
| `channels_to_join` | `[]` | Channels joined on startup |
| `use_ssl` | `true` | Use TLS for the initial connection |
| `connect_timeout_s` | `10.0` | Connect timeout in seconds |

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

## `tools`

| Field | Default | Description |
|---|---|---|
| `default_timeout_s` | `20.0` | Global default timeout for tool execution when no tool-specific timeout overrides it |
| `timeouts` | `{}` | Per-tool timeout overrides such as `{"exec": 90, "browser": 45}` |

## `tools.safety`

| Field | Default | Description |
|---|---|---|
| `enabled` | `true` | Enables runtime tool safety enforcement |
| `risky_tools` | `["browser","exec","run_skill","web_fetch","web_search","mcp"]` | Whole-tool risky baseline |
| `risky_specifiers` | `[]` | Granular risky operations like `browser:evaluate` or `run_skill:github` |
| `approval_specifiers` | `[]` | Tool/specifier rules that should require approval instead of running immediately |
| `approval_channels` | `[]` | Channels where approval-gated rules should pause/fail closed |
| `approval_grant_ttl_s` | `900.0` | Lifetime in seconds for a temporary grant after an operator approves a tool request |
| `blocked_channels` | `[]` | Channels where risky entries are blocked |
| `allowed_channels` | `[]` | Channels that can still use risky entries even when blocked elsewhere |
| `profile` | `""` | Active safety profile |
| `profiles` | `{}` | Named overrides for risky lists and channel gates |
| `by_agent` | `{}` | Per-agent overrides |
| `by_channel` | `{}` | Per-channel overrides |

Example:

```json
{
  "tools": {
    "safety": {
      "risky_tools": ["exec"],
      "risky_specifiers": ["browser:evaluate", "run_skill:github", "exec:git", "exec:shell"],
      "approval_specifiers": ["browser", "web_fetch", "exec:env-key:git-ssh-command"],
      "approval_channels": ["telegram", "discord"],
      "approval_grant_ttl_s": 600,
      "blocked_channels": ["telegram", "discord"],
      "allowed_channels": ["cli"]
    }
  }
}
```

`risky_tools` blocks the whole tool. `risky_specifiers` is more precise and supports `tool:*` wildcards. `approval_specifiers` uses the same matcher, but returns an approval-required result instead of running immediately. On Telegram and Discord, those requests now surface native approve/reject controls, and approval grants only apply to the same session/channel/specifier for `approval_grant_ttl_s` seconds. For `exec`, derived specifiers include the resolved command token (`exec:git`, `exec:cmd:git`), shell-wrapper usage (`exec:shell` / `exec:shell-meta`), env override keys (`exec:env-key:git-ssh-command`), and explicit cwd overrides (`exec:cwd`).

---

## Environment variables

| Variable | Effect |
|---|---|
| `CLAWLITE_MODEL` | Override `agents.defaults.model` |
| `CLAWLITE_WORKSPACE` | Override `workspace_path` |
| `CLAWLITE_LITELLM_BASE_URL` | Override `provider.litellm_base_url` |
| `CLAWLITE_LITELLM_API_KEY` | Override `provider.litellm_api_key` |
| `CLAWLITE_BUS_BACKEND` | Override `bus.backend` |
| `CLAWLITE_BUS_REDIS_URL` | Override `bus.redis_url` |
| `CLAWLITE_BUS_REDIS_PREFIX` | Override `bus.redis_prefix` |
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
