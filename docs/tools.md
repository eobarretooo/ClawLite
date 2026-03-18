# Tools

ClawLite registers 30 tool IDs at gateway startup, including compatibility aliases. Agents can call them during normal turns, and clients can inspect the live catalog from the gateway.

## Inspect the Live Catalog

HTTP:

```bash
curl -sS http://127.0.0.1:8787/v1/tools/catalog
curl -sS "http://127.0.0.1:8787/v1/tools/catalog?include_schema=true"
```

WebSocket clients can request `tools.catalog`.

If gateway auth is enabled, call the catalog with the same bearer token used for `/v1/chat` and `/v1/diagnostics`.

## Compatibility Aliases

These aliases are exported on purpose so prompts and clients can use older names safely:

| Alias | Canonical tool |
| --- | --- |
| `bash` | `exec` |
| `apply-patch` | `apply_patch` |
| `read_file` | `read` |
| `write_file` | `write` |
| `edit_file` | `edit` |
| `memory_recall` | `memory_search` |

## Tool Config

The runtime-level tool config lives under `tools` in `~/.clawlite/config.json`:

```json
{
  "tools": {
    "restrict_to_workspace": false,
    "exec": {
      "timeout": 60,
      "path_append": "",
      "deny_patterns": [],
      "allow_patterns": [],
      "deny_path_patterns": [],
      "allow_path_patterns": []
    },
    "web": {
      "proxy": "",
      "timeout": 15.0,
      "search_timeout": 10.0,
      "max_redirects": 5,
      "max_chars": 12000,
      "block_private_addresses": true,
      "brave_api_key": "",
      "brave_base_url": "https://api.search.brave.com/res/v1/web/search",
      "searxng_base_url": "",
      "allowlist": [],
      "denylist": []
    },
    "mcp": {
      "default_timeout_s": 20.0,
      "policy": {
        "allowed_schemes": ["http", "https"],
        "allowed_hosts": [],
        "denied_hosts": []
      },
      "servers": {}
    },
    "loop_detection": {
      "enabled": false,
      "history_size": 20,
      "repeat_threshold": 3,
      "critical_threshold": 6
    },
    "safety": {
      "enabled": true,
      "risky_tools": ["browser", "exec", "run_skill", "web_fetch", "web_search", "mcp"],
      "risky_specifiers": [],
      "approval_specifiers": [],
      "approval_channels": [],
      "approval_grant_ttl_s": 900.0,
      "blocked_channels": [],
      "allowed_channels": [],
      "profile": "",
      "profiles": {},
      "by_agent": {},
      "by_channel": {}
    }
  }
}
```

Important behavior:

- `restrict_to_workspace` applies to file tools, `exec`, `process`, and `apply_patch`.
- `tools.safety` can allow, require approval, or block tools/specifiers per channel or per agent.
- `exec` has deny-pattern guards even when workspace restriction is off.
- `web_fetch` blocks private and local targets by default.
- `mcp` only allows `http` and `https`, and it denies private/local addresses unless explicitly allowed.

Example granular policy:

```json
{
  "tools": {
    "safety": {
      "enabled": true,
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

Specifier rules are lowercase and support `tool:*` wildcards. Common derived forms include:

- `browser:navigate`, `browser:evaluate`
- `browser:navigate:host:example-com`
- `web_fetch:host:example-com`
- `run_skill:github`, `run_skill:weather`
- `exec:git`, `exec:cmd:git`
- `exec:shell`, `exec:shell-meta`
- `exec:env`, `exec:env-key:git-ssh-command`
- `exec:cwd`

You can preview the effective decision locally without running the tool:

```bash
clawlite tools safety browser --session-id telegram:1 --channel telegram --args-json '{"action":"evaluate"}'
clawlite tools safety browser --session-id telegram:1 --channel telegram --args-json '{"action":"navigate","url":"https://example.com"}'
```

The preview returns a `decision` of `allow`, `approval`, or `block`.

For `exec`, ClawLite now also derives approval-friendly specifiers from shell meta syntax, env override keys, and explicit cwd overrides. That lets operators write tighter rules such as `exec:shell` or `exec:env-key:git-ssh-command` instead of approving every `exec` call. The runtime also rejects dangerous env override pivots like `PATH`, `NODE_OPTIONS`, `DYLD_*`, `LD_*`, `GIT_CONFIG_*`, and `GIT_SSH_COMMAND`.

On live Telegram and Discord turns, approval-gated tool calls now attach native approve/reject controls to the reply. Approving creates a temporary grant scoped to the reviewed request fingerprint plus the same session, channel, and matched safety specifier; the operator then retries the original request manually.

The same approval queue is now inspectable over the gateway and CLI:

```bash
clawlite tools approvals --include-grants
clawlite tools approve <request_id> --actor ops --note "approved after review"
clawlite tools reject <request_id> --actor ops --note "use a safer command"
clawlite tools revoke-grant --session-id telegram:1 --channel telegram --rule browser:evaluate
```

`tools approvals` returns live request snapshots (`pending`, `approved`, `rejected`, or `all`) and can include active grants with their remaining TTL plus `scope` / `request_id` metadata. `tools revoke-grant` removes one or more of those temporary grants early, so operators do not have to wait for TTL expiry when they want to close the window immediately. This mirrors the channel-native operator buttons without forcing the review to happen inside Telegram or Discord.

For live catalog inspection through the gateway:

```bash
clawlite tools catalog --include-schema
clawlite tools show bash
```

## Files

| Tool | What it does | Typical use |
| --- | --- | --- |
| `read` | Reads a file as text bytes, with optional `offset` and `limit` | Open part of a file without editing it |
| `write` | Atomically writes a full text file | Create or replace a file |
| `edit` | Replaces one unique `search` string with `replace` | Small, exact file edits |
| `apply_patch` | Applies OpenCode-style patch envelopes with add/update/delete/move support | Multi-file or diff-style edits |
| `list_dir` | Lists direct children of a directory | Explore a folder quickly |

Useful arguments:

- `read`: `path`, `offset`, `limit`, `allow_large_file`
- `write`: `path`, `content`, `allow_large_file`
- `edit`: `path`, `search`, `replace`, `allow_large_file`
- `apply_patch`: `input` or `patch`
- `list_dir`: `path`

## Runtime

| Tool | What it does | Typical use |
| --- | --- | --- |
| `exec` | Runs a shell command without `shell=True` | `git status`, `pytest`, `python script.py` |
| `process` | Manages background process sessions | Start a long-running job and poll logs later |

Useful arguments:

- `exec`: `command`, `timeout`, `max_output_chars`, optional `cwd` / `workdir`, optional `env`
- `process`: `action`, `session_id`, `command`, `data`, `offset`, `limit`, `timeout`

`process.action` supports `start`, `list`, `poll`, `log`, `write`, `kill`, `remove`, and `clear`.

## Web

| Tool | What it does | Typical use |
| --- | --- | --- |
| `web_fetch` | Fetches a URL and returns extracted text/markdown/html | Pull the contents of a page or document |
| `web_search` | Searches the web and returns snippets/results | Gather links before deeper fetches |

Useful arguments:

- `web_fetch`: `url`, `timeout`, `mode`, `max_chars`
- `web_search`: `query`, `limit`, `timeout`

Search backend order is DuckDuckGo first, then Brave if configured, then SearXNG if configured.

## Memory

| Tool | What it does | Typical use |
| --- | --- | --- |
| `memory_search` | Retrieves related memory snippets with provenance | Pull relevant long-term context before answering |
| `memory_get` | Reads workspace memory markdown files only | Inspect `MEMORY.md` or workspace memory notes |
| `memory_learn` | Writes a durable memory note | Store a stable fact or preference |
| `memory_forget` | Deletes memory by ref, query, or source | Remove stale or unwanted memory items |
| `memory_analyze` | Returns memory footprint and category stats | Inspect coverage, reasoning layers, and examples |

Useful arguments:

- `memory_search`: `query`, `limit`, `include_metadata`, `reasoning_layers`, `min_confidence`
- `memory_get`: `path`, `from`, `lines`
- `memory_learn`: `text`, `source`, `reasoning_layer`, `confidence`
- `memory_forget`: `ref`, `query`, `source`, `limit`, `dry_run`
- `memory_analyze`: `query`, `limit`, `include_examples`

Notes:

- `memory_search` and `memory_recall` are the same implementation.
- `memory_get` is intentionally restricted to `MEMORY.md` and `workspace/memory/*.md`.
- `memory_learn` is subject to the current memory integration policy.

## Sessions and Subagents

| Tool | What it does | Typical use |
| --- | --- | --- |
| `sessions_list` | Lists saved sessions with previews | See what sessions exist |
| `sessions_history` | Returns the message history for one session | Inspect a specific session timeline |
| `sessions_send` | Sends a message into another session | Continue work in an existing session |
| `sessions_spawn` | Delegates one or more tasks into target sessions | Parallelize work across sessions |
| `subagents` | Lists, resumes, kills, or sweeps subagent runs | Manage delegated work |
| `session_status` | Returns a status card for one session | Quick health check for a session |
| `agents_list` | Lists the main agent and subagent inventory | Inspect agent/subagent state |
| `spawn` | Starts a background subagent from a task string | Fire off independent work |

Useful arguments:

- `sessions_list`: `limit`
- `sessions_history`: `session_id`, `limit`, `include_tools`, `include_subagents`, `subagent_limit`
- `sessions_send`: `session_id`, `message`, `timeout`
- `sessions_spawn`: `task` or `tasks`, `session_id`, `target_sessions`, `share_scope`
- `subagents`: `action`, `session_id`, `group_id`, `run_id`, `all`, `limit`
- `session_status`: `session_id`
- `agents_list`: `session_id`, `active_only`, `include_runs`, `limit`
- `spawn`: `task`

Notes:

- `sessions_send` and `sessions_spawn` can add continuation context from memory retrieval.
- `spawn` and `run_skill` can be blocked when memory quality policy disallows delegation.

## Messaging, Automation, Nodes, and Skills

| Tool | What it does | Typical use |
| --- | --- | --- |
| `message` | Sends proactive outbound messages to channels | Push a message to Telegram, Discord, WhatsApp, Email, or Slack |
| `discord_admin` | Inspects and administers Discord guild structure | List guilds, channels, roles, or build server layout |
| `cron` | Adds, removes, runs, lists, enables, or disables scheduled jobs | Schedule a later reminder or recurring task |
| `mcp` | Calls tools from configured MCP servers | Reach remote tool servers through the registry |
| `run_skill` | Executes a discovered `SKILL.md` binding | Invoke built-in or workspace skills |

Useful arguments:

- `message`: `channel`, `target`, `text`, `action`, `message_id`, `reply_to_message_id`, `emoji`, `topic_name`, `metadata`, `media`, `buttons`
- `discord_admin`: `action`, `guild_id`, `name`, `kind`, `parent_id`, `topic`, `permissions`, `reason`, `template`
- `cron`: `action`, `expression`, `every_seconds`, `cron_expr`, `at`, `timezone`, `prompt`, `name`, `session_id`, `channel`, `target`, `force`, `run_once`
- `mcp`: `server`, `tool`, `arguments`, `timeout_s`
- `run_skill`: `name`, `input`, `args`, `timeout`, `query`, `location`, `tool_arguments`

Notes:

- `message.action` defaults to `send`.
- Telegram-only `message` actions are `reply`, `edit`, `delete`, `react`, and `create_topic`.
- `discord_admin` expects a configured `channels.discord.token`; server mutations also require matching Discord bot permissions.
- `mcp` accepts namespaced tools like `server::tool`.
- `run_skill` can execute command-based skills, script shims, and tool-backed skills.

## Example Calls

Read a file:

```json
{"name":"read","arguments":{"path":"README.md","limit":4000}}
```

Run a command:

```json
{"name":"exec","arguments":{"command":"python -m pytest tests -q","timeout":120}}
```

Run a command from a specific working directory:

```json
{"name":"exec","arguments":{"command":"python -m pytest tests -q","cwd":"./workspace","timeout":120}}
```

Start and poll a background process:

```json
{"name":"process","arguments":{"action":"start","session_id":"pytest","command":"python -m pytest tests -q"}}
{"name":"process","arguments":{"action":"poll","session_id":"pytest"}}
```

Send a proactive Telegram reply:

```json
{"name":"message","arguments":{"channel":"telegram","target":"123456789","text":"Build finished.","action":"send"}}

For Discord, prefer typed targets:

```json
{"name":"message","arguments":{"channel":"discord","target":"channel:112233445566778899","text":"Build finished.","action":"send"}}
```

```json
{"name":"message","arguments":{"channel":"discord","target":"user:746561804100042812","text":"Can you review this?","action":"send"}}
```

List accessible Discord guilds:

```json
{"name":"discord_admin","arguments":{"action":"list_guilds"}}
```

Apply a Discord server layout:

```json
{"name":"discord_admin","arguments":{"action":"apply_layout","guild_id":"123456789012345678","reason":"initial server setup","template":{"roles":[{"name":"Admin","permissions":"8"},{"name":"Moderator"}],"categories":[{"name":"Info","channels":[{"name":"rules","kind":"text","topic":"Leia antes de participar"},{"name":"announcements","kind":"text"}]},{"name":"Voice","channels":[{"name":"General","kind":"voice","user_limit":20}]}]}}}
```

Call an MCP tool:

```json
{"name":"mcp","arguments":{"tool":"docs::search","arguments":{"query":"gateway auth"}}}
```

## browser

Control a headless Chromium browser via Playwright. Actions: `navigate`, `click`, `fill`, `screenshot`, `evaluate`, `close`.

`navigate` now applies the same basic host policy model as `web_fetch`: only `http` / `https`, optional allowlist / denylist, and private-address blocking by default.
The safety registry also derives host-aware specifiers for `web_fetch` and `browser:navigate`, so you can target rules like `web_fetch:host:example-com` or `browser:navigate:host:example-com` instead of approving the whole tool.

Install with `pip install -e ".[browser]"`, then run `python -m playwright install chromium` once.

```json
{"name":"browser","arguments":{"action":"navigate","url":"https://example.com"}}
```

## tts

Convert text to speech using edge-tts. Returns path to an MP3 file.

Install with `pip install -e ".[media]"`.

```json
{"name":"tts","arguments":{"text":"Hello world","voice":"en-US-AriaNeural","rate":"+0%"}}
```

## pdf_read

Extract text from a PDF file (local path or HTTPS URL). Supports page ranges.

Install with `pip install -e ".[media]"`.

```json
{"name":"pdf_read","arguments":{"path":"/workspace/doc.pdf","pages":"1-5"}}
```
