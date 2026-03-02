---
name: cron
description: Schedule reminders and recurring tasks.
always: true
requires: scheduler
command: cron
---

Use this skill when a task must run later or repeatedly.
- Accept natural schedule intent and convert to cron expression.
- Prefer `every N` for simple recurrence.
- Confirm timezone assumptions before one-shot jobs.
