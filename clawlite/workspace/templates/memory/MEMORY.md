# Long-Term Memory

Use this file for durable facts:
- stable user preferences
- recurring workflows
- project context worth preserving

Do not store secrets in plain text.

## Operational notes
- Store heartbeat bookkeeping in `memory/heartbeat-state.json`.
- `memory/heartbeat-state.json` is runtime-owned and includes check-state metadata (`last_check_iso`, `last_action`, `last_reason`, `last_ok_iso`, `last_actionable_iso`).
- Keep this file concise and curated; avoid raw noisy logs.
