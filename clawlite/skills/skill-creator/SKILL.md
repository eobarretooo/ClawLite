---
name: skill-creator
description: Create and maintain high-quality SKILL.md packages with clear triggers and workflow instructions.
always: false
metadata: {"clawlite":{"emoji":"🛠️"}}
---

# Skill Creator

Use this skill to create or improve skills in `clawlite/skills/` or `~/.clawlite/workspace/skills/`.

## Checklist

1. Define clear trigger conditions in `description`.
2. Keep frontmatter minimal and accurate.
3. Include practical command examples.
4. Document limitations and prerequisites.
5. Prefer concise body text over verbose tutorials.

## Frontmatter fields

- `name`
- `description`
- `always`
- `requires`
- `metadata` (optional)
- `command` or `script` (optional)

Aim for deterministic guidance that the agent can execute reliably.
