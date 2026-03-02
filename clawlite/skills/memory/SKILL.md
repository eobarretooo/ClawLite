---
name: memory
description: Maintain stable user and project facts across sessions using workspace memory files and runtime memory state.
always: true
metadata: {"clawlite":{"emoji":"🧠"}}
---

# Memory

Use memory for facts that must survive session boundaries.

## Sources

- `~/.clawlite/workspace/memory/MEMORY.md`: curated long-term facts.
- `~/.clawlite/state/memory.jsonl`: runtime memory records.

## Common operations

Read curated memory:
```json
{"path":"~/.clawlite/workspace/memory/MEMORY.md"}
```

Update curated memory with precise edits:
```json
{"path":"~/.clawlite/workspace/memory/MEMORY.md","search":"old fact","replace":"new fact"}
```

Search runtime memory quickly:
```bash
rg -i "deadline|timezone|preference" ~/.clawlite/state/memory.jsonl
```

## Store this

- user preferences (tone, language, timezone, cadence)
- project constraints, decisions, and durable context
- recurring routines that influence future behavior

## Do not store

- temporary noise
- secrets/tokens in clear text
