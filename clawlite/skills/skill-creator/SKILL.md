---
name: skill-creator
description: Create or update SKILL.md packages with deterministic frontmatter, clear trigger descriptions, and valid command/script execution mappings.
always: false
metadata: {"clawlite":{"emoji":"🛠️"}}
---

# Skill Creator

Use this skill to create or improve skills in `clawlite/skills/` or `~/.clawlite/workspace/skills/`.

## Checklist

1. Keep frontmatter deterministic: `name`, `description`, optional `always`, optional `homepage`, optional `metadata`, and only one of `command` or `script`.
2. Keep `metadata` as single-line JSON (`metadata: {"clawlite":{...}}`).
3. Put environment/binary/OS requirements in `metadata.clawlite.requires` and `metadata.clawlite.os`.
4. Use tool names that exist in ClawLite (for example `web_search` for `script`).
5. Keep instructions concise and action-oriented; avoid non-executable filler.
