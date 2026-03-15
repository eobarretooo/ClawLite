# Skills

ClawLite uses markdown skills (`SKILL.md`) with automatic discovery.

## Loaded sources

1. Builtin (repo): `clawlite/skills/*/SKILL.md`
2. User workspace: `~/.clawlite/workspace/skills/*/SKILL.md`
3. Marketplace local: `~/.clawlite/marketplace/skills/*/SKILL.md`

## Supported frontmatter fields

- `name`
- `description`
- `always`
- `requires` (legacy, CSV list of binaries)
- `requirements` (new JSON format with `bins`, `env`, `os`)
- `command` / `script` (execution metadata)

`metadata` JSON with `clawlite`/`nanobot`/`openclaw` namespace is also accepted, for example:

```yaml
metadata: {"clawlite":{"requires":{"bins":["gh"],"env":["GITHUB_TOKEN"]},"os":["linux","darwin"]}}
```

## Duplicate policy

When two skills have the same `name`, resolution is deterministic:

1. `workspace` overrides `marketplace`
2. `marketplace` overrides `builtin`
3. tie in the same source: lower lexicographic path (`path`) wins

## Current built-ins

- `cron`
- `memory`
- `github`
- `summarize`
- `skill-creator`
- `web-search`
- `weather`
- `tmux`
- `hub`
- `clawhub`

## Inspection CLI

```bash
clawlite skills list
clawlite skills list --all
clawlite skills show cron
```

`skills list --all` includes unavailable skills in the current environment and shows missing requirements.

## Real skill execution (tool)

Runtime exposes the `run_skill` tool.

Main fields:
- `name` (required)
- `input` or `args`
- `timeout`
- `query` (for `web-search`)
- `location` (for `weather`)

Flow:
1. resolve skill by name
2. validate availability (`bins/env/os`)
3. execute mapped `command` or `script`

## Runtime summary format

`render_for_prompt()` uses an XML contract compatible with the skills tool:

```xml
<available_skills>
<skill>
<name>github</name>
<description>Interact with GitHub using gh CLI for PRs, issues, runs and API queries.</description>
<location>/path/to/SKILL.md</location>
</skill>
</available_skills>
```

## Progressive Loading

`SkillsLoader.build_skills_summary()` returns a compact XML summary of all skills (name + description only) for injection into the agent context. This avoids bloating the prompt with full skill content.

Use `load_skill_full(name)` to fetch the complete `SKILL.md` content on demand when the agent needs to execute a specific skill.