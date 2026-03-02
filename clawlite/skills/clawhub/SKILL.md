---
name: clawhub
description: Search, install, list, and update agent skills from ClawHub into ~/.clawlite/workspace.
always: false
homepage: https://clawhub.ai
metadata: {"clawlite":{"emoji":"🦞","requires":{"bins":["npx"]}}}
command: npx --yes clawhub@latest
---

# ClawHub

Use this skill when the user asks to find, install, list, or update community skills.

## Search

```bash
npx --yes clawhub@latest search "web scraping" --limit 5
```

## Install

```bash
npx --yes clawhub@latest install <slug> --workdir ~/.clawlite/workspace
```

## Update

```bash
npx --yes clawhub@latest update --all --workdir ~/.clawlite/workspace
```

## List installed

```bash
npx --yes clawhub@latest list --workdir ~/.clawlite/workspace
```

Always keep `--workdir ~/.clawlite/workspace` so installed skills land in `~/.clawlite/workspace/skills/`.
