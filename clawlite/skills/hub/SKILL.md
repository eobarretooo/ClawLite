---
name: hub
description: "Discover, install, and update community skills from the ClawHub registry into the ClawLite workspace. Use when the user wants to find new skills, install a skill from the hub, or update installed skills to their latest versions."
always: false
homepage: https://clawhub.ai
metadata: {"clawlite":{"emoji":"🦞","requires":{"bins":["npx"]}}}
command: npx --yes clawhub@latest
---

# Hub

Find, install, and update community skills from the ClawHub registry.

## Workflow

1. **Search**: Find skills matching the user's need from the registry.
2. **Review**: Check skill details, ratings, and compatibility before installing.
3. **Install**: Add the skill to the ClawLite workspace so it is discovered at runtime.
4. **Verify**: Confirm the skill appears in `clawlite status` or skill listings.
5. **Update**: Keep installed skills current with the latest registry versions.

## Commands

### Search for skills
```bash
npx --yes clawhub@latest search "<query>" --limit 5
```

### Install a skill
```bash
npx --yes clawhub@latest install <slug> --workdir ~/.clawlite/workspace
```

Always install into `~/.clawlite/workspace/skills/` so ClawLite discovers the skill at runtime.

### Update all installed skills
```bash
npx --yes clawhub@latest update --all --workdir ~/.clawlite/workspace
```

## Example

User: "Find me a skill for managing Docker containers"

1. Search: `npx --yes clawhub@latest search "docker" --limit 5`
2. Review results — pick the best match (e.g. `community/docker-manager`).
3. Install: `npx --yes clawhub@latest install community/docker-manager --workdir ~/.clawlite/workspace`
4. Verify: Run `clawlite status` to confirm the skill is loaded.

## Notes

- Requires `npx` (Node.js) — ensure Node.js is installed on the host.
- Skills are installed into the user workspace, not the project `clawlite/skills/` directory.
- Use `clawhub` skill for the full-featured registry experience; `hub` is a backward-compatible alias.
