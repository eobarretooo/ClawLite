---
name: cron
description: Schedule reminders and recurring tasks using the cron tool.
always: true
metadata: {"clawlite":{"emoji":"⏱️"}}
command: cron
---

# Cron

Use this skill whenever the user asks for reminders, recurring checks, or one-time scheduled tasks.

## Supported expressions

- `every <seconds>`
- `at <ISO datetime>`
- standard cron expression (`*/5 * * * *`)

## Patterns

1. Reminder
`cron add --session-id <session> --expression "every 1200" --prompt "Time to take a break"`

2. Recurring task
`cron add --session-id <session> --expression "*/15 * * * *" --prompt "Check service health and report"`

3. One-time task
`cron add --session-id <session> --expression "at 2026-03-02T18:00:00+00:00" --prompt "Remind owner about meeting"`

## Management

- List: `cron list --session-id <session>`
- Remove: `cron remove --job-id <id>`

When the user provides a natural language schedule, convert it to one of the supported expressions.
