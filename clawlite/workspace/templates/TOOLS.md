# Tools

## Execution
- `exec`: run shell commands with timeout and structured output.

## Filesystem
- `read_file`, `write_file`, `list_files`, `edit_file`: workspace file operations.

## Web
- `web_fetch`, `web_search`: fetch pages and search the web when needed.

## Scheduling
- `cron_add`, `cron_list`, `cron_remove`: schedule and manage recurring tasks.

## Messaging
- `message_send`: send proactive notifications to channels.

## Delegation
- `spawn_subagent`: run delegated background tasks in parallel.

## MCP
- `mcp_call`: call MCP servers using configured endpoints.

## Limits and Care
- Validate inputs before execution.
- Respect channel/provider rate limits.
- Avoid destructive commands unless explicitly requested.
