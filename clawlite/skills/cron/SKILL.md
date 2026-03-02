---
name: cron
description: Schedule reminders and recurring tasks with the `cron` tool (add/list/remove/enable/disable/run).
always: true
metadata: {"clawlite":{"emoji":"⏱️"}}
---

# Cron

Use the `cron` tool whenever the user asks for reminders, recurring checks, or one-time scheduled tasks.

## Actions

- `add`: create a schedule
- `list`: list current jobs
- `remove`: delete a job
- `enable` / `disable`: toggle execution
- `run`: force immediate run

## Add examples

Fixed reminder:
```json
{"action":"add","message":"Time to take a break","every_seconds":1200}
```

Agent task on every run:
```json
{"action":"add","prompt":"Check repo CI status and report only failures","every_seconds":600}
```

One-time schedule:
```json
{"action":"add","message":"Remind me about the meeting","at":"2026-03-02T18:00:00Z"}
```

Timezone-aware cron:
```json
{"action":"add","prompt":"Morning standup","cron_expr":"0 9 * * 1-5","tz":"America/Vancouver"}
```

List and remove:
```json
{"action":"list"}
{"action":"remove","job_id":"abc123"}
```

## Notes

- `prompt` and `message` are both accepted; use `prompt` for agent tasks.
- Convert natural-language schedules into `every_seconds`, `at`, or `cron_expr`.
- For `add`, only provide `session_id`/`channel`/`target` when routing to another session or destination.
