---
name: memory
description: Maintain long-term memory and stable user/project facts.
always: true
metadata: {"clawlite":{"emoji":"🧠"}}
---

# Memory

Use memory for facts that should survive session boundaries.

## What to store

- user preferences (tone, timezone, channels)
- stable project constraints and decisions
- recurring routines that influence future actions

## What to avoid

- temporary noise
- raw secrets/tokens in plain text

## Operating model

ClawLite uses:

- session history in JSONL (`~/.clawlite/state/sessions/*.jsonl`)
- long-term memory index (`~/.clawlite/state/memory.jsonl`)

Always prefer concise, factual statements that are useful in future sessions.
