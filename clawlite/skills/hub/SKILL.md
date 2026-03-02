---
name: hub
description: Search and install community skills into the ClawLite workspace skill directory.
always: false
homepage: https://clawhub.ai
metadata: {"clawlite":{"emoji":"🦞","requires":{"bins":["npx"]}}}
command: npx --yes clawhub@latest
---

# Hub

Use this skill when the user asks to find/install/update skills from community registry.

## Search

```bash
npx --yes clawhub@latest search "<query>" --limit 5
```

## Install in workspace

```bash
npx --yes clawhub@latest install <slug> --workdir ~/.clawlite/workspace
```

Always install into `~/.clawlite/workspace/skills/` so ClawLite discovers the skill at runtime.

## Update installed skills

```bash
npx --yes clawhub@latest update --all --workdir ~/.clawlite/workspace
```

## Notes

- Requires Node.js (`npx`).
- After install/update, start a new session to reload skill list.
