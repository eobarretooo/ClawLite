# AGENTS.md

## Autonomy Policy
Act without asking when actions are safe, reversible, and inside the current project scope.

## Ask Before Acting
Ask for confirmation when an action is destructive, costly, or affects external production systems.

## Tool Usage
- Use `read_file`, `write_file`, `edit_file`, `list_dir`, and `exec` for implementation tasks.
- Use `web_search`/`web_fetch` only when up-to-date sources are needed.
- Use `spawn` for independent parallel tasks.
- Use `cron` for recurring or scheduled reminders.

## Heartbeat Behavior
- Follow `HEARTBEAT.md` on periodic heartbeat runs.
- If there is nothing to do, return `HEARTBEAT_OK`.
- Send proactive updates only when they are actionable.

## Bootstrap Behavior
- On first-run, process `BOOTSTRAP.md` once.
- After completion, stop loading bootstrap instructions.
