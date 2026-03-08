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
      "risky_tools": ["exec", "run_skill", "web_fetch", "web_search", "mcp"],
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
- `tools.safety` can block risky tools per channel or per agent.
- `exec` has deny-pattern guards even when workspace restriction is off.
- `web_fetch` blocks private and local targets by default.
- `mcp` only allows `http` and `https`, and it denies private/local addresses unless explicitly allowed.

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

- `exec`: `command`, `timeout`, `max_output_chars`
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
| `cron` | Adds, removes, runs, lists, enables, or disables scheduled jobs | Schedule a later reminder or recurring task |
| `mcp` | Calls tools from configured MCP servers | Reach remote tool servers through the registry |
| `run_skill` | Executes a discovered `SKILL.md` binding | Invoke built-in or workspace skills |

Useful arguments:

- `message`: `channel`, `target`, `text`, `action`, `message_id`, `reply_to_message_id`, `emoji`, `topic_name`, `metadata`, `media`, `buttons`
- `cron`: `action`, `expression`, `every_seconds`, `cron_expr`, `at`, `timezone`, `prompt`, `name`, `session_id`, `channel`, `target`, `force`, `run_once`
- `mcp`: `server`, `tool`, `arguments`, `timeout_s`
- `run_skill`: `name`, `input`, `args`, `timeout`, `query`, `location`, `tool_arguments`

Notes:

- `message.action` defaults to `send`.
- Telegram-only `message` actions are `reply`, `edit`, `delete`, `react`, and `create_topic`.
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

Start and poll a background process:

```json
{"name":"process","arguments":{"action":"start","session_id":"pytest","command":"python -m pytest tests -q"}}
{"name":"process","arguments":{"action":"poll","session_id":"pytest"}}
```

Send a proactive Telegram reply:

```json
{"name":"message","arguments":{"channel":"telegram","target":"123456789","text":"Build finished.","action":"send"}}
```

Call an MCP tool:

```json
{"name":"mcp","arguments":{"tool":"docs::search","arguments":{"query":"gateway auth"}}}
```
