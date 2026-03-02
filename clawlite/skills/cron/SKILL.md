---
name: cron
description: Schedule reminders and recurring tasks with the `cron` tool.
always: true
metadata: {"clawlite":{"emoji":"⏱️"}}
---

# Cron

Use this skill whenever the user asks for reminders, recurring checks, or one-time scheduled tasks.

## Tool contract
Use `cron` with one of these actions:
- `add` (`session_id`, `expression`, `prompt`, optional `name`)
- `list` (`session_id`)
- `remove` (`job_id`)
- `enable` / `disable` (`job_id`)
- `run` (`job_id`)

## Supported expressions
- `every <seconds>`
- `at <ISO datetime>`
- standard cron expression (`*/5 * * * *`)

When the user provides a natural-language schedule, convert it to one of the supported expressions.
