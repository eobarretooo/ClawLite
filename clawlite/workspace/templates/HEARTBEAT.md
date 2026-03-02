# HEARTBEAT.md

Use this file to define periodic checks for the heartbeat loop.

## Contract
- The heartbeat prompt runs every configured interval.
- If there is nothing actionable, the agent must return exactly `HEARTBEAT_OK`.
- Any non-`HEARTBEAT_OK` response is treated as an actionable update and may be sent to channels.

## Suggested checklist
- Check overdue cron jobs and pending reminders.
- Check urgent inbox/alerts if tools are available.
- Report only meaningful changes.

Keep this file short to reduce token usage.
