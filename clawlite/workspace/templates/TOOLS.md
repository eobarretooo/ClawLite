# Tools

## Execution
- `exec`: run shell commands with timeout and structured output (`command`, optional `timeout`).

## Filesystem
- `read_file`: read UTF-8 file content.
- `write_file`: write UTF-8 file content.
- `edit_file`: replace text in a file (`search` -> `replace`).
- `list_dir`: list directory entries.

## Web
- `web_fetch`: fetch content from a URL.
- `web_search`: search the web and return snippets.

## Scheduling
- `cron`: manage jobs with `action`:
  - `add` (`session_id`, `expression`, `prompt`, optional `name`)
  - `list` (`session_id`)
  - `remove` (`job_id`)
  - `enable` / `disable` (`job_id`)
  - `run` (`job_id`)

## Messaging and Delegation
- `message`: send proactive notifications (`channel`, `target`, `text`).
- `spawn`: run delegated background tasks (`task`, optional `session_id`).

## MCP and Skills
- `mcp`: call configured MCP endpoint (`url`, `tool`, `arguments`).
- `run_skill`: execute SKILL.md bindings by `name`.

## Safety Rules
- Validate inputs before execution.
- Respect provider/channel rate limits.
- Avoid destructive commands unless explicitly requested.
